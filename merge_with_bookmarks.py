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
from pdf2image import convert_from_path
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
income_priorities = {'W-2':1,'1099-NEC':2,'1099-PATR':3,'1099-MISC':4,'1099-OID':5,'1099-G':6,'W-2G':7,'1065':8,'1120-S':9,'1041':10,'1099-INT':11,'1099-DIV':12,'1099-R':13,'1099-Q':14,'K-1':15,'1099-Other':16}
expense_priorities = {'5498-SA':1,'1095-A':2,'1095-B':3,'1095-C':4,'1098-Mortgage':5,'1098-T':6,'Property Tax':7,'1098-Other':8}

def get_form_priority(ftype: str, category: str) -> int:
    table = income_priorities if category=='Income' else (expense_priorities if category=='Expenses' else {})
    return table.get(ftype, max(table.values())+1 if table else 9999)

# ── Logging helper
def log_extraction(src: str, method: str, text: str):
    snippet = text[:2000].replace('\n',' ') + ('...' if len(text)>2000 else '')
    logger.info(f"[{method}] {os.path.basename(src)} → '{snippet}'")

# ── Tiered text extraction for PDF pages
def extract_text(path: str, page_index: int) -> str:
    text = ""
    # OCR fallback
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            opts = {'poppler_path': POPPLER_PATH} if POPPLER_PATH else {}
            img = convert_from_path(path, first_page=page_index+1, last_page=page_index+1, **opts)[0]
            t3 = pytesseract.image_to_string(img, config="--psm 6") or ""
            #print(f"[OCR full]\n{t3}", file=sys.stderr)
            if len(t3.strip()) > len(text): text = t3
        except Exception:
            traceback.print_exc()
    # PDFMiner
    try:
        t1 = pdfminer_extract(path, page_numbers=[page_index], laparams=PDFMINER_LA_PARAMS) or ""
        #print(f"[PDFMiner full]\n{t1}", file=sys.stderr)
        if len(t1.strip()) > len(text): text = t1
    except Exception:
        traceback.print_exc()
    # PyPDF2 fallback
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            reader = PdfReader(path)
            t2 = reader.pages[page_index].extract_text() or ""
         #   print(f"[PyPDF2 full]\n{t2}", file=sys.stderr)
            if len(t2.strip()) > len(text): text = t2
        except Exception:
            traceback.print_exc()
    
    return text

# ── Full‐PDF text extractor
def extract_text_from_pdf(file_path: str) -> str:
    text = ""
    try:
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for i, page in enumerate(reader.pages):
                pt = page.extract_text() or ""
                if pt.strip():
                    #print_phrase_context(pt)
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
        if img.mode!='RGB': img = img.convert('RGB')
        et = pytesseract.image_to_string(img)
        if et.strip():
            print_phrase_context(et)
            text = f"\n--- OCR Image {os.path.basename(file_path)} ---\n" + et
        else: text = f"No text in image: {os.path.basename(file_path)}"
    except Exception as e:
        logger.error(f"Error OCR image {file_path}: {e}")
        text = f"Error OCR image: {e}"
    return text
# --- Classification Helper
def classify_text(text: str) -> Tuple[str, str]:
    t = text.lower()
    lower = text.lower()
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
    div_category = [
        "1a total ordinary dividends",
        "1b Qualified dividends Distributions",
        "form 1099-div",
        "2a total capital gain diste",
        "2b unrecap. sec",
        "2c section 1202 gain "
    ]
    
    for pat in div_category:
        if pat in lower:
            return "Income", "1099-DIV"
    #1098-Mortgage form page 1
    mort_front = [
        "Refund of overpaid interest",
        "Mortgage insurance premiums",
        "Mortgage origination date",
        "Number of properties securing the morgage",
        "Address or description of property securing",
        "form 1098 mortgage",
        "limits based on the loan amount"
    ]
    for pat in mort_front:
        if pat in lower:
            return "Expenses", "1098-Mortgage"
    #1098-Mortgage unused
    mort_unused = [
        "instructions for payer/borrower",
        "payer’s/borrower’s taxpayer identification number",
        "box 1. shows the mortgage interest received",
        "Box 1. Shows the mortgage interest received by the recipient",
        "Box 3. Shows the date of the mortgage origination",
        "Box 5. If an amount is reported in this box",
        "Box 8. Shows the address or description"
        "This information is being provided to you as",
        "We’re providing the mortgage insurance",
        
    ]
    
    for pat in mort_unused:
        if pat in lower:
            return "Others", "Unused"
    #3) fallback form detectors
    if 'w-2' in t or 'w2' in t: return 'Income', 'W-2'
    if '1099-int' in t or 'interest income' in t: return 'Income', '1099-INT'
    if '1099-div' in t: return 'Income', '1099-DIV'
    if 'form 1099-div' in t: return 'Income', '1099-DIV'
    if '1098-t' in t: return 'Expenses', '1098-T'
    if '1099' in t: return 'Income', '1099-Other'
    if 'donation' in t: return 'Expenses', 'Donation'
    return 'Unknown', 'Unused'

    
    # Detect W-2 pages by their header phrases
    if 'wage and tax statement' in t or ("employer's name" in t and 'address' in t):
        return 'Income', 'W-2'
    
# ── Parse W-2 fields bookmarks
def normalize_entity_name(raw: str) -> str:
    """
    Cleans up employer names for bookmark use:
    - Removes trailing 'TAX WITHHELD'
    - Removes trailing numbers (including decimals)
    - Collapses repeated words and normalizes whitespace
    """
    stripped = raw.strip()
    # 1. Collapse whole-line duplicates (e.g., "X X" or "Y Y Y")
    whole_dup = re.match(r'^(?P<seq>.+?)\s+(?P=seq)(?:\s+(?P=seq))*$', stripped, flags=re.IGNORECASE)
    if whole_dup:
        stripped = whole_dup.group('seq')

    # 2. Collapse any repeated adjacent words (case-insensitive)
    collapsed = re.sub(r'\b(.+?)\b(?:\s+\1\b)+', r'\1', stripped, flags=re.IGNORECASE)

    # 3. Remove trailing 'TAX WITHHELD' (case-insensitive)
    collapsed = re.sub(r'\s*TAX WITHHELD\s*$', '', collapsed, flags=re.IGNORECASE)

    # 4. Remove trailing numbers (including decimals, possibly multiple, separated by space)
    collapsed = re.sub(r'(?:\s+\d+(?:\.\d+)?)+\s*$', '', collapsed)

    # 5. Standardize whitespace
    return ' '.join(collapsed.split()).strip()

def parse_w2(text: str) -> Dict[str, str]:
    """
    Parses SSN/EIN and pulls out employer_name and employer_address,
    normalizing duplicate employer names.

    Fallback order:
    1) Triple-cent-sign marker
    2) Standard W-2 header parsing
    3) PAYROL marker
    4) ©-marker fallback
    """
    # SSN & EIN
    ssn_m = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", text)
    ssn = ssn_m.group(1) if ssn_m else "N/A"
    ein_m = re.search(r"\b(\d{2}-\d{7})\b", text)
    ein = ein_m.group(1) if ein_m else "N/A"

    lines: List[str] = text.splitlines()
    emp_name = emp_addr = "N/A"

    # 1) Triple-cent-sign marker fallback
    triple_marker = (
        "© Employer's name, address, and ZIP code |[e Employer's name, address, and ZIP code |[e Employer's name, address, and ZIP code"
    )
    if triple_marker in text:
        # find its line index
        for i, L in enumerate(lines):
            if triple_marker in L:
                # next non-blank line
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    raw = lines[j].strip()
                    # split on '|' then dedupe words across all parts
                    parts = [p.strip() for p in raw.split("|")]
                    tokens, seen = [], set()
                    for part in parts:
                        for w in part.split():
                            if w not in seen:
                                seen.add(w)
                                tokens.append(w)
                    emp_name = normalize_entity_name(" ".join(tokens))
                break

        # return immediately if we got it
        return {
            'ssn': ssn,
            'ein': ein,
            'employer_name': emp_name,
            'employer_address': emp_addr,
            'employee_name': 'N/A',
            'employee_address': 'N/A'
        }

    # 2) Standard W-2 parsing
    for i, line in enumerate(lines):
        if "employer" in line.lower() and "name" in line.lower():
            # next non-blank = name
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
            # next non-blank = address
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                emp_addr = lines[j].strip()
            break

    # dedupe if found
    if emp_name != "N/A":
        toks, seen = emp_name.split(), set()
        emp_name = " ".join(w for w in toks if w not in seen and not seen.add(w)).rstrip("\\/")

    else:
        # 3) PAYROL fallback
        for i, line in enumerate(lines):
            if "0000000845 - PAYROL" in line:
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    emp_name = lines[j].strip().split()[0]
                break

        # 4) ©-marker fallback
        if emp_name == "N/A":
            marker = "© Employer's name, address, and ZIP code"
            for i, line in enumerate(lines):
                if marker in line:
                    j = i + 1
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines):
                        raw = lines[j].strip()
                        # split on '|' and dedupe words
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



def print_w2_summary(info: Dict[str,str]):
    print("\n=== W-2 Summary ===\n")
    print(f"Employer: {info['employer_name']}, Address: {info['employer_address']}, EIN: {info['ein']}")
    print("===================\n")
# ___ 1099-INTBookmark helper
def extract_1099int_bookmark(text: str) -> str:
    """
    1) US Bank NA override (normalize USS to US)
    2) BANK OF AMERICA override
    3) After your trigger patterns:
       • skip blanks, skip any TIN/RTN lines
       • if underscores-only, return that
       • else:
         a) strip “reel Form 1099-INT” + anything after
         b) strip trailing “, N.A” (opt. period)
         c) strip leftover punctuation/quotes
         d) strip any trailing single-character token (e.g. “i”)
         e) return the result
    """
    lines: List[str] = text.splitlines()
    lower = text.lower()
    # 1) US Bank NA override (including USS Bank NA)
    if "uss bank na" in lower or "us bank na" in lower or "u s bank na" in lower:
        # Normalize any variant to "US Bank NA"
        return "US Bank NA"
    # 2) BANK OF AMERICA override
    if "bank of america" in lower:
        for L in lines:
            if "bank of america" in L.lower():
                return re.sub(r"[^\w\s]+$", "", L.strip())
    # 3) trigger patterns
    patterns = [
        "Interest income Income",
        "ZIP or foreign postal code, and telephone no.",
        "Federal ID Number:",
    ]
    for i, L in enumerate(lines):
        if any(pat.lower() in L.lower() for pat in patterns):
            for j in range(i+1, len(lines)):
                s = lines[j].strip()
                if not s:
                    continue
                low = s.lower()
                if "tin" in low or "rtn" in low:
                    continue
                if set(s) == {"_"}:
                    return s
                # a) strip “reel Form 1099-INT…” and whatever follows
                cleaned = re.sub(
                    r"(?i)\s*reel\s+form\s+1099-?int\b.*$", "", s
                )
                # b) strip trailing ", N.A" (with or without dot)
                cleaned = re.sub(r",\s*n\.a\.?$", "", cleaned, flags=re.IGNORECASE)
                # c) strip leftover punctuation or stray quotes
                cleaned = re.sub(r"[^\w\s]+$", "", cleaned)
                # d) drop any final single-character token
                cleaned = re.sub(r"\b\w\b$", "", cleaned).strip()
                return cleaned
    # fallback
    return "1099-INT"
# ___ 1099-DIV Bookmark helper
def extract_1099div_bookmark(text: str) -> str:
    """
    Grab the payer’s (or, if missing, the recipient’s) name for Form 1099-DIV by:
    0) If the full PAYER header (sometimes repeated) is present, take the line after that.
    1) Otherwise scan for the PAYER’S name header line,
    2) Otherwise scan for the RECIPIENT’S name header line,
    3) Skip blanks and return the very next non-blank line (stripping trailing junk).
    """
    import re

    lines = text.splitlines()
    lower_text = text.lower()
    lower_lines = [L.lower() for L in lines]

    # 0) Triple-marker fallback: if the full PAYER header shows up (maybe repeated),
    #    pull the very next non-blank line as the bookmark.
    marker = (
        "payer's name, street address, city or town, "
        "state or province, country, zip or foreign postal code, and telephone no."
    )
    if marker in lower_text:
        for i, L in enumerate(lower_lines):
            if marker in L:
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    # strip trailing punctuation/quotes
                    return re.sub(r"[^\w\s]+$", "", lines[j].strip())
                break

    # helper to find the next non-blank after a header predicate
    def find_after(header_pred):
        for i, L in enumerate(lower_lines):
            if header_pred(L):
                for j in range(i + 1, len(lines)):
                    cand = lines[j].strip()
                    if cand:
                        return re.sub(r"[^\w\s]+$", "", cand)
        return None

    # 1) Try the PAYER header
    payer = find_after(lambda L: "payer's name" in L and "street address" in L)
    if payer:
        return payer

    # 2) Fallback: RECIPIENT header
    recip = find_after(lambda L: "recipient's name" in L and "street address" in L)
    if recip:
        return recip

    # 3) Ultimate fallback
    return "1099-DIV"
# 1098-Mortgage
def clean_bookmark(name: str) -> str:
    # Remove any trailing junk starting from 'Interest' and strip whitespace
    cleaned = re.sub(r"\bInterest.*$", "", name, flags=re.IGNORECASE)
    return cleaned.strip()


def extract_1098mortgage_bookmark(text: str) -> str:
    """
    1) Dovenmuehle Mortgage override
    2) Huntington National Bank override
    3) UNITED NATIONS FCU override
    4) LOANDEPOT COM LLC override
    5) "Limits based" header override (grab first non-empty next line, strip any 'and' clause)
    6) FCU override
    7) PAYER(S)/BORROWER(S) override
    8) RECIPIENT’S/LENDER’S header override
    9) Fallback to "1098-Mortgage"
    After extraction, cleans up any trailing junk starting from 'Interest'.
    """
    lines: List[str] = text.splitlines()
    lower_lines = [L.lower() for L in lines]

    # 1) Dovenmuehle Mortgage override
    for L in lines:
        if re.search(r"dovenmuehle\s+mortgage", L, flags=re.IGNORECASE):
            m = re.search(r"(Dovenmuehle Mortgage, Inc)", L, flags=re.IGNORECASE)
            name = m.group(1) if m else re.sub(r"[^\w\s,]+$", "", L.strip())
            return clean_bookmark(name)

    # 2) Huntington National Bank override
    for L in lines:
        if re.search(r"\bhuntington\s+national\s+bank\b", L, flags=re.IGNORECASE):
            m = re.search(r"\b(?:The\s+)?Huntington\s+National\s+Bank\b", L, flags=re.IGNORECASE)
            name = m.group(0) if m else re.sub(r"[^\w\s]+$", "", L.strip())
            return clean_bookmark(name)

    # 3) UNITED NATIONS FCU override
    for L in lines:
        if re.search(r"\bunited\s+nations\s+fcu\b", L, flags=re.IGNORECASE):
            return clean_bookmark("UNITED NATIONS FCU")

    # 4) LOANDEPOT COM LLC override
    for L in lines:
        if re.search(r"\bloan\s*depot\s*com\s*llc\b", L, flags=re.IGNORECASE):
            m = re.search(r"\bloan\s*depot\s*com\s*llc\b", L, flags=re.IGNORECASE)
            name = m.group(0) if m else re.sub(r"[^\w\s]+$", "", L.strip())
            return clean_bookmark(name)

    # 5) "Limits based" header override (grab first non-blank NEXT line after match, clean smartly)
    for i, line in enumerate(lines):
        if "limits based on the loan amount" in line.lower():
            # Found the trigger line — look for next non-empty line
            for j in range(i + 1, len(lines)):
                candidate = lines[j].strip()
                if not candidate:
                    continue

                # Normalize fancy quotes and weird spacing
                candidate = candidate.replace("‘", "'").replace("’", "'").replace("\u00A0", " ")
                
                # Strip after 'Interest' if present
                candidate = re.sub(r"\bInterest.*$", "", candidate, flags=re.IGNORECASE)

                # Optionally, strip after 'and' if appears to be extra text
                candidate = re.split(r"\band\b", candidate, maxsplit=1, flags=re.IGNORECASE)[0].strip()

                # Final trailing punctuation cleanup
                candidate = re.sub(r"[^\w\s]+$", "", candidate)

                return candidate


    # 6) FCU override
    for L in lines:
        if re.search(r"\bfcu\b", L, flags=re.IGNORECASE):
            m = re.search(r"(.*?FCU)\b", L, flags=re.IGNORECASE)
            name = m.group(1) if m else re.sub(r"[^\w\s]+$", "", L.strip())
            return clean_bookmark(name)

    # 7) PAYER(S)/BORROWER(S) override
    for i, header in enumerate(lower_lines):
        if "payer" in header and "borrower" in header:
            for cand in lines[i+1:]:
                s = cand.strip()
                if not s or len(set(s)) == 1 or re.search(r"[\d\$]|page", s, flags=re.IGNORECASE):
                    continue
                raw = re.sub(r"[^\w\s]+$", "", s)
                raw = re.sub(r"(?i)\s+d/b/a\s+.*$", "", raw).strip()
                return clean_bookmark(raw)

    # 8) RECIPIENT’S/LENDER’S header override
    #    catch any line containing “recipient’s/lender’s” (ASCII or curly quotes),
    #    then use the very next non-blank line as the mortgage company name.
    for i, L in enumerate(lines):
        if re.search(r"recipient.?s\s*/\s*lender.?s", L, flags=re.IGNORECASE):
            for j in range(i+1, len(lines)):
                cand = lines[j].strip()
                if not cand:
                    continue
                # strip trailing punctuation
                name = re.sub(r"[^\w\s]+$", "", cand)
                return clean_bookmark(name)

    # 9) fallback
    return "1098-Mortgage"

def group_by_type(entries: List[Tuple[str,int,str]]) -> Dict[str,List[Tuple[str,int,str]]]:
    d=defaultdict(list)
    for e in entries: d[e[2]].append(e)
    return d

def print_pdf_bookmarks(path: str):
    try:
        reader = PdfReader(path)
        outlines = reader.outlines
        print(f"\n--- Bookmark structure for {os.path.basename(path)} ---")
        def recurse(bms, depth=0):
            for bm in bms:
                if isinstance(bm, list):
                    recurse(bm, depth+1)
                else:
                    title = getattr(bm, 'title', str(bm))
                    print("  " * depth + f"- {title}")
        recurse(outlines)
    except Exception as e:
        logger.error(f"Error reading bookmarks from {path}: {e}")

# ── Merge + bookmarks + multi-method extraction
nek = None 
# ── Merge + bookmarks + cleanup
def merge_with_bookmarks(input_dir: str, output_pdf: str):
    # Prevent storing merged file inside input_dir
    abs_input = os.path.abspath(input_dir)
    abs_output = os.path.abspath(output_pdf)
    if abs_output.startswith(abs_input + os.sep):
        abs_output = os.path.join(os.path.dirname(abs_input), os.path.basename(abs_output))
        logger.warning(f"Moved output outside: {abs_out}")
    all_files = sorted(
       f for f in os.listdir(abs_input)
       if f.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.tiff'))
       and f != os.path.basename(abs_output)
    )
   # remove any zero‐byte files so PdfReader never sees them
    files = []
    for f in all_files:
        p = os.path.join(abs_input, f)
        if os.path.getsize(p) == 0:
           logger.warning(f"Skipping empty file: {f}")
           continue
        files.append(f)
    logger.info(f"Found {len(files)} files in {abs_input}")

    income, expenses, others = [], [], []
    # what bookmarks we want in workpapaer shoudl be add in this
    w2_titles = {}
    int_titles = {}
    div_titles = {} # <-- Add this line
    mort_titles = {}
    for fname in files:
        path = os.path.join(abs_input, fname) 
        if fname.lower().endswith('.pdf'):
            total = len(PdfReader(path).pages)
            for i in range(total):
                # ── New: print extraction header like in your past code
                print("=" * 400, file=sys.stderr)
                text = extract_text(path, i)
                #print(f"📄 {fname} p{i+1} → {text or '[NO TEXT]'}", file=sys.stderr)

                print("=" * 400, file=sys.stderr)

                # Multi-method extraction
                extracts = {}
                try: extracts['PDFMiner'] = pdfminer_extract(path, page_numbers=[i], laparams=PDFMINER_LA_PARAMS) or ""
                except: extracts['PDFMiner'] = ""
                try: extracts['PyPDF2'] = PdfReader(path).pages[i].extract_text() or ""
                except: extracts['PyPDF2'] = ""
                try:
                    img = convert_from_path(path, first_page=i+1, last_page=i+1, poppler_path=POPPLER_PATH or None)[0]
                    extracts['Tesseract'] = pytesseract.image_to_string(img, config="--psm 6") or ""
                except:
                    extracts['Tesseract'] = ""
                extracts['FullPDF'] = extract_text_from_pdf(path)
                try:
                    with pdfplumber.open(path) as pdf:
                        extracts['pdfplumber'] = pdf.pages[i].extract_text() or ""
                except:
                    extracts['pdfplumber'] = ""
                try:
                    doc = fitz.open(path)
                    extracts['PyMuPDF'] = doc.load_page(i).get_text()
                    doc.close()
                except:
                    extracts['PyMuPDF'] = ""
                    
              

                # Collect W-2 employer names across methods
                info_by_method, names = {}, []
                for method, txt in extracts.items():
                    cat, ft = classify_text(txt)
                    if cat == 'Income' and ft == 'W-2':
                        info = parse_w2(txt)
                        if info['employer_name'] != 'N/A':
                            info_by_method[method] = info
                            names.append(info['employer_name'])
                    # --- 1099-INT bookmark extraction ---
                    if cat == 'Income' and ft == '1099-INT':
                        title = extract_1099int_bookmark(txt)
                        if title and title != '1099-INT':
                            int_titles[(path, i)] = title
                    # <<< new DIV logic
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
                    chosen = next(m for m,i in info_by_method.items() if i['employer_name'] == common)
                    print(f"--- Chosen employer ({chosen}): {common} ---", file=sys.stderr)
                    print_w2_summary(info_by_method[chosen])
                    w2_titles[(path, i)] = common

                # Classification & grouping
                    # … after you’ve extracted text …
                tiered = extract_text(path, i)
                cat, ft = classify_text(tiered)
                
                # NEW: log every classification
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

    # Sort
    income.sort(key=lambda e:(get_form_priority(e[2],'Income'), e[0], e[1]))
    expenses.sort(key=lambda e:(get_form_priority(e[2],'Expenses'), e[0], e[1]))
    # merge & bookmarks
    merger = PdfMerger()
    page_num = 0
    stop_after_na = False
    def append_and_bookmark(entry, parent, title):
        nonlocal page_num
        p, idx, _ = entry
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            w = PdfWriter()
            try:
                w.add_page(PdfReader(p).pages[idx])
                w.write(tmp)
                tmp.flush()
                os.fsync(tmp.fileno())
            except Exception:
                print(f"Temp write failed: {p} p{idx+1}", file=sys.stderr)
                traceback.print_exc()
                print(f"⚠️  Temp write failed for {p!r} (page {idx+1}); skipping.", file=sys.stderr)
                traceback.print_exc()
                return 
            tmp_path = tmp.name
        with open(tmp_path,'rb') as fh:
            merger.append(fileobj=fh)
        os.unlink(tmp_path)
        merger.add_outline_item(title, page_num, parent=parent)
        page_num += 1


    # ── Bookmarks
    if income and not stop_after_na:
        root = merger.add_outline_item('Income', page_num)
        for form, grp in group_by_type(income).items():
            if stop_after_na:
                break
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, entry in enumerate(grp, 1):
                path, idx, _ = entry
                # build the label
                lbl = form if len(grp) == 1 else f"{form}#{j}"
                if form == 'W-2':
                    emp = w2_titles.get((path, idx))
                    if emp:
                        lbl = emp
                elif form == '1099-INT':
                    payer = int_titles.get((path, idx))
                    if payer:
                        lbl = payer
                elif form == '1099-DIV':                  # <<< new
                    payer = div_titles.get((path, idx))
                    if payer:
                        lbl = payer
                # NEW: strip ", N.A" and stop after this bookmark
                if ", N.A" in lbl:
                    lbl = lbl.replace(", N.A", "")
                    print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Income', Form='{form}', Title='{lbl}'", file=sys.stderr)
                    append_and_bookmark(entry, node, lbl)
                    stop_after_na = True
                    break

                # normal case
                print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Income', Form='{form}', Title='{lbl}'", file=sys.stderr)
                append_and_bookmark(entry, node, lbl)
            if stop_after_na:
                break

    if expenses and not stop_after_na:
        root = merger.add_outline_item('Expenses', page_num)
        for form, grp in group_by_type(expenses).items():
            if stop_after_na:
                break
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, entry in enumerate(grp, 1):
                path, idx, _ = entry
                lbl = form if len(grp) == 1 else f"{form}#{j}"
                if form == '1098-Mortgage':
                    m = mort_titles.get((path, idx))
                    if m:
                      lbl = m

                # NEW: strip ", N.A" and stop
                if ", N.A" in lbl:
                    lbl = lbl.replace(", N.A", "")
                    print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Expenses', Form='{form}', Title='{lbl}'", file=sys.stderr)
                    append_and_bookmark(entry, node, lbl)
                    stop_after_na = True
                    break

                # normal case
                print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Expenses', Form='{form}', Title='{lbl}'", file=sys.stderr)
                append_and_bookmark(entry, node, lbl)
            if stop_after_na:
                break

    # Others        
    if others:
        root = merger.add_outline_item('Others', page_num)
        node = merger.add_outline_item('Unused', page_num, parent=root)
        for j, entry in enumerate(others,1):
            path, idx, _ = entry
            lbl = 'Unused' if len(others)==1 else f"Unused#{j}"
            

        # NEW:
            print(
                f"[Bookmark] {os.path.basename(path)} p{idx+1} → "
                f"Category='Others', Form='Unused', Title='{lbl}'",
                file=sys.stderr
            )

            append_and_bookmark(entry, node, lbl)


    # Write merged output
    os.makedirs(os.path.dirname(abs_output), exist_ok=True)
    with open(abs_output,'wb') as f:
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
if __name__=='__main__':
    import argparse
    p = argparse.ArgumentParser(description="Merge PDFs with robust text extraction and cleanup")
    p.add_argument('input_dir', help="Folder containing PDFs to merge")
    p.add_argument('output_pdf', help="Path for the merged PDF (outside input_dir)")
    args = p.parse_args()
    merge_with_bookmarks(args.input_dir, args.output_pdf)
