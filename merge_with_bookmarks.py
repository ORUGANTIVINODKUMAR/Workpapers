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
from PyPDF2 import PdfReader, PdfMerger

import pytesseract
#rom pdf2image import convert_from_path
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
#OPPLER_PATH = os.environ.get("POPPLER_PATH")  # e.g. "C:\\poppler\\Library\\bin"
OCR_MIN_CHARS = 50
PDFMINER_LA_PARAMS = LAParams(line_margin=0.2, char_margin=2.0)

# ── Priority tables
income_priorities = {
    'W-2': 1,
    'Consolidated-1099': 2,        # << add this line
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
    '1099-SA': 17
}
expense_priorities = {'1098-Mortgage':1,'1095-A':2,'1095-B':3,'1095-C':4,'5498-SA':5,'1098-T':6,'Property Tax':7,'1098-Other':8}

def get_form_priority(ftype: str, category: str) -> int:
    table = income_priorities if category=='Income' else (expense_priorities if category=='Expenses' else {})
    return table.get(ftype, max(table.values())+1 if table else 9999)

# ── Logging helper
def log_extraction(src: str, method: str, text: str):
    snippet = text[:2000].replace('\n',' ') + ('...' if len(text)>2000 else '')
    logger.info(f"[{method}] {os.path.basename(src)} → '{snippet}'")

# to extract text from image

import io
import fitz  # PyMuPDF
from PIL import Image, ImageOps, ImageEnhance, ImageFilter

def pdf_page_to_image(path: str, page_index: int, dpi: int = 400) -> Image.Image:
    """
    Convert a PDF page to a preprocessed PIL image optimized for OCR.
    Steps (no OpenCV):
      - High DPI render
      - Convert to grayscale
      - Auto-contrast & brightness boost
      - Sharpen twice
      - Adaptive dual-thresholding (light & dark)
      - Rescale small text images
    """
    doc = fitz.open(path)
    page = doc.load_page(page_index)

    # Render with high DPI
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    doc.close()

    # Base grayscale image
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")

    # Normalize brightness & contrast
    img = ImageOps.autocontrast(img)
    img = ImageEnhance.Brightness(img).enhance(1.2)   # brighten slightly
    img = ImageEnhance.Contrast(img).enhance(1.5)     # increase contrast

    # Double sharpen
    img = img.filter(ImageFilter.SHARPEN)
    img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))

    # Rescale if image is small (OCR likes ~3000px width for full page)
    w, h = img.size
    if w < 2000:
        scale = 2000 / w
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    # Try two threshold passes: light and dark
    def threshold(im, cutoff):
        return im.point(lambda x: 0 if x < cutoff else 255, "1")

    light = threshold(img, 160)
    dark = threshold(img, 200)

    # Heuristic: choose the version with more black pixels (more likely text-heavy)
    black_ratio_light = sum(light.getdata()) / (255 * light.size[0] * light.size[1])
    black_ratio_dark = sum(dark.getdata()) / (255 * dark.size[0] * dark.size[1])

    img_final = light if black_ratio_light < black_ratio_dark else dark

    return img_final

def extract_text(path: str, page_index: int) -> str:
    text = ""
    # OCR fallback
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
        # 🔹 Use only 300 DPI for sharper OCR
            dpi = 300
            img = pdf_page_to_image(path, page_index, dpi=dpi)

        # 🔹 Preprocess: convert to grayscale + threshold (binarization)
            gray = img.convert("L")
            bw = gray.point(lambda x: 0 if x < 180 else 255, '1')  # simple binarization

        # 🔹 OCR with stronger settings
            t_ocr = pytesseract.image_to_string(
                bw,
                lang="eng",
                config="--oem 3 --psm 6"   # OEM 3 = default LSTM, PSM 6 = block of text
            ) or ""

            print(f"[OCR dpi={dpi}]\n{t_ocr}", file=sys.stderr)

            if len(t_ocr.strip()) > len(text):
                text = t_ocr

        except Exception:
            traceback.print_exc()


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


def is_unused_page(text: str) -> bool:
    """
    Detect pages that are just year-end messages, instructions,
    or generic investment details (not real 1099 forms).
    """
    import re
    lower = text.lower()
    # normalize multiple spaces to single
    norm = re.sub(r"\s+", " ", lower)

    investment_details = re.search(r"\b\d{4}\s+investment details", norm)

    return (
        "understanding your form 1099" in norm
              
        or "year-end messages" in norm
        or "important: if your etrade account transitioned" in norm
        or "please visit etrade.com/tax" in norm
        or "tax forms for robinhood markets" in norm
        or "robinhood retirements accounts" in norm
        or "new for 2023 tax year" in norm
        or "new for 2024 tax year" in norm
        or "new for 2025 tax year" in norm
        or "that are necessary for tax" in norm
        or "please note there may be a slight timing" in norm
        or "account statement will not have included" in norm
        #1099-SA
        or "fees and interest earnings are not considered" in norm
        or "an hsa distribution" in norm
        or "death is includible in the account" in norm
        or "the account as of the date of death" in norm
        or "amount on the account holder" in norm
        #1099-Mortgage
        or "for clients with paid mortgage insurance" in norm
        or "you can also contact the" in norm
        #or "" in norm
       
        or "may be requested by the mortgagor" in norm
       
        or "you should contact a competent" in norm
        or "tax lot closed on a first in" in norm
        or "your form 1099 composite may include the following internal revenue service " in norm
        or "schwab provides your form 1099 tax information as early" in norm
        or "if you have any questions or need additional information about your" in norm
        or "schwab is not providing cost basis" in norm
        or "the amount displayed in this column has been adjusted for option premiums" in norm
        or "you may select a different cost basis method for your brokerage" in norm
        or "to view and change your default cost basis" in norm
        or "this information is not intended to be a substitue for specific individualized" in norm
        or "shares will be gifted based on your default cost basis" in norm
        or "if you sell shares at a loss and buy additional shares" in norm
        or "we are required to send you a corrected from with the revisions clearly marked" in norm
        or "referenced to indicate individual items that make up the totals appearing" in norm
        or "issuers of the securities in your account reallocated certain income distribution" in norm
        or "the amount shown may be dividends a corporation paid directly" in norm
        or "if this form includes amounts belonging to another person" in norm
        or "spouse is not required to file a nominee return to show" in norm
        or "character when passed through or distributed to its direct or in" in norm
        or "brokers and barter exchanges must report proceeds from" in norm
        or "first in first out basis" in norm
        or "see the instructions for your schedule d" in norm
        or "other property received in a reportable change in control or capital" in norm
        or "enclosed is your" in norm and "consolidated tax statement" in norm
        or "filing your taxes" in norm and "turbotax" in norm
        or ("details of" in norm and "investment activity" in norm)
        or bool(investment_details)
    )


def extract_account_number(text: str) -> str:
    """
    Extract and normalize the account number or ORIGINAL number from page text.
    - Handles 'Account Number: ####' format
    - Handles 'ORIGINAL: ####' format
    Returns None if nothing found.
    """
    #Account Number
    #2360-9180
    match = re.search(r"Account\s*Number[:\s]*([\d\-]+)", text, re.IGNORECASE)
    if match:
        return match.group(1).replace(" ", "").strip()
    # First try to capture "Account Number:"
    match = re.search(r"Account Number:\s*([\d\s]+)", text, re.IGNORECASE)
    if match:
        return match.group(1).replace(" ", "").strip()

    # If not found, try to capture "ORIGINAL:"
    match = re.search(r"ORIGINAL:\s*([\d\s]+)", text, re.IGNORECASE)
    if match:
        return match.group(1).replace(" ", "").strip()
   
    #Account 697296887
    match = re.search(r"Account\s+(\d+)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
   

    return None


# consolidated-1099 forms bookmark
def has_nonzero_misc(text: str) -> bool:
    patterns = [
        r"1\.RENTS\s*\$([0-9,]+\.\d{2})",
        r"2\.ROYALTIES\s*\$([0-9,]+\.\d{2})",
        r"3\.OTHER INCOME\s*\$([0-9,]+\.\d{2})",
        r"4\.FEDERAL INCOME TAX WITHHELD\s*\$([0-9,]+\.\d{2})",
        r"8\.SUBSTITUTE PAYMENTS.*\$\s*([0-9,]+\.\d{2})",
    ]
    return _check_nonzero(patterns, text)
def has_nonzero_oid(text: str) -> bool:
    patterns = [
        r"1\.ORIGINAL ISSUE DISCOUNT.*\$\s*([0-9,]+\.\d{2})",
        r"2\.OTHER PERIODIC INTEREST.*\$\s*([0-9,]+\.\d{2})",
        r"4\.FEDERAL INCOME TAX WITHHELD.*\$\s*([0-9,]+\.\d{2})",
        r"5\.MARKET DISCOUNT.*\$\s*([0-9,]+\.\d{2})",
        r"6\.ACQUISITION PREMIUM.*\$\s*([0-9,]+\.\d{2})",
        r"8\.OID ON.*\$\s*([0-9,]+\.\d{2})",
        r"9\.INVESTMENT EXPENSES.*\$\s*([0-9,]+\.\d{2})",
        r"10\.BOND PREMIUM.*\$\s*([0-9,]+\.\d{2})",
        r"11\.TAX-EXEMPT OID.*\$\s*([0-9,]+\.\d{2})",
    ]
    return _check_nonzero(patterns, text)
def has_nonzero_b(text: str) -> bool:
    """
    Detects if a 1099-B form is present.
    Returns True if there are nonzero dollar values OR if structural
    summary keywords (SHORT-TERM, LONG-TERM, UNKNOWN TERM with FORM 8949)
    are present.
    """
    # 1. Numeric value checks
    patterns = [
        r"1d\.PROCEEDS.*\$\s*([0-9,]+\.\d{2})",
        r"COVERED SECURITIES.*\$\s*([0-9,]+\.\d{2})",
        r"NONCOVERED SECURITIES.*\$\s*([0-9,]+\.\d{2})",
        r"1e\.COST OR OTHER BASIS.*\$\s*([0-9,]+\.\d{2})",
        r"1f\.ACCRUED MARKET DISCOUNT.*\$\s*([0-9,]+\.\d{2})",
        r"1g\.WASH SALE LOSS DISALLOWED.*\$\s*([0-9,]+\.\d{2})",
        r"4\.FEDERAL INCOME TAX WITHHELD.*\$\s*([0-9,]+\.\d{2})",
    ]
    if _check_nonzero(patterns, text):
        return True

    lower = text.lower()

    # 2. Structural fallback (existing)
    if (
        "short-term gains or (losses)" in lower
        or "long-term gains or (losses)" in lower
        or "unknown term" in lower
    ) and "form 8949" in lower:
        return True

    # 3. ✅ NEW: catch summary table headers even if all values are 0
    if any(kw in lower for kw in [
        "short a", "short b", "short c",
        "long d", "long e", "long f",
        "total short-term", "total long-term", "total undetermined"
    ]):
        return True

    return False


def has_nonzero_div(text: str) -> bool:
    """
    Detects if a 1099-DIV form has any nonzero amounts.
    Works for both UPPERCASE and lowercase extractions, with or without spaces.
    """
    patterns = [
        r"1a\s*\.?\s*.*ordinary dividends.*?\$\s*([0-9,]+\.\d{2})",
        r"1b\s*\.?\s*.*qualified dividends.*?\$\s*([0-9,]+\.\d{2})",
        r"2a\s*\.?\s*.*capital gain.*?\$\s*([0-9,]+\.\d{2})",
        r"2b\s*\.?\s*.*1250 gain.*?\$\s*([0-9,]+\.\d{2})",
        r"2c\s*\.?\s*.*1202 gain.*?\$\s*([0-9,]+\.\d{2})",
        r"2d\s*\.?\s*.*collectibles.*?\$\s*([0-9,]+\.\d{2})",
        r"2e\s*\.?\s*.*897 ordinary dividends.*?\$\s*([0-9,]+\.\d{2})",
        r"2f\s*\.?\s*.*897 capital.*?\$\s*([0-9,]+\.\d{2})",
        r"3\s*\.?\s*.*non[- ]?dividend.*?\$\s*([0-9,]+\.\d{2})",
        r"4\s*\.?\s*.*federal income tax withheld.*?\$\s*([0-9,]+\.\d{2})",
        r"5\s*\.?\s*.*199a dividends.*?\$\s*([0-9,]+\.\d{2})",
        r"6\s*\.?\s*.*investment expenses.*?\$\s*([0-9,]+\.\d{2})",
        r"7\s*\.?\s*.*foreign tax paid.*?\$\s*([0-9,]+\.\d{2})",
        r"9\s*\.?\s*.*cash liquidation.*?\$\s*([0-9,]+\.\d{2})",
        r"10\s*\.?\s*.*non[- ]?cash liquidation.*?\$\s*([0-9,]+\.\d{2})",
        r"12\s*\.?\s*.*exempt[- ]?interest dividends.*?\$\s*([0-9,]+\.\d{2})",
        r"13\s*\.?\s*.*specified private activity.*?\$\s*([0-9,]+\.\d{2})",
    ]

    return _check_nonzero(patterns, text)

def has_nonzero_int(text: str) -> bool:
    patterns = [
        r"1[\.\-,)]?\s*INTEREST\s+INCOME.*\$\s*([0-9,]+\.\d{2})",
        r"2[\.\-,)]?\s*EARLY\s+WITHDRAWAL\s+PENALTY.*\$\s*([0-9,]+\.\d{2})",
        r"3[\.\-,)]?\s*INTEREST\s+ON\s+U\.?S\.?\s+SAVINGS.*\$\s*([0-9,]+\.\d{2})",
        r"4[\.\-,)]?\s*FEDERAL\s+INCOME\s+TAX\s+WITHHELD.*\$\s*([0-9,]+\.\d{2})",
        r"5[\.\-,)]?\s*INVESTMENT\s+EXPENSES.*\$\s*([0-9,]+\.\d{2})",
        r"6[\.\-,)]?\s*FOREIGN\s+TAX\s+PAID.*\$\s*([0-9,]+\.\d{2})",
        r"8[\.\-,)]?\s*TAX[-\s]*EXEMPT\s+INTEREST.*\$\s*([0-9,]+\.\d{2})",
        r"9[\.\-,)]?\s*SPECIFIED\s+PRIVATE\s+ACTIVITY.*\$\s*([0-9,]+\.\d{2})",
        r"10[\.\-,)]?\s*MARKET\s+DISCOUNT.*\$\s*([0-9,]+\.\d{2})",
        r"(?:11|41|iS)[\.\-,)]?\s*BOND\s+PREMIUM.*\$\s*([0-9,]+\.\d{2})",   # OCR confusion: 11 ↔ 41 ↔ iS
        r"12[\.\-,)]?\s*BOND\s+PREMIUM\s+ON\s+TREASURY.*\$\s*([0-9,]+\.\d{2})",
        r"13[\.\-,)]?\s*BOND\s+PREMIUM\s+ON\s+TAX[-\s]*EXEMPT.*\$\s*([0-9,]+\.\d{2})",
    ]

    return _check_nonzero(patterns, text)
def _check_nonzero(patterns, text: str) -> bool:
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE | re.DOTALL)
        if m:
            try:
                val = float(m.group(1).replace(",", "").replace("$", "").strip())
                if val != 0.0:
                    return True
            except:
                continue
    return False
# --- Post-processing cleanup for bookmarks ---
def filter_bookmarks(bookmarks: list[str]) -> list[str]:
    """
    If both '1099-B' and 'ST-A/B/C OR LT-D/E/F' appear,
    keep only 'ST-A/B/C OR LT-D/E/F'.
    """
    if "1099-B" in bookmarks and any(
        b for b in bookmarks if "ST-" in b or "LT-" in b
    ):
        return [b for b in bookmarks if b != "1099-B"]
    return bookmarks
def classify_text_multi(text: str) -> list[str]:
    """Return a list of form names detected in the page text."""
    lower = text.lower()
    matches = []

    has_int = ("1099-int" in lower or "form 1099-int" in lower) and has_nonzero_int(text)
    has_div = ("total ordinary dividends" in lower or "qualified dividends" in lower) and has_nonzero_div(text)

    # Other forms
    if "1099-b" in lower or "form 1099-b" in lower or has_nonzero_b(text):                                        
        if has_nonzero_b(text):
            matches.append("1099-B")

    if "1099-misc" in lower or "form 1099-misc" in lower:
        if has_nonzero_misc(text):
            matches.append("1099-MISC")

    if "1099-oid" in lower or "form 1099-oid" in lower:
        if has_nonzero_oid(text):
            matches.append("1099-OID")

    # ✅ NEW: Form 8949 Box conditions (ST/LT with A–F)
    box_map = {
        "box a checked": "ST-A",
        "box b checked": "ST-B",
        "box c checked": "ST-C",
        "box d checked": "LT-D",
        "box e checked": "LT-E",
        "box f checked": "LT-F",
    }
   
    for key, label in box_map.items():
        if key in lower:
            matches.append(label)

    # Combined condition for INT + DIV
    if has_int and has_div:
        cond1 = ("total federal income tax withheld" in lower
                 and "total interest income 1099-int box 1" in lower)
        cond2 = ("total qualified dividends" in lower
                 and "interest income" in lower)

        if cond1 or cond2:
            matches.append("1099-INT & DIV Description")
        elif cond1:
            matches.append("1099-DIV Description")
        elif cond2:
            matches.append("1099-INT Description")
        else:
            matches.append("1099-INT")
            matches.append("1099-DIV")
    else:
        if has_int:
            matches.append("1099-INT")
        if has_div:
            matches.append("1099-DIV")

    return matches

# --- Classification Helper

def classify_text(text: str) -> Tuple[str, str]:
    normalized = re.sub(r'\s+', '', text.lower())
    t = text.lower()
    lower = text.lower()
   
    if "#bwnjgwm" in normalized:
        return "Others", "Unused"
    sa_front_patterns = [
        r"earnings\s+on\s+excess\s+cont",   # will also match 'cont.'
        r"form\s+1099-?sa",                 # matches '1099-SA' or '1099SA'
        r"fmv\s+on\s+date\s+of\s+death",
    ]

    found_sa_front = any(re.search(pat, lower) for pat in sa_front_patterns)

    # 🔁 Priority: 1099-SA > Unused
    if found_sa_front:
        return "Income", "1099-SA"

    if is_unused_page(text):
        return "Unknown", "Unused"
   
    # 1) Detect W-2 pages by key header phrases
    if (
        "wages, tips, other compensation" in lower or
        ("employer's name" in lower and "address" in lower)
    ):
        return "Income", "W-2"

    #5498-SA
    sa5498_front_patterns = [
       r"2\s+total\s+contributions\s+made\s+in\s+\d{4}",
        r"3\s+total\s+hsa\s+or\s+archer\s+msa\s+contributions\s+made\s+in\s+\d{4}\s+for\s+\d{4}",
        r"4\s+rollover\s+contributions",
        r"5\s+fair\s+market\s+value\s+of\s+hsa"
    ]


    found_sa5498_front = any(re.search(pat, lower) for pat in sa5498_front_patterns)

    # 🔁 Priority: 5498-SA > Unused
    if found_sa5498_front:
        return "Expenses", "5498-SA"

   
   
   
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
        if pat in lower:
            return "Income", "1099-DIV"  
    # --- 1099-MISC ---
    misc_category = [
        "form 1099-misc",
        "miscellaneous information",
        "1.rents",
        "2.royalties",
        "3.other income",
        "8.substitute payments in lieu of dividends or interest"
    ]
    for pat in misc_category:
        if pat in lower:
            return "Income", "1099-MISC"

    # --- 1099-OID ---
    oid_category = [
        "form 1099-oid",
        "original issue discount",
        "1.original issue discount",
        "2.other periodic interest",
        "5.market discount",
        "6.acquisition premium",
        "8.oid on u.s. treasury obligations",
        "10.bond premium",
        "11.tax-exempt oid"
    ]
    for pat in oid_category:
        if pat in lower:
            return "Income", "1099-OID"

    # --- 1099-B ---
    b_category = [
        "form 1099-b",
        "proceeds from broker and barter exchange transactions",
        "1d.proceeds",
        "covered securities",
        "noncovered securities",
        "1e.cost or other basis of covered securities",
        "1f.accrued market discount",
        "1g.wash sale loss disallowed"
    ]
    for pat in b_category:
        if pat in lower:
            return "Income", "1099-B"

    #---------------------------Consolidated-1099----------------------------------#
   
     # E*TRADE text in parts
   
   

    con_unused = [
        "etrade from morgan stanley 1099 consolidated tax statement for 2023 provides your official tax information",
        "income information that was reported on your december account statement will not have included certain adjustments",
        "if your etrade account was transferred to morgan stanley smith barney llc in 2023 you may receive a separate 1099 consolidated tax statement",
        "consider and review both consolidated tax statements when preparing your 2023 income tax return",
        "for more information on what to expect, visit etrade.com/taxyear2023",
        "the following tax documents are not included in this statement and are sent individually",
        "forms 1099-q, 1042-s, 2439, 5498, 5498-esa, remic information statement, schedule k-1 and puerto rico forms 480.6a, 480.6b, 480.6c and 480.6d"
    ]
   
    for pat in con_unused:
        if pat in lower:
            return "Others", "Unused"  
    #---------------------------Consolidated-1099----------------------------------#

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
        "Box 10. For a taxable or tax-exempt covered security",
        "if you are registered in the account",
        "subject to reporting when paid regardless",
        "if we are required to withhold tax"
    ]
    lower = text.lower()
    found_int_front = any(pat.lower() in lower for pat in int_front)
    found_int_unused = any(pat.lower() in lower for pat in int_unused)

# 🔁 Priority: 1099-INT > Unused
    if found_int_front:
        return "Income", "1099-INT"
    elif found_int_unused:
        return "Others", "Unused"
    #---------------------------1099-SA----------------------------------#
    #1099-INT for page 1

   
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

import re
from typing import Dict, List
from difflib import SequenceMatcher

def normalize_entity_name(raw: str) -> str:
    if not raw:
        return "N/A"
    raw = re.split(
        r"\b(employer|employee|ein|ssn|address|social security|withheld)\b",
        raw,
        flags=re.IGNORECASE
    )[0].strip()
    BAD_PREFIXES = (
        "employee", "wages", "social security", "medicare",
        "withheld", "tax", "omb", "form w-2", "department", "irs",
        "c employer", "© employer", "¢ employer", "= employer"
    )
    INLINE_JUNK = ["less:", "gross pay", "deductions", "earnings", "withheld", "retirement"]
    JUNK_SUFFIXES = ["TAX WITHHELD", "WITHHELD", "COPY", "VOID", "DUPLICATE"]

    stripped = raw.strip()

    # 🚫 skip if it's a header/junk line
    if any(stripped.lower().startswith(b) for b in BAD_PREFIXES):
        return "N/A"

    # Remove inline junk
    for jt in INLINE_JUNK:
        idx = stripped.lower().find(jt)
        if idx != -1:
            stripped = stripped[:idx].strip()
            break

    # Remove SSN/EIN patterns
    stripped = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '', stripped)  # SSN
    stripped = re.sub(r'\b\d{2}-\d{7}\b', '', stripped)        # EIN
    stripped = stripped.strip()

    # Collapse whole-line duplicates
    whole_dup = re.match(r'^(?P<seq>.+?)\s+(?P=seq)(?:\s+(?P=seq))*$', stripped, flags=re.IGNORECASE)
    if whole_dup:
        stripped = whole_dup.group('seq')

    # Collapse repeated adjacent words
    collapsed = re.sub(r'\b(.+?)\b(?:\s+\1\b)+', r'\1', stripped, flags=re.IGNORECASE)

    # Remove trailing numbers
    collapsed = re.sub(r'(?:\s+\d+(?:[\.,]\d+)?)+\s*$', '', collapsed)

    # Remove trailing junk suffixes
    words = collapsed.split()
    cleaned = True
    while cleaned and words:
        cleaned = False
        for junk in JUNK_SUFFIXES:
            parts = junk.split()
            if len(words) >= len(parts) and [w.upper() for w in words[-len(parts):]] == [p.upper() for p in parts]:
                words = words[:-len(parts)]
                cleaned = True
                break
    collapsed = " ".join(words)

    # Remove duplicated trailing employer names (fuzzy match)
    parts = collapsed.split()
    for cut in range(1, len(parts)):
        left = " ".join(parts[:cut])
        right = " ".join(parts[cut:])
        if right:
            ratio = SequenceMatcher(None, left.lower(), right.lower()).ratio()
            if ratio > 0.75:
                collapsed = left
                break

    # Drop stray numeric tokens at the end
    collapsed = re.sub(r'(\s+\d[\d\-\.,]*)+$', '', collapsed).strip()

    return ' '.join(collapsed.split()).strip() or "N/A"


def next_valid_line(lines: List[str], start: int) -> str:
    """Return the next non-empty, non-header line after `start` index."""
    j = start
    while j < len(lines):
        cand = lines[j].strip()
        if cand and not ("employer" in cand.lower() and "address" in cand.lower() and "zip" in cand.lower()):
            return cand
        j += 1
    return ""
def is_name_like(s: str) -> bool:
    """Return True if s looks like a company name, not just numbers or junk."""
    if not s:
        return False
    # Must contain at least 2 alphabetic characters
    if sum(c.isalpha() for c in s) < 2:
        return False
    # Reject if it's only numbers, EIN, SSN, or amounts
    if re.fullmatch(r"[\d\-\.,]+", s):
        return False
    return True

def next_valid_line(lines, start_index, junk_phrases=None):
    if junk_phrases is None:
        junk_phrases = [
            "omb no",
            "control number",
            "payrol",
            "allocated tips",
            "social security wages",
            "social security tax withheld",
        ]

    j = start_index
    while j < len(lines):
        raw = lines[j].strip()
        if raw and not any(p in raw.lower() for p in junk_phrases):
            if is_name_like(raw):  # ⬅ ensure it looks like a name
                return raw
        j += 1
    return None




def parse_w2(text: str) -> Dict[str, str]:
    # SSN & EIN
    ssn_m = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", text)
    ssn = ssn_m.group(1) if ssn_m else "N/A"
    ein_m = re.search(r"\b(\d{2}-\d{7})\b", text)
    ein = ein_m.group(1) if ein_m else "N/A"

    lines = text.splitlines()
    emp_name = emp_addr = "N/A"
    bookmark = None
    full_lower = text.lower()
   
    # 🚨 Hard-coded override for Salesforce
    if re.search(r"\bSALESFORCE[, ]+INC\.?\b", text, flags=re.IGNORECASE):
        emp_name = "SALESFORCE, INC"
        return {
            'ssn': ssn,
            'ein': ein,
            'employer_name': emp_name,
            'employer_address': emp_addr,
            'employee_name': 'N/A',
            'employee_address': 'N/A',
            'bookmark': emp_name
        }

    # 🔹 1) FCA US LLC override
    if any(v in full_lower for v in ("fca us llc", "fca us, llc", "fcaus llc")):
        emp_name = "FCA US LLC"
        return {
            'ssn': ssn, 'ein': ein,
            'employer_name': emp_name,
            'employer_address': emp_addr,
            'employee_name': 'N/A',
            'employee_address': 'N/A',
            'bookmark': emp_name
        }
        # 🔹 2) GEORGIA INSTITUTE TECHNOLOGY override
    if "georgia institute technology" in full_lower or "georgia institute of technology" in full_lower:
        emp_name = "GEORGIA INSTITUTE TECHNOLOGY"
        return {
            'ssn': ssn, 'ein': ein,
            'employer_name': emp_name,
            'employer_address': emp_addr,
            'employee_name': 'N/A',
            'employee_address': 'N/A',
            'bookmark': emp_name
        }
    # 🔹 3) Standard W-2 parsing
    for i, line in enumerate(lines):
        if "allocated tips" in line.lower() and "social security" in line.lower():
            raw = next_valid_line(lines, i + 1)
            if raw:
                emp_name = normalize_entity_name(raw)
                bookmark = emp_name
            emp_addr = next_valid_line(lines, i + 2)
            break
    #DOTCOM TEAM LLC B Employer Verification number …
    for i, line in enumerate(lines):
    # Match anything ending with "- PAYROL"
        if re.search(r".+\s*-\s*PAYROL", line, re.IGNORECASE):
            raw = next_valid_line(lines, i + 1)   # ⬅ skip "PAYROL" line and junk
            if raw:
            # If line has "b Employer..." trailing text, strip it out
                raw = re.sub(r"\bb\s*employer.*", "", raw, flags=re.IGNORECASE).strip()

            # Normalize (remove trailing numbers, extra spaces, etc.)
                emp_name = normalize_entity_name(raw)
                bookmark = emp_name
            break

           
    # 🔹 2) Marker block
    marker = (
        "c employer's name, address, and zip code 3 social security wages"
        "c Employer's name, address, and ZIP code "
        "8 Allocated tips 3 Social security wages 4 Social security tax withheld"
       
    ).lower()
    for i, L in enumerate(lines):
        if marker in L.lower():
            raw = next_valid_line(lines, i + 1)
            if raw:
                emp_name = normalize_entity_name(raw)
                bookmark = emp_name
                return {
                    'ssn': ssn, 'ein': ein,
                    'employer_name': emp_name,
                    'employer_address': emp_addr,
                    'employee_name': 'N/A',
                    'employee_address': 'N/A',
                    'bookmark': bookmark
                }

    # 🔹 3) Standard W-2 parsing
    for i, line in enumerate(lines):
        if "employer" in line.lower() and "name" in line.lower():
            raw = next_valid_line(lines, i + 1)
            if raw:
                emp_name = normalize_entity_name(raw)
                bookmark = emp_name
            emp_addr = next_valid_line(lines, i + 2)
            break
    # 🔹 3.1) Standard W-2 parsing
    for i, line in enumerate(lines):
        if "erreroyers" in line.lower() and "name" in line.lower():
            raw = next_valid_line(lines, i + 1)
            if raw:
                emp_name = normalize_entity_name(raw)
                bookmark = emp_name
            emp_addr = next_valid_line(lines, i + 2)
            break

    # 🔹 4) PAYROL fallback
    if emp_name == "N/A":
        for i, line in enumerate(lines):
            if re.search(r".+\s*-\s*PAYROL", line, re.IGNORECASE):
                raw = next_valid_line(lines, i + 1)
                if raw:
                    emp_name = normalize_entity_name(raw)
                    bookmark = emp_name
                break

    # 🔹 5) © / triple marker fallbacks
    triple_markers = [
        "© Employer's name, address, and ZIP code",
        "c Employer's name, address, and ZIP code",
        "¢ Employer's name, address and ZIP code",
        "= EMPLOYER'S name, address, and ZIP code",
        "c Employer's name, address and ZIP code t c Employer's name, address and ZIP code"
    ]
    if emp_name == "N/A":
        for marker in triple_markers:
            if marker.lower() in full_lower:
                for i, line in enumerate(lines):
                    if marker.lower() in line.lower():
                        raw = next_valid_line(lines, i + 1)
                        if raw:
                            emp_name = normalize_entity_name(raw)
                            bookmark = emp_name
                        break

    # 🔹 Final cleanup
    if emp_name != "N/A":
        emp_name = normalize_entity_name(emp_name)
        bookmark = emp_name

    return {
        'ssn': ssn,
        'ein': ein,
        'employer_name': emp_name,
        'employer_address': emp_addr,
        'employee_name': 'N/A',
        'employee_address': 'N/A',
        'bookmark': bookmark or emp_name
    }

   
def print_w2_summary(info: Dict[str, str]):
    print("\n=== W-2 Summary ===\n")
    print(f"Employer: {info['employer_name']}, Address: {info['employer_address']}, EIN: {info['ein']}")
    print("===================\n")

#---------------------------W2----------------------------------#
#---------------------------1099-INT----------------------------------#
import re
from typing import List

def extract_1099int_bookmark(text: str) -> str:
    """
    Extract a clean payer/institution name for Form 1099-INT.
    
    Priority:
    1. Known overrides (US Bank, Capital One, Bank of America, etc.)
    2. First ALL-CAPS / title-cased line after 'foreign postal code, and telephone no.'
    3. Fallback: first line that looks like a bank/credit union name
    4. Default: '1099-INT'
    """

    import re
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    lower_lines = [l.lower() for l in lines]

    # --- Step 1: Overrides for common institutions ---
    overrides = {
        "us bank na": "US Bank NA",
        "u.s. bank na": "US Bank NA",
        "capital one": "Capital One NA",
        "bank of america": "Bank of America",
        "digital federal credit union": "Digital Federal Credit Union",
        "fifth third bank": "FIFTH THIRD BANK, N.A.",   # ✅ new override
        "discover bank": "Discover Bank"
    }
    for key, val in overrides.items():
        if key in text.lower():
            return val

    # --- Step 2: Top-down scan for bank-like names ---
    for cand in lines:
        cand_lower = cand.lower()
        if any(word in cand_lower for word in ["bank", "credit union", "mortgage", "trust", "financial"]):
            # strip trailing garbage like punctuation
            return re.sub(r"[^\w\s.&,'-]+$", "", cand).strip()
        
    # --- Step 3: Look after payer header (if available) ---
    for i, l in enumerate(lower_lines):
        if ("payer" in l and "information" in l) or ("foreign postal code" in l and "telephone" in l):
            for offset in range(1, 4):
                if i + offset >= len(lines):
                    break
                cand = lines[i + offset].strip()
                cand_lower = cand.lower()

                # skip junk
                bad_tokens = ["payer", "recipient", "federal id", "tin",
                              "street", "road", "apt", "zip"]
                if any(bad in cand_lower for bad in bad_tokens):
                    continue
                if re.match(r"^\d+[\s.]", cand):  # skip box lines
                    continue

                if (re.match(r"^[A-Z][A-Z\s&.,'-]{5,}$", cand) and not re.search(r"\d", cand)) \
                   or any(word in cand_lower for word in ["bank", "credit union", "mortgage", "trust", "financial"]):
                    return re.sub(r"[^\w\s.&'-]+$", "", cand).strip()
    # --- Step 4: Global scan again as a last resort ---
    for cand in lines:
        cand_lower = cand.lower()
        bad_tokens = ["payer", "recipient", "federal id", "tin",
                      "street", "road", "apt", "zip"]
        if any(bad in cand_lower for bad in bad_tokens):
            continue
        if re.match(r"^\d+[\s.]", cand):
            continue

        if any(word in cand_lower for word in ["bank", "credit union", "mortgage", "trust", "financial"]):
            return re.sub(r"[^\w\s.&'-]+$", "", cand).strip()


    # --- Step 4: Fallback ---
    return "1099-INT"


#---------------------------1099-INT----------------------------------#
# --- Issuer display aliases ---
ISSUER_ALIASES = {
    "morgan stanley capital management, llc": "E*TRADE",
    # add more mappings here if needed
}

def alias_issuer(name: str) -> str:
    return ISSUER_ALIASES.get(name.lower().strip(), name)

# --------------------------- Consolidated-1099 issuer name --------------------------- #
def extract_consolidated_issuer(text: str) -> str | None:
    """
    Returns a friendly issuer name for consolidated 1099 pages when detectable.
    Currently supports an explicit match for 'Morgan Stanley Capital Management, LLC'
    and a light heuristic fallback near 'Consolidated 1099'/'Composite 1099'.
    """
    lower = text.lower()

    # Explicit ask: Morgan Stanley Capital Management, LLC
    if re.search(r"morgan\s+stanley\s+capital\s+management,\s*llc", lower):
        return "Morgan Stanley Capital Management, LLC"
    # Explicit: Robinhood Markets Inc
    if re.search(r"robinhood\s+markets?\s+inc", lower):
        return "Robinhood Markets Inc"
    if re.search(r"robinhood\s+markets?\s+inc", lower):
        return "Charles Schwab"
    # Heuristic fallback: if the page looks like a consolidated/composite cover,
    # grab the first plausible line that looks like an issuer/legal name.
    if "consolidated 1099" in lower or "composite 1099" in lower:
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            # skip headings / noisy bits
            if re.search(r"(form|1099|copy|page|\baccount\b)", s, re.IGNORECASE):
                continue
            # something that looks like a firm name
            if re.search(r"(LLC|Bank|Securities|Wealth|Brokerage|Advisors?)", s):
                return re.sub(r"[^\w\s,&.\-]+$", "", s)

    return None
# --------------------------- Consolidated-1099 issuer name --------------------------- #
#---------------------------1099-DIV----------------------------------#
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
#---------------------------1099-DIV----------------------------------#

def clean_bookmark(name: str) -> str:
    # Remove any trailing junk starting from 'Interest' and strip whitespace
    cleaned = re.sub(r"\bInterest.*$", "", name, flags=re.IGNORECASE)
    return cleaned.strip()
# 1099-SA

def clean_institution_name(raw: str) -> str:
    """
    Post-process extracted institution name.
    Keeps the full institution name like 'Optum Bank',
    'The Bank of New York Mellon', 'XYZ Trust Company', etc.
    Trims legal suffixes, copyright, FDIC notes, etc.
    """
    import re

    if not raw:
        return "1099-SA"

    text = raw.strip()

    # Remove leading © or copyright notices
    text = re.sub(r"^[©\d\s,.]*", "", text)

    # Capture everything around Bank/Trust/Credit Union until punctuation/legal text
    m = re.search(
        r"\b([A-Z][A-Za-z& ]*?(?:Bank|Trust|Credit Union)[A-Za-z& ]*)",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    # Otherwise, trim after common trailing junk
    text = re.split(
        r"(member fdic|all rights reserved|copyright|©|\d{4,})",
        text,
        flags=re.IGNORECASE,
    )[0].strip(" ,.-")

    return text or "1099-SA"



def normalize_text(s: str) -> str:
    import re
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"\s+", " ", s)  # collapse multiple spaces
    return s.strip().lower()


def is_junk_line(s: str) -> bool:
    """
    Return True if the line looks like IRS instructions or generic text,
    not a payer/institution name.
    """
    import re
    junk_patterns = [
        r"providing the trustee allows the repayment",
        r"you may repay a mistaken distribution",
        r"see the instructions",
        r"report the fmv",
        r"include the earnings",
        r"this information is being furnished",
        r"department of the treasury",
        r"internal revenue service",
        r"form 1099-sa",
        r"instructions for recipient",
        r"omb no",
        r"copy b",
    ]
    for pat in junk_patterns:
        if re.search(pat, s, flags=re.IGNORECASE):
            return True
    return False


def extract_1099sa_bookmark(text: str) -> str:
    """
    Extract the payer/issuer name from 1099-SA text.
    Priority:
      0. Institution glued with 'Form 1099-SA From an HSA'
      1. Inline 'From an HSA, <institution>'
      1.5. First candidate after 'foreign postal code, and telephone'
      2. First candidate after header with address keywords
      3. Any line in whole text containing Bank/Trust/Credit Union/Equity/Corporate
      4. Fallback: 1099-SA
    """
    import re

    lines = text.splitlines()
    lower_lines = [normalize_text(L) for L in lines]

    skip_phrases = (
        "omb no",
        "form 1099-sa",
        "distributions",
        "recipient",
        "payer's tin",
        "recipient's tin",
        "account number",
        "street address",
        "city or town",
        "state or province",
        "zip",
        "telephone",
    )
    # --- Rule -1: Explicit overrides ---
    OVERRIDES = {
        "national financial services llc": "National Financial Services LLC",
        "national financial serves llc": "National Financial Services LLC",  # OCR fallback
    }
    normalized_text = normalize_text(text)
    for key, val in OVERRIDES.items():
        if key in normalized_text:
            return val
    # --- Rule 0: Handle glued "Form 1099-SA From an HSA" ---
    for L in lines:
        if re.search(r"form\s*1099-sa.*from an hsa", L, flags=re.IGNORECASE):
            cand = re.split(r"form\s*1099-sa", L, flags=re.IGNORECASE)[0].strip(" ,|-")
            if cand:
                return clean_institution_name(cand)

    # --- Rule 1: Inline "From an HSA, Optum Bank ..." ---
    for L in lines:
        match = re.search(r"from an hsa.*?(bank|trust|credit union|corporate)[^,]*", L, flags=re.IGNORECASE)
        if match:
            cand = match.group(0)
            cand = re.sub(r"from an hsa[, ]*", "", cand, flags=re.IGNORECASE)
            return clean_institution_name(cand)

    # --- Rule 1.5: Immediately after "foreign postal code, and telephone" ---
    for i, L in enumerate(lower_lines):
        if "foreign postal code, and telephone" in L:
            for offset in range(1, 4):  # look ahead up to 3 lines
                idx = i + offset
                if idx >= len(lines):
                    break
                candidate = lines[idx].strip()
                candidate_lower = normalize_text(candidate)

                if not candidate or len(candidate) <= 3:
                    continue
                if any(skip in candidate_lower for skip in skip_phrases) or is_junk_line(candidate_lower):
                    continue

                candidate = re.split(r"(form\s*1099-sa|from an hsa)", candidate, flags=re.IGNORECASE)[0].strip(" ,|-")
                if candidate:
                    return clean_institution_name(candidate)

    # --- Rule 2: After generic header line with address keywords ---
    for i, L in enumerate(lower_lines):
        if "country" in L and "zip" in L and "telephone" in L:
            candidates = []
            for j in range(i + 1, len(lines)):
                cand = lines[j].strip()
                cand_lower = normalize_text(cand)
                if not cand:
                    continue
                if any(skip in cand_lower for skip in skip_phrases) or is_junk_line(cand_lower):
                    continue
                cand = re.split(r"(form 1099-sa|from an hsa)", cand, flags=re.IGNORECASE)[0].strip(" ,|-")
                if cand:
                    candidates.append(cand)
                if re.search(r"\b(po box|p\.?o\.?|drive|street|road|ave|blvd)\b", cand_lower):
                    break
            for cand in candidates:
                if re.search(r"(bank|trust|credit union|equity|corporate)", cand, flags=re.IGNORECASE):
                    return clean_institution_name(cand)
            if candidates:
                return clean_institution_name(candidates[0])

    # --- Rule 3: Global scan for institution names ---
    for cand in lines:
        cand_norm = normalize_text(cand)
        if re.search(r"(bank|trust|credit union|equity|corporate)", cand_norm):
            if not is_junk_line(cand_norm):
                return clean_institution_name(cand)

    # --- Rule 4: Last-resort fallback ---
    return "1099-SA"




# 1099-SA
#---------------------------1098-Mortgage----------------------------------#
import re
from typing import List

def clean_bookmark(name: str) -> str:
    """Helper to normalize bookmark names."""
    name = name.strip()
    name = re.sub(r"[^\w\s.,&-]+$", "", name)  # strip trailing junk
    return name

def extract_1098mortgage_bookmark(text: str) -> str:
    lines: List[str] = text.splitlines()
    lower_lines = [L.lower() for L in lines]

    # 1) Rocket Mortgage override
    for L in lines:
        if re.search(r"rocket\s+mortgage", L, flags=re.IGNORECASE):
            bookmark = "ROCKET MORTGAGE LLC"
            return finalize_bookmark(bookmark)

    # 2) Dovenmuehle Mortgage override
    for L in lines:
        if re.search(r"dovenmuehle\s+mortgage", L, flags=re.IGNORECASE):
            m = re.search(r"(Dovenmuehle Mortgage, Inc)", L, flags=re.IGNORECASE)
            bookmark = m.group(1) if m else L.strip()
            return finalize_bookmark(bookmark)

    # 3) Huntington National Bank override
    for L in lines:
        if re.search(r"\bhuntington\s+national\s+bank\b", L, flags=re.IGNORECASE):
            m = re.search(r"\b(?:The\s+)?Huntington\s+National\s+Bank\b", L, flags=re.IGNORECASE)
            bookmark = m.group(0) if m else L.strip()
            return finalize_bookmark(bookmark)

    # 4) UNITED NATIONS FCU override
    for L in lines:
        if re.search(r"\bunited\s+nations\s+fcu\b", L, flags=re.IGNORECASE):
            return finalize_bookmark("UNITED NATIONS FCU")

    # 5) LOANDEPOT COM LLC override
    for L in lines:
        if re.search(r"\bloan\s*depot\s*com\s*llc\b", L, flags=re.IGNORECASE):
            m = re.search(r"\bloan\s*depot\s*com\s*llc\b", L, flags=re.IGNORECASE)
            bookmark = m.group(0) if m else L.strip()
            return finalize_bookmark(bookmark)

    # 6) JPMORGAN CHASE BANK, N.A.
    for L in lines:
        if re.search(r"jp\s*morgan\s+chase", L, flags=re.IGNORECASE):
            m = re.search(r"(JPMORGAN CHASE BANK, N\.A\.)", L, flags=re.IGNORECASE)
            bookmark = m.group(1) if m else L.strip()
            return finalize_bookmark(bookmark)

    # 7) "Limits based" override — handles SAME-LINE + NEXT-LINE lender names
    for i, line in enumerate(lines):
        if "limits based on the loan amount" in line.lower():
            if not line.strip().lower().startswith("limits based"):
                cand = re.split(r"limits\s+based", line, maxsplit=1, flags=re.IGNORECASE)[0].strip()
                if cand:
                    return finalize_bookmark(cand)
            for j in range(i + 1, len(lines)):
                candidate = lines[j].strip()
                if not candidate:
                    continue
                candidate = re.sub(r"\bInterest.*$", "", candidate, flags=re.IGNORECASE)
                candidate = re.split(r"\band\b", candidate, maxsplit=1, flags=re.IGNORECASE)[0].strip()
                return finalize_bookmark(candidate)

    # 8) FCU override
    for L in lines:
        if re.search(r"\bfcu\b", L, flags=re.IGNORECASE):
            m = re.search(r"(.*?FCU)\b", L, flags=re.IGNORECASE)
            bookmark = m.group(1) if m else L.strip()
            return finalize_bookmark(bookmark)

    # 9) PAYER(S)/BORROWER(S) override
    for i, header in enumerate(lower_lines):
        if "payer" in header and "borrower" in header:
            for cand in lines[i+1:]:
                s = cand.strip()
                if not s or len(set(s)) == 1 or re.search(r"[\d\$]|page", s, flags=re.IGNORECASE):
                    continue
                raw = re.sub(r"[^\w\s]+$", "", s)
                raw = re.sub(r"(?i)\s+d/b/a\s+.*$", "", raw).strip()
                return finalize_bookmark(raw)

    # 10) RECIPIENT’S/LENDER’S header override
    for i, L in enumerate(lines):
        if re.search(r"recipient.?s\s*/\s*lender.?s", L, flags=re.IGNORECASE):
            for j in range(i+1, len(lines)):
                cand = lines[j].strip()
                if not cand:
                    continue
                return finalize_bookmark(cand)

    # 11) Fallback
    return finalize_bookmark("1098-Mortgage")


def finalize_bookmark(bookmark: str) -> str:
    """Final cleanup of extracted bookmark."""
    bookmark = clean_bookmark(bookmark)

    # Trim if known noise appears inside
    noise_markers = [
        "ang the cost",   # from OCR line you mentioned
        "not be fully deductible",
        "limits based on",
    ]
    for marker in noise_markers:
        if marker.lower() in bookmark.lower():
            bookmark = bookmark.split(marker, 1)[0].strip()

    return bookmark


def group_by_type(entries: List[Tuple[str,int,str]]) -> Dict[str,List[Tuple[str,int,str]]]:
    d=defaultdict(list)
    for e in entries: d[e[2]].append(e)
    return d
#---------------------------1098-Mortgage----------------------------------#

#5498-SA


def clean_bookmark(name: str) -> str:
    """Normalize bookmark string."""
    name = name.strip()
    name = re.sub(r"[^\w\s.&-]", "", name)
    return name

def extract_5498sa_bookmark(text: str) -> str:
    """
    Extract trustee/institution name for Form 5498-SA.
    Works even when the name is glued with address/ZIP.
    """
    import re

    # Normalize spaces a bit
    cleaned = text.replace("\n", " ").replace("  ", " ")

    # --- Primary regex: look for known trustee-like names before address/ZIP ---
    m = re.search(
        r"\b([A-Z][A-Za-z& ]{2,40}?(?:Care|Corporate|Corporation|Bank|Trust|LLC|Inc))",
        cleaned
    )
    if m:
        return m.group(1).strip()

    # --- Backup: search after 'foreign postal code' phrase ---
    lines = text.splitlines()
    lower_lines = [L.lower() for L in lines]
    for i, header in enumerate(lower_lines):
        if "foreign postal code" in header and "telephone" in header:
            for cand in lines[i+1:]:
                s = cand.strip()
                if not s:
                    continue
                # Stop if it's just numbers or contribution text
                if re.search(r"\d{2,}", s) or "contribution" in s.lower():
                    continue
                raw = re.sub(r"[^\w\s]+$", "", s)
                raw = re.split(r"contributions\s+made\s+in\s+\d{4}.*",
                               raw, 1, flags=re.IGNORECASE)[0].strip()
                if raw:
                    return raw

    # --- Fallback ---
    return "5498-SA"

#1098-T
def extract_1098t_bookmark(text: str) -> str:
    """
    Extract institution name for 1098-T forms.

    Rule:
    - Find a line containing BOTH "foreign postal code" and "qualified tuition"
    - Then take the very next non-empty line as the institution name
    - Only accept it if it looks like a real institution (contains University/College/etc.)
    - Otherwise fallback search
    """
    import re
    lines = text.splitlines()
    lower_lines = [l.lower() for l in lines]

    for i, L in enumerate(lower_lines):
        if "foreign postal code" in L and "qualified tuition" in L:
            if i + 1 < len(lines):
                cand = lines[i + 1].strip()
                cand = re.sub(r"\s*expenses.*$", "", cand, flags=re.IGNORECASE)
                cand = re.sub(r"[^\w\s.&-]", "", cand).strip()

                # ✅ Only accept if it's a real institution name
                if re.search(r"(University|College|Institute|Academy)", cand, flags=re.IGNORECASE):
                    return cand

    # Fallback: catch any line with University/College/etc.
    for line in lines:
        if re.search(r"(University|College|Institute|Academy)", line, flags=re.IGNORECASE):
            cand = re.sub(r"\s*expenses.*$", "", line, flags=re.IGNORECASE)
            return cand.strip()

    return "1098-T"

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
def classify_div_int(text: str) -> str | None:
    """
    Classify a page as 1099-DIV or 1099-INT if it matches the required
    header lines. Returns "1099-DIV", "1099-INT", or None.
    """
    lower = text.lower()

    div_match = (
        "1099-div" in lower
        and "dividends & distributions" in lower
        and "ordinary dividends" in lower
        and "description cusippay" in lower
    )
    int_match = (
        "1099-int" in lower
        and "interest income" in lower
        and "description cusippay" in lower
    )

    if div_match:
        return "1099-DIV"
    elif int_match:
        return "1099-INT"
    return None
# ── Merge + bookmarks + cleanup
def merge_with_bookmarks(input_dir: str, output_pdf: str):
    # Prevent storing merged file inside input_dir
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
   
   # remove any zero‐byte files so PdfReader never sees them
    files = []
    for f in all_files:
        p = os.path.join(abs_input, f)
        if os.path.getsize(p) == 0:
           logger.warning(f"Skipping empty file: {f}")
           continue
        files.append(f)
    # 🔄 Convert images into PDFs so the rest of the pipeline sees only PDFs
    converted_files = []
    for f in list(files):
        if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff')):
            path = os.path.join(abs_input, f)
            try:
                img = Image.open(path)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                pdf_path = os.path.splitext(path)[0] + "_conv.pdf"
                img.save(pdf_path, "PDF", resolution=300.0)
                print(f"🖼️ Converted {f} → {os.path.basename(pdf_path)}", file=sys.stderr)

                # replace the image with its new PDF
                files.remove(f)
                files.append(os.path.basename(pdf_path))
                converted_files.append(pdf_path)
            except Exception as e:
                print(f"❌ Failed to convert {f}: {e}", file=sys.stderr)

    logger.info(f"Found {len(files)} files in {abs_input}")

    income, expenses, others = [], [], []
    # what bookmarks we want in workpapaer shoudl be add in this
    w2_titles = {}
    int_titles = {}
    div_titles = {} # <-- Add this line
    sa_titles = {}  
    mort_titles = {}
    sa5498_titles = {}
    t1098_titles = {}
    account_pages = {}  # {account_number: [(path, page_index, 'Consolidated-1099')]}
    account_names = {}
    for fname in files:
        path = os.path.join(abs_input, fname)
        if fname.lower().endswith('.pdf'):
            total = len(PdfReader(path).pages)
            for i in range(total):
                print("=" * 400, file=sys.stderr)
                print(f"Processing: {fname}, Page {i+1}", file=sys.stderr)

                # ── Print header before basic extract_text
                print("→ extract_text() output:", file=sys.stderr)
                try:
                    text = extract_text(path, i)
                    print(text or "[NO TEXT]", file=sys.stderr)
                except Exception as e:
                    print(f"[ERROR] extract_text failed: {e}", file=sys.stderr)

                print("=" * 400, file=sys.stderr)

                # Multi-method extraction
                extracts = {}

                print("→ PDFMiner:", file=sys.stderr)
                try:
                    extracts['PDFMiner'] = pdfminer_extract(path, page_numbers=[i], laparams=PDFMINER_LA_PARAMS) or ""
                    print(extracts['PDFMiner'], file=sys.stderr)
                except Exception as e:
                    extracts['PDFMiner'] = ""
                    print(f"[ERROR] PDFMiner failed: {e}", file=sys.stderr)

               

                print("→ Tesseract OCR:", file=sys.stderr)
                try:
                    img = pdf_page_to_image(path, i, dpi=200)  # ✅ use your PyMuPDF helper
                    extracts['Tesseract'] = pytesseract.image_to_string(img, config="--psm 6") or ""
                    print(extracts['Tesseract'], file=sys.stderr)
                except Exception as e:
                    extracts['Tesseract'] = ""
                    print(f"[ERROR] Tesseract failed: {e}", file=sys.stderr)

                print("→ pdfplumber:", file=sys.stderr)
                try:
                    with pdfplumber.open(path) as pdf:
                        extracts['pdfplumber'] = pdf.pages[i].extract_text() or ""
                        print(extracts['pdfplumber'], file=sys.stderr)
                except Exception as e:
                    extracts['pdfplumber'] = ""
                    print(f"[ERROR] pdfplumber failed: {e}", file=sys.stderr)

                print("→ PyMuPDF (fitz):", file=sys.stderr)
                try:
                    doc = fitz.open(path)
                    extracts['PyMuPDF'] = doc.load_page(i).get_text()
                    doc.close()
                    print(extracts['PyMuPDF'], file=sys.stderr)
                except Exception as e:
                    extracts['PyMuPDF'] = ""
                    print(f"[ERROR] PyMuPDF failed: {e}", file=sys.stderr)

                print("=" * 400, file=sys.stderr)
             

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
                    if cat == 'Income' and ft == '1099-SA':
                        title = extract_1099sa_bookmark(txt)
                        if title and title != '1099-SA':
                            sa_titles[(path, i)] = title

                    if cat == 'Expenses' and ft == '1098-Mortgage':
                        title = extract_1098mortgage_bookmark(txt)
                        if title and title != '1098-Mortgage':
                            mort_titles[(path, i)] = title
                    if cat == 'Expenses' and ft == '1098-T':
                        title = extract_1098t_bookmark(txt)
                        if title and title != '1098-T':
                            t1098_titles[(path, i)] = title
                if names:
                    common = Counter(names).most_common(1)[0][0]
                    chosen = next(m for m,i in info_by_method.items() if i['employer_name'] == common)
                    print(f"--- Chosen employer ({chosen}): {common} ---", file=sys.stderr)
                    print_w2_summary(info_by_method[chosen])
                    w2_titles[(path, i)] = common

                # Classification & grouping
                    # … after you’ve extracted text …
                   # NEW: {acct: "Issuer Name"}

                tiered = extract_text(path, i)
                acct_num = extract_account_number(tiered)
                if acct_num:
                    account_pages.setdefault(acct_num, []).append((path, i, "Consolidated-1099"))
                # NEW: capture issuer name for this account if present
                    issuer = extract_consolidated_issuer(tiered)
                    if issuer:
                        account_names.setdefault(acct_num, issuer)
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

   
    # ---- Consolidated-1099 synthesis (insert this BEFORE income.sort(...)) ----
    consolidated_payload = {}        # key -> list of real page entries
    consolidated_pages = set()       # pages already placed under Consolidated-1099
    # Track pages we already decided are "Unused" so we don't touch them again
    unused_pages: set[tuple[str, int]] = set()


    for acct, pages in account_pages.items():
        if len(pages) <= 1:
            continue  # only group repeated accounts
        key = f"CONSOLIDATED::{acct}"
        consolidated_payload[key] = [(p, i, "Consolidated-1099") for (p, i, _) in pages]
        for (p, i, _) in pages:
            consolidated_pages.add((p, i))
    # add a synthetic income row that will sort using priority of 'Consolidated-1099'
        income.append((key, -1, "Consolidated-1099"))
# --------------------------------------------------------------------------

    # Sort
    income.sort(key=lambda e:(get_form_priority(e[2],'Income'), e[0], e[1]))
    expenses.sort(key=lambda e:(get_form_priority(e[2],'Expenses'), e[0], e[1]))
    # merge & bookmarks
    merger = PdfMerger()
    page_num = 0
    stop_after_na = False
    import mimetypes
    seen_pages = set()
    def append_and_bookmark(entry, parent, title, with_bookmark=True):
        nonlocal page_num, seen_pages
        sig = (entry[0], entry[1])
        if sig in seen_pages:
            print(f"[DUPLICATE] Skipping {os.path.basename(entry[0])} page {entry[1]+1}", file=sys.stderr)
            return
        seen_pages.add(sig)
        p, idx, _ = entry
        mime_type, _ = mimetypes.guess_type(p)

        if mime_type != 'application/pdf':
            print(f"⚠️  Skipping non-PDF file: {p}", file=sys.stderr)
            return

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
                return
            tmp_path = tmp.name
        with open(tmp_path, 'rb') as fh:
            merger.append(fileobj=fh)
        os.unlink(tmp_path)

    # ✅ Only add bookmark if requested
        if with_bookmark and title:
            merger.add_outline_item(title, page_num, parent=parent)

        page_num += 1


   
   
   
    # ── Bookmarks
   
    if income:
        root = merger.add_outline_item('Income', page_num)
        groups = group_by_type(income)
        for form, grp in sorted(groups.items(), key=lambda kv: get_form_priority(kv[0], 'Income')):
            # Skip creating form bookmarks if all pages are already under Consolidated-1099
            filtered_grp = [e for e in grp if (e[0], e[1]) not in consolidated_pages]
            if not filtered_grp:
                continue  # nothing left for this form after filtering

            if stop_after_na:
                break
            if form == 'Consolidated-1099':
                cons_root = merger.add_outline_item('Consolidated-1099', page_num, parent=root)

                for entry in filtered_grp:
                    key, _, _ = entry
                    acct = key.split("::", 1)[1]

                    issuer = account_names.get(acct)
                    issuer = alias_issuer(issuer) if issuer else None
                    forms_label = issuer or f"Account {acct}"
                    forms_node = merger.add_outline_item(forms_label, page_num, parent=cons_root)

                    real_entries = consolidated_payload.get(key, [])

        # (optional context labels — does NOT skip appends)
             

        # ALWAYS append the real pages
                    for real_entry in real_entries:
                        page_text = extract_text(real_entry[0], real_entry[1])
                        if is_unused_page(page_text):
                            print(f"[DROP?] {os.path.basename(real_entry[0])} page {real_entry[1]+1} "
                                    f"marked as UNUSED", file=sys.stderr)
                            others.append((real_entry[0], real_entry[1], "Unused"))
                            #append_and_bookmark(real_entry, forms_node, "Unused")
                            continue

    # 1️⃣ First, check strong classifier
                        form_type = classify_div_int(page_text)

                        if form_type == "1099-DIV":
                            append_and_bookmark(real_entry, forms_node, "1099-DIV Description")

        # 2️⃣ Also check for other forms on same page
                            extra_forms = [ft for ft in (classify_text_multi(page_text) or [])
                                           if ft != "1099-DIV"]
                            for ft in extra_forms:
                                merger.add_outline_item(ft, page_num - 1, parent=forms_node)

                        elif form_type == "1099-INT":
                            if has_nonzero_int(page_text):
                                append_and_bookmark(real_entry, forms_node, "1099-INT Description")
                            else:
        # Still append the page, but give it a neutral label
                                append_and_bookmark(real_entry, forms_node, "1099-INT (all zero)")
                                print(f"[NOTE] {os.path.basename(real_entry[0])} page {real_entry[1]+1} "
                                  f"→ 1099-INT detected but all zero; kept page with neutral bookmark", file=sys.stderr)

                        # 2️⃣ Also check for other forms on same page
                            extra_forms = [ft for ft in (classify_text_multi(page_text) or [])
                                           if ft != "1099-INT"]
                            for ft in extra_forms:
                                merger.add_outline_item(ft, page_num - 1, parent=forms_node)

                        else:
        # 3️⃣ Fallback: pure multi-form logic
                            form_matches = classify_text_multi(page_text)

                            title = None
                            extra_forms = []

                            if form_matches:
    # Special rule: drop 1099-INT if all zero
                                if "1099-INT" in form_matches and not has_nonzero_int(page_text):
                                    form_matches = [f for f in form_matches if f != "1099-INT"]

                                if form_matches:
                                    title = form_matches[0]
                                    extra_forms = form_matches[1:]

# Append once, with or without bookmark
                            if title:
                                append_and_bookmark(real_entry, forms_node, title)
                                for ft in extra_forms:
                                    merger.add_outline_item(ft, page_num - 1, parent=forms_node)
                            else:
    # Only zero INT → keep page, no bookmark
                                append_and_bookmark(real_entry, forms_node, "", with_bookmark=False)

                continue
  # done with this form; go to next
            #Normal Forms
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, entry in enumerate(filtered_grp, 1):
                path, idx, _ = entry
               
                # 🚫 Skip if already appended under Consolidated-1099
                if (path, idx) in consolidated_pages:
                    continue

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
                elif form == '1099-SA':
                    payer = sa_titles.get((path, idx))
                    if payer:
                        lbl = payer

                # NEW: strip ", N.A" and stop after this bookmark
                if ", N.A" in lbl:
                    lbl = lbl.replace(", N.A", "")
                print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Income', Form='{form}', Title='{lbl}'", file=sys.stderr)
                   
                # normal case
                print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Income', Form='{form}', Title='{lbl}'", file=sys.stderr)
                append_and_bookmark(entry, node, lbl)
            if stop_after_na:
                break

    if expenses:
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
                elif form == '5498-SA':
                    trustee = sa5498_titles.get((path, idx))
                    if trustee:
                        lbl = trustee
                    else:
                        lbl = extract_5498sa_bookmark(text)

                elif form == '1098-T':
                    trustee = t1098_titles.get((path, idx))
                    if trustee:
                        lbl = trustee
                    else:
                        lbl = extract_1098t_bookmark(page_text)
               
                # NEW: strip ", N.A" and stop
                if ", N.A" in lbl:
                    lbl = lbl.replace(", N.A", "")
                print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Expenses', Form='{form}', Title='{lbl}'", file=sys.stderr)
                   
                # normal case
                print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Expenses', Form='{form}', Title='{lbl}'", file=sys.stderr)
                append_and_bookmark(entry, node, lbl)
            if stop_after_na:
                break

    # Others        
    if others:
        root = merger.add_outline_item('Others', page_num)
        node = merger.add_outline_item('Unused', page_num, parent=root)

        for entry in others:
        # Just append the page(s) under the single "Unused" node, no sub-bookmarks
            append_and_bookmark(entry, node, "", with_bookmark=False)

            print(
                f"[Bookmark] {os.path.basename(entry[0])} p{entry[1]+1} → "
                f"Category='Others', Form='Unused', Title='Unused (grouped)'",
                file=sys.stderr
            )


            #append_and_bookmark(entry, node, lbl)

    input_count = sum(
    len(PdfReader(os.path.join(input_dir, f)).pages)
    for f in files if f.lower().endswith(".pdf")
    )
    print(f"[SUMMARY] Input pages={input_count}, Output pages={page_num}", file=sys.stderr)

    # Write merged output
    os.makedirs(os.path.dirname(abs_output), exist_ok=True)
    with open(abs_output,'wb') as f:
        merger.write(f)
    merger.close()
    print(f"Merged PDF created at {abs_output}", file=sys.stderr)

    # Cleanup uploads
    # Cleanup uploads
    # Cleanup uploads (originals + converted PDFs)
    to_delete = set(files) | set(os.path.basename(f) for f in converted_files)

    for fname in list(to_delete):
        fpath = os.path.join(input_dir, fname)
        try:
            if os.path.exists(fpath):
                os.remove(fpath)
                print(f"🧹 Deleted {fname}", file=sys.stderr)
        except Exception as e:
            print(f"⚠️ Failed to delete {fname}: {e}", file=sys.stderr)

    # Also remove any leftover images (JPG, PNG, etc.)
    for fname in os.listdir(input_dir):
        if fname.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff')):
            try:
                os.remove(os.path.join(input_dir, fname))
                print(f"🧹 Deleted leftover image {fname}", file=sys.stderr)
            except Exception as e:
                print(f"⚠️ Failed to delete leftover image {fname}: {e}", file=sys.stderr)


# ── CLI
if __name__=='__main__':
    import argparse
    p = argparse.ArgumentParser(description="Merge PDFs with robust text extraction and cleanup")
    p.add_argument('input_dir', help="Folder containing PDFs to merge")
    p.add_argument('output_pdf', help="Path for the merged PDF (outside input_dir)")
    args = p.parse_args()
    merge_with_bookmarks(args.input_dir, args.output_pdf)
    
    
    
    
