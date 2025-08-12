import sys, os, io, tempfile, traceback, re
from collections import defaultdict, Counter
from typing import Dict, List, Tuple
import re
from collections import Counter

# …
EMP_BRACKET_RE = re.compile(
    r"Employer's name, address, and ZIP code.*?\[(.*?)\]",
    re.IGNORECASE | re.DOTALL
)

from PyPDF2 import PdfMerger, PdfReader, PdfWriter
import PyPDF2
from pdfminer.high_level import extract_text as pdfminer_extract
from pdfminer.layout import LAParams
import pytesseract
#from pdf2image import convert_from_path
import fitz  # PyMuPDF
import pdfplumber
from PIL import Image
import logging

# Add the helper at the [To get bookmark for]
PHRASE = "Employer's name, address, and ZIP code"
INT_PHRASE = "Interest income"


def print_phrase_context(text: str, phrase: str = PHRASE, num_lines: int = 2):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if phrase.lower() in line.lower():
            for j in range(i, min(i + 1 + num_lines, len(lines))):
                print(lines[j], file=sys.stderr)
            break

# ── Unicode console on Windows
def configure_unicode():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
configure_unicode()

# ── Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Configuration
POPPLER_PATH = os.environ.get("POPPLER_PATH")  # e.g. "C:\\poppler\\Library\\bin"
OCR_MIN_CHARS = 50
PDFMINER_LA_PARAMS = LAParams(line_margin=0.2, char_margin=2.0)

# ── Priority tables
income_priorities = {
    'W-2': 1,
    'Consolidated-1099': 2,
    '1099-NEC': 3,
    '1099-PATR': 4,
    '1099-MISC': 5,
    '1099-OID': 6,
    '1099-G': 7,
    'W-2G': 8,
    '1065': 9,
    '1120-S': 10,
    '1041': 11,
    '1099-INT': 12,
    '1099-DIV': 13,
    '1099-R': 14,
    '1099-Q': 15,
    'K-1': 16,
    '1099-Other': 17
}
expense_priorities = {
    '5498-SA': 1, '1095-A': 2, '1095-B': 3, '1095-C': 4,
    '1098-Mortgage': 5, '1098-T': 6, 'Property Tax': 7, '1098-Other': 8
}

def get_form_priority(ftype: str, category: str) -> int:
    table = income_priorities if category == 'Income' else (expense_priorities if category == 'Expenses' else {})
    return table.get(ftype, max(table.values()) + 1 if table else 9999)

# ── Logging helper
def log_extraction(src: str, method: str, text: str):
    snippet = text[:2000].replace('\n', ' ') + ('...' if len(text) > 2000 else '')
    logger.info(f"[{method}] {os.path.basename(src)} → '{snippet}'")

# ── Tiered text extraction for PDF pages
def extract_text(path: str, page_index: int) -> str:
    text = ""
    # OCR fallback
    if len(text.strip()) < OCR_MIN_CHARS:
        t3 = _ocr_page_with_pymupdf(path, page_index)
        print(f"[OCR full]\n{t3}", file=sys.stderr)
        if len(t3.strip()) > len(text):
            text = t3
    # PDFMiner
    try:
        t1 = pdfminer_extract(path, page_numbers=[page_index], laparams=PDFMINER_LA_PARAMS) or ""
        print(f"[PDFMiner full]\n{t1}", file=sys.stderr)
        if len(t1.strip()) > len(text): text = t1
    except Exception:
        traceback.print_exc()
    # PyPDF2 fallback
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            reader = PdfReader(path)
            t2 = reader.pages[page_index].extract_text() or ""
            print(f"[PyPDF2 full]\n{t2}", file=sys.stderr)
            if len(t2.strip()) > len(text): text = t2
        except Exception:
            traceback.print_exc()
    return text
# ocr extraction
def _ocr_page_with_pymupdf(pdf_path: str, page_index: int) -> str:
    """Render a PDF page with PyMuPDF and OCR it with Tesseract (no Poppler needed)."""
    try:
        doc = fitz.open(pdf_path)
        page = doc.load_page(page_index)
        pix = page.get_pixmap(dpi=300)          # render at 300 DPI
        img_bytes = pix.tobytes("png")          # get PNG bytes
        img = Image.open(io.BytesIO(img_bytes)) # PIL Image
        text = pytesseract.image_to_string(img, config="--psm 6") or ""
        return text
    except Exception:
        traceback.print_exc()
        return ""
    finally:
        try:
            doc.close()
        except Exception:
            pass

# ── Full‐PDF text extractor
def extract_text_from_pdf(file_path: str) -> str:
    text = ""
    try:
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for i, page in enumerate(reader.pages):
                pt = page.extract_text() or ""
                if pt.strip():
                    print_phrase_context(pt)
                    text += f"\n--- Page {i+1} ---\n" + pt
    except Exception as e:
        logger.error(f"Error in full PDF extract {file_path}: {e}")
        text = f"Error extracting full PDF: {e}"
    return text

# ── OCR for images
def extract_text_from_image(file_path: str) -> str:
    text = ""
    try:
        img = Image.open(file_path)
        if img.mode != 'RGB': img = img.convert('RGB')
        et = pytesseract.image_to_string(img)
        if et.strip():
            print_phrase_context(et)
            text = f"\n--- OCR Image {os.path.basename(file_path)} ---\n" + et
        else:
            text = f"No text in image: {os.path.basename(file_path)}"
    except Exception as e:
        logger.error(f"Error OCR image {file_path}: {e}")
        text = f"Error OCR image: {e}"
    return text

def extract_account_number(text: str) -> str:
    """
    Extract and normalize the account number from page text.
    """
    match = re.search(r"Account Number:\s*([\d\s]+)", text, re.IGNORECASE)
    if match:
        return match.group(1).replace(" ", "").strip()
    return None

# --- Classification Helper
def classify_text(text: str) -> Tuple[str, str]:
    t = text.lower()
    lower = text.lower()
    
    # 1) Detect W-2 pages by key header phrases
    if (
        "wages, tips, other compensation" in lower or
        ("employer's name" in lower and "address" in lower)
    ):
        return "Income", "W-2"
    consolidated_unused = [
    "1099 consolidated tax statement for 20",      
    "you may receive a separate 1099 consolidated tax statement",
    "consider and review both consolidated tax statements",
    "visit etrade.com/taxyear20",
    "etrade from morgan stanley",
    "morgan stanley smith barney llc",
    ]
    lower = text.lower()
    for pat in consolidated_unused:
        if pat in lower:
            return "Others", "Unused"

    # If page matches any instruction patterns, classify as Others → Unused
    instruction_patterns = [
    # full “Instructions for Employee…” block (continued from back of Copy C)
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
    "if your name, SSN, or address is incorrect",
    "corrected wage and tax statement",
    "credit for excess taxes",
    "instructions for employee  (continued from back of copy c) "
    "box 12 (continued)",
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
    # 1098-Mortgage 
    ]
    for pat in instruction_patterns:
        if pat in lower:
            return "Others", "Unused"
    #-----1099-DIV
    div_category = [
        "1a total ordinary dividends",
        "1b Qualified dividends Distributions",
        "form 1099-div",
        "2a total capital gain diste",
        "2b unrecap. sec",
        "2c section 1202 gain "
    ]
    
    for pat in div_category:
        if pat.lower() in lower:
            return "Income", "1099-DIV"   
    
    
    #---------------------------1099-INT----------------------------------# 
    #1099-INT for page 1
    int_front = [
        "3 Interest on U.S. Savings Bonds and Treasury obligations",
        "Investment expenses",
        "Tax-exempt interest",
        "ond premium on Treasury obligations",
        "withdrawal penalty",
    
    ]

    int_unused = [
        "Box 1. Shows taxable interest paid to you ",
        "Box 2. Shows interest or principal forfeited",
        "Box 3. Shows interest on U.S. Savings Bonds",
        "Box 8. Shows tax-exempt interest paid to",
        "Box 10. For a taxable or tax-exempt covered security"
    ]
    lower = text.lower()
    found_int_front = any(pat.lower() in lower for pat in int_front)
    found_int_unused = any(pat.lower() in lower for pat in int_unused)

# 🔁 Priority: 1099-INT > Unused
    if found_int_front:
        return "Income", "1099-INT"
    elif found_int_unused:
        return "Others", "Unused"
    #---------------------------1099-INT----------------------------------# 
    #---------------------------1098-Mortgage----------------------------------#     
    #1098-Mortgage form page 1
    mort_front = [
    "Mortgage insurance premiums",
    "Mortgage origination date",
    "Number of properties securing the morgage",  # typo here, maybe fix to "mortgage"
    "Address or description of property securing",
    "form 1098 mortgage",
    "limits based on the loan amount",
    "refund of overpaid",
    "Mortgage insurance important tax Information",
    "Account number (see instructions)"
    ]
    mort_unused = [
        "instructions for payer/borrower",
        "payer’s/borrower’s taxpayer identification number",
        "box 1. shows the mortgage interest received",
        "Box 1. Shows the mortgage interest received by the recipient",
        "Box 3. Shows the date of the mortgage origination",
        "Box 5. If an amount is reported in this box",
        "Box 8. Shows the address or description",  # ← this line was missing a comma
        "This information is being provided to you as",
        "We’re providing the mortgage insurance",
        "If you received this statement as the payer of",
        "If your mortgage payments were subsidized"
        
    ]
    lower = text.lower()
    found_front = any(pat.lower() in lower for pat in mort_front)
    found_unused = any(pat.lower() in lower for pat in mort_unused)

# 🔁 Priority: 1098-Mortgage > Unused
    if found_front:
        return "Expenses", "1098-Mortgage"
    elif found_unused:
        return "Others", "Unused"

    #---------------------------1098-Mortgage----------------------------------#
#3) fallback form detectors
    if 'wage and tax statement' in t or ("employer's name" in t and 'address' in t):
        return 'Income', 'W-2'
    if 'w-2' in t or 'w2' in t: return 'Income', 'W-2'
    if '1098-t' in t: return 'Expenses', '1098-T'
    if '1099' in t: return 'Income', '1099-Other'
    if 'donation' in t: return 'Expenses', 'Donation'
    return 'Unknown', 'Unused'

# Parse W-2
def normalize_entity_name(raw: str) -> str:
    stripped = raw.strip()
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

    lines: List[str] = text.splitlines()
    emp_name = emp_addr = "N/A"
    bookmark = None

    marker = ("c Employer's name, address, and ZIP code "
              "8 Allocated tips 3 Social security wages 4 Social security tax withheld").lower()
    lower_lines = [l.lower() for l in lines]

    for i, L in enumerate(lower_lines):
        if marker in L:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                raw = lines[j].strip()
                if re.match(r'^[A-Za-z]', raw):
                    m = re.match(r'^(.+?)\s+\d', raw)
                    company = (m.group(1).strip() if m else raw)
                    emp_name = normalize_entity_name(company)
                    bookmark = company
                    return {
                        'ssn': ssn, 'ein': ein,
                        'employer_name': emp_name,
                        'employer_address': emp_addr,
                        'employee_name': 'N/A',
                        'employee_address': 'N/A',
                        'bookmark': bookmark
                    }
            break

    for i, line in enumerate(lines):
        if "0000000845 - PAYROL" in line:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                words = lines[j].strip().split()
                emp_name = " ".join(words[:3])
            break

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
                'ssn': ssn, 'ein': ein,
                'employer_name': emp_name,
                'employer_address': emp_addr,
                'employee_name': 'N/A',
                'employee_address': 'N/A',
                'bookmark': bookmark
            }

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
            if "c Employer's name, address, and ZIP code" in line:
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    words = lines[j].strip().split()
                    emp_name = " ".join(words[:3])
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
        'employee_address': 'N/A'
    }

def print_w2_summary(info: Dict[str, str]):
    print("\n=== W-2 Summary ===\n")
    print(f"Employer: {info['employer_name']}, Address: {info['employer_address']}, EIN: {info['ein']}")
    print("===================\n")

# 1099-INT bookmark extraction
def extract_1099int_bookmark(text: str) -> str:
    lines: List[str] = text.splitlines()
    lower_lines = [L.lower() for L in lines]
    full_lower = text.lower()

    if any(v in full_lower for v in ("uss bank na", "us bank na", "u s bank na")):
        return "US Bank NA"
    if any(v in full_lower for v in ("capital one na", "capital one n.a", "capital one national association")):
        return "CAPITAL ONE NA"
    if "bank of america" in full_lower:
        for L in lines:
            if "bank of america" in L.lower():
                return re.sub(r"[^\w\s]+$", "", L.strip())

    def extract_all_bookmarks(lines):
        lower_lines = [l.lower() for l in lines]
        bookmarks = []
        skip_phrases = {
            "omb no", "payer's tin", "payer's rtn", "rtn",
            "1099-int interest", "recipient's tin", "fatca filing",
            "copy b", "account number", "form 1099-int", "1 interest income income"
        }
        for i, L in enumerate(lower_lines):
            if "or foreign postal code, and telephone no." in L:
                for offset in range(1, 4):
                    idx = i + offset
                    if idx >= len(lines):
                        break
                    candidate = lines[idx].strip()
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

    patterns = [
        "interest income income",
        "zip or foreign postal code, and telephone no.",
        "federal id number:",
    ]
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

# --- Issuer display aliases ---
ISSUER_ALIASES = {
    "morgan stanley capital management, llc": "E*TRADE",
}
def alias_issuer(name: str) -> str:
    return ISSUER_ALIASES.get(name.lower().strip(), name)

# --------------------------- Consolidated-1099 issuer name --------------------------- #
def extract_consolidated_issuer(text: str) -> str | None:
    lower = text.lower()
    if re.search(r"morgan\s+stanley\s+capital\s+management,\s*llc", lower):
        return "Morgan Stanley Capital Management, LLC"
    if "consolidated 1099" in lower or "composite 1099" in lower:
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            if re.search(r"(form|1099|copy|page|\baccount\b)", s, re.IGNORECASE):
                continue
            if re.search(r"(LLC|Bank|Securities|Wealth|Brokerage|Advisors?)", s):
                return re.sub(r"[^\w\s,&.\-]+$", "", s)
    return None

# 1099-DIV bookmark extractor
def extract_1099div_bookmark(text: str) -> str:
    lines = text.splitlines()
    lower_text = text.lower()
    lower_lines = [L.lower() for L in lines]
    marker = ("payer's name, street address, city or town, state or province, country, "
              "zip or foreign postal code, and telephone no.")
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
    cleaned = re.sub(r"\bInterest.*$", "", name, flags=re.IGNORECASE)
    return cleaned.strip()

# 1098-Mortgage bookmark extractor
def extract_1098mortgage_bookmark(text: str) -> str:
    lines: List[str] = text.splitlines()
    lower_lines = [L.lower() for L in lines]

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

def group_by_type(entries: List[Tuple[str, int, str]]) -> Dict[str, List[Tuple[str, int, str]]]:
    d = defaultdict(list)
    for e in entries:
        d[e[2]].append(e)
    return d

def print_pdf_bookmarks(path: str):
    try:
        reader = PdfReader(path)
        outlines = reader.outlines
        print(f"\n--- Bookmark structure for {os.path.basename(path)} ---")
        def recurse(bms, depth=0):
            for bm in bms:
                if isinstance(bm, list):
                    recurse(bm, depth + 1)
                else:
                    title = getattr(bm, 'title', str(bm))
                    print("  " * depth + f"- {title}")
        recurse(outlines)
    except Exception as e:
        logger.error(f"Error reading bookmarks from {path}: {e}")

# ---------- Multi-form detector for a page ----------
def detect_income_forms(text: str) -> List[str]:
    t = (text or "").lower()
    out = []
    if ("form 1099-int" in t or "interest income" in t or "box 1. shows taxable interest" in t):
        out.append("1099-INT")
    if ("form 1099-div" in t or "total ordinary dividends" in t or "qualified dividends" in t):
        out.append("1099-DIV")
    if ("form 1099-misc" in t) or ("rents" in t and "royalties" in t and "other income" in t):
        out.append("1099-MISC")
    if "form 1099-oid" in t or "original issue discount" in t:
        out.append("1099-OID")
    if "form 1099-b" in t or "proceeds from broker" in t or "cost or other basis" in t:
        out.append("1099-B")
    if "form 1099-nec" in t or "nonemployee compensation" in t:
        out.append("1099-NEC")
    seen, res = set(), []
    for f in out:
        if f not in seen:
            seen.add(f); res.append(f)
    return res

# ── Merge + bookmarks + cleanup
def merge_with_bookmarks(input_dir: str, output_pdf: str):
    abs_input = os.path.abspath(input_dir)
    abs_output = os.path.abspath(output_pdf)
    if abs_output.startswith(abs_input + os.sep):
        abs_output = os.path.join(os.path.dirname(abs_input), os.path.basename(abs_output))
        logger.warning(f"Moved output outside: {abs_output}")
    all_files = sorted(
        f for f in os.listdir(abs_input)
        if f.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.tiff'))
        and f != os.path.basename(abs_output)
    )
    files = []
    for f in all_files:
        p = os.path.join(abs_input, f)
        if os.path.getsize(p) == 0:
            logger.warning(f"Skipping empty file: {f}")
            continue
        files.append(f)
    logger.info(f"Found {len(files)} files in {abs_input}")

    income, expenses, others = [], [], []
    w2_titles = {}
    int_titles = {}
    div_titles = {}
    mort_titles = {}
    account_pages = {}   # {account_number: [(path, page_index, 'Consolidated-1099')]}
    account_names = {}   # {account_number: issuer_name}
    # NEW: track original classification per (file path, page index)
    page_class: Dict[Tuple[str, int], Tuple[str, str]] = {}

    for fname in files:
        path = os.path.join(abs_input, fname)
        if fname.lower().endswith('.pdf'):
            total = len(PdfReader(path).pages)
            for i in range(total):
                print("=" * 200, file=sys.stderr)
                print(f"Processing: {fname}, Page {i+1}", file=sys.stderr)

                # Multi-method extraction
                extracts = {}

                print("→ PDFMiner:", file=sys.stderr)
                try:
                    extracts['PDFMiner'] = pdfminer_extract(path, page_numbers=[i], laparams=PDFMINER_LA_PARAMS) or ""
                    print(extracts['PDFMiner'], file=sys.stderr)
                except Exception as e:
                    extracts['PDFMiner'] = ""
                    print(f"[ERROR] PDFMiner failed: {e}", file=sys.stderr)

                print("→ PyPDF2:", file=sys.stderr)
                try:
                    extracts['PyPDF2'] = PdfReader(path).pages[i].extract_text() or ""
                    print(extracts['PyPDF2'], file=sys.stderr)
                except Exception as e:
                    extracts['PyPDF2'] = ""
                    print(f"[ERROR] PyPDF2 failed: {e}", file=sys.stderr)

                print("→ Tesseract OCR (PyMuPDF render):", file=sys.stderr)
                try:
                    doc_ocr = fitz.open(path)
                    page_ocr = doc_ocr.load_page(i)
                    pix = page_ocr.get_pixmap(dpi=300)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    extracts['Tesseract'] = pytesseract.image_to_string(img, config="--psm 6") or ""
                    doc_ocr.close()
                    print(extracts['Tesseract'], file=sys.stderr)
                except Exception as e:
                    extracts['Tesseract'] = ""
                    print(f"[ERROR] Tesseract failed: {e}", file=sys.stderr)
                print("→ PyMuPDF (fitz):", file=sys.stderr)
                try:
                    doc = fitz.open(path)
                    extracts['PyMuPDF'] = doc.load_page(i).get_text()
                    doc.close()
                    print(extracts['PyMuPDF'], file=sys.stderr)
                except Exception as e:
                    extracts['PyMuPDF'] = ""
                    print(f"[ERROR] PyMuPDF failed: {e}", file=sys.stderr)

                print("=" * 200, file=sys.stderr)

                # Collect W-2 employer names across methods + payers for other forms
                info_by_method, names = {}, []
                for method, txt in extracts.items():
                    cat, ft = classify_text(txt)
                    if cat == 'Income' and ft == 'W-2':
                        info = parse_w2(txt)
                        if info['employer_name'] != 'N/A':
                            info_by_method[method] = info
                            names.append(info['employer_name'])
                    if cat == 'Income' and ft == '1099-INT':
                        title = extract_1099int_bookmark(txt)
                        if title and title != '1099-INT':
                            int_titles[(path, i)] = title
                    if cat == 'Income' and ft == '1099-DIV':
                        title = extract_1099div_bookmark(txt)
                        if title and title != '1099-DIV':
                            div_titles[(path, i)] = title
                    if cat == 'Expenses' and ft == '1098-Mortgage':
                        title = extract_1098mortgage_bookmark(txt)
                        if title and title != '1098-Mortgage':
                            mort_titles[(path, i)] = title
                if names:
                    common = Counter(names).most_common(1)[0][0]
                    chosen = next(m for m, i_ in info_by_method.items() if i_['employer_name'] == common)
                    print(f"--- Chosen employer ({chosen}): {common} ---", file=sys.stderr)
                    print_w2_summary(info_by_method[chosen])
                    w2_titles[(path, i)] = common

                # Classification & grouping
                tiered = extract_text(path, i)
                acct_num = extract_account_number(tiered)
                if acct_num:
                    account_pages.setdefault(acct_num, []).append((path, i, "Consolidated-1099"))
                    issuer = extract_consolidated_issuer(tiered)
                    if issuer:
                        account_names.setdefault(acct_num, issuer)
                cat, ft = classify_text(tiered)
                # NEW: remember original classification for this page
                page_class[(path, i)] = (cat, ft)

                print(
                    f"[Classification] {os.path.basename(path)} p{i+1} → "
                    f"Category='{cat}', Form='{ft}', "
                    f"snippet='{tiered[:150].strip().replace(chr(80),' ')}…'",
                    file=sys.stderr
                )

                entry = (path, i, ft)
                if cat == 'Income':
                    income.append(entry)
                elif cat == 'Expenses':
                    expenses.append(entry)
                else:
                    others.append(entry)

        else:
            # Image handling
            print(f"\n=== Image {fname} ===", file=sys.stderr)
            oi = extract_text_from_image(path)
            print("--- OCR Image ---", file=sys.stderr)
            print(oi, file=sys.stderr)
            cat, ft = classify_text(oi)
            entry = (path, 0, ft)
            if cat == 'Income':
                income.append(entry)
            elif cat == 'Expenses':
                expenses.append(entry)
            else:
                others.append(entry)



#---------------------
    # ---- Consolidated-1099 synthesis (group ALL account pages, even singletons) ----
    consolidated_payload = {}
    consolidated_pages = set()

    for acct, pages in account_pages.items():
        key = f"CONSOLIDATED::{acct}"
        consolidated_payload[key] = [(p, i, "Consolidated-1099") for (p, i, _) in pages]
        for (p, i, _) in pages:
            consolidated_pages.add((p, i))
    # add one synthetic row per account so it appears under the Consolidated-1099 group
        income.append((key, -1, "Consolidated-1099"))


    # Sort
    income.sort(key=lambda e: (get_form_priority(e[2], 'Income'), e[0], e[1]))
    expenses.sort(key=lambda e: (get_form_priority(e[2], 'Expenses'), e[0], e[1]))

    # merge & bookmarks
    merger = PdfMerger()
    page_num = 0
    import mimetypes

    # Track merged page index to allow multiple bookmarks to the same page
    page_location: Dict[Tuple[str, int], int] = {}

    def append_and_bookmark(entry, parent, title):
        nonlocal page_num
        p, idx, _ = entry
        mime_type, _ = mimetypes.guess_type(p)

        if mime_type != 'application/pdf':
            print(f"⚠️  Skipping non-PDF file: {p}", file=sys.stderr)
            return

        # If already appended, just add another outline item pointing to same merged page
        if (p, idx) in page_location:
            merger.add_outline_item(title, page_location[(p, idx)], parent=parent)
            return

        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            w = PdfWriter()
            try:
                w.add_page(PdfReader(p).pages[idx])
                w.write(tmp)
                tmp.flush()
                os.fsync(tmp.fileno())
            except Exception:
                print(f"⚠️  Temp write failed for {p!r} (page {idx+1}); skipping.", file=sys.stderr)
                traceback.print_exc()
                return
            tmp_path = tmp.name

        with open(tmp_path, 'rb') as fh:
            merger.append(fileobj=fh)
        os.unlink(tmp_path)

        page_location[(p, idx)] = page_num
        merger.add_outline_item(title, page_num, parent=parent)
        page_num += 1

    # ── Bookmarks
    if income:
        root = merger.add_outline_item('Income', page_num)
        groups = group_by_type(income)
        for form, grp in sorted(groups.items(), key=lambda kv: get_form_priority(kv[0], 'Income')):
            if form == 'Consolidated-1099':
                cons_root = merger.add_outline_item('Consolidated-1099', page_num, parent=root)

                # Cache per-issuer: (issuer_node, {form_type -> form_node}, Counter)
                issuer_nodes: Dict[str, Tuple[object, Dict[str, object], Counter]] = {}

                for entry in grp:
                    key, _, _ = entry  # "CONSOLIDATED::<acct>"
                    acct = key.split("::", 1)[1]

                    issuer_raw = account_names.get(acct)
                    issuer_label = alias_issuer(issuer_raw) if issuer_raw else "Consolidated Issuer"

                    if issuer_label not in issuer_nodes:
                        issuer_node = merger.add_outline_item(issuer_label, page_num, parent=cons_root)
                        issuer_nodes[issuer_label] = (issuer_node, {}, Counter())

                    issuer_node, form_nodes, form_counts = issuer_nodes[issuer_label]

                    for real_entry in consolidated_payload.get(key, []):
                        p, i, _ = real_entry

                        # Respect original classification
                        orig_cat, orig_ft = page_class.get((p, i), ("Unknown", "Unused"))
                        if orig_cat == "Others" and orig_ft == "Unused":
                            # Put under a single Unused node per issuer
                            if "Unused" not in form_nodes:
                                form_nodes["Unused"] = merger.add_outline_item("Unused", page_num, parent=issuer_node)
                            append_and_bookmark(real_entry, form_nodes["Unused"], "Unused")
                            continue  # ← do NOT run detect_income_forms

                        # Otherwise, detect forms for this page
                        try:
                            page_text = extract_text(p, i)
                        except Exception:
                            page_text = ""

                        forms_here = detect_income_forms(page_text) or ["Page"]
                        for ftype in forms_here:
                            if ftype not in form_nodes:
                                form_nodes[ftype] = merger.add_outline_item(ftype, page_num, parent=issuer_node)
                            form_counts[ftype] += 1
                            label = ftype if form_counts[ftype] == 1 else f"{ftype}#{form_counts[ftype]}"
                            append_and_bookmark(real_entry, form_nodes[ftype], label)


                continue  # done with Consolidated-1099

            # Normal Income forms
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, entry in enumerate(grp, 1):
                path, idx, _ = entry

                # Skip if this page was already placed under Consolidated-1099
                if (path, idx) in consolidated_pages:
                    continue

                lbl = form if len(grp) == 1 else f"{form}#{j}"
                if form == 'W-2':
                    emp = w2_titles.get((path, idx))
                    if emp:
                        lbl = emp
                elif form == '1099-INT':
                    payer = int_titles.get((path, idx))
                    if payer:
                        lbl = payer
                elif form == '1099-DIV':
                    payer = div_titles.get((path, idx))
                    if payer:
                        lbl = payer

                # Normalize trailing ", N.A."
                lbl = re.sub(r",?\s*N\.A\.?$", "", lbl, flags=re.IGNORECASE)

                print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Income', Form='{form}', Title='{lbl}'", file=sys.stderr)
                append_and_bookmark(entry, node, lbl)

    if expenses:
        root = merger.add_outline_item('Expenses', page_num)
        for form, grp in group_by_type(expenses).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, entry in enumerate(grp, 1):
                path, idx, _ = entry
                lbl = form if len(grp) == 1 else f"{form}#{j}"
                if form == '1098-Mortgage':
                    m = mort_titles.get((path, idx))
                    if m:
                        lbl = m
                lbl = re.sub(r",?\s*N\.A\.?$", "", lbl, flags=re.IGNORECASE)
                print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Expenses', Form='{form}', Title='{lbl}'", file=sys.stderr)
                append_and_bookmark(entry, node, lbl)

    if others:
        root = merger.add_outline_item('Others', page_num)
        node = merger.add_outline_item('Unused', page_num, parent=root)
        for j, entry in enumerate(others, 1):
            path, idx, _ = entry
            lbl = 'Unused' if len(others) == 1 else f"Unused#{j}"
            print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Others', Form='Unused', Title='{lbl}'", file=sys.stderr)
            append_and_bookmark(entry, node, lbl)

    # Write merged output
    os.makedirs(os.path.dirname(abs_output), exist_ok=True)
    with open(abs_output, 'wb') as f:
        merger.write(f)
    merger.close()
    print(f"Merged PDF created at {abs_output}", file=sys.stderr)

    # Cleanup uploads
    for fname in files:
        try:
            os.remove(os.path.join(input_dir, fname))
            print(f"Deleted {fname}", file=sys.stderr)
        except Exception as e:
            print(f"Failed to delete {fname}: {e}", file=sys.stderr)

# ── CLI
if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description="Merge PDFs with robust text extraction and cleanup")
    p.add_argument('input_dir', help="Folder containing PDFs to merge")
    p.add_argument('output_pdf', help="Path for the merged PDF (outside input_dir)")
    args = p.parse_args()
    merge_with_bookmarks(args.input_dir, args.output_pdf)












