import sys, os, io, tempfile, traceback, re
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Optional

from PyPDF2 import PdfMerger, PdfReader
import PyPDF2
from pdfminer_high_level import extract_text as pdfminer_extract  # alias kept
from pdfminer.high_level import extract_text as pdfminer_extract
from pdfminer.layout import LAParams
import pytesseract
import fitz  # PyMuPDF
import pdfplumber
from PIL import Image
import logging

# -------------------------- Unicode console on Windows --------------------------
def configure_unicode():
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    except Exception:
        pass
configure_unicode()

# ------------------------------- Logger setup -----------------------------------
LOG_LEVEL = os.environ.get("CODE2_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)

# ------------------------------- Configuration ---------------------------------
OCR_MIN_CHARS = int(os.environ.get("OCR_MIN_CHARS", 80))
PDFMINER_LA_PARAMS = LAParams(line_margin=0.2, char_margin=2.0)
OCR_DPI = int(os.environ.get("OCR_DPI", 260))  # 260 is a good speed/quality tradeoff

PHRASE = "Employer's name, address, and ZIP code"
INT_PHRASE = "Interest income"

# ------------------------------- Priority tables --------------------------------
income_priorities = {
    'W-2': 1,
    '1099-NEC': 2,
    '1099-PATR': 3,
    '1099-MISC': 4,
    '1099-OID': 5,
    '1099-G': 6,
    'W-2G': 7,
    '1065': 8,
    '1120-S': 9,
    '1041': 10,
    '1099-INT': 11,
    '1099-DIV': 12,
    '1099-R': 13,
    '1099-Q': 14,
    'K-1': 15,
    '1099-Other': 16,
}
expense_priorities = {
    '5498-SA': 1,
    '1095-A': 2,
    '1095-B': 3,
    '1095-C': 4,
    '1098-Mortgage': 5,
    '1098-T': 6,
    'Property Tax': 7,
    '1098-Other': 8,
}

def get_form_priority(ftype: str, category: str) -> int:
    table = income_priorities if category == 'Income' else (expense_priorities if category == 'Expenses' else {})
    return table.get(ftype, max(table.values()) + 1 if table else 9999)

# ------------------------------- Caches -----------------------------------------
PAGE_TEXT_CACHE: Dict[Tuple[str, int], str] = {}
PAGE_CLASS: Dict[Tuple[str, int], Tuple[str, str]] = {}

# Per-page title caches
w2_titles: Dict[Tuple[str, int], str] = {}
int_titles: Dict[Tuple[str, int], str] = {}
div_titles: Dict[Tuple[str, int], str] = {}
mort_titles: Dict[Tuple[str, int], str] = {}

# ------------------------------- Helpers ----------------------------------------
EMP_BRACKET_RE = re.compile(r"Employer's name, address, and ZIP code.*?\[(.*?)\]", re.IGNORECASE | re.DOTALL)


def _clean_label(name: str) -> str:
    return re.sub(r",?\s*N\.A\.?$", "", (name or "").strip(), flags=re.IGNORECASE)


def print_phrase_context(text: str, phrase: str = PHRASE, num_lines: int = 2):
    lines = (text or "").splitlines()
    for i, line in enumerate(lines):
        if phrase.lower() in line.lower():
            for j in range(i, min(i + 1 + num_lines, len(lines))):
                logger.debug(lines[j])
            break

# ---------------------------- Text extraction (fast) ----------------------------

def get_page_text(path: str, page_index: int, *, reader: Optional[PdfReader] = None, doc: Optional[fitz.Document] = None) -> str:
    """Fast, cached page text: use PDF text first; OCR only if too short."""
    key = (path, page_index)
    if key in PAGE_TEXT_CACHE:
        return PAGE_TEXT_CACHE[key]

    text = ""

    # 1) PDFMiner
    try:
        t1 = pdfminer_extract(path, page_numbers=[page_index], laparams=PDFMINER_LA_PARAMS) or ""
        if len(t1.strip()) > len(text.strip()):
            text = t1
    except Exception:
        logger.debug("PDFMiner failed", exc_info=True)

    # 2) PyPDF2
    try:
        _reader = reader or PdfReader(path)
        t2 = _reader.pages[page_index].extract_text() or ""
        if len(t2.strip()) > len(text.strip()):
            text = t2
    except Exception:
        logger.debug("PyPDF2 failed", exc_info=True)

    # 3) PyMuPDF text
    try:
        _doc = doc or fitz.open(path)
        t3 = _doc.load_page(page_index).get_text() or ""
        if len(t3.strip()) > len(text.strip()):
            text = t3
    except Exception:
        logger.debug("PyMuPDF get_text failed", exc_info=True)

    # 4) OCR only if needed
    if len((text or "").strip()) < OCR_MIN_CHARS:
        try:
            _doc = doc or fitz.open(path)
            page = _doc.load_page(page_index)
            pix = page.get_pixmap(dpi=OCR_DPI)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            t_ocr = pytesseract.image_to_string(img, config="--psm 6") or ""
            if len(t_ocr.strip()) > len(text.strip()):
                text = t_ocr
        except Exception:
            logger.debug("OCR failed", exc_info=True)

    PAGE_TEXT_CACHE[key] = text or ""
    return PAGE_TEXT_CACHE[key]

# --------------------------- Classification helpers ---------------------------

def classify_text(text: str) -> Tuple[str, str]:
    t = (text or "").lower()
    lower = t

    # 1) Detect W-2 pages by key header phrases
    if ("wages, tips, other compensation" in lower) or ("employer's name" in lower and "address" in lower):
        return "Income", "W-2"

    # If page matches any instruction patterns, classify as Others → Unused
    instruction_patterns = [
        # W-2 instructions
        "box 1. enter this amount on the wages line of your tax return",
        "box 2. enter this amount on the federal income tax withheld line",
        "box 5. you may be required to report this amount on form 8959",
        "box 6. this amount includes the 1.45% medicare tax withheld",
        "box 8. this amount is not included in box 1, 3, 5, or 7",
        "you must file form 4137",
        "box 10. this amount includes the total dependent care benefits",
        "instructions for form 8949",
        "regulations section 1.6045-1",
        "recipient's taxpayer identification number",
        "fata filing requirement",
        "payer’s routing transit number",
        "refer to the form 1040 instructions",
        "earned income credit",
        "if your name, ssn, or address is incorrect",
        "corrected wage and tax statement",
        "credit for excess taxes",
        "instructions for employee  (continued from back of copy c) box 12 (continued)",
        "f—elective deferrals under a section 408(k)(6) salary reduction sep",
        "g—elective deferrals and employer contributions (including  nonelective ",
        "deferrals) to a section 457(b) deferred compensation plan",
        "h—elective deferrals to a section 501(c)(18)(d) tax-exempt  organization ",
        "plan. see the form 1040 instructions for how to deduct.",
        "j—nontaxable sick pay (information only, not included in box 1, 3, or 5)",
        "k—20% excise tax on excess golden parachute payments. see the ",
        "form 1040 instructions.",
        "l—substantiated employee business expense reimbursements ",
        "(nontaxable)",
        "m—uncollected social security or rrta tax on taxable cost  of group-",
        "term life insurance over $50,000 (former employees only). see the form ",
        "1040 instructions.",
        "n—uncollected medicare tax on taxable cost of group-term  life ",
        "insurance over $50,000 (former employees only). see the form 1040 ",
        "instructions.",
        "p—excludable moving expense reimbursements paid directly to a ",
        "member of the u.s. armed forces (not included in box 1, 3, or 5)",
        "q—nontaxable combat pay. see the form 1040 instructions for details ",
        "on reporting this amount.",
        # 1099-INT instructions
        "box 1. shows taxable interest",
        "box 2. shows interest or principal forfeited",
        "box 3. shows interest on u.s. savings bonds",
        "box 4. shows backup withholding",
        "box 5. any amount shown is your share",
        "box 6. shows foreign tax paid",
        "box 7. shows the country or u.s. territory",
        "box 8. shows tax-exempt interest",
        "box 9. shows tax-exempt interest subject",
        "box 10. for a taxable or tax-exempt covered security",
        "box 11. for a taxable covered security",
        "box 12. for a u.s. treasury obligation",
        "box 13. for a tax-exempt covered security",
        "box 14. shows cusip number",
        "boxes 15-17. state tax withheld",
        # 1098-T instruction lines
        "you, or the person who can claim you as a dependent, may be able to claim an education credit",
        "student’s taxpayer identification number (tin)",
        "box 1. shows the total payments received by an eligible educational institution",
        "box 2. reserved for future use",
        "box 3. reserved for future use",
        "box 4. shows any adjustment made by an eligible educational institution",
        "box 5. shows the total of all scholarships or grants",
        "tip: you may be able to increase the combined value of an education credit",
        "box 6. shows adjustments to scholarships or grants for a prior year",
        "box 7. shows whether the amount in box 1 includes amounts",
        "box 8. shows whether you are considered to be carrying at least one-half",
        "box 9. shows whether you are considered to be enrolled in a program leading",
        "box 10. shows the total amount of reimbursements or refunds",
        "future developments. for the latest information about developments related to form 1098-t",
    ]
    for pat in instruction_patterns:
        if pat in lower:
            return "Others", "Unused"

    # 1099-DIV
    div_category = [
        "1a total ordinary dividends",
        "1b qualified dividends distributions",
        "form 1099-div",
        "2a total capital gain diste",
        "2b unrecap. sec",
        "2c section 1202 gain ",
    ]
    for pat in div_category:
        if pat in lower:
            return "Income", "1099-DIV"

    # 1099-INT
    int_front = [
        "3 interest on u.s. savings bonds and treasury obligations",
        "investment expenses",
        "tax-exempt interest",
        "ond premium on treasury obligations",
        "withdrawal penalty",
    ]
    int_unused = [
        "box 1. shows taxable interest paid to you ",
        "box 2. shows interest or principal forfeited",
        "box 3. shows interest on u.s. savings bonds",
        "box 8. shows tax-exempt interest paid to",
        "box 10. for a taxable or tax-exempt covered security",
    ]
    found_int_front = any(pat in lower for pat in int_front)
    found_int_unused = any(pat in lower for pat in int_unused)
    if found_int_front:
        return "Income", "1099-INT"
    elif found_int_unused:
        return "Others", "Unused"

    # 1098-Mortgage
    mort_front = [
        "mortgage insurance premiums",
        "mortgage origination date",
        "number of properties securing the morgage",
        "address or description of property securing",
        "form 1098 mortgage",
        "limits based on the loan amount",
        "refund of overpaid",
        "mortgage insurance important tax information",
        "account number (see instructions)",
    ]
    mort_unused = [
        "instructions for payer/borrower",
        "payer’s/borrower’s taxpayer identification number",
        "box 1. shows the mortgage interest received",
        "box 1. shows the mortgage interest received by the recipient",
        "box 3. shows the date of the mortgage origination",
        "box 5. if an amount is reported in this box",
        "box 8. shows the address or description",
        "this information is being provided to you as",
        "we’re providing the mortgage insurance",
        "if you received this statement as the payer of",
        "if your mortgage payments were subsidized",
    ]
    found_front = any(pat in lower for pat in mort_front)
    found_unused = any(pat in lower for pat in mort_unused)
    if found_front:
        return "Expenses", "1098-Mortgage"
    elif found_unused:
        return "Others", "Unused"

    # Fallbacks
    if 'w-2' in t or 'w2' in t:
        return 'Income', 'W-2'
    if '1099-int' in t or 'interest income' in t:
        return 'Income', '1099-INT'
    if '1099-div' in t or 'form 1099-div' in t:
        return 'Income', '1099-DIV'
    if '1098-t' in t:
        return 'Expenses', '1098-T'
    if '1099' in t:
        return 'Income', '1099-Other'
    if 'donation' in t:
        return 'Expenses', 'Donation'
    return 'Unknown', 'Unused'

# ------------------------------ W-2 parsing ----------------------------------

def normalize_entity_name(raw: str) -> str:
    stripped = (raw or "").strip()
    whole_dup = re.match(r'^(?P<seq>.+?)\s+(?P=seq)(?:\s+(?P=seq))*$', stripped, flags=re.IGNORECASE)
    if whole_dup:
        stripped = whole_dup.group('seq')
    collapsed = re.sub(r'\b(.+?)\b(?:\s+\1\b)+', r'\1', stripped, flags=re.IGNORECASE)
    collapsed = re.sub(r'\s*TAX WITHHELD\s*$', '', collapsed, flags=re.IGNORECASE)
    collapsed = re.sub(r'(?:\s+\d+(?:\.\d+)?)+\s*$', '', collapsed)
    return ' '.join(collapsed.split()).strip()


def parse_w2(text: str) -> Dict[str, str]:
    ssn_m = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", text)
    ssn = ssn_m.group(1) if ssn_m else "N/A"
    ein_m = re.search(r"\b(\d{2}-\d{7})\b", text)
    ein = ein_m.group(1) if ein_m else "N/A"

    lines: List[str] = (text or "").splitlines()
    emp_name = emp_addr = "N/A"
    bookmark = None

    marker = (
        "c employer's name, address, and zip code "
        "8 allocated tips 3 social security wages 4 social security tax withheld"
    )
    lower_lines = [l.lower() for l in lines]
    for i, L in enumerate(lower_lines):
        if marker in L:
            for offset in range(1, 4):
                idx = i + offset
                if idx >= len(lines):
                    break
                candidate = lines[idx].strip()
                if not candidate or len(candidate) <= 3:
                    continue
                bookmark = candidate
                emp_name = normalize_entity_name(bookmark)
                return {
                    'ssn': ssn,
                    'ein': ein,
                    'employer_name': emp_name,
                    'employer_address': emp_addr,
                    'employee_name': 'N/A',
                    'employee_address': 'N/A',
                    'bookmark': bookmark,
                }
            break

    # Triple-marker variants
    triple_variants = [
        "© Employer's name, address, and ZIP code |[e Employer's name, address, and ZIP code |[e Employer's name, address, and ZIP code",
        "c Employer's name, address, and ZIP code c Employer's name, address, and ZIP code c Employer's name, address, and ZIP code",
        "¢ Employer's name, address and ZIP code | © Employers name, address and ZIP code",
        "= EMPLOYER'S name, address, and ZIP code — ee ls. EMPLOYER'S nama, atidress, and ZIP cade eee ~ |",
    ]
    for triple_marker in triple_variants:
        if triple_marker in text:
            for i, L in enumerate(lines):
                if triple_marker in L:
                    j = i + 1
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines):
                        raw = lines[j].strip()
                        parts = re.split(r"[|)]+", raw)
                        tokens, seen = [], set()
                        for part in parts:
                            for w in part.split():
                                w_clean = w.strip()
                                if w_clean:
                                    up = w_clean.upper()
                                    if up not in seen:
                                        seen.add(up)
                                        tokens.append(w_clean)
                        emp_name = normalize_entity_name(" ".join(tokens))
                        bookmark = emp_name
                    break
            return {
                'ssn': ssn,
                'ein': ein,
                'employer_name': emp_name,
                'employer_address': emp_addr,
                'employee_name': 'N/A',
                'employee_address': 'N/A',
                'bookmark': bookmark,
            }

    # Standard W-2 parsing
    for i, line in enumerate(lines):
        if "employer" in line.lower() and "name" in line.lower():
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                parts = [p.strip() for p in re.split(r"[|]", lines[j])]
                for p in parts:
                    if p and re.search(r"[A-Za-z]", p) and not re.match(r"^\d", p):
                        emp_name = normalize_entity_name(p)
                        break
                j += 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                emp_addr = lines[j].strip()
            break

    if emp_name != "N/A":
        toks, seen = emp_name.split(), set()
        emp_name = " ".join(w for w in toks if w not in seen and not seen.add(w)).rstrip("\\/")
    else:
        for i, line in enumerate(lines):
            if "0000000845 - PAYROL" in line:
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    emp_name = lines[j].strip().split()[0]
                break
        if emp_name == "N/A":
            marker = "© Employer's name, address, and ZIP code"
            for i, line in enumerate(lines):
                if marker in line:
                    j = i + 1
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines):
                        raw = lines[j].strip()
                        parts = [p.strip() for p in raw.split("|")]
                        tokens, seen = [], set()
                        for part in parts:
                            for w in part.split():
                                if w not in seen:
                                    seen.add(w)
                                    tokens.append(w)
                        emp_name = normalize_entity_name(" ".join(tokens))
                    break

    return {
        'ssn': ssn,
        'ein': ein,
        'employer_name': emp_name,
        'employer_address': emp_addr,
        'employee_name': 'N/A',
        'employee_address': 'N/A',
    }


def print_w2_summary(info: Dict[str, str]):
    logger.debug("W-2 Employer=%s EIN=%s", info.get('employer_name'), info.get('ein'))

# ------------------------ 1099 bookmark extractors --------------------------

from typing import List as _List  # avoid shadowing

def extract_1099int_bookmark(text: str) -> str:
    lines: _List[str] = (text or "").splitlines()
    lower_lines = [L.lower() for L in lines]
    full_lower = (text or "").lower()

    if any(v in full_lower for v in ("uss bank na", "us bank na", "u s bank na")):
        return "US Bank NA"
    if any(v in full_lower for v in ("capital one na", "capital one n.a", "capital one national association")):
        return "CAPITAL ONE NA"
    if "bank of america" in full_lower:
        for L in lines:
            if "bank of america" in L.lower():
                return _clean_label(L)

    def extract_all_bookmarks(_lines):
        _lower = [l.lower() for l in _lines]
        bookmarks = []
        skip_phrases = {"omb no", "payer's tin", "payer's rtn", "rtn", "1099-int interest", "recipient's tin", "fatca filing", "copy b", "account number", "form 1099-int", "1 interest income income"}
        for i, L in enumerate(_lower):
            if "or foreign postal code, and telephone no." in L:
                for offset in range(1, 4):
                    idx = i + offset
                    if idx >= len(_lines):
                        break
                    candidate = _lines[idx].strip()
                    candidate_lower = candidate.lower()
                    if not candidate or len(candidate) <= 3:
                        continue
                    if "mortgage" in candidate_lower or "servicer" in candidate_lower:
                        return [candidate]
                    if len(candidate) <= 3 or any(skip in candidate_lower for skip in skip_phrases):
                        continue
                    bookmarks.append(candidate)
                    break
        return bookmarks

    bookmarks = extract_all_bookmarks(lines)
    if bookmarks:
        return bookmarks[0]

    patterns = ["interest income income", "zip or foreign postal code, and telephone no.", "federal id number:"]
    for i, L in enumerate(lines):
        if any(pat in L.lower() for pat in patterns):
            for j in range(i + 1, len(lines)):
                s = lines[j].strip()
                if not s:
                    continue
                low = s.lower()
                if "tin" in low or "rtn" in low:
                    continue
                if set(s) == {"_"}:
                    return s
                cleaned = re.sub(r"(?i)\s*reel\s+form\s+1099-?int\b.*$", "", s)
                cleaned = re.sub(r",\s*n\.a\.?$", "", cleaned, flags=re.IGNORECASE)
                cleaned = re.sub(r"[^\w\s]+$", "", cleaned)
                cleaned = re.sub(r"\b\w\b$", "", cleaned).strip()
                return cleaned

    return "1099-INT"


def extract_1099div_bookmark(text: str) -> str:
    lines = (text or "").splitlines()
    lower_text = (text or "").lower()
    lower_lines = [L.lower() for L in lines]
    marker = ("payer's name, street address, city or town, state or province, country, zip or foreign postal code, and telephone no.")
    if marker in lower_text:
        for i, L in enumerate(lower_lines):
            if marker in L:
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    return re.sub(r"[^\w\s]+$", "", lines[j].strip())
                break

    def find_after(header_pred):
        for i, L in enumerate(lower_lines):
            if header_pred(L):
                for j in range(i + 1, len(lines)):
                    cand = lines[j].strip()
                    if cand:
                        return re.sub(r"[^\w\s]+$", "", cand)
        return None

    payer = find_after(lambda L: "payer's name" in L and "street address" in L)
    if payer:
        return payer
    recip = find_after(lambda L: "recipient's name" in L and "street address" in L)
    if recip:
        return recip
    return "1099-DIV"


def clean_bookmark(name: str) -> str:
    cleaned = re.sub(r"\bInterest.*$", "", name or "", flags=re.IGNORECASE)
    return cleaned.strip()


def extract_1098mortgage_bookmark(text: str) -> str:
    lines: List[str] = (text or "").splitlines()
    for L in lines:
        if re.search(r"dovenmuehle\s+mortgage", L, flags=re.IGNORECASE):
            m = re.search(r"(Dovenmuehle Mortgage, Inc)", L, flags=re.IGNORECASE)
            name = m.group(1) if m else re.sub(r"[^\w\s,]+$", "", L.strip())
            return clean_bookmark(name)
    for L in lines:
        if re.search(r"\bhuntington\s+national\s+bank\b", L, flags=re.IGNORECASE):
            m = re.search(r"\b(?:The\s+)?Huntington\s+National\s+Bank\b", L, flags=re.IGNORECASE)
            name = m.group(0) if m else re.sub(r"[^\w\s]+$", "", L.strip())
            return clean_bookmark(name)
    for L in lines:
        if re.search(r"\bunited\s+nations\s+fcu\b", L, flags=re.IGNORECASE):
            return clean_bookmark("UNITED NATIONS FCU")
    for L in lines:
        if re.search(r"\bloan\s*depot\s*com\s*llc\b", L, flags=re.IGNORECASE):
            m = re.search(r"\bloan\s*depot\s*com\s*llc\b", L, flags=re.IGNORECASE)
            name = m.group(0) if m else re.sub(r"[^\w\s]+$", "", L.strip())
            return clean_bookmark(name)

    for i, line in enumerate(lines):
        if "limits based on the loan amount" in line.lower():
            for j in range(i + 1, len(lines)):
                candidate = lines[j].strip()
                if not candidate:
                    continue
                candidate = candidate.replace("‘", "'").replace("’", "'").replace("\u00A0", " ")
                candidate = re.sub(r"\bInterest.*$", "", candidate, flags=re.IGNORECASE)
                candidate = re.split(r"\band\b", candidate, maxsplit=1, flags=re.IGNORECASE)[0].strip()
                candidate = re.sub(r"[^\w\s]+$", "", candidate)
                return candidate

    for L in lines:
        if re.search(r"\bfcu\b", L, flags=re.IGNORECASE):
            m = re.search(r"(.*?FCU)\b", L, flags=re.IGNORECASE)
            name = m.group(1) if m else re.sub(r"[^\w\s]+$", "", L.strip())
            return clean_bookmark(name)

    lower_lines = [L.lower() for L in lines]
    for i, header in enumerate(lower_lines):
        if "payer" in header and "borrower" in header:
            for cand in lines[i + 1:]:
                s = cand.strip()
                if not s or len(set(s)) == 1 or re.search(r"[\d\$]|page", s, flags=re.IGNORECASE):
                    continue
                raw = re.sub(r"[^\w\s]+$", "", s)
                raw = re.sub(r"(?i)\s+d/b/a\s+.*$", "", raw).strip()
                return clean_bookmark(raw)

    for i, L in enumerate(lines):
        if re.search(r"recipient.?s\s*/\s*lender.?s", L, flags=re.IGNORECASE):
            for j in range(i + 1, len(lines)):
                cand = lines[j].strip()
                if not cand:
                    continue
                name = re.sub(r"[^\w\s]+$", "", cand)
                return clean_bookmark(name)

    return "1098-Mortgage"

# ------------------------------ Grouping helpers ------------------------------

def group_by_type(entries: List[Tuple[str, int, str]]) -> Dict[str, List[Tuple[str, int, str]]]:
    d = defaultdict(list)
    for e in entries:
        d[e[2]].append(e)
    return d

# --------------------------------- Merging -------------------------------------

def merge_with_bookmarks(input_dir: str, output_pdf: str, *, delete_inputs: bool = False):
    abs_input = os.path.abspath(input_dir)
    abs_output = os.path.abspath(output_pdf)
    if abs_output.startswith(abs_input + os.sep):
        abs_output = os.path.join(os.path.dirname(abs_input), os.path.basename(abs_output))
        logger.warning(f"Moved output outside: {abs_output}")

    all_files = sorted(
        f for f in os.listdir(abs_input)
        if f.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.tiff')) and f != os.path.basename(abs_output)
    )

    # remove zero-byte
    files = []
    for f in all_files:
        p = os.path.join(abs_input, f)
        if os.path.getsize(p) == 0:
            logger.warning(f"Skipping empty file: {f}")
            continue
        files.append(f)
    logger.info(f"Found {len(files)} files in {abs_input}")

    income: List[Tuple[str, int, str]] = []
    expenses: List[Tuple[str, int, str]] = []
    others: List[Tuple[str, int, str]] = []

    # ---- Single-pass extraction per file (open once) ----
    for fname in files:
        path = os.path.join(abs_input, fname)
        if not fname.lower().endswith('.pdf'):
            # Optional: image OCR to include in 'others'; not appended to output
            logger.debug("Non-PDF skipping for merge: %s", fname)
            continue
        try:
            reader = PdfReader(path)
            doc = fitz.open(path)
        except Exception:
            logger.error("Failed to open %s", path, exc_info=True)
            continue

        total = len(reader.pages)
        for i in range(total):
            text = get_page_text(path, i, reader=reader, doc=doc)
            if not text:
                logger.debug("No text extracted for %s p%d", fname, i + 1)
            cat, ft = classify_text(text)
            PAGE_CLASS[(path, i)] = (cat, ft)

            # Titles
            if cat == 'Income' and ft == 'W-2':
                info = parse_w2(text)
                if info.get('employer_name') and info.get('employer_name') != 'N/A':
                    w2_titles[(path, i)] = info['employer_name']
            elif cat == 'Income' and ft == '1099-INT':
                t = extract_1099int_bookmark(text)
                if t and t != '1099-INT':
                    int_titles[(path, i)] = t
            elif cat == 'Income' and ft == '1099-DIV':
                t = extract_1099div_bookmark(text)
                if t and t != '1099-DIV':
                    div_titles[(path, i)] = t
            elif cat == 'Expenses' and ft == '1098-Mortgage':
                t = extract_1098mortgage_bookmark(text)
                if t and t != '1098-Mortgage':
                    mort_titles[(path, i)] = t

            entry = (path, i, ft)
            if cat == 'Income':
                income.append(entry)
            elif cat == 'Expenses':
                expenses.append(entry)
            else:
                others.append(entry)

        try:
            doc.close()
        except Exception:
            pass

    # Sort
    income.sort(key=lambda e: (get_form_priority(e[2], 'Income'), e[0], e[1]))
    expenses.sort(key=lambda e: (get_form_priority(e[2], 'Expenses'), e[0], e[1]))

    merger = PdfMerger()
    page_num = 0
    page_location: Dict[Tuple[str, int], int] = {}

    def append_and_bookmark(entry, parent, title):
        nonlocal page_num
        p, idx, _ = entry
        # Deduplicate appends: multiple bookmarks to same page
        if (p, idx) in page_location:
            merger.add_outline_item(title, page_location[(p, idx)], parent=parent)
            return
        # Append directly without temp files
        merger.append(p, pages=(idx, idx + 1))
        page_location[(p, idx)] = page_num
        merger.add_outline_item(title, page_num, parent=parent)
        page_num += 1

    # ---- Build outline ----
    if income:
        root = merger.add_outline_item('Income', page_num)
        for form, grp in group_by_type(income).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, entry in enumerate(grp, 1):
                path, idx, _ = entry
                lbl = form if len(grp) == 1 else f"{form}#{j}"
                if form == 'W-2':
                    lbl = w2_titles.get((path, idx), lbl)
                elif form == '1099-INT':
                    lbl = int_titles.get((path, idx), lbl)
                elif form == '1099-DIV':
                    lbl = div_titles.get((path, idx), lbl)
                lbl = _clean_label(lbl)
                append_and_bookmark(entry, node, lbl)

    if expenses:
        root = merger.add_outline_item('Expenses', page_num)
        for form, grp in group_by_type(expenses).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, entry in enumerate(grp, 1):
                path, idx, _ = entry
                lbl = form if len(grp) == 1 else f"{form}#{j}"
                if form == '1098-Mortgage':
                    lbl = mort_titles.get((path, idx), lbl)
                lbl = _clean_label(lbl)
                append_and_bookmark(entry, node, lbl)

    if others:
        root = merger.add_outline_item('Others', page_num)
        node = merger.add_outline_item('Unused', page_num, parent=root)
        for j, entry in enumerate(others, 1):
            lbl = 'Unused' if len(others) == 1 else f"Unused#{j}"
            append_and_bookmark(entry, node, lbl)

    # Write merged output
    os.makedirs(os.path.dirname(abs_output), exist_ok=True)
    with open(abs_output, 'wb') as f:
        merger.write(f)
    merger.close()
    logger.info("Merged PDF created at %s", abs_output)

    # Optional cleanup
    if delete_inputs:
        for fname in files:
            try:
                os.remove(os.path.join(abs_input, fname))
                logger.debug("Deleted %s", fname)
            except Exception:
                logger.warning("Failed to delete %s", fname, exc_info=True)

# ----------------------------------- CLI ---------------------------------------
if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description="Merge PDFs with bookmarks (fast)")
    p.add_argument('input_dir', help="Folder containing PDFs to merge")
    p.add_argument('output_pdf', help="Path for the merged PDF (outside input_dir)")
    p.add_argument('--delete-inputs', action='store_true', help='Delete inputs after merge')
    args = p.parse_args()
    merge_with_bookmarks(args.input_dir, args.output_pdf, delete_inputs=args.delete_inputs)
