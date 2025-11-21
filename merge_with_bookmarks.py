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

import platform
import pytesseract


# ✅ Auto-detect OS and set Tesseract path accordingly
if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
else:
    pytesseract.pytesseract.tesseract_cmd = "tesseract"


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
expense_priorities = {'1098-Mortgage':1,'1095-A':2,'1095-B':3,'1095-j':4,'5498-SA':5,'1098-T':6,'Property Tax':7,'Child Care Expenses':8,'1098-Other':9,'529-Plan':10}
other_priorities = {'1095-C':1}

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
# ── Prevent PIL DecompressionBombError for large tax PDFs
Image.MAX_IMAGE_PIXELS = None  # Safe because inputs are trusted (W-2/1099 client docs)


def pdf_page_to_image(path: str, page_index: int, dpi: int = 300) -> Image.Image:
    """
    Convert a PDF page to a preprocessed PIL image optimized for OCR.
    Adds automatic rotation correction for 0°, 90°, 180°, 270° pages.
    Steps (no OpenCV):
      - Detect & fix PDF metadata rotation
      - OCR-based auto-rotation (Tesseract OSD)
      - High DPI render
      - Convert to grayscale
      - Auto-contrast & brightness boost
      - Sharpen twice
      - Adaptive dual-thresholding (light & dark)
      - Rescale small text images
    """
    doc = fitz.open(path)
    page = doc.load_page(page_index)

    # 🧭 Step 1: Correct rotation using PDF metadata
    rotation = int(page.rotation or 0)
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom).prerotate(-rotation)

    pix = page.get_pixmap(matrix=mat, alpha=False)

    # Convert to RGB image
    try:
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    except Image.DecompressionBombError:
        logger.warning(f"⚠️ Skipping OCR: page too large in {path} p{page_index+1}")
        doc.close()
        return Image.new("L", (100, 100), color=255)

    # 🧠 Step 2: OCR-based auto-rotation (for scanned sideways pages)
    try:
        osd = pytesseract.image_to_osd(img, output_type=pytesseract.Output.DICT)
        angle = osd.get("rotate", 0)
        if angle != 0:
            print(f"[Rotation Fix] Auto-rotating page {page_index+1} by {angle}°")
            img = img.rotate(-angle, expand=True)
    except Exception as e:
        print(f"[WARN] Tesseract OSD rotation failed on page {page_index+1}: {e}")

    doc.close()

    # 🖼 Step 3: Continue your original preprocessing
    img = img.convert("L")  # grayscale
    img = ImageOps.autocontrast(img)
    img = ImageEnhance.Brightness(img).enhance(1.2)
    img = ImageEnhance.Contrast(img).enhance(1.5)
    img = img.filter(ImageFilter.SHARPEN)
    img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))

    # Rescale if small
    w, h = img.size
    if w < 2000:
        scale = 2000 / w
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    # Dual thresholding
    def threshold(im, cutoff):
        return im.point(lambda x: 0 if x < cutoff else 255, "1")

    light = threshold(img, 160)
    dark = threshold(img, 200)
    black_ratio_light = sum(light.getdata()) / (255 * light.size[0] * light.size[1])
    black_ratio_dark = sum(dark.getdata()) / (255 * dark.size[0] * dark.size[1])
    img_final = light if black_ratio_light < black_ratio_dark else dark

    return img_final


def preprocess_old_safe(img: Image.Image) -> Image.Image:
    """
    Gentle, safe OCR preprocessing that improves clarity
    WITHOUT breaking W-2 text.
    """
    # 1. Convert to grayscale
    img = img.convert("L")

    # 2. Light auto-contrast (safe)
    img = ImageOps.autocontrast(img, cutoff=1)

    # 3. Slight sharpness boost
    img = ImageEnhance.Sharpness(img).enhance(1.2)

    # 4. Light contrast/brightness (safe)
    img = ImageEnhance.Contrast(img).enhance(1.15)
    img = ImageEnhance.Brightness(img).enhance(1.05)

    # 5. Light noise reduction
    img = img.filter(ImageFilter.MedianFilter(size=3))

    # 6. Upscale if image is small
    w, h = img.size
    if w < 1800:
        scale = 1800 / w
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    return img

def extract_text(path: str, page_index: int) -> str:
    text = ""
    # OCR fallback
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
        # 🔹 Use only 300 DPI for sharper OCR
            dpi = 300
            img = pdf_page_to_image(path, page_index, dpi=300)

# NEW safe preprocessing
            img = preprocess_old_safe(img)

            t_ocr = pytesseract.image_to_string(
                img,
                lang="eng",
                config="--oem 3 --psm 6 -c preserve_interword_spaces=1"
            )


            print(f"[OCR dpi={dpi}]\n{t_ocr}", file=sys.stderr)

            if len(t_ocr.strip()) > len(text):
                text = t_ocr

        except Exception:
            traceback.print_exc()

    # PDFMiner
    try:
        t1 = pdfminer_extract(path, page_numbers=[page_index], laparams=PDFMINER_LA_PARAMS) or ""
        t1 = t1.strip()
        print(f"[PDFMiner full] {len(t1)} chars\n{t1}", file=sys.stderr)
        if len(t1) > len(text.strip()):
            text = t1
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
#For rotating pages
import io
from PIL import Image
import pytesseract
import fitz

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
        #fidelity
        or "the amount of tax-exempt interest paid to you must be reported on the applicable" in norm 
        or "form 1040, u.s. individual income tax return" in norm
        or "the amount of tax-exempt alternative minimum tax" in norm
        or "interest paid to you must be taken into account in computing the" in norm
        #Td Ameritrade
        or "The tax character of the distribution has been allocated based on information provided by the security issuer" in norm
        or "the tax character of the distribution has been allocated" in norm
        or "tax lot closed is a specified lot" in norm
        or "allocated based on information provided by the security issuer" in norm  
        or "importanttaxreturndocumentenclosed" in norm
        #Apex clearing
        or "please verify your personal information for accuracy and contact us" in norm
        or "if you hold these securities or another security that is" in norm
        or "information that may be helpful to you for filing your tax return" in norm
       #merrill
        #or "" in norm
        or "to view additional tax resources available online" in norm
        or "merrill is only required to revise 1099 tax reporting statements when" in norm
        or "amount shown on line 1b of form 1099 div as a qualified dividend indicates" in norm       
        or "california residents be advised that payers are required to report" in norm
        or "this page was intentionally left blank" in norm
        or "this page was intentionally left blank" in norm
       #w2
        or "for the latest information about developments related to form" in norm
        or "you and any qualifying children must have valid social security numbers" in norm
       
       #w2
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


import re

def extract_account_number(text: str, page_number: int = None) -> str:
    """
    Extract and normalize the account number or ORIGINAL number from page text.
    Handles:
    - 'Account Number: ####'
    - 'ORIGINAL: ####'
    - 'Account ####'
    - 'Apex Clearing' followed by account number (next line or same line)
    Automatically consolidates if both detections match.
    Prints the detected account number per page for debugging.
    Returns None if not found.
    """

    # --- 1️⃣ Standard patterns ---
    std_patterns = [
        r"Account\s*Number[:\s]*([\dA-Za-z\-]+)",
        r"Account Number:\s*([\dA-Za-z\s]+)",
        r"Account\s*No\.?[:\s]*([\dA-Za-z\-]+)",   # ✅ added: "Account No." or "Account No"s
        r"ORIGINAL:\s*([\dA-Za-z\s]+)",
        r"Account\s+(?!WITH\b)(?=[A-Za-z0-9\-]*\d)([A-Za-z0-9\-]+)",
        r"Account\s*No\.?\s*[:\-]?\s*([A-Za-z0-9]{1,3}[A-Za-z0-9\-]{3,})",
        r"AccountNo\.?\s*[:\-]?\s*([A-Za-z0-9]{1,3}[A-Za-z0-9\-]{3,})",
        r"Account\s*No\.?[^\n\r]*\n\s*([A-Za-z0-9]{1,3}[A-Za-z0-9\-]{3,})",
        r"AccountNo\.?[^\n\r]*\n\s*([A-Za-z0-9]{1,3}[A-Za-z0-9\-]{3,})",
        r"AccountNo\.?\s*([A-Za-z0-9]{4,})",
        r"Account\s*No\s+([A-Za-z0-9]{4,})",
        r"Account\s+([A-Za-z0-9]{1,4}\s+[0-9]{3,})",
        r"Account\s*No\.?\s*([A-Za-z0-9]+[\u2010\u2011\u2012\u2013\u2014\-][A-Za-z0-9\-]+)",
        # Case 1: Same line → "Account No. 76W-59336"
        r"Account\s*No\.?\s*[:\-]?\s*([A-Za-z0-9\-]{4,})",
        # Case 2: Next line → "Account No.\n76W-59336"
        r"Account\s*No\.?[^\n\r]*\n\s*([A-Za-z0-9\-]{4,})",
        # Merrill-specific labels
        r"(?:Merrill(?:\s+Lynch|\s+Edge)?)?\s*Account\s*No\.?\s*[:\-]?\s*([A-Za-z0-9\-]{4,})",
        # OCR distortions → Accoumt / Accouni / Accourt
        r"Accou[nmrt]+\s*No\.?\s*[:\-]?\s*([A-Za-z0-9\-]{4,})",
        # "Customer Account Number"
        r"Customer\s*Account\s*Number[:\s]*([A-Za-z0-9\s\-]{4,})",
        # Plain "Account XXXXX"
        r"Account\s+([A-Za-z0-9]{4,})",

    ]

    std_account = None
    for p in std_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            std_account = m.group(1).replace(" ", "").strip()
            break

    # --- 2️⃣ Apex Clearing: account on next line ---
    apex_match = re.search(
        r"Apex\s+Clearing[^\n\r]*\n\s*([A-Z0-9\-]{4,})",
        text,
        re.IGNORECASE
    )
    apex_nextline = apex_match.group(1).strip() if apex_match else None

    # --- 3️⃣ Apex Clearing: account on same line ---
    apex_inline = re.search(
        r"Apex\s+Clearing[^\n\r]{0,60}?([A-Z0-9\-]{4,})",
        text,
        re.IGNORECASE
    )
    apex_inline_acc = apex_inline.group(1).strip() if apex_inline else None

    # --- 4️⃣ Combine and normalize ---
    found = {std_account, apex_nextline, apex_inline_acc}
    found = {a for a in found if a}  # remove None

    detected_account = None
    if found:
        normalized = {a.replace("-", "").upper() for a in found}
        if len(normalized) == 1:
            detected_account = list(found)[0]
        else:
            detected_account = std_account or apex_nextline or apex_inline_acc

    # --- 5️⃣ Debug output ---
    if page_number is not None:
        if detected_account:
            print(f"✅ Page {page_number} → Account detected: {detected_account}")
        else:
            print(f"⚠️ Page {page_number} → No account found")

    return detected_account


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


def extract_1099b_section(text: str) -> str:
    """
    Extract only the 1099-B summary table section.
    """
    pattern = r"SUMMARY OF PROCEEDS.*?Grand total.*?(?:\n|$)"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return m.group(0) if m else ""


def find_nonzero_after(label: str, text: str, window: int = 120) -> bool:
    """
    Finds the label (e.g. 'Short A', 'Box A', etc.) and scans the next
    `window` characters for any non-zero numeric value.
    Works even when OCR breaks the line.
    """
    pattern = re.compile(label, re.IGNORECASE)

    for match in pattern.finditer(text):
        start = match.end()
        chunk = text[start:start + window]

        # extract numbers like 42,118.15 or 0.00 or $19,295.46
        nums = re.findall(r"-?\$?\s*[0-9][\d,]*\.\d{2}", chunk)

        for num in nums:
            val = float(num.replace("$", "").replace(",", "").strip())
            if val != 0:
                return True

    return False

def has_nonzero_1099b(text: str) -> bool:
    # FORMAT 1 — Vanguard / Robinhood / TD Ameritrade
    legacy_labels = [
        "Short A",
        "Short B",
        "Short C",
        "Total Short-term",
        "Long D",
        "Long E",
        "Long F",
        "Total Long-term",
        "Undetermined B",
        "Undetermined C",
        "Total Undetermined-term",
        "Grand total",
    ]

    # FORMAT 2 — Morgan Stanley / E*TRADE / Fidelity / Schwab
    box_labels = [
        r"Box A\b",
        r"Box A - Ordinary",
        r"Box B\b",
        r"Box B - Ordinary",
        r"Box D\b",
        r"Box D - Ordinary",
        r"Box E\b",
        r"Box E - Ordinary",

        r"Total Short\s*-?\s*Term",
        r"Total Long\s*-?\s*Term",
        r"Total Unknown\s*-?\s*Term",
        r"Unknown Term",
    ]

    # FORMAT 3 — Fidelity / Schwab "Full Text" Section Names
    fidelity_labels = [
        r"Short-term transactions for which basis is reported to the IRS",
        r"Short-term transactions for which basis is not reported to the IRS",
        r"Long-term transactions for which basis is reported to the IRS",
        r"Long-term transactions for which basis is not reported to the IRS",
        r"Transactions for which basis is not reported to the IRS and Term is Unknown",
    ]

    # Scan all available formats
    all_labels = legacy_labels + box_labels + fidelity_labels

    for label in all_labels:
        if find_nonzero_after(label, text, window=120):
            return True

    return False

def has_nonzero_div(text: str) -> bool:
    """
    Detects non-zero dividend amounts from:
      - 1a Ordinary Dividends
      - 1b Qualified Dividends
      - 2a Capital Gain Distributions
      - 3 Nondividend Distributions
      - 5 Section 199A Dividends
      - 7 Foreign Tax Paid
    """

    import re
    t = text.lower()

    # Robust OCR-safe patterns
    patterns = [
        r"1a[^0-9a-z]+.*ordinary dividends.*?([-]?\d[\d,]*\.\d{2})",
        r"1b[^0-9a-z]+.*qualified dividends.*?([-]?\d[\d,]*\.\d{2})",
        r"2a[^0-9a-z]+.*capital gain.*?([-]?\d[\d,]*\.\d{2})",
        r"3[^0-9a-z]+.*non.?dividend.*?([-]?\d[\d,]*\.\d{2})",
        r"5[^0-9a-z]+.*199a dividends.*?([-]?\d[\d,]*\.\d{2})",
        r"7[^0-9a-z]+.*foreign tax paid.*?([-]?\d[\d,]*\.\d{2})",
        r"11[^0-9a-z]+.*exempt.?interest dividends.*?([-]?\d[\d,]*\.\d{2})",
    ]

    for p in patterns:
        m = re.search(p, t, flags=re.DOTALL)
        if m:
            try:
                value = float(m.group(1).replace(",", ""))
                if value != 0.0:
                    return True
            except:
                pass

    return False


def has_nonzero_int(text: str) -> bool:
    import re

    t = text.lower()

    # Match ONLY numbers at the END of the line, not in the middle
    m = re.search(
        r"interest\s+income[^\n\r]*?([-]?[0-9oO]{1,5}\.?[0-9oO]+)\s*$",
        t,
        flags=re.IGNORECASE | re.MULTILINE
    )

    if not m:
        return False

    val = (
        m.group(1)
        .replace("O", "0")
        .replace("o", "0")
        .replace(",", "")
        .strip()
    )

    try:
        return float(val) > 0.0
    except:
        return False


import re

def _check_nonzero(patterns, text: str) -> bool:
    """
    Scan text with given regex patterns and return True
    if any captured numeric value is greater than zero.
    Works even when '$' is missing or OCR introduces stray spaces/letters.
    """
    for pat in patterns:
        matches = re.findall(pat, text, flags=re.IGNORECASE | re.DOTALL)
        for m in matches:
            # Clean OCR artifacts like "3.9O" or "$ 3.90"
            val_str = (
                str(m)
                .replace(",", "")
                .replace("$", "")
                .replace("O", "0")   # OCR 'O' → '0'
                .strip()
            )

            try:
                val = float(val_str)
                if val > 0.0:
                    print(f"[DEBUG] ✅ Nonzero value detected: {val_str}", file=sys.stderr)
                    return True
            except ValueError:
                continue
    return False


# --- Post-processing cleanup for bookmarks ---

def classify_text_multi(text: str) -> list[str]:
    """
    Return list of detected IRS forms on a page.
    Handles INT, DIV, B, MISC, OID.
    """
    import re, sys

    lower = text.lower()
    matches = []

    # --- Debug Area ---
    print("\n========== DEBUG PAGE ==========", file=sys.stderr)
    print(text[:500], file=sys.stderr)
    print("LOWER:", lower[:200], file=sys.stderr)
    print("===============================\n", file=sys.stderr)

    # ================================================================
    # 1️⃣ 1099-INT detection (NEW: ONLY based on non-zero interest)
    # ================================================================
    has_int = has_nonzero_int(text)

    # ================================================================
    # 2️⃣ 1099-DIV detection
    # ================================================================
    has_div = (
        ("1099-div" in lower or
         "form 1099-div" in lower or
         "ordinary dividends" in lower or
         "qualified dividends" in lower)
        and has_nonzero_div(text)
    )

    # Additional DIV safety (helps OCR cases)
    div_pattern = re.search(r"1099[\s\-]*div", lower)
    div_section = re.search(r"dividends\s+and\s+distributions", lower)
    if (div_pattern or div_section):
        if re.search(r"(ordinary|qualified)\s+divid.{0,10}[0-9,]+\.\d{2}", lower):
            matches.append("1099-DIV")

    # ================================================================
    # 3️⃣ 1099-B detection
    # ================================================================
    if "1099-b" in lower or "form 1099-b" in lower or has_nonzero_1099b(text):
        if has_nonzero_1099b(text):
            matches.append("1099-B")

    # ================================================================
    # 4️⃣ 1099-MISC
    # ================================================================
    if "1099-misc" in lower or "form 1099-misc" in lower:
        if has_nonzero_misc(text):
            matches.append("1099-MISC")

    # ================================================================
    # 5️⃣ 1099-OID
    # ================================================================
    if "1099-oid" in lower or "form 1099-oid" in lower:
        if has_nonzero_oid(text):
            matches.append("1099-OID")

    # ================================================================
    # 6️⃣ Combined INT + DIV
    # ================================================================
    # --- New INT + DIV independent logic ---

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
      # Detect W-2 pages by their header phrases
    t = re.sub(r"\s+", " ", text.lower()).strip()
    # --- Detect Schedule K-1 (Form 1065) ---
    if "schedule k-1" in t or "form 1065" in t:
        return "Income", "K-1"
    if "statement a" in t and "qbi" in t:
        return "Income", "K-1"

    #Property Tax
    if (
        "total allowable community college" in t
        or "school district property tax paid" in t
        or "district property tax paid" in t
        or "parcel id property property" in t
        or "axing unit taxrate previous tax" in t
        or "homestead exempt" in t
        or "real property tax proper iy location" in t
        or "property assessment" in t
        or "real property taxsssss" in t
        or "REAL PROPERTY TAX PROPERTY LOCATION" in t
        or "real property tax property location" in t
        or "www.dctreasurer.ora" in t
        or "homesteadexempt" in t
    ):
        return "Expenses", "Property Tax"

    # --------------------------- 1095-C --------------------------- #
    if (
        "form 1095-c" in lower
        or "employer-provided health insurance offer and coverage" in lower
        or "employee offer of coverage" in lower
        or "covered individuals" in lower
        or "employer-provided health insurance offer" in lower
        or "do not attach to your tax return" in lower
        
    ):
        return "Others", "1095-C"
    # --------------------------- 1095-C --------------------------- #
    


    if (
        "fees and interest earnings are not considered contributions" in t
        or "contact a competent tax advisor or the irs" in t
        or "retirement plans for small business" in t
        or "civil service retirement benefits" in t
        or "general rule for pensions and annuities" in t
        or "hsas and other tax-favored health plan" in t
        # New lines from E*TRADE statement:
        or "the following tax documents are not included in this statement" in t
        or "forms 1099-r, 1099-q, 1042-s, 2439, 5498" in t
        or "e*trade from morgan stanley is pleased to provide" in t
        or "warning - corrected tax forms possible" in t
        or "prepared based upon information provided by the issuer" in t
        or "we will be required to send you one or more corrections" in t
        # Existing unused checks...
        or "the following tax documents are not included in this statement" in t
        or "e*trade from morgan stanley" in t
        or "1099 consolidated tax statement" in t
        or "*** warning - corrected tax forms possible ***" in t
        or "prepared based upon information provided by the issuer" in t
        or "will be required to send you one or more corrections" in t
        #1042-S
        or "explanation of codes" in t
        or "einbehaltung der steuern" in t
    ):
        return "Others", "Unused"

    #1099-R
    r1099 = [
        #"federal income tax withheld",
        "taxable amount iras",
        "contrib or insurance premiums",
        "6 net unrealized appreciation",
        "13 date of 17 local tax withheld 18 name",
        "total employee contributions the irs",
        "2b taxable amount total copy b",
        
        
    ]
    for pat in r1099:
        if pat in lower:
            return "Income", "1099-R"

    # --- Detect 1099-G (State Income Tax Refund) ---
    g1099 = [
        "1099 g",
        "form 1099 g",
        "1099-g",
        "form 1099-g",
    ]
    for pat in g1099:
        if pat in lower:
            return "Income", "1099-G"

    if (
        "child care" in lower
        or "day care" in lower
        or "to the parents" in lower
      
        or "provider information" in lower
        or "total payments paid by" in lower
        #or "dates of service" in lower
        or "late payment fee late payment fee" in lower
        or "assistant business administrator" in lower
        or "preschool tuition payments" in lower
        or "the student named above has" in lower
        or "ach - returned - online payment" in lower
        or "registration fee new enrollmeny" in lower
        #or "" in lower
        
    ):
        print(f"[DEBUG] CHILD CARE EXPENSE DETECTED in page: {text[:120]}...", file=sys.stderr)
        return "Expenses", "Child Care Expenses"
   
    unuseddiv = [
        "fundrise strives to provide your",
        "#although the fundrise team seeks to",
        "fundrise receives updated information for",
        #1099-SA
        "fees and interest earnings",
        "if you have questions regarding",
        "you should contact a competent tax advisor"
        "Fees and interest earnings are not considered contributions",
        "contact a competent tax advisor or the irs",
        "contributions or distributions and are not",
        "if you have questions regarding specific circumstances",
        "if you have questions regarding specific circumstances",
        "if you have questions regarding specific circumstances",
        #1098-T
        #"for the latest information about developments"
        "may result in an increase in tax",
        "reimbursements or refunds for the calendar",
        "rippling",
        #W2
        "if this form includes amounts belonging to",
        "a spouse is not required to file a",
        "such a legislation enacted after",
        #1099-INT
        "continued on the back of copy",
       
       
    ]
    for pat in unuseddiv:
        if pat in lower:
            return "Others", "Unused"
    # --------------------------- 529 Plan / College Savings --------------------------- #
    # Detect 529 college savings plan statements or transaction notices
    clean_text = re.sub(r'[^A-Za-z0-9\s]', '', text.lower())  # normalize OCR artifacts
   
    if (
        "529" in clean_text
        and (
            #"indiana529" in clean_text
            "indiana 529" in clean_text
            or "529 direct savings plan" in clean_text
            or "education savings authority" in clean_text
            or "college savings" in clean_text
            or "qualified tuition program" in clean_text
            or "investment allocations" in clean_text
            or "investment portfolio" in clean_text
            or "funding information" in clean_text
            or "recurring contribution" in clean_text
            or "bank information" in clean_text
            or "electronic bank transfer" in clean_text
            #or "indiana529directcom" in clean_text
            #or "indiana 529 direct com" in clean_text
            or "indiana education savings" in clean_text
            or "contribution ebt" in clean_text
            or "please see below for details pertaining to" in clean_text
        )
    ):
        return "Expenses", "529-Plan"
    if "#bwnjgwm" in normalized:
        return "Others", "Unused"
    
    if "#rippling" in normalized:
        return "Others", "Unused"
    sa_front_patterns = [
        r"earnings\s+on\s+excess\s+cont",   # will also match 'cont.'
        #r"form\s+1099-?sa",                 # matches '1099-SA' or '1099SA'
        r"fmv\s+on\s+date\s+of\s+death",
    ]

    found_sa_front = any(re.search(pat, lower) for pat in sa_front_patterns)

    # 🔁 Priority: 1099-SA > Unused
    if found_sa_front:
        return "Income", "1099-SA"

   
    # 1) Detect W-2 pages by key header phrases
    if (
        "wages, tips, other compensation" in lower or
        ("employer's name" in lower and "address" in lower)
    ):
        return "Income", "W-2"

    #5498-SA
    # --- 5498-SA detection (more tolerant OCR patterns) ---
    sa5498_front_patterns = [
        r"form\s+[s§5]\s*498-?\s*sa",             # catches “5498-SA”, “S498-SA”, “§498-SA”
        r"form\s+5498sa",                         # no dash
        r"form\s+s498-sa",                        # OCR “5”→“S”
        r"form\s+§498-sa",                        # OCR “5”→“§”
        r"total\s+contributions\s+made\s+in\s+\d{4}",
        r"fair\s+market\s+value\s+of\s+(account|hsa)",
        r"\b2[\.\-)]?\s*rollover\s+contributions",
        r"\b5[\.\-)]?\s*fair\s+market\s+value\s+of\s+(account|hsa)",
        r"\b7[\.\-)]?\s*ira\s+type",
        r"\b11[\.\-)]?\s*required\s+minimum\s+distribution.*\d{4}"
    ]
    if any(re.search(pat, lower) for pat in sa5498_front_patterns):
        return "Expenses", "5498-SA"

   
    if is_unused_page(text):
        return "Unknown", "Unused"
    if '1098-t' in t: return 'Expenses', '1098-T'
   
    # If page matches any instruction patterns, classify as Others → Unused
    instruction_patterns = [
    # full “Instructions for Employee…” block (continued from back of Copy C)
    # W-2 instructions
    #"box 1. enter this amount on the wages line of your tax return",
    #"box 2. enter this amount on the federal income tax withheld line",
    #"box 5. you may be required to report this amount on form 8959",
    ##"box 6. this amount includes the 1.45% medicare tax withheld",
    #"box 8. this amount is not included in box 1, 3, 5, or 7",
    #"you must file form 4137",
    #"box 10. this amount includes the total dependent care benefits",
    "instructions for form 8949",
    "employee w-4 profile to change your employee w-4 profile information",
    "the following information reflects your final pay statement plus employer adjustments",
    "the following information reflects your final pay statement plus statement plus",
    "regulations section 1.6045-1",
    "recipient's taxpayer identification number",
    "fata filing requirement",
    "payer’s routing transit number",
    #"refer to the form 1040 instructions",
    "earned income credit",
    "if your name, SSN, or address is incorrect",
    #"corrected wage and tax statement",
    #"credit for excess taxes",
    #"instructions for employee  (continued from back of copy c) "
    #"box 12 (continued)",
    #"f—elective deferrals under a section 408(k)(6) salary reduction sep",
    "g—elective deferrals and employer contributions (including  nonelective ",
    "deferrals) to a section 457(b) deferred compensation plan",
    "h—elective deferrals to a section 501(c)(18)(d) tax-exempt  organization ",
    "plan. see the form 1040 instructions for how to deduct.",
    #"j—nontaxable sick pay (information only, not included in box 1, 3, or 5)",
    #"k—20% excise tax on excess golden parachute payments. see the ",
    #"form 1040 instructions.",
    #"l—substantiated employee business expense reimbursements ",
    #"(nontaxable)",
    "m—uncollected social security or rrta tax on taxable cost  of group-",
    "term life insurance over $50,000 (former employees only). see the form ",
    #"1040 instructions.",
    "n—uncollected medicare tax on taxable cost of group-term  life ",
    "insurance over $50,000 (former employees only). see the form 1040 ",
    #"instructions.",
    #"p—excludable moving expense reimbursements paid directly to a ",
    "member of the u.s. armed forces (not included in box 1, 3, or 5)",
    #"q—nontaxable combat pay. see the form 1040 instructions for details ",
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
       
       
        #---------------------------1099-DIV----------------------------------#
    #1099-INT for page 1
    div_front = [
        "form 1099-div",
        #"dividends and distributions",
        "1a total ordinary dividends",
        "1b qualified dividends distributions",
        "2a Total capital gain distr",
        "specified private activity bond interest dividends",
        "qualified dividends",
        "total capital gain distr",
        "section 1202 gain",
        "section 1250 gain",
    ]

    div_unused = [
       
        "the information contained herein",
        "please note that we have changed",
        "your redeemed shares has not been",
        "we are requested by trh irs",
        ]
    lower = text.lower()
    found_div_front = any(pat.lower() in lower for pat in div_front)
    found_div_unused = any(pat.lower() in lower for pat in div_unused)

# 🔁 Priority: 1099-INT > Unused
    if found_div_front:
        return "Income", "1099-DIV"
    elif found_div_unused:
        return "Others", "Unused"
           
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
        #"Investment expenses",
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
    "mortgage origination date the information",
    "1 mortgage interest received from",
    #"Account number (see instructions)"
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
    #if '1099-div' in t: return 'Income', '1099-DIV'
    #if 'form 1099-div' in t: return 'Income', '1099-DIV'
   
    #if '1099' in t: return 'Income', '1099-Other'
    front_donation = [
        "donation",
        "volunteers greatly appreciate your",
        "Volunteers greatly appreciate your generous coma"
    ]
   
    for pat in front_donation:
        if pat in lower:
            return "Expenses", "Donation"  
    
    return 'Unknown', 'Unused'

   

   
# Detect W-2 pages by their header phrases
    if 'wage and tax statement' in t or ("employer's name" in t and 'address' in t):
        return 'Income', 'W-2'
   
# --------------------------- 1095-C --------------------------- #
def extract_1095c_bookmark(text: str) -> str:
    """
    Extract a clean bookmark title for Form 1095-C pages.
    Keeps it short and consistent across issuers.
    """
    import re

    if not text:
        return "Form 1095-C"

    # Normalize text
    t = text.lower()
    if "employer-provided health insurance" in t or "form 1095-c" in t:
        return "1095-C – Employer-Provided Coverage"
    return "Form 1095-C"


# --------------------------- 1095-C --------------------------- #
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
        "discover bank": "Discover Bank",
        "goldman sachs bank usa": "Goldman Sachs Bank USA",  # ✅ new override
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
    Detects the brokerage or custodian issuing a Consolidated 1099.
    Supports all major U.S. firms and custodians (Fidelity, Schwab, E*TRADE, Robinhood, etc.)
    Returns a clean, friendly issuer name if detected, else None.
    """

    lower = text.lower()

    # --- Master company map (key phrases -> friendly label) ---
    issuers = {
        # Core brokerages
        r"fidelity(\s+investments)?": "Fidelity Investments",
        r"charles\s+schwab": "Charles Schwab & Co., Inc.",
        r"etrade|e\*trade": "E*TRADE (Morgan Stanley)",
        r"robinhood": "Robinhood Markets, Inc.",
        r"edward\s+jones": "Edward Jones",
        r"janney\s+montgomery\s+scott": "Janney Montgomery Scott LLC",
        r"stifel": "Stifel Financial Corp.",
        r"td\s*ameri?trade\s*clearing": "TD Ameritrade Clearing, Inc.",
        r"td\s*ameri?trade\s+clearing,\s*inc\.?": "TD Ameritrade Clearing, Inc.",
        r"td\s*ameri?trade": "TD Ameritrade (Charles Schwab)",
        r"tdameri?trade": "TD Ameritrade",
        r"td\s*ameri?trade\s+inc": "TD Ameritrade",
        r"ameritrade\s+clearing": "TD Ameritrade Clearing, Inc.",
        r"ameritrade": "TD Ameritrade",
        r"td\s+ameritrade\s+clearing": "TD Ameritrade Clearing, Inc.",
        r"ameritrade": "TD Ameritrade",
        r"td\s+ameritrade": "TD Ameritrade (Charles Schwab)",
        r"merrill|bank\s+of\s+america": "Merrill Lynch (Bank of America)",
        r"vanguard": "Vanguard Brokerage Services",
        r"interactive\s+brokers": "Interactive Brokers LLC",
        r"ally\s+invest": "Ally Invest",
        r"tastytrade|tastyworks": "Tastytrade, Inc.",
        r"morgan\s+stanley\s+wealth": "Morgan Stanley Wealth Management",
        r"raymond\s+james": "Raymond James & Associates, Inc.",
        r"pershing": "Pershing LLC",
        r"lpl\s+financial": "LPL Financial LLC",
        r"apex\s+clearing": "Apex Clearing",
        r"ameriprise": "Ameriprise Financial Services, Inc.",
        # UBS – must be BEFORE short patterns, but AFTER specific patterns like Ameritrade
        r"\bubs\s+financial\s+services\b": "UBS Financial Services Inc.",
        r"\bubs\s+financial\b": "UBS Financial Services Inc.",
        #r"ubs": "UBS Financial Services Inc.",
        r"wells\s+fargo": "Wells Fargo Advisors, LLC",
        r"j\.?p\.?\s*morgan|chase": "J.P. Morgan Securities LLC",
        r"goldman\s+sachs|marcus": "Goldman Sachs (Marcus / PWM)",
        r"sofi": "SoFi Invest",
        r"public\.com": "Public.com",
        r"acorns": "Acorns Advisers, LLC",
        r"betterment": "Betterment LLC",
        r"wealthfront": "Wealthfront Brokerage LLC",
        r"m1\s+finance": "M1 Finance LLC",
        r"firstrade": "Firstrade Securities Inc.",
        r"tradestation": "TradeStation Securities, Inc.",
        r"intelligent\s+portfolios": "Charles Schwab Intelligent Portfolios",
        r"fidelity\s+go|fidelity\s+spire": "Fidelity Go / Fidelity Spire",
        r"self[-\s]*directed\s+investing": "J.P. Morgan Self-Directed Investing",
        r"eaton\s+vance": "Eaton Vance Brokerage (Morgan Stanley)",
        r"hsbc\s+securities": "HSBC Securities (USA) Inc.",
        r"citi\s+personal\s+wealth": "Citi Personal Wealth Management",
        r"baird|robert\s+w\.?\s*baird": "Robert W. Baird & Co.",
        r"oppenheimer": "Oppenheimer & Co. Inc.",
        r"cowen": "Cowen and Company, LLC",
        r"jefferies": "Jefferies Financial Group Inc.",
        r"evercore": "Evercore ISI",
        r"hennion\s+&\s+walsh": "Hennion & Walsh, Inc.",
        r"zions": "Zions Direct (Zions Bancorporation)",
        r"fifth\s+third\s+securit": "Fifth Third Securities, Inc.",
        r"regions\s+investment": "Regions Investment Services, Inc.",
        r"pnc\s+invest": "PNC Investments, LLC",
        r"synovus": "Synovus Securities, Inc.",
        r"citizens\s+securit": "Citizens Securities, Inc.",
        r"first\s+horizon": "First Horizon Advisors, Inc.",
        
        r"merrill": "Merrill Lynch",
    }

    # --- 1️⃣ Direct known match (fast path) ---
    for pattern, name in issuers.items():
        if re.search(pattern, lower):
            return name

    # --- 2️⃣ Special explicit handling (legacy from old version) ---
    if re.search(r"morgan\s+stanley\s+capital\s+management,\s*llc", lower):
        return "Morgan Stanley Capital Management, LLC"

    # --- 3️⃣ Heuristic fallback for unknown but structured consolidated 1099s ---
    if "consolidated 1099" in lower or "composite 1099" in lower:
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            # skip headings / noise
            if re.search(r"(form|1099|copy|page|\baccount\b)", s, re.IGNORECASE):
                continue
            # probable issuer-style line
            if re.search(r"(LLC|Bank|Securities|Wealth|Brokerage|Advisors?)", s):
                return re.sub(r"[^\w\s,&.\-]+$", "", s)

    return None
# --------------------------- Consolidated-1099 issuer name --------------------------- #
#---------------------------1099-DIV----------------------------------#
def extract_1099div_bookmark(text: str) -> str:
    """
    Extract the payer name for Form 1099-DIV.
    Handles OCR noise, skips junk lines, and applies direct overrides
    for known payers like Fundrise, Bank of America, etc.
    """
    import re

    # --- Step 1: normalize text for pattern matching ---
    normalized_text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    normalized_text = re.sub(r"\s+", " ", normalized_text).strip()

    # --- Step 2: hardcoded overrides (fast exact detection) ---
    OVERRIDES = {
        "fundrise income real estate fund": "Fundrise Income Real Estate Fund, LLC",
        "fundrise income fund": "Fundrise Income Fund, LLC",
        # 🔹 Morgan Stanley (new)
        "morgan stanley domestic holdings": "Morgan Stanley Domestic Holdings, Inc",
        "morgan stanley domestic holding": "Morgan Stanley Domestic Holdings, Inc",
        "morgan stanley holdings inc": "Morgan Stanley Domestic Holdings, Inc",
        "morgan stanley holdings": "Morgan Stanley Domestic Holdings, Inc",
   
    }

    for key, val in OVERRIDES.items():
        if key in normalized_text:
            return val  # ✅ immediate return on match

    # --- Step 3: fallback pattern-based extraction ---
    lines = text.splitlines()
    lower_lines = [L.lower() for L in lines]
        # Normalize apostrophes to avoid OCR mismatch between ’ and '
    def normalize_apostrophes(s: str) -> str:
        return s.replace("’", "'").replace("`", "'")

    lower_lines = [normalize_apostrophes(L) for L in lower_lines]

    # Header detection pattern
    header_keywords = [
        "payer's name",
        "street address",
        "city or town",
        "state or province",
        "country",
        "zip",
        "telephone",
    ]

    # 1️⃣ Find header line that matches all key parts
    for i, L in enumerate(lower_lines):
        if all(k in L for k in header_keywords):
            # 2️⃣ Get the next non-empty line as bookmark
            for j in range(i + 1, len(lines)):
                candidate = lines[j].strip()
                if not candidate:
                    continue

                # Clean unwanted right-hand text
                candidate = re.sub(r"\s*\|.*$", "", candidate)   # remove trailing table/columns
                candidate = re.sub(r"\s*\$.*$", "", candidate)   # remove dollar values
                candidate = re.sub(r"[^\w\s,&.\-]+$", "", candidate).strip()

                if candidate:
                    return candidate

    def find_after(header_pred):
        for i, L in enumerate(lower_lines):
            if header_pred(L):
                for j in range(i + 1, len(lines)):
                    cand = lines[j].strip()
                    if not cand:
                        continue
                    cand_lower = cand.lower()

                    # Skip junk and header lines
                    if any(x in cand_lower for x in [
                        "foreign postal code", "telephone", "omb", "dividends", "distributions",
                        "copy b", "for recipient", "calendar year", "recipient’s tin",
                        "payer’s tin", "section", "gain", "tax withheld", "account number",
                    ]):
                        continue

                    if re.search(r"\bform\b", cand_lower):
                        continue
                    if len(cand) < 5 or not re.search(r"[A-Za-z]", cand):
                        continue

                    # If looks like an organization name
                    if re.search(r"\b(LLC|Inc|Fund|Trust|Bank|Corp|Company|Services|Advisors)\b", cand, re.IGNORECASE):
                        cand = re.sub(r"\s*\$.*$", "", cand)
                        return cand.strip(" ,.-")

                    # fallback
                    fallback = re.sub(r"[^\w\s,&.-]+$", "", cand).strip()
                    if fallback:
                        return fallback
        return None

    # Try payer header
    payer = find_after(lambda L: "payer's name" in L and "street address" in L)
    if payer:
        return payer

    # Fallback: recipient header
    recip = find_after(lambda L: "recipient's name" in L and "street address" in L)
    if recip:
        return recip

    return "1099-DIV"

#---------------------------1099-DIV----------------------------------#


def clean_bookmark(name: str) -> str:
    # Remove any trailing junk starting from 'Interest' and strip whitespace
    cleaned = re.sub(r"\bInterest.*$", "", name, flags=re.IGNORECASE)
    return cleaned.strip()

#1099-R
def extract_1099r_bookmark(text: str) -> str:
    """
    Robust extractor for 1099-R payer/company names.
    Handles both:
      - 'country, ZIP or foreign postal code, and telephone no.' layout (Schwab)
      - 'PAYER’S name, street address...' layout (Fidelity, Vanguard, etc.)
    """
    import re
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    lower_lines = [l.lower() for l in lines]
    for i, line in enumerate(lines):
        if (
            ("country" in line.lower() and "telephone" in line.lower())
            or ("payer" in line.lower() and "name" in line.lower())
        ):
            # --- Look ahead a few lines only within payer section ---
            for offset in range(1, 6):
                if i + offset >= len(lines):
                    break
                cand = lines[i + offset].strip()
                # Stop if we hit unrelated sections
                if re.search(
                    r"(recipient's|account number|department|form\s*1099|treasury|omb\s*no)", cand, re.I
                ):
                    break
                # Skip empty or generic lines
                if not cand:
                    continue
                # Skip "Retirement or" and trim if attached
                if re.fullmatch(r"(?i)retirement\s*or", cand):
                    continue
                cand = re.sub(r"(?i)\s*Retirement\s*or\s*$", "", cand).strip()
                # Remove noise like $amounts, “Form 1099-R Contracts, etc.”
                cand = re.sub(r"(?i)\$?\d.*$", "", cand)
                cand = re.sub(r"(?i)\bForm\s*1099.*$", "", cand)
                cand = re.sub(r"(?i)\bContracts.*$", "", cand)
                cand = re.sub(r"(?i)\bInsurance.*$", "", cand)
                # Skip addresses or numeric-heavy lines
                if re.search(r"\d{3,}", cand):
                    continue
                if re.search(r"(street|city|state|zip|address|drive|road|way|blvd)", cand, re.I):
                    continue
                # --- Check for continuation line (next line looks like part of company name) ---
                next_line = (
                    lines[i + offset + 1].strip()
                    if i + offset + 1 < len(lines)
                    else ""
                )
                if (
                    next_line
                    and not re.search(r"\d|city|state|zip|address|form|recipient|account", next_line, re.I)
                    and re.match(r"^[A-Z][A-Z\s&.,'-]{3,}$", next_line)
                ):
                    cand = f"{cand} {next_line}".strip()
                # Accept likely company name
                if len(cand.split()) >= 2 and not re.search(r"\d", cand):
                    return cand.title()
            break
    return "1099-R"

                #1099-R

#1099-G
import re
import unicodedata





#1099-G
# 1099-SA

def clean_institution_name(raw: str) -> str:
    """
    Post-process extracted institution name.
    Keeps the full institution name like 'Optum Bank',
    'The Bank of New York Mellon', etc.
    Trims copyright, FDIC notes, and OCR garbage tails like "we Til SAS Ne ee".
    """
    import re, unicodedata

    if not raw:
        return "1099-SA"

    # --- Step 1: Unicode normalization and invisible cleanup ---
    text = unicodedata.normalize("NFKC", raw)
    text = text.encode("ascii", "ignore").decode("ascii")  # drop weird OCR chars
    text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)  # remove zero-width chars
    text = re.sub(r"\s+", " ", text).strip()

    # --- Step 2: Core extraction ---
    m = re.search(
        r"\b([A-Z][A-Za-z& ]{0,60}?(?:Bank|Trust|Credit Union|Financial Services|Savings)[A-Za-z& ]{0,60})\b",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        name = m.group(1).strip(" ,.-")
    else:
        name = text

    # --- Step 3: Remove known OCR garbage (robust pattern) ---
    name = re.sub(
        r"(?i)\bwe\s*[t1i|l]+\s*s[a4@]s+\s*n[e3]+\s*e[e3]*\b.*$",
        "",
        name,
    )

    # --- Step 4: Remove trailing punctuation or leftover junk ---
    name = re.sub(r"[\s,.\-]+$", "", name).strip()

    return name or "1099-SA"

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
    # --- Known OCR Fixes / Existing ---
        "healthequity inc": "HealthEquity Inc.",
        # --- New: Bank of New York Mellon variations ---
        "the bank of new york mellon": "The Bank of New York Mellon",
        "the bank of new yok mellon": "The Bank of New York Mellon",   # common OCR missing 'r'
        "bank of new york mellon": "The Bank of New York Mellon",
        "bank of new yok mellon": "The Bank of New York Mellon",
        "coudl u add for thi stex t also": "The Bank of New York Mellon", 
        "optum bank inc": "Optum Bank Inc.",
        "fidelity investments hsa": "Fidelity Investments HSA",
        "hsa bank": "HSA Bank (Webster Bank N.A.)",
        "hsa bank webster bank": "HSA Bank (Webster Bank N.A.)",
        "hsa bank webster bank na": "HSA Bank (Webster Bank N.A.)",
        "lively hsa inc": "Lively HSA Inc.",
        "bank of america hsa services": "Bank of America HSA Services",
        "umb bank": "UMB Bank N.A.",
        "umb bank na": "UMB Bank N.A.",
        "first american bank": "First American Bank",
        "wells fargo bank": "Wells Fargo Bank N.A.",
        "wells fargo bank na": "Wells Fargo Bank N.A.",
        "jpmorgan chase bank": "JPMorgan Chase Bank N.A.",
        "jpmorgan chase bank na": "JPMorgan Chase Bank N.A.",
        "associated bank": "Associated Bank N.A.",
        "associated bank na": "Associated Bank N.A.",
        "fifth third bank": "Fifth Third Bank N.A.",
        "fifth third bank na": "Fifth Third Bank N.A.",
        "keybank": "KeyBank N.A.",
        "keybank na": "KeyBank N.A.",
        "payflex": "PayFlex (Aetna)",
        "payflex aetna": "PayFlex (Aetna)",
        #"benefitwallet": "BenefitWallet (Conduent)",
        "benefitwallet conduent": "BenefitWallet (Conduent)",
        "bend hsa inc": "Bend HSA Inc.",
        "saturna capital": "Saturna Capital (HSA Investing)",
        "saturna capital hsa investing": "Saturna Capital (HSA Investing)",
        "further": "Further (Health Savings Admin by BCBS MN)",
        "further health savings admin": "Further (Health Savings Admin by BCBS MN)",
        "elements financial credit union": "Elements Financial Credit Union",
        "patelco credit union": "Patelco Credit Union",
        "digital federal credit union": "Digital Federal Credit Union (DCU)",
        "digital federal credit union dcu": "Digital Federal Credit Union (DCU)",
        "america first credit union": "America First Credit Union",
        "golden 1 credit union": "Golden 1 Credit Union",
        "truist bank": "Truist Bank",
        "pnc bank": "PNC Bank N.A.",
        "pnc bank na": "PNC Bank N.A.",
        "regions bank": "Regions Bank",
        "us bank": "U.S. Bank N.A.",
        "us bank na": "U.S. Bank N.A.",
        "comerica bank": "Comerica Bank",
        "citizens bank": "Citizens Bank N.A.",
        "citizens bank na": "Citizens Bank N.A.",
        "first horizon bank": "First Horizon Bank",
        "hancock whitney bank": "Hancock Whitney Bank",
        "zions bank": "Zions Bank N.A.",
        "zions bank na": "Zions Bank N.A.",
        "frost bank": "Frost Bank",
        "old national bank": "Old National Bank",
        "synovus bank": "Synovus Bank",
        "bok financial": "BOK Financial (Bank of Oklahoma)",
        "bok financial bank of oklahoma": "BOK Financial (Bank of Oklahoma)",
        "commerce bank": "Commerce Bank",
        "first interstate bank": "First Interstate Bank",
        "glacier bank": "Glacier Bank",
        "banner bank": "Banner Bank",
        "first citizens bank": "First Citizens Bank",
        "huntington national bank": "Huntington National Bank",
        "associated healthcare credit union": "Associated Healthcare Credit Union",
        "advia credit union": "Advia Credit Union",
        "premier america credit union": "Premier America Credit Union",
        "bethpage federal credit union": "Bethpage Federal Credit Union",
        "mountain america credit union": "Mountain America Credit Union",
        "alliant credit union": "Alliant Credit Union",
        "penfed credit union": "PenFed Credit Union",
        "navy federal credit union": "Navy Federal Credit Union",
        "schoolsfirst federal credit union": "SchoolsFirst Federal Credit Union",
        "boeing employees credit union": "Boeing Employees Credit Union (BECU)",
        "boeing employees credit union becu": "Boeing Employees Credit Union (BECU)",
        "space coast credit union": "Space Coast Credit Union",
        "redstone federal credit union": "Redstone Federal Credit Union",
        "desert financial credit union": "Desert Financial Credit Union",
        "gesa credit union": "Gesa Credit Union",
        "bellco credit union": "Bellco Credit Union",
        "ent credit union": "Ent Credit Union",
        "vystar credit union": "VyStar Credit Union",
        "randolph brooks federal credit union": "Randolph-Brooks Federal Credit Union (RBFCU)",
        "randolph brooks federal credit union rbfcu": "Randolph-Brooks Federal Credit Union (RBFCU)",
        "american airlines federal credit union": "American Airlines Federal Credit Union",
        "delta community credit union": "Delta Community Credit Union",
        "state employees credit union": "State Employees’ Credit Union (SECU)",
        "vantage west credit union": "Vantage West Credit Union",
        "oregon community credit union": "Oregon Community Credit Union",
        "truwest credit union": "TruWest Credit Union",
        "lasso healthcare msa": "Lasso Healthcare MSA",
        "unitedhealthcare msa plans": "UnitedHealthcare MSA Plans",
        "humana msa plans": "Humana MSA Plans",
        "blue cross blue shield msa plans": "Blue Cross Blue Shield MSA Plans",
        "vibrant usa msa plans": "Vibrant USA MSA Plans",
        "healthsavings administrators": "HealthSavings Administrators",
        "connectyourcare": "ConnectYourCare (now Optum)",
        "connectyourcare now optum": "ConnectYourCare (now Optum)",
        "benefit resource inc": "Benefit Resource Inc.",
        "hsa authority": "HSA Authority (Old National Bank Division)",
        "hsa authority old national bank division": "HSA Authority (Old National Bank Division)",
        "selectaccount": "SelectAccount (HealthEquity)",
        "selectaccount healthequity": "SelectAccount (HealthEquity)",
        "starship hsa": "Starship HSA",
        "first bank and trust": "First Bank & Trust",
        "peoples bank midwest": "Peoples Bank Midwest",
        "choice bank": "Choice Bank",
        "midwestone bank": "MidWestOne Bank",
        "first financial bank": "First Financial Bank",
        "cadence bank": "Cadence Bank",
        "great southern bank": "Great Southern Bank",
        "independent bank": "Independent Bank",
        "origin bank": "Origin Bank",
        "texas capital bank": "Texas Capital Bank",
        "pinnacle financial partners": "Pinnacle Financial Partners",
        "columbia bank": "Columbia Bank",
        "townebank": "TowneBank",
        "bank ozk": "Bank OZK",
        "firstbank": "FirstBank (TN)",
        "firstbank tn": "FirstBank (TN)",
        "glacier hills credit union": "Glacier Hills Credit Union",
        "security health savings": "Security Health Savings",
        "bell bank": "Bell Bank",
        "banner life insurance co": "Banner Life Insurance Co.",
        "farmers and merchants bank": "Farmers & Merchants Bank",
        "first national bank of omaha": "First National Bank of Omaha",
        "arvest bank": "Arvest Bank",
        "bancorpsouth bank": "BancorpSouth Bank",
        "bank of tampa": "Bank of Tampa",
        "bank of the west": "Bank of the West",
        "bb&t": "BB&T (now Truist)",
        "bb&t now truist": "BB&T (now Truist)",
        "beneficial bank": "Beneficial Bank",
        "bmo harris bank": "BMO Harris Bank N.A.",
        "bmo harris bank na": "BMO Harris Bank N.A.",
        "california bank and trust": "California Bank & Trust",
        "cambridge trust company": "Cambridge Trust Company",
        "capital one bank": "Capital One Bank N.A.",
        "capital one bank na": "Capital One Bank N.A.",
        "centier bank": "Centier Bank",
        "central bank and trust co": "Central Bank & Trust Co.",
        "citizens equity first credit union": "Citizens Equity First Credit Union (CEFCU)",
        "citizens equity first credit union cefcu": "Citizens Equity First Credit Union (CEFCU)",
        "community america credit union": "Community America Credit Union",
        "community bank": "Community Bank N.A.",
        "community bank na": "Community Bank N.A.",
        "cornerstone community credit union": "Cornerstone Community Credit Union",
        "country bank for savings": "Country Bank for Savings",
        "credit human federal credit union": "Credit Human Federal Credit Union",
        "dearborn federal savings bank": "Dearborn Federal Savings Bank",
        "dedham savings bank": "Dedham Savings Bank",
        "deere employees credit union": "Deere Employees Credit Union",
        "denali federal credit union": "Denali Federal Credit Union",
        "dugood federal credit union": "DuGood Federal Credit Union",
        "elevations credit union": "Elevations Credit Union",
        "emprise bank": "Emprise Bank",
        "everence federal credit union": "Everence Federal Credit Union",
        "farm bureau bank": "Farm Bureau Bank FSB",
        "farm bureau bank fsb": "Farm Bureau Bank FSB",
        "first community bank": "First Community Bank",
        "first federal bank of the midwest": "First Federal Bank of the Midwest",
        "first merchants bank": "First Merchants Bank",
        "first mid bank and trust": "First Mid Bank & Trust",
        "first republic bank": "First Republic Bank",
        "first united bank and trust": "First United Bank & Trust Co.",
        "first united bank and trust co": "First United Bank & Trust Co.",
        "flagstar bank": "Flagstar Bank",
        "fulton bank": "Fulton Bank N.A.",
        "fulton bank na": "Fulton Bank N.A.",
        "gateway bank": "Gateway Bank",
        "georgias own credit union": "Georgia’s Own Credit Union",
        "great plains bank": "Great Plains Bank",
        "great western bank": "Great Western Bank",
        "greenstate credit union": "GreenState Credit Union",
        "guaranty bank and trust company": "Guaranty Bank & Trust Company",
        "heritage bank of commerce": "Heritage Bank of Commerce",
        "homestreet bank": "HomeStreet Bank",
        "intouch credit union": "InTouch Credit Union",
        "investors bank": "Investors Bank",
        "johnson financial group bank": "Johnson Financial Group Bank",
        "kinecta federal credit union": "Kinecta Federal Credit Union",
        "lake city bank": "Lake City Bank",
        "liberty bank": "Liberty Bank N.A.",
        "liberty bank na": "Liberty Bank N.A.",
        "lincoln savings bank": "Lincoln Savings Bank",
        "mainstreet credit union": "Mainstreet Credit Union",
        "marine federal credit union": "Marine Federal Credit Union",
        "marquette bank": "Marquette Bank",
        "mechanics bank": "Mechanics Bank",
        "merchants bank of indiana": "Merchants Bank of Indiana",
        "midfirst bank": "MidFirst Bank",
        "midland states bank": "Midland States Bank",
        "mutualone bank": "MutualOne Bank",
        "nicolet national bank": "Nicolet National Bank",
        "north island credit union": "North Island Credit Union",
        "north shore bank": "North Shore Bank",
        "northwest bank": "Northwest Bank",
        "old point national bank": "Old Point National Bank",
        "p1fcu": "P1FCU (Potlatch No. 1 Financial CU)",
        "pathfinder bank": "Pathfinder Bank",
        "patriot federal credit union": "Patriot Federal Credit Union",
        "peoples trust credit union": "Peoples Trust Credit Union",
        "provident bank of new jersey": "Provident Bank of New Jersey",
        "quorum federal credit union": "Quorum Federal Credit Union",
        "renasant bank": "Renasant Bank",
        "republic bank and trust company": "Republic Bank & Trust Company",
        "river city bank": "River City Bank",
        "rockland trust company": "Rockland Trust Company",
        "rocky mountain bank": "Rocky Mountain Bank",
        "rogue credit union": "Rogue Credit Union",
        "salem five bank": "Salem Five Bank",
        "san diego county credit union": "San Diego County Credit Union",
        "seattle bank": "Seattle Bank",
        "service credit union": "Service Credit Union",
        "shore united bank": "Shore United Bank",
        "simmons bank": "Simmons Bank",
        "south state bank": "South State Bank",
        "southern bank and trust co": "Southern Bank & Trust Co.",
        "space city credit union": "Space City Credit Union",
        "stellar one bank": "Stellar One Bank",
        "stockman bank of montana": "Stockman Bank of Montana",
        "summit credit union": "Summit Credit Union",
        "sunflower bank": "Sunflower Bank N.A.",
        "sunflower bank na": "Sunflower Bank N.A.",
        "tcf bank": "TCF Bank (now Huntington)",
        "tcf bank now huntington": "TCF Bank (now Huntington)",
        "texas bank and trust company": "Texas Bank and Trust Company",
        "the commerce bank of washington": "The Commerce Bank of Washington",
        "towpath credit union": "Towpath Credit Union",
        "tompkins trust company": "Tompkins Trust Company",
        "tower federal credit union": "Tower Federal Credit Union",
        "town and country bank": "Town & Country Bank",
        "tri counties bank": "Tri Counties Bank",
        "triad bank": "Triad Bank",
        "tricity credit union": "TriCity Credit Union",
        "tristate capital bank": "TriState Capital Bank",
        "trustco bank": "TrustCo Bank",
        "tulsa federal credit union": "Tulsa Federal Credit Union",
        "ufirst credit union": "UFirst Credit Union",
        "umb healthcare services": "UMB Healthcare Services",
        "unify financial credit union": "Unify Financial Credit Union",
        "union state bank": "Union State Bank",
        "united bank": "United Bank (WV)",
        "united bank wv": "United Bank (WV)",
        "united community bank": "United Community Bank (GA)",
        "united community bank ga": "United Community Bank (GA)",
        "united federal credit union": "United Federal Credit Union",
        "university federal credit union": "University Federal Credit Union (TX)",
        "university federal credit union tx": "University Federal Credit Union (TX)",
        "university of wisconsin credit union": "University of Wisconsin Credit Union",
        "usaa federal savings bank": "USAA Federal Savings Bank",
        "utah first credit union": "Utah First Credit Union",
        "valley strong credit union": "Valley Strong Credit Union",
        "veritex community bank": "Veritex Community Bank",
        "vermont federal credit union": "Vermont Federal Credit Union",
        "vibe credit union": "Vibe Credit Union",
        "virginia credit union": "Virginia Credit Union",
        "visions federal credit union": "Visions Federal Credit Union",
        "vystar credit union": "VyStar Credit Union",
        "wafd bank": "WaFd Bank (Washington Federal Bank)",
        "wafd bank washington federal bank": "WaFd Bank (Washington Federal Bank)",
        "wallis bank": "Wallis Bank",
        "waterstone bank": "WaterStone Bank",
        "waukesha state bank": "Waukesha State Bank",
        "webster five cents savings bank": "Webster Five Cents Savings Bank",
        "wesbanco bank": "WesBanco Bank Inc.",
        "wesbanco bank inc": "WesBanco Bank Inc.",
        "westfield bank": "Westfield Bank",
        "wheaton bank and trust": "Wheaton Bank & Trust",
        "whitefish credit union": "Whitefish Credit Union",
        "wilmington savings fund society": "Wilmington Savings Fund Society (WSFS Bank)",
        "wilmington savings fund society wsfs bank": "Wilmington Savings Fund Society (WSFS Bank)",
        "winchester savings bank": "Winchester Savings Bank",
        "wintrust financial corp": "Wintrust Financial Corp.",
        "wright patt credit union": "Wright-Patt Credit Union",
        "wyhy federal credit union": "WyHy Federal Credit Union",
        "xceed financial credit union": "Xceed Financial Credit Union",
        "abbybank": "AbbyBank",
        "adams bank and trust": "Adams Bank & Trust",
        "adirondack bank": "Adirondack Bank",
        "advantage bank": "Advantage Bank",
        "aimbank": "AIMBank",
        "alabama credit union": "Alabama Credit Union",
        "albina community bank": "Albina Community Bank",
        "alliance bank central texas": "Alliance Bank Central Texas",
        "alpine bank": "Alpine Bank",
        "amalgamated bank of chicago": "Amalgamated Bank of Chicago",
        "amboy bank": "Amboy Bank",
        "american bank and trust": "American Bank & Trust (SD)",
        "american bank and trust sd": "American Bank & Trust (SD)",
        "american bank and trust company": "American Bank & Trust Company (LA)",
        "american bank and trust company la": "American Bank & Trust Company (LA)",
        "american eagle financial credit union": "American Eagle Financial Credit Union",
        "american first credit union": "American First Credit Union",
        "american heritage bank": "American Heritage Bank",
        "american heritage credit union": "American Heritage Credit Union",
        "americu credit union": "AmeriCU Credit Union",
        "androscoggin bank": "Androscoggin Bank",
        "anstaff bank": "Anstaff Bank",
        "appalachian community fcu": "Appalachian Community FCU",
        "apple bank for savings": "Apple Bank for Savings",
        "aptiva bank": "Aptiva Bank",
        "arbor bank": "Arbor Bank",
        "arcola first bank": "Arcola First Bank",
        "armed forces bank": "Armed Forces Bank",
        "arrowhead credit union": "Arrowhead Credit Union",
        "artisans bank": "Artisans Bank",
        "ascentra credit union": "Ascentra Credit Union",
        "asheville savings bank": "Asheville Savings Bank",
        "atlantic city federal credit union": "Atlantic City Federal Credit Union",
        "atlantic federal credit union": "Atlantic Federal Credit Union (ME)",
        "atlantic federal credit union me": "Atlantic Federal Credit Union (ME)",
        "atlantic stewardship bank": "Atlantic Stewardship Bank",
        "auburn community federal credit union": "Auburn Community Federal Credit Union",
        "austin bank": "Austin Bank",
        "baker boyer bank": "Baker Boyer Bank",
        "ballston spa national bank": "Ballston Spa National Bank",
        "bank five nine": "Bank Five Nine",
        "bank iowa": "Bank Iowa",
        "bank midwest": "Bank Midwest (MN)",
        "bank midwest mn": "Bank Midwest (MN)",
        "bank of bozeman": "Bank of Bozeman",
        "bank of clarke county": "Bank of Clarke County",
        "bank of colorado": "Bank of Colorado",
        "bank of desoto": "Bank of Desoto",
        "bank of eastern oregon": "Bank of Eastern Oregon",
        "bank of george": "Bank of George",
        "bank of hawaii": "Bank of Hawaii (HSA Division)",
        "bank of hawaii hsa division": "Bank of Hawaii (HSA Division)",
        "bank of jackson hole": "Bank of Jackson Hole",
        "bank of little rock": "Bank of Little Rock",
        "bank of north carolina": "Bank of North Carolina (merged with Pinnacle)",
        "bank of north carolina merged with pinnacle": "Bank of North Carolina (merged with Pinnacle)",
        "bank of prairie du sac": "Bank of Prairie du Sac",
        "bank of san francisco": "Bank of San Francisco",
        "bank of tennessee": "Bank of Tennessee",
        "bank of travelers rest": "Bank of Travelers Rest",
        "bank of washington": "Bank of Washington",
        "bank rhode island": "Bank Rhode Island",
        "bankers trust company": "Bankers Trust Company",
        "bankfirst financial services": "BankFirst Financial Services",
        "banner county bank": "Banner County Bank",
        "baraboo state bank": "Baraboo State Bank",
        "bath savings institution": "Bath Savings Institution",
        "baxter credit union": "Baxter Credit Union (BECU subsidiary)",
        "baxter credit union becu subsidiary": "Baxter Credit Union (BECU subsidiary)",
        "bay federal credit union": "Bay Federal Credit Union",
        "baycoast bank": "BayCoast Bank",
        "bayvanguard bank": "BayVanguard Bank",
        "beacon credit union": "Beacon Credit Union",
        "beaumont community credit union": "Beaumont Community Credit Union",
        "belco community credit union": "Belco Community Credit Union",
        "bellwood cu": "Bellwood CU",
        "benchmark bank": "Benchmark Bank (TX)",
        "benchmark bank tx": "Benchmark Bank (TX)",
        "beneficial state bank": "Beneficial State Bank",
        "benton state bank": "Benton State Bank",
        "berkshire bank": "Berkshire Bank",
        "beverly bank": "Beverly Bank",
        "big horn federal savings bank": "Big Horn Federal Savings Bank",
        "black hills federal credit union": "Black Hills Federal Credit Union",
        "bluff view bank": "Bluff View Bank",
        "blue ridge bank": "Blue Ridge Bank N.A.",
        "blue ridge bank na": "Blue Ridge Bank N.A.",
        "bmi federal credit union": "BMI Federal Credit Union",
        "bogota savings bank": "Bogota Savings Bank",
        "boone bank and trust": "Boone Bank & Trust Co.",
        "boone bank and trust co": "Boone Bank & Trust Co.",
        "boston firefighters credit union": "Boston Firefighters Credit Union",
        "brannen bank": "Brannen Bank",
        "bridgewater credit union": "Bridgewater Credit Union",
        "brightstar credit union": "BrightStar Credit Union",
        "broadview federal credit union": "Broadview Federal Credit Union",
        "brookline bank": "Brookline Bank",
        "brotherhood credit union": "Brotherhood Credit Union",
        "buckeye state bank": "Buckeye State Bank",
        "buffalo federal bank": "Buffalo Federal Bank",
        "butte community bank": "Butte Community Bank",
        "cabot and company bankers": "Cabot & Company Bankers",
        "california credit union": "California Credit Union",
        "cambridge savings bank": "Cambridge Savings Bank",
        "camden national bank": "Camden National Bank",
        "canandaigua federal credit union": "Canandaigua Federal Credit Union",
        "cape ann savings bank": "Cape Ann Savings Bank",
        "capital city bank": "Capital City Bank",
        "capital community bank": "Capital Community Bank (CCBank)",
        "capital community bank ccbank": "Capital Community Bank (CCBank)",
        "capitol federal savings bank": "Capitol Federal Savings Bank",
        "carolina foothills federal credit union": "Carolina Foothills Federal Credit Union",
        "carter bank and trust": "Carter Bank & Trust",
        "cascade community credit union": "Cascade Community Credit Union",
        "cathay bank": "Cathay Bank",
        "cbs bank": "CB&S Bank",
        "zia credit union": "Zia Credit Union",
        "cbi bank and trust": "CBI Bank & Trust",
        "centennial bank": "Centennial Bank (AR)",
        "centennial bank ar": "Centennial Bank (AR)",
        "centerstate bank": "CenterState Bank",
        "centric bank": "Centric Bank",
        "central bank": "Central Bank (UT)",
        "central bank ut": "Central Bank (UT)",
        "central pacific bank": "Central Pacific Bank",
        "century bank": "Century Bank (MA)",
        "century bank ma": "Century Bank (MA)",
        "chambers bank": "Chambers Bank",
        "charles river bank": "Charles River Bank",
        "chelsea state bank": "Chelsea State Bank",
        "chemung canal trust company": "Chemung Canal Trust Company",
        "cherokee state bank": "Cherokee State Bank",
        "chesapeake bank": "Chesapeake Bank",
        "chittenden bank": "Chittenden Bank",
        "choiceone bank": "ChoiceOne Bank",
        "citizens bank of las cruces": "Citizens Bank of Las Cruces",
        "citizens bank of west virginia": "Citizens Bank of West Virginia",
        "citizens first bank": "Citizens First Bank (FL)",
        "citizens first bank fl": "Citizens First Bank (FL)",
        "citizens national bank of texas": "Citizens National Bank of Texas",
        "citizens state bank of loyal": "Citizens State Bank of Loyal",
        "city and county credit union": "City & County Credit Union",
        "city national bank of florida": "City National Bank of Florida",
        "clackamas county bank": "Clackamas County Bank",
        "classic bank": "Classic Bank N.A.",
        "classic bank na": "Classic Bank N.A.",
        "clayton bank and trust": "Clayton Bank & Trust",
        "clinton savings bank": "Clinton Savings Bank",
        "coastal community bank": "Coastal Community Bank",
        "coastal heritage bank": "Coastal Heritage Bank",
        "coastalstates bank": "CoastalStates Bank",
        "coeur d’alene bank": "Coeur d’Alene Bank",
        "colfax bank and trust": "Colfax Bank & Trust",
        "colony bank": "Colony Bank",
        "columbia state bank": "Columbia State Bank",
        "commonwealth community bank": "Commonwealth Community Bank",
        "community 1st credit union": "Community 1st Credit Union (IA)",
        "community 1st credit union ia": "Community 1st Credit Union (IA)",
        "community bank of pleasant hill": "Community Bank of Pleasant Hill",
        "community bank of raymore": "Community Bank of Raymore",
        "community first bank of indiana": "Community First Bank of Indiana",
        "community resource credit union": "Community Resource Credit Union",
        "community trust bank": "Community Trust Bank (KY)",
        "community trust bank ky": "Community Trust Bank (KY)",
        "communityamerica financial services": "CommunityAmerica Financial Services",
        "communitybank of texas": "CommunityBank of Texas N.A.",
        "communitybank of texas na": "CommunityBank of Texas N.A.",
        "consumers national bank": "Consumers National Bank",
        "cornerstone financial credit union": "Cornerstone Financial Credit Union",
        "corporate america credit union": "Corporate America Credit Union",
        "county bank": "County Bank (IA)",
        "county bank ia": "County Bank (IA)",
        "county national bank": "County National Bank (MI)",
        "county national bank mi": "County National Bank (MI)",
        "covenant bank": "Covenant Bank",
        "crescent credit union": "Crescent Credit Union",
        "cross river bank": "Cross River Bank",
        "crystal lake bank and trust": "Crystal Lake Bank & Trust",
        "cse federal credit union": "CSE Federal Credit Union",
        "cta bank and trust": "CTA Bank & Trust",
        "customers bank": "Customers Bank",
        "dakota community federal cu": "Dakota Community Federal CU",
        "dakota heritage bank": "Dakota Heritage Bank",
        "dallas capital bank": "Dallas Capital Bank",
        "danbury savings bank": "Danbury Savings Bank",
        "day air credit union": "Day Air Credit Union",
        "dedham institution for savings": "Dedham Institution for Savings",
        "delta bank": "Delta Bank",
        "denison state bank": "Denison State Bank",
        "deposit bank of frankfort": "Deposit Bank of Frankfort",
        "deseret first credit union": "Deseret First Credit Union",
        "diamond credit union": "Diamond Credit Union",
        "dime community bank": "Dime Community Bank",
        "dnb first bank": "DNB First Bank",
        "dorchester savings bank": "Dorchester Savings Bank",
        "dover federal credit union": "Dover Federal Credit Union",
        "drummond community bank": "Drummond Community Bank",
        "dupage credit union": "DuPage Credit Union",
        "dupaco community credit union": "Dupaco Community Credit Union",
        "durden bank and trust": "Durden Bank & Trust",
        "eagle community credit union": "Eagle Community Credit Union",
        "eagle federal credit union": "Eagle Federal Credit Union",
        "eagle savings bank": "Eagle Savings Bank",
        "east bank": "East Bank (East Chicago, IN)",
        "east bank east chicago": "East Bank (East Chicago, IN)",
        "east boston savings bank": "East Boston Savings Bank",
        "east cambridge savings bank": "East Cambridge Savings Bank",
        "east river federal credit union": "East River Federal Credit Union",
        "eastern savings bank": "Eastern Savings Bank (MD)",
        "eastern savings bank md": "Eastern Savings Bank (MD)",
        "eaton community bank": "Eaton Community Bank",
        "educators credit union": "Educators Credit Union (TX)",
        "educators credit union tx": "Educators Credit Union (TX)",
        "eecu credit union": "EECU Credit Union (TX)",
        "eecu credit union tx": "EECU Credit Union (TX)",
        "el paso area teachers federal credit union": "El Paso Area Teachers Federal Credit Union",
        "elevate bank": "Elevate Bank",
        "elk river bank": "Elk River Bank",
        "elmira savings bank": "Elmira Savings Bank",
        "embassy bank for the lehigh valley": "Embassy Bank for the Lehigh Valley",
        "empower federal credit union": "Empower Federal Credit Union",
        "endura financial credit union": "Endura Financial Credit Union",
        "enterprise bank and trust": "Enterprise Bank & Trust",
        "envista credit union": "Envista Credit Union",
        "equitable bank": "Equitable Bank (NE)",
        "equitable bank ne": "Equitable Bank (NE)",
        "erie federal credit union": "Erie Federal Credit Union",
        "evertrust bank": "EverTrust Bank",
        "exchange state bank": "Exchange State Bank",
        "excite credit union": "Excite Credit Union",
        "f&m bank": "F&M Bank (NC)",
        "f&m bank nc": "F&M Bank (NC)",
        "f&m trust": "F&M Trust (Franklin Co. PA)",
        "f&m trust franklin co pa": "F&M Trust (Franklin Co. PA)",
        "fairfield county bank": "Fairfield County Bank",
        "farmers and drovers bank": "Farmers & Drovers Bank",
        "farmers and merchants bank of central california": "Farmers & Merchants Bank of Central California",
        "farmers bank and trust": "Farmers Bank & Trust (AR)",
        "farmers bank and trust ar": "Farmers Bank & Trust (AR)",
        "farmers state bank in": "Farmers State Bank (IN)",
        "farmers state bank ia": "Farmers State Bank (IA)",
        "farmers state bank mt": "Farmers State Bank (MT)",
        "fayette county bank": "Fayette County Bank",
        "fidelity bank of florida": "Fidelity Bank of Florida",
        "fidelity deposit and discount bank": "Fidelity Deposit and Discount Bank",
        "financial partners credit union": "Financial Partners Credit Union",
        "finex credit union": "Finex Credit Union",
        "first alliance credit union": "First Alliance Credit Union",
        "first american trust fsb": "First American Trust FSB",
        "first arkansas bank and trust": "First Arkansas Bank & Trust",
        "first bank hampton": "First Bank Hampton",
        "first bank kansas": "First Bank Kansas",
        "first bank richmond": "First Bank Richmond",
        "first bankers trust company": "First Bankers Trust Company N.A.",
        "first bankers trust company na": "First Bankers Trust Company N.A.",
        "first basin credit union": "First Basin Credit Union",
        "first capital federal credit union": "First Capital Federal Credit Union",
        "first central state bank": "First Central State Bank",
        "first chatham bank": "First Chatham Bank",
        "first citizens national bank": "First Citizens National Bank (TN)",
        "first citizens national bank tn": "First Citizens National Bank (TN)",
        "first city credit union": "First City Credit Union",
        "first commerce credit union": "First Commerce Credit Union",
        "first community credit union": "First Community Credit Union (MO)",
        "first community credit union mo": "First Community Credit Union (MO)",
        "first community credit union tx": "First Community Credit Union (TX)",
        "first county bank": "First County Bank",
        "first dakota national bank": "First Dakota National Bank",
        "first eagle bank": "First Eagle Bank",
        "first enterprise bank": "First Enterprise Bank",
        "first federal bank": "First Federal Bank (KY)",
        "first federal bank ky": "First Federal Bank (KY)",
        "first federal savings bank of champaign urbana": "First Federal Savings Bank of Champaign-Urbana",
        "first financial bank": "First Financial Bank (OH)",
        "first financial bank oh": "First Financial Bank (OH)",
        "first financial northwest bank": "First Financial Northwest Bank",
        "first florida credit union": "First Florida Credit Union",
        "first freedom bank": "First Freedom Bank",
        "first hawaiian bank": "First Hawaiian Bank (HSA Division)",
        "first hawaiian bank hsa division": "First Hawaiian Bank (HSA Division)",
        "first hope bank": "First Hope Bank",
        "first independent bank": "First Independent Bank (NV)",
        "first independent bank nv": "First Independent Bank (NV)",
        "first international bank and trust": "First International Bank & Trust",
        "first interstate credit union": "First Interstate Credit Union",
        "first mid illinois bank and trust": "First Mid-Illinois Bank & Trust",
        "first midwest bank": "First Midwest Bank (IL)",
        "first midwest bank il": "First Midwest Bank (IL)",
        "first national bank in sioux falls": "First National Bank in Sioux Falls",
        "first national bank north": "First National Bank North",
        "first national bank of bastrop": "First National Bank of Bastrop",
        "first national bank of brookfield": "First National Bank of Brookfield",
        "first national bank of durango": "First National Bank of Durango",
        "first national bank of hutchinson": "First National Bank of Hutchinson",
        "first national bank of mcgregor": "First National Bank of McGregor",
        "first national bank of pennsylvania": "First National Bank of Pennsylvania",
        "first national bank of pulaski": "First National Bank of Pulaski",
        "first national bank of st louis": "First National Bank of St. Louis",
        "first national bank of waseca": "First National Bank of Waseca",
        "first national bank of winnsboro": "First National Bank of Winnsboro",
        "first national community bank": "First National Community Bank (GA)",
        "first national community bank ga": "First National Community Bank (GA)",
        "first northern credit union": "First Northern Credit Union",
        "first oklahoma bank": "First Oklahoma Bank",
        "first premier bank": "First PREMIER Bank",
        "first robinson savings bank": "First Robinson Savings Bank",
        "first savings bank": "First Savings Bank (IN)",
        "first savings bank in": "First Savings Bank (IN)",
        "first security bank": "First Security Bank (AR)",
        "first security bank ar": "First Security Bank (AR)",
        "first security bank of missoula": "First Security Bank of Missoula",
        "first service bank": "First Service Bank",
        "first southern bank": "First Southern Bank (IL)",
        "first southern bank il": "First Southern Bank (IL)",
        "first state bank": "First State Bank (IL)",
        "first state bank il": "First State Bank (IL)",
        "first state bank mi": "First State Bank (MI)",
        "first state bank tx": "First State Bank (TX)",
        "first state bank nebraska": "First State Bank Nebraska",
        "first state community bank": "First State Community Bank",
        "first state credit union": "First State Credit Union",
        "first tennessee bank": "First Tennessee Bank (now Truist)",
        "first tennessee bank now truist": "First Tennessee Bank (now Truist)",
        "first texas bank": "First Texas Bank",
        "first united bank": "First United Bank (OK)",
        "first united bank ok": "First United Bank (OK)",
        "first western bank and trust": "First Western Bank & Trust",
        "first western federal savings bank": "First Western Federal Savings Bank",
        "firstbank": "FirstBank (CO)",
        "firstbank co": "FirstBank (CO)",
        "firstbank of nebraska": "FirstBank of Nebraska",
        "five star bank": "Five Star Bank",
        "flagship bank minnesota": "Flagship Bank Minnesota",
        "fnb bank": "FNB Bank (KY)",
        "fnb bank ky": "FNB Bank (KY)",
        "fnbc bank": "FNBC Bank (AR)",
        "fnbc bank ar": "FNBC Bank (AR)",
        "foothill credit union": "Foothill Credit Union",
        "forest park bank": "Forest Park Bank",
        "fort knox federal credit union": "Fort Knox Federal Credit Union",
        "fort sill federal credit union": "Fort Sill Federal Credit Union",
        "forward bank": "Forward Bank",
        "fox communities credit union": "Fox Communities Credit Union",
        "freedom bank of virginia": "Freedom Bank of Virginia",
        "freedom credit union": "Freedom Credit Union (MA)",
        "freedom credit union ma": "Freedom Credit Union (MA)",
        "frontier bank": "Frontier Bank (NE)",
        "frontier bank ne": "Frontier Bank (NE)",
        "frontwave credit union": "Frontwave Credit Union",
        "fsnb national bank": "FSNB National Bank",
    
        "fulton bank of new jersey": "Fulton Bank of New Jersey",
        "g bank": "G Bank (Bank of Guam USA)",
        "g bank bank of guam usa": "G Bank (Bank of Guam USA)",
        "gainesville bank and trust": "Gainesville Bank & Trust",
        "gannon bank": "Gannon Bank",
        "generations bank": "Generations Bank",
        "generations credit union": "Generations Credit Union",
        "george d warthen bank": "George D. Warthen Bank",
        "georgia banking company": "Georgia Banking Company",
        "germantown trust and savings bank": "Germantown Trust & Savings Bank",
        "gnb bank": "GNB Bank",
        "goldenwest credit union": "Goldenwest Credit Union",
        "goodfield state bank": "Goodfield State Bank",
        "gorham savings bank": "Gorham Savings Bank",
        "grand ridge national bank": "Grand Ridge National Bank",
        "granite bank": "Granite Bank",
        "granite state credit union": "Granite State Credit Union",
        "great lakes credit union": "Great Lakes Credit Union",
        "great river federal credit union": "Great River Federal Credit Union",
        "greater nevada credit union": "Greater Nevada Credit Union",
        "greater texas credit union": "Greater Texas Credit Union",
        "green cove springs state bank": "Green Cove Springs State Bank",
        "green dot bank": "Green Dot Bank",
        "greenfield savings bank": "Greenfield Savings Bank",
        "greenleaf bank": "Greenleaf Bank",
        "greenville national bank": "Greenville National Bank",
        "greylock federal credit union": "Greylock Federal Credit Union",
        "guaranty bank and trust": "Guaranty Bank & Trust (IA)",
        "guaranty bank and trust ia": "Guaranty Bank & Trust (IA)",
        "gulf coast federal credit union": "Gulf Coast Federal Credit Union",
        "gulf winds credit union": "Gulf Winds Credit Union",
        "hancock county savings bank": "Hancock County Savings Bank",
        "hancock whitney bank": "Hancock Whitney Bank (HSA Dept.)",
        "hancock whitney bank hsa dept": "Hancock Whitney Bank (HSA Dept.)",
        "happy state bank": "Happy State Bank",
        "harborone bank": "HarborOne Bank",
        "harrison county bank": "Harrison County Bank",
        "hartford federal credit union": "Hartford Federal Credit Union",
        "hawaiiusa federal credit union": "HawaiiUSA Federal Credit Union",
        "heartland credit union": "Heartland Credit Union (WI)",
        "heartland credit union wi": "Heartland Credit Union (WI)",
        "heartland tri state bank": "Heartland Tri-State Bank",
        "helena community credit union": "Helena Community Credit Union",
        "heritage family credit union": "Heritage Family Credit Union",
        "heritage grove federal credit union": "Heritage Grove Federal Credit Union",
        "heritage south credit union": "Heritage South Credit Union",
        "heritage west credit union": "Heritage West Credit Union",
        "highland community bank": "Highland Community Bank",
        "hilltop national bank": "Hilltop National Bank",
        "hingham institution for savings": "Hingham Institution for Savings",
        "horizon bank": "Horizon Bank (MI)",
        "horizon bank mi": "Horizon Bank (MI)",
        "horizon community bank": "Horizon Community Bank (AZ)",
        "horizon community bank az": "Horizon Community Bank (AZ)",
        "horizon credit union": "Horizon Credit Union (WA)",
        "horizon credit union wa": "Horizon Credit Union (WA)",
        "horizon federal credit union": "Horizon Federal Credit Union (PA)",
        "horizon federal credit union pa": "Horizon Federal Credit Union (PA)",
        "houston federal credit union": "Houston Federal Credit Union",
        "howard county bank": "Howard County Bank",
        "hudson city savings bank": "Hudson City Savings Bank",
        "hudson heritage federal credit union": "Hudson Heritage Federal Credit Union",
        "hughes federal credit union": "Hughes Federal Credit Union",
        "huntingdon valley bank": "Huntingdon Valley Bank",
        "ic federal credit union": "IC Federal Credit Union",
        "idb bank": "IDB Bank (Industrial Bank of Israel)",
        "idb bank industrial bank of israel": "IDB Bank (Industrial Bank of Israel)",
        "ih mississippi valley credit union": "IH Mississippi Valley Credit Union",
        "illinois state credit union": "Illinois State Credit Union",
        "incrediblebank": "IncredibleBank",
        "industrial bank": "Industrial Bank (Washington DC)",
        "industrial bank washington dc": "Industrial Bank (Washington DC)",
        "inland northwest bank": "Inland Northwest Bank",
        "inspirus credit union": "Inspirus Credit Union",
        "integrity bank for business": "Integrity Bank for Business",
        "interamerican bank": "Interamerican Bank (Miami)",
        "interamerican bank miami": "Interamerican Bank (Miami)",
        "international bank of commerce": "International Bank of Commerce (IBC Bank)",
        "international bank of commerce ibc bank": "International Bank of Commerce (IBC Bank)",
        "investar bank": "Investar Bank N.A.",
        "investar bank na": "Investar Bank N.A.",
        "ion bank": "ION Bank",
        "iowa heartland credit union": "Iowa Heartland Credit Union",
        "iowa state bank and trust": "Iowa State Bank & Trust (Iowa City)",
        "iowa state bank and trust iowa city": "Iowa State Bank & Trust (Iowa City)",
        "iron bank": "Iron Bank (St. Louis)",
        "iron bank st louis": "Iron Bank (St. Louis)",
        "ironworkers bank": "Ironworkers Bank",
        "jersey shore state bank": "Jersey Shore State Bank",
        "john marshall bank": "John Marshall Bank",
        "johnson city bank": "Johnson City Bank",
        "joplin metro credit union": "Joplin Metro Credit Union",
        "jupiter miners bank": "Jupiter Miners Bank",
        "national financial services llc": "National Financial Services LLC",
        "national financial serves llc": "National Financial Services LLC",
        "bank of america": "Bank of America",
        "bark of america": "Bank of America",
        "bank of amerlca": "Bank of America",
        "bank of amerlca na": "Bank of America",

        # --- Major HSA / Financial Admins ---
        "healthequity corporate": "HealthEquity Corporate",
        "healthequity corp": "HealthEquity Corporate",
        "health equity corporate": "HealthEquity Corporate",
        "health equity corp": "HealthEquity Corporate",
        "healthequity": "HealthEquity Inc.",
        "healthequity inc": "HealthEquity Inc.",
        "optum bank": "Optum Bank Inc.",
        "optum bank inc": "Optum Bank Inc.",
        "fidelity investments": "Fidelity Investments",
        "webster bank": "Webster Bank N.A.",
        "webster bank n a": "Webster Bank N.A.",
        "lively hsa": "Lively HSA Inc.",
        "lively hsa inc": "Lively HSA Inc.",

        # --- Large Banks ---
        "umb bank": "UMB Bank N.A.",
        "umb bank n a": "UMB Bank N.A.",
        "first american bank": "First American Bank",
        "wells fargo": "Wells Fargo Bank N.A.",
        "wells fargo bank": "Wells Fargo Bank N.A.",
        "jpmorgan chase": "JPMorgan Chase Bank N.A.",
        "chase bank": "JPMorgan Chase Bank N.A.",
        "associated bank": "Associated Bank N.A.",
        "fifth third": "Fifth Third Bank N.A.",
        "keybank": "KeyBank N.A.",
        "bend hsa": "Bend HSA Inc.",
        "elements financial": "Elements Financial Credit Union",
        "patelco": "Patelco Credit Union",
        "digital federal credit union": "Digital Federal Credit Union (DCU)",
        "america first credit union": "America First Credit Union",
        "golden 1 credit union": "Golden 1 Credit Union",
        "truist": "Truist Bank",
        "pnc": "PNC Bank N.A.",
        "regions bank": "Regions Bank",
        "us bank": "US Bank N.A.",
        "comerica": "Comerica Bank",
        "citizens bank": "Citizens Bank N.A.",
        "first horizon": "First Horizon Bank",
        "hancock whitney": "Hancock Whitney Bank",
        "zions bank": "Zions Bank N.A.",
        "frost bank": "Frost Bank",
        "old national": "Old National Bank",
        "synovus": "Synovus Bank",
        "commerce bank": "Commerce Bank",
        "first interstate": "First Interstate Bank",
        "glacier bank": "Glacier Bank",
        "banner bank": "Banner Bank",
        "first citizens": "First Citizens Bank",
        "huntington national": "Huntington National Bank",

        # --- Credit Unions ---
        "associated healthcare credit union": "Associated Healthcare Credit Union",
        "advia credit union": "Advia Credit Union",
        "premier america credit union": "Premier America Credit Union",
        "bethpage federal credit union": "Bethpage Federal Credit Union",
        "mountain america credit union": "Mountain America Credit Union",
        "alliant credit union": "Alliant Credit Union",
        "penfed": "PenFed Credit Union",
        "navy federal": "Navy Federal Credit Union",
        "schoolsfirst": "SchoolsFirst Federal Credit Union",
        "becu": "Boeing Employees Credit Union (BECU)",
        "boeing employees credit union": "Boeing Employees Credit Union (BECU)",
        "space coast": "Space Coast Credit Union",
        "redstone federal": "Redstone Federal Credit Union",
        "desert financial": "Desert Financial Credit Union",
        "gesa credit union": "Gesa Credit Union",
        "bellco credit union": "Bellco Credit Union",
        "ent credit union": "Ent Credit Union",
        "vystar credit union": "VyStar Credit Union",
        "randolph brooks": "Randolph-Brooks Federal Credit Union",
        "american airlines federal credit union": "American Airlines Federal Credit Union",
        "delta community credit union": "Delta Community Credit Union",
        "state employees credit union": "State Employees’ Credit Union (SECU)",
        "vantage west": "Vantage West Credit Union",
        "oregon community": "Oregon Community Credit Union",
        "truwest": "TruWest Credit Union",

        # --- MSA / Health-related Plans ---
        "lasso healthcare": "Lasso Healthcare MSA",
        "unitedhealthcare": "UnitedHealthcare MSA Plans",
        "humana": "Humana MSA Plans",
        "blue cross blue shield": "Blue Cross Blue Shield MSA Plans",
        "vibrant usa": "Vibrant USA MSA Plans",
        "wex": "WEX Inc.",
                # --- Additional Financial Institutions (Extension Set) ---
        "pioneer trust bank": "Pioneer Trust Bank (ND)",
        "pioneer trust bank nd": "Pioneer Trust Bank (ND)",

        "planters first bank": "Planters First Bank",
        "platte valley bank": "Platte Valley Bank (NE)",
        "platte valley bank ne": "Platte Valley Bank (NE)",
        "platte valley national bank": "Platte Valley National Bank",

        "pnc financial services": "PNC Financial Services Group",
        "pnc financial services group": "PNC Financial Services Group",

        "point breeze credit union": "Point Breeze Credit Union (MD)",
        "point breeze credit union md": "Point Breeze Credit Union (MD)",
        "police and fire federal credit union": "Police and Fire Federal Credit Union",
        "popular bank": "Popular Bank (NY)",
        "popular bank ny": "Popular Bank (NY)",

        "port washington state bank": "Port Washington State Bank",
        "prairie bank": "Prairie Bank",
        "prairie mountain bank": "Prairie Mountain Bank",

        "premier bank": "Premier Bank (Rochester MN)",
        "premier bank rochester": "Premier Bank (Rochester MN)",
        "premier bank rochester mn": "Premier Bank (Rochester MN)",

        "premier members credit union": "Premier Members Credit Union (CO)",
        "premier members credit union co": "Premier Members Credit Union (CO)",

        "presidential bank": "Presidential Bank (FSB)",
        "presidential bank fsb": "Presidential Bank (FSB)",

        "primeway federal credit union": "PrimeWay Federal Credit Union (TX)",
        "primeway federal credit union tx": "PrimeWay Federal Credit Union (TX)",

        "princeton state bank": "Princeton State Bank",
        "professional bank": "Professional Bank (FL)",
        "professional bank fl": "Professional Bank (FL)",
        "progressive bank": "Progressive Bank (LA)",
        "progressive bank la": "Progressive Bank (LA)",
        "prosperity bank": "Prosperity Bank (TX)",
        "prosperity bank tx": "Prosperity Bank (TX)",

        "provident bank of maryland": "Provident Bank of Maryland",
        "provident credit union": "Provident Credit Union (CA)",
        "provident credit union ca": "Provident Credit Union (CA)",

        "ps bank": "PS Bank (Pa.)",
        "ps bank pa": "PS Bank (Pa.)",
        "public service credit union": "Public Service Credit Union (CO)",
        "public service credit union co": "Public Service Credit Union (CO)",

        "publix employees federal credit union": "Publix Employees Federal Credit Union",
        "puget sound bank": "Puget Sound Bank",

        "quad city bank": "Quad City Bank and Trust",
        "quad city bank and trust": "Quad City Bank and Trust",

        "queenstown bank of maryland": "Queenstown Bank of Maryland",
        "quincy state bank": "Quincy State Bank (FL)",
        "quincy state bank fl": "Quincy State Bank (FL)",

        "quorum federal credit union": "Quorum Federal Credit Union (NY)",
        "quorum federal credit union ny": "Quorum Federal Credit Union (NY)",

        "raccoon valley bank": "Raccoon Valley Bank",
        "randolph savings bank": "Randolph Savings Bank",

        "raymond james bank": "Raymond James Bank",
        "red river bank": "Red River Bank",
        "red river employees federal credit union": "Red River Employees Federal Credit Union",

        "redwood capital bank": "Redwood Capital Bank",
        "reliabank dakota": "Reliabank Dakota",
        "reliant community credit union": "Reliant Community Credit Union (NY)",
        "reliant community credit union ny": "Reliant Community Credit Union (NY)",

        "republic bank of arizona": "Republic Bank of Arizona",
        "republic bank of chicago": "Republic Bank of Chicago",

                # --- Additional Banks and Credit Unions (Requested) ---
        "republic first bank": "Republic First Bank (Philadelphia PA)",
        "republic first bank philadelphia": "Republic First Bank (Philadelphia PA)",
        "republic first bank philadelphia pa": "Republic First Bank (Philadelphia PA)",

        "resurgens bank": "Resurgens Bank",
        "ridgewood savings bank": "Ridgewood Savings Bank (NY)",
        "ridgewood savings bank ny": "Ridgewood Savings Bank (NY)",

        "rising community federal credit union": "Rising Community Federal Credit Union",
        "river bank": "River Bank (WI)",
        "river bank wi": "River Bank (WI)",
        "river city federal credit union": "River City Federal Credit Union (TX)",
        "river city federal credit union tx": "River City Federal Credit Union (TX)",
        "river falls state bank": "River Falls State Bank",
        "river valley credit union": "River Valley Credit Union (OH)",
        "river valley credit union oh": "River Valley Credit Union (OH)",
        "riverland federal credit union": "RiverLand Federal Credit Union (LA)",
        "riverland federal credit union la": "RiverLand Federal Credit Union (LA)",
        "riverset credit union": "Riverset Credit Union (PA)",
        "riverset credit union pa": "Riverset Credit Union (PA)",
        "riverview community bank": "Riverview Community Bank (WA)",
        "riverview community bank wa": "Riverview Community Bank (WA)",
        "rock canyon bank": "Rock Canyon Bank (UT)",
        "rock canyon bank ut": "Rock Canyon Bank (UT)",
        "rockland federal credit union": "Rockland Federal Credit Union (MA)",
        "rockland federal credit union ma": "Rockland Federal Credit Union (MA)",
        "rockville bank": "Rockville Bank",
        "rogue federal credit union": "Rogue Federal Credit Union (OR)",
        "rogue federal credit union or": "Rogue Federal Credit Union (OR)",
        "rolling hills bank": "Rolling Hills Bank and Trust (IA)",
        "rolling hills bank and trust": "Rolling Hills Bank and Trust (IA)",
        "rolling hills bank ia": "Rolling Hills Bank and Trust (IA)",
        "roundbank": "Roundbank (Fairbault MN)",
        "roundbank fairbault": "Roundbank (Fairbault MN)",
        "roundbank fairbault mn": "Roundbank (Fairbault MN)",
        "royal business bank": "Royal Business Bank (CA)",
        "royal business bank ca": "Royal Business Bank (CA)",
                "kahoka state bank": "Kahoka State Bank",
        "katahdin trust co": "Katahdin Trust Co. (HSA Dept.)",
        "katahdin trust co hsa dept": "Katahdin Trust Co. (HSA Dept.)",
        "kaw valley bank": "Kaw Valley Bank",
        "keystone bank": "Keystone Bank (Austin TX)",
        "keystone bank austin": "Keystone Bank (Austin TX)",
        "keystone bank austin tx": "Keystone Bank (Austin TX)",
        "kish bank": "Kish Bank",
        "kitsap credit union": "Kitsap Credit Union",
        "kodabank": "KodaBank",
        "kohler credit union": "Kohler Credit Union",
        "ks statebank": "KS StateBank",
        "la capitol federal credit union": "La Capitol Federal Credit Union",
        "la salle state bank": "La Salle State Bank",
        "labor credit union": "Labor Credit Union",
        "ladue bank": "Ladue Bank",
        "lake city federal bank": "Lake City Federal Bank",
        "lake sunapee bank": "Lake Sunapee Bank",
        "lakeland bank": "Lakeland Bank",
        "lakeside bank of salina": "Lakeside Bank of Salina",
        "lamar bank and trust": "Lamar Bank and Trust Co.",
        "lamar bank and trust co": "Lamar Bank and Trust Co.",
        "landmark national bank": "Landmark National Bank",
        "langley state bank": "Langley State Bank",
        "lansdale bank": "Lansdale Bank",
        "laramie plains federal credit union": "Laramie Plains Federal Credit Union",
        "laramie plains bank": "Laramie Plains Bank",
        "lawson bank": "Lawson Bank",
        "leader one bank": "Leader One Bank",
        "legacy community federal credit union": "Legacy Community Federal Credit Union",
        "legend bank": "Legend Bank",
        "lehigh valley educators credit union": "Lehigh Valley Educators Credit Union",
        "lewiston state bank": "Lewiston State Bank",
        "liberty bank": "Liberty Bank (CT)",
        "liberty bank ct": "Liberty Bank (CT)",
        "liberty national bank": "Liberty National Bank (OH)",
        "liberty national bank oh": "Liberty National Bank (OH)",
        "lincoln national bank": "Lincoln National Bank (Hodgenville KY)",
        "lincoln national bank hodgenville": "Lincoln National Bank (Hodgenville KY)",
        "lincoln national bank hodgenville ky": "Lincoln National Bank (Hodgenville KY)",
        "linn co op credit union": "Linn Co-op Credit Union",
        "lisbon bank and trust": "Lisbon Bank & Trust",
        "little horn state bank": "Little Horn State Bank",
        "lnb community bank": "LNB Community Bank",
        "logan bank and trust": "Logan Bank & Trust Co.",
        "logan bank and trust co": "Logan Bank & Trust Co.",
        "lone star credit union": "Lone Star Credit Union",
        "lormet community federal credit union": "LorMet Community Federal Credit Union",
        "los padres bank": "Los Padres Bank",
        "louisiana federal credit union": "Louisiana Federal Credit Union",
        "louisiana national bank": "Louisiana National Bank",
        "lowell five savings bank": "Lowell Five Savings Bank",
        "luther burbank savings": "Luther Burbank Savings",
        "lyons national bank": "Lyons National Bank",
        "macon bank and trust": "Macon Bank & Trust Co.",
        "macon bank and trust co": "Macon Bank & Trust Co.",
        "magnolia bank": "Magnolia Bank Inc.",
        "magnolia bank inc": "Magnolia Bank Inc.",
        "main street bank": "Main Street Bank (MA)",
        "main street bank ma": "Main Street Bank (MA)",
        "malvern bank": "Malvern Bank (National Association)",
        "malvern bank national association": "Malvern Bank (National Association)",
        "manasquan bank": "Manasquan Bank",
        "mansfield bank": "Mansfield Bank",
        "manufacturers bank of lewiston": "Manufacturers Bank of Lewiston",
        "marblehead bank": "Marblehead Bank",
        "marine midland bank": "Marine Midland Bank",
        "marion county bank": "Marion County Bank",
        "markesan state bank": "Markesan State Bank",
        "marquette bank of chicago": "Marquette Bank of Chicago",
        "marshall and ilsley bank": "Marshall & Ilsley Bank",
        "massmutual federal credit union": "MassMutual Federal Credit Union",
        "mayville state bank": "Mayville State Bank",
        "mcfarland state bank": "McFarland State Bank",
        "mcintosh county bank": "McIntosh County Bank",
        "mediapolis savings bank": "Mediapolis Savings Bank",
        "members 1st federal credit union": "Members 1st Federal Credit Union",
        "members choice credit union": "Members Choice Credit Union",
        "members heritage credit union": "Members Heritage Credit Union",
        "merrimack county savings bank": "Merrimack County Savings Bank",
        "metairie bank and trust": "Metairie Bank & Trust Co.",
        "metairie bank and trust co": "Metairie Bank & Trust Co.",
        "metro health services federal credit union": "Metro Health Services Federal Credit Union",
        "metropolitan commercial bank": "Metropolitan Commercial Bank",
        "meyers savings bank": "Meyers Savings Bank",
        "michigan schools and government credit union": "Michigan Schools & Government Credit Union",
        "midamerica credit union": "MidAmerica Credit Union",
        "midcountry federal credit union": "MidCountry Federal Credit Union",


        "midfirst credit union": "MidFirst Credit Union",


        "midland community credit union": "Midland Community Credit Union",


        "midminnesota federal credit union": "MidMinnesota Federal Credit Union",


        "midsouth bank": "MidSouth Bank",


        "midstate bank": "Midstate Bank",


        "midstates bank": "Midstates Bank N.A.",


        "midstates bank na": "Midstates Bank N.A.",


        "midwestone credit union": "MidWestOne Credit Union",


        "millbury federal credit union": "Millbury Federal Credit Union",


        "minnco credit union": "Minnco Credit Union",


        "minnesota bank and trust": "Minnesota Bank & Trust",


        "minnstar bank": "MinnStar Bank N.A.",


        "minnstar bank na": "MinnStar Bank N.A.",


        "mississippi federal credit union": "Mississippi Federal Credit Union",


        "modern woodmen bank": "Modern Woodmen Bank",


        "monroe bank and trust": "Monroe Bank & Trust",


        "monroe federal savings bank": "Monroe Federal Savings Bank",


        "montana credit union": "Montana Credit Union",


        "mountain valley bank": "Mountain Valley Bank (NH)",


        "mountain valley bank nh": "Mountain Valley Bank (NH)",


        "mountain west bank": "Mountain West Bank (ID)",


        "mountain west bank id": "Mountain West Bank (ID)",


        "mutual bank": "Mutual Bank (MA)",


        "mutual bank ma": "Mutual Bank (MA)",


        "mutual federal savings bank": "Mutual Federal Savings Bank",


        "nantucket bank": "Nantucket Bank",


        "national bank of commerce": "National Bank of Commerce (Duluth MN)",


        "national bank of commerce duluth": "National Bank of Commerce (Duluth MN)",


        "national bank of middlebury": "National Bank of Middlebury",


        "national exchange bank and trust": "National Exchange Bank & Trust",


        "national grid us federal credit union": "National Grid US Federal Credit Union",


        "national jersey bank": "National Jersey Bank",


        "national parks federal credit union": "National Parks Federal Credit Union",


        "nebraska bank": "Nebraska Bank",


        "nebraska energy federal credit union": "Nebraska Energy Federal Credit Union",


        "neighborhood national bank": "Neighborhood National Bank",


        "netbank federal savings bank": "NetBank Federal Savings Bank",


        "new alliance bank": "New Alliance Bank",


        "new century bank": "New Century Bank",


        "new dominion bank": "New Dominion Bank",


        "new haven county credit union": "New Haven County Credit Union",


        "new milford bank and trust": "New Milford Bank & Trust Co.",


        "new tripoli bank": "New Tripoli Bank",


        "new york community bank": "New York Community Bank",


        "newburyport five cents savings bank": "Newburyport Five Cents Savings Bank",


        "newtown savings bank": "Newtown Savings Bank",


        "nicolet federal credit union": "Nicolet Federal Credit Union",


        "nodaway valley bank": "Nodaway Valley Bank",


        "north american bank and trust": "North American Bank & Trust Co.",


        "north brookfield savings bank": "North Brookfield Savings Bank",


        "north community bank": "North Community Bank",


        "north country federal credit union": "North Country Federal Credit Union",


        "north easton savings bank": "North Easton Savings Bank",


        "north island federal credit union": "North Island Federal Credit Union",


        "north shore federal credit union": "North Shore Federal Credit Union",


        "north state bank": "North State Bank (NC)",


        "north state bank nc": "North State Bank (NC)",


        "northeast bank": "Northeast Bank (ME)",


        "northeast bank me": "Northeast Bank (ME)",


        "northern interstate bank": "Northern Interstate Bank N.A.",


        "northern interstate bank na": "Northern Interstate Bank N.A.",


        "northern skies federal credit union": "Northern Skies Federal Credit Union",


        "northern trust bank": "Northern Trust Bank",


        "northfield savings bank": "Northfield Savings Bank (VT)",


        "northfield savings bank vt": "Northfield Savings Bank (VT)",


        "northland area federal credit union": "Northland Area Federal Credit Union",


        "northwest community credit union": "Northwest Community Credit Union (OR)",


        "northwest community credit union or": "Northwest Community Credit Union (OR)",


        "northwest federal credit union": "Northwest Federal Credit Union (VA)",


        "northwest federal credit union va": "Northwest Federal Credit Union (VA)",


        "norway savings bank": "Norway Savings Bank",


        "notre dame federal credit union": "Notre Dame Federal Credit Union (IN)",


        "notre dame federal credit union in": "Notre Dame Federal Credit Union (IN)",


        "nuvision credit union": "NuVision Credit Union (CA)",


        "nuvision credit union ca": "NuVision Credit Union (CA)",


        "oak bank": "Oak Bank (WI)",


        "oak bank wi": "Oak Bank (WI)",


        "oakstar bank": "OakStar Bank",


        "ocean financial federal credit union": "Ocean Financial Federal Credit Union",


        "oceanfirst bank": "OceanFirst Bank (NJ)",


        "oceanfirst bank nj": "OceanFirst Bank (NJ)",


        "oceanview federal credit union": "OceanView Federal Credit Union",


        "ohio catholic federal credit union": "Ohio Catholic Federal Credit Union",


        "ohio savings bank": "Ohio Savings Bank",


        "old dominion national bank": "Old Dominion National Bank",


        "old point trust": "Old Point Trust and Financial Services",


        "old point trust and financial services": "Old Point Trust and Financial Services",


        "old second national bank": "Old Second National Bank (IL)",


        "old second national bank il": "Old Second National Bank (IL)",


        "old west federal credit union": "Old West Federal Credit Union",


        "olean area federal credit union": "Olean Area Federal Credit Union",


        "onpoint community credit union": "OnPoint Community Credit Union",


        "orange bank and trust": "Orange Bank & Trust Company",


        "orange bank and trust company": "Orange Bank & Trust Company",


        "oregon pacific bank": "Oregon Pacific Bank",


        "oriental bank": "Oriental Bank (Puerto Rico division excluded)",


        "oriental bank puerto rico": "Oriental Bank (Puerto Rico division excluded)",


        "orrstown bank": "Orrstown Bank",
        "oswego county federal credit union": "Oswego County Federal Credit Union",
        "ouachita valley federal credit union": "Ouachita Valley Federal Credit Union",
        "ozark bank": "Ozark Bank",
        "ozark federal credit union": "Ozark Federal Credit Union",
        "pacific crest federal credit union": "Pacific Crest Federal Credit Union",
        "pacific premier bank": "Pacific Premier Bank",
        "pacific service credit union": "Pacific Service Credit Union",
        "pacific valley bank": "Pacific Valley Bank",
        "palmetto citizens federal credit union": "Palmetto Citizens Federal Credit Union",
        "palo savings bank": "Palo Savings Bank",
        "park national bank": "Park National Bank",
        "parkway bank and trust": "Parkway Bank & Trust Co.",
        "parkway bank and trust co": "Parkway Bank & Trust Co.",
        "partners federal credit union": "Partners Federal Credit Union",
        "pathways financial credit union": "Pathways Financial Credit Union",
        "patriot bank": "Patriot Bank (Norwalk CT)",
        "patriot bank norwalk": "Patriot Bank (Norwalk CT)",
        "patriot bank norwalk ct": "Patriot Bank (Norwalk CT)",
        "paul federated credit union": "Paul Federated Credit Union",
        "peach state federal credit union": "Peach State Federal Credit Union",
        "peapack gladstone financial corp": "Peapack-Gladstone Financial Corp.",
        "pella state bank": "Pella State Bank",
        "penair federal credit union": "PenAir Federal Credit Union",
        "peninsula federal credit union": "Peninsula Federal Credit Union",
        "peoples bank": "Peoples Bank (Bellingham WA)",
        "peoples bank bellingham": "Peoples Bank (Bellingham WA)",
        "peoples bank bellingham wa": "Peoples Bank (Bellingham WA)",
        "peoples bank of alabama": "Peoples Bank of Alabama",
        "peoples bank of kankakee": "Peoples Bank of Kankakee County",
        "peoples bank of kankakee county": "Peoples Bank of Kankakee County",
        "peoples community bank": "Peoples Community Bank (MO)",
        "peoples community bank mo": "Peoples Community Bank (MO)",
        "peoples exchange bank": "Peoples Exchange Bank",
        "peoples national bank": "Peoples National Bank (TN)",
        "peoples national bank tn": "Peoples National Bank (TN)",
        "peoples state bank": "Peoples State Bank (IN)",
        "peoples state bank in": "Peoples State Bank (IN)",
        "peoples trust federal credit union": "Peoples Trust Federal Credit Union",
        "perkins state bank": "Perkins State Bank",
        "perpetual federal savings bank": "Perpetual Federal Savings Bank",
        "piedmont advantage credit union": "Piedmont Advantage Credit Union",
        "pima federal credit union": "Pima Federal Credit Union",
        "pinnacle bank": "Pinnacle Bank (NE)",
        "pinnacle bank ne": "Pinnacle Bank (NE)",
        "pioneer bank": "Pioneer Bank (NY)",
        "pioneer bank ny": "Pioneer Bank (NY)",
        "pioneer credit union": "Pioneer Credit Union",
        "pioneer federal credit union": "Pioneer Federal Credit Union (ID)",
        "pioneer federal credit union id": "Pioneer Federal Credit Union (ID)"

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
    """
    Extract lender name for Form 1098-Mortgage.
    Prints which rule fired for debugging.
    Detects lenders like 'NEWREZ LLC DBA SHELLPOINT MORTGAGE SERVICING'.
    """
    lines: List[str] = text.splitlines()
    lower_lines = [L.lower() for L in lines]
    bookmark = ""

    # 7) PHH Mortgage Corporation override
    for L in lines:
        if re.search(r"\bphh\s+mortgage\s+corporation\b", L, flags=re.IGNORECASE):
            bookmark = "PHH MORTGAGE CORPORATION"
            print(f"[1098-MORTGAGE] Rule: PHH Mortgage override → {bookmark}", file=sys.stderr)
            return finalize_bookmark(bookmark)
    # 1) Rocket Mortgage override
    for L in lines:
        if re.search(r"rocket\s+mortgage", L, flags=re.IGNORECASE):
            bookmark = "ROCKET MORTGAGE LLC"
            print(f"[1098-MORTGAGE] Rule: Rocket Mortgage override → {bookmark}", file=sys.stderr)
            return finalize_bookmark(bookmark)

    # 2) Dovenmuehle Mortgage override
    for L in lines:
        if re.search(r"dovenmuehle\s+mortgage", L, flags=re.IGNORECASE):
            bookmark = "DOVENMUEHLE MORTGAGE, INC"
            print(f"[1098-MORTGAGE] Rule: Dovenmuehle override → {bookmark}", file=sys.stderr)
            return finalize_bookmark(bookmark)

    # 3) Huntington National Bank override
    for L in lines:
        if re.search(r"\bhuntington\s+national\s+bank\b", L, flags=re.IGNORECASE):
            bookmark = "THE HUNTINGTON NATIONAL BANK"
            print(f"[1098-MORTGAGE] Rule: Huntington Bank override → {bookmark}", file=sys.stderr)
            return finalize_bookmark(bookmark)

    # 4) UNITED NATIONS FCU override
    for L in lines:
        if re.search(r"\bunited\s+nations\s+fcu\b", L, flags=re.IGNORECASE):
            bookmark = "UNITED NATIONS FCU"
            print(f"[1098-MORTGAGE] Rule: United Nations FCU override → {bookmark}", file=sys.stderr)
            return finalize_bookmark(bookmark)

    # 5) LOANDEPOT COM LLC override
    for L in lines:
        if re.search(r"\bloan\s*depot\s*com\s*llc\b", L, flags=re.IGNORECASE):
            bookmark = "LOANDEPOT.COM LLC"
            print(f"[1098-MORTGAGE] Rule: LoanDepot override → {bookmark}", file=sys.stderr)
            return finalize_bookmark(bookmark)

    # 6) JPMORGAN CHASE BANK, N.A.
    for L in lines:
        if re.search(r"jp\s*morgan\s+chase", L, flags=re.IGNORECASE):
            bookmark = "JPMORGAN CHASE BANK, N.A."
            print(f"[1098-MORTGAGE] Rule: JPMorgan Chase override → {bookmark}", file=sys.stderr)
            return finalize_bookmark(bookmark)
            # 🔹 NEW Rule: handle "RECIPIENT'S/LENDER'S name..." header pattern
    # 8) FOR RETURN SERVICE ONLY override
    for L in lines:
        if re.search(r"\bfor\s+return\s+service\s+only\b", L, flags=re.IGNORECASE):
            bookmark = "FOR RETURN SERVICE ONLY"
            print(f"[1098-MORTGAGE] Rule: FOR RETURN SERVICE ONLY override → {bookmark}", file=sys.stderr)
            return finalize_bookmark(bookmark)
    # 9) Citizens Bank override
        # 8) Citizens Bank override
    for L in lines:
        # Match clean and OCR-distorted variations of 'Citizens Bank'
        if re.search(r"cit[i1l]zens?\s*(bank|banx|banc)", L, flags=re.IGNORECASE):
            bookmark = "CITIZENS BANK, N.A."
            print(f"[1098-MORTGAGE] Rule: Citizens Bank override → {bookmark}", file=sys.stderr)
            return finalize_bookmark(bookmark)

    for i, line in enumerate(lines):
        lline = line.lower()

    # detect the header line for lender section
        if "foreign postal code" in lline and "telephone" in lline:
        # --- CASE 1: lender name might be on the next line ---
            if i + 1 < len(lines):
                nxt = lines[i + 1].strip()

            # 🧹 Remove common junk that appears after lender name
                nxt = re.sub(
                    r"(?i)\band\s+the\s+cost.*|Form.*|OMB.*|Department.*|Treasury.*|Caution.*|may\s+not\s+be\s+fully.*",
                    "",
                    nxt
                ).strip(" *-,.:;")

            # if next line has lender-like keywords, it’s the company name
                if re.search(r"(bank|mortgage|servicing|loan|llc|fcu|credit|trust|dba|company|corp|inc)", nxt, re.IGNORECASE):
                    print(f"[1098-MORTGAGE] Rule: Next line after FOREIGN POSTAL header → {nxt}", file=sys.stderr)
                    return finalize_bookmark(trim_lender_text(nxt))

        # --- CASE 2: lender name might be on the same line (rare OCR merge) ---
        if re.search(r"(bank|mortgage|servicing|loan|llc|fcu|credit|trust|dba|company|corp|inc)", line, re.IGNORECASE):
            # Trim the header portion and keep the right-side company name
            same_line = re.sub(
                r"(?i)^.*telephone\s*(no\.?|number)?:?\s*",
                "",
                line
            )
            same_line = re.sub(
                r"(?i)\band\s+the\s+cost.*|may\s+not\s+be\s+fully.*|Form.*|Department.*|Treasury.*|Caution.*",
                "",
                same_line
            ).strip(" *-,.:;")

            print(f"[1098-MORTGAGE] Rule: Inline FOREIGN POSTAL line → {same_line}", file=sys.stderr)
            return finalize_bookmark(trim_lender_text(same_line))

    
# --- Improved lender extraction around FOREIGN POSTAL header ---
    for i, line in enumerate(lines):
        lline = line.lower()

        if "foreign postal code" in lline and "mortgage" in lline:
            # Look up to 5 lines below (OCR lines may shift)
            for j in range(1, 5):
                if i + j < len(lines):
                    nxt = lines[i + j].strip()

                    # Clean obvious junk
                    nxt = re.sub(
                        r"and\s+the\s+cost.*|Form.*|OMB.*|Department.*|Treasury.*|Caution.*|may\s+not\s+be\s+fully\s+deductible.*|Limits\s+based.*|1\s*0*98\s*Mortgage.*|Interest\s+Received\s+From.*|Outstanding\s+Mortgage.*|Payer.*|Borrower.*|Box\s*\d+",
                        "",
                        nxt,
                        flags=re.IGNORECASE
                    ).strip(" *-,")
                    if len(nxt) < 4:
                        continue

                # If it contains company indicators, merge continuation lines
                    if re.search(r"(llc|bank|mortgage|servicing|fcu|trust|credit|dba|company|corp)", nxt, re.IGNORECASE):
                        merged = nxt
                        # Merge up to next two lines if they continue the name
                        for k in range(1, 3):
                            if i + j + k < len(lines):
                                nxt2 = lines[i + j + k].strip()
                                if re.search(r"(mortgage|servicing|bank|llc|trust|credit|company|dba|corp|inc)", nxt2, re.IGNORECASE):
                                    merged += " " + nxt2
                                else:
                                    break

                        print(f"[1098-MORTGAGE] Rule: Found lender after FOREIGN POSTAL header → {merged}", file=sys.stderr)
                        #return finalize_bookmark()
                        return finalize_bookmark(trim_lender_text(merged))


    for i, line in enumerate(lines):
        lline = line.lower()

        if "recipient" in lline and "lender" in lline and "telephone" in lline:
            # check the same line for lender name (sometimes merged)
            if re.search(r"(bank|mortgage|servicing|loan|llc|fcu|credit|trust)", line, re.IGNORECASE):
                # Extract only up to the first "may not be fully deductible" or "OMB" etc.
                cleaned = re.split(
                    r"may\s+not\s+be\s+fully\s+deductible|OMB|Form|Department|Treasury|Caution",
                    line,
                    maxsplit=1,
                    flags=re.IGNORECASE
                )[0].strip(" *-,")

                # If name seems valid, finalize it
                if len(cleaned) > 5 and re.search(r"[A-Za-z]{3,}", cleaned):
                    print(f"[1098-MORTGAGE] Rule: Inline RECIPIENT/LENDER line → {cleaned}", file=sys.stderr)
                    return finalize_bookmark(cleaned)

            # otherwise look at next line (most common pattern)
            if i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                nxt = re.sub(
                    r"may\s+not\s+be\s+fully\s+deductible.*|OMB.*|Form.*|Department.*|Treasury.*|Caution.*",
                    "",
                    nxt,
                    flags=re.IGNORECASE
                ).strip(" *-,")

                if re.search(r"(bank|mortgage|servicing|loan|llc|fcu|credit|trust)", nxt, re.IGNORECASE):
                    print(f"[1098-MORTGAGE] Rule: Next-line after RECIPIENT/LENDER header → {nxt}", file=sys.stderr)
                    #return finalize_bookmark(nxt)
                    return finalize_bookmark(trim_lender_text(nxt))



    for i, line in enumerate(lines):
        lline = line.lower()

        # match the header line that includes the phrase "foreign postal code, and telephone no."
        if "foreign postal code" in lline and "telephone" in lline:
            # check the same line for any lender name words (rare but possible)
            if re.search(r"(bank|mortgage|servicing|loan|llc|fcu|credit|trust|dba|company|corp)", line, re.IGNORECASE):
                cleaned = re.split(
                    r"limits\s+based|may\s+not\s+be\s+fully\s+deductible|OMB|Form|Department|Treasury|Caution",
                    line,
                    maxsplit=1,
                    flags=re.IGNORECASE
                )[0].strip(" *-,")
                if len(cleaned) > 5 and re.search(r"[A-Za-z]{3,}", cleaned):
                    print(f"[1098-MORTGAGE] Rule: Inline FOREIGN POSTAL line → {cleaned}", file=sys.stderr)
                    #return finalize_bookmark(cleaned)
                    return finalize_bookmark(trim_lender_text(cleaned))

            # otherwise look at the next line (typical OCR pattern)
            if i + 1 < len(lines):
                nxt = lines[i + 1].strip()

                # remove OCR junk like “and the cost…” or “Form…”
                nxt = re.sub(
                    r"and\s+the\s+cost.*|Form.*|OMB.*|Department.*|Treasury.*|Caution.*|may\s+not\s+be\s+fully\s+deductible.*",
                    "",
                    nxt,
                    flags=re.IGNORECASE
                ).strip(" *-,")

                # check if line contains any lender indicators
                if re.search(r"(bank|mortgage|servicing|loan|llc|fcu|credit|trust|dba|company|corp)", nxt, re.IGNORECASE):
                    # optionally merge with next line if it continues (like "MORTGAGE SERVICING")
                    if i + 2 < len(lines):
                        nxt2 = lines[i + 2].strip()
                        if re.search(
                            r"(mortgage|servicing|bank|llc|fcu|credit|company|association|trust|loan)",
                            nxt2,
                            re.IGNORECASE,
                        ):
                            nxt = f"{nxt} {nxt2}"
                    print(f"[1098-MORTGAGE] Rule: Next-line after FOREIGN POSTAL header → {nxt}", file=sys.stderr)
                    return finalize_bookmark(trim_lender_text(nxt))


    # 9) FCU fallback
    for L in lines:
        if re.search(r"\bfcu\b", L, flags=re.IGNORECASE):
            m = re.search(r"(.*?FCU)\b", L, flags=re.IGNORECASE)
            bookmark = m.group(1) if m else L.strip()
            print(f"[1098-MORTGAGE] Rule: FCU fallback → {bookmark}", file=sys.stderr)
            return finalize_bookmark(trim_lender_text(bookmark))

    # 11) Global fallback: scan all lines for any valid lender name if earlier logic failed
    for L in lines:
        if re.search(r"(bank|mortgage|servicing|llc|fcu|trust|corp|company|association|credit|dba|corporation)", L, re.IGNORECASE):
        # Skip if line looks like IRS or instruction text
            if re.search(r"(department of the treasury|irs|payer|borrower|form 1098|instructions)", L, re.IGNORECASE):
                continue
            clean = re.sub(r"[^A-Za-z0-9&.,' ]+", " ", L).strip()
            if len(clean) > 8:
                print(f"[1098-MORTGAGE] Rule: Global lender fallback → {clean}", file=sys.stderr)
                #return finalize_bookmark(clean)
                return finalize_bookmark(trim_lender_text(clean))
    # Final fallback if nothing matched
    return finalize_bookmark(trim_lender_text(bookmark or text))


def trim_lender_text(raw: str) -> str:
    """
    Clean OCR text to isolate the lender name for 1098-Mortgage.
    Keeps real names like 'NVR Mortgage Finance, Inc'
    but trims junk like 'On The Loan Amount Mortgage West Gate Bank...'
    """
    if not raw or not isinstance(raw, str):
        return ""

    cleaned = raw.strip()

    # --- Step 1: detect if 'Mortgage' seems part of company name ---
    # If 'Mortgage' is followed by Finance, LLC, Inc, Bank, Company, etc. -> keep everything
    if re.search(r"(?i)mortgage\s+(finance|llc|inc|bank|company|corp|servicing)", cleaned):
        pass  # Don't trim anything
    else:
        # --- Step 2: only trim prefixes if there are junk words before 'Mortgage'
        # (like "On The Loan Amount Mortgage West Gate Bank...")
        if re.search(r"(?i)(on the|loan amount|understanding|page|box|form)", cleaned):
            cleaned = re.sub(r"(?i)^.*?\bmortgage\b\s*", "", cleaned)

    # --- Step 3: remove junk that appears *after* company name ---
    cleaned = re.split(
        r"(?i)\band\s+the\s+cost|\bmay\s+not\s+be\s+fully|\blimits\s+based|\byou\s+may\s+only|\bform\b|\bdepartment\b|\btreasury\b|\bcaution\b",
        cleaned,
        maxsplit=1
    )[0]

    # --- Step 4: fix OCR noise ---
    cleaned = cleaned.replace(" ang ", " and ").replace(" apoly", " apply")
    cleaned = cleaned.replace(" may ", " ")

    # --- Step 5: remove boilerplate phrases ---
    phrases_to_trim = [
        "on the loan amount",
        "limits based",
        "interest statement",
        "mortgage interest statement",
        "internal revenue service",
        "form 1098",
        "keep for your records",
        "statement",
        "page",
    ]
    for phrase in phrases_to_trim:
        cleaned = re.sub(phrase, "", cleaned, flags=re.IGNORECASE)

    # --- Step 6: normalize spaces/punctuation ---
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,.-")

    return cleaned



def finalize_bookmark(bookmark: str) -> str:
    """Final cleanup of extracted 1098-Mortgage bookmark without removing 'Mortgage' from real company names."""
    bookmark = clean_bookmark(bookmark)

    # 1) Remove leading boilerplate phrases
    bookmark = re.sub(
        r'^(limits\s+based.*?|caution[:\s].*?|may\s+not\s+be\s+fully\s+deductible.*?)\b',
        '',
        bookmark,
        flags=re.IGNORECASE
    ).strip(" ,.-")

    # 2) Remove trailing boilerplate tails
    bookmark = re.sub(
        r'\b(and\s+the\s+cost.*|may\s+apply.*|you\s+may\s+only.*)$',
        '',
        bookmark,
        flags=re.IGNORECASE
    ).strip(" ,.-")

    # 3) Kill generic headers like "1098 Mortgage" or "Mortgage Interest Statement"
    bookmark = re.sub(
        r'^(?:form\s*)?1098\s*mortgage\b|\bmortgage\s+interest\s+statement\b',
        '',
        bookmark,
        flags=re.IGNORECASE
    ).strip(" ,.-")

    # 4) If we captured a chunk like "... MORTGAGE SERVICING ...", prefer that segment
    m = re.search(
        r'([A-Z][A-Za-z0-9&.,\'\- ]*?\b(?:MORTGAGE\s+SERVICING|MORTGAGE\s+COMPANY|MORTGAGE\s+BANK|MORTGAGE\s+GROUP)\b[^\n,]*)',
        bookmark,
        flags=re.IGNORECASE
    )
    if m:
        bookmark = m.group(1).strip(" ,.-")

    # 5️⃣ Preserve Mortgage in legitimate company names (now includes "Corporation")
    safe_suffixes = r'(LLC|INC\.?|N\.A\.|BANK|SERVICING|COMPANY|CORP\.?|FCU|ASSOCIATION|CORPORATION)'
    if not re.search(rf'\b{safe_suffixes}\b', bookmark, re.IGNORECASE):
        # Safe-strip standalone "Mortgage" if not followed by legit suffix
        bookmark = re.sub(
            rf'\bmortgage\b(?!\s+{safe_suffixes}\b)',
            '',
            bookmark,
            flags=re.IGNORECASE
        )
        bookmark = re.sub(r'\s{2,}', ' ', bookmark).strip(" ,.-")

    # 6) Trim internal noise fragments
    noise_markers = [
        "not be fully deductible",
        "limits based on",
        "interest received from",
        "outstanding mortgage principal",
        "payer",
        "borrower",
        "department of the treasury",
        "irs",
    ]
    low = bookmark.lower()
    for marker in noise_markers:
        idx = low.find(marker)
        if idx != -1:
            bookmark = bookmark[:idx].strip(" ,.-")
            break

    # 7) Normalize spacing
    bookmark = re.sub(r'\s{2,}', ' ', bookmark).strip(" ,.-")

    # 8) Smart-case: Title-case but preserve common suffixes
    def smart_case(s: str) -> str:
        s = s.title()
        replacements = {
            r'\bLlc\b': 'LLC',
            r'\bInc\b\.?': 'INC',
            r'\bCorp\b\.?': 'CORP',
            r'\bCorporation\b': 'Corporation',
            r'\bFcu\b': 'FCU',
            r'\bDba\b': 'DBA',
            r'\bN\.?A\b\.?': 'N.A.',
            r'\bUsa\b': 'USA',
        }
        for pat, rep in replacements.items():
            s = re.sub(pat, rep, s)
        return s

    bookmark = smart_case(bookmark)
    return bookmark




def group_by_type(entries: List[Tuple[str,int,str]]) -> Dict[str,List[Tuple[str,int,str]]]:
    d=defaultdict(list)
    for e in entries: d[e[2]].append(e)
    return d
#---------------------------1098-Mortgage----------------------------------#
#---------------------------529-Plan ----------------------------------#
def extract_529_bookmark(text: str) -> str:
    # Try to detect Indiana or state-specific plan first
   

    # Fallback for generic 529 terms
    if re.search(r'\b529\b', text, re.IGNORECASE):
        return "529 Plan"

    # Default fallback
    return "529-Plan"

#---------------------------529-Plan ----------------------------------#
#5498-SA


def clean_bookmark(name: str) -> str:
    """Normalize bookmark string."""
    name = name.strip()
    name = re.sub(r"[^\w\s.&-]", "", name)
    return name

def extract_5498sa_bookmark(text: str) -> str:
    """
    Extract trustee/institution name for Form 5498-SA.
    Works even when the name is glued with address/ZIP or preceded by junk text.
    Cleans common OCR headers like 'Do Not Cut', 'Separate Forms on This Page', etc.
    """
    import re

    # --- Normalize spaces ---
    cleaned = text.replace("\n", " ").replace("  ", " ")
      # --- Step 6: Apply known OCR-based overrides ---
    OVERRIDES = {
    # --- Known OCR Fixes / Existing ---
        # --- New: Bank of New York Mellon variations ---
        "the bank of new york mellon": "The Bank of New York Mellon",
        "the bank of new yok mellon": "The Bank of New York Mellon",   # common OCR missing 'r'
        "bank of new york mellon": "The Bank of New York Mellon",
        "bank of new yok mellon": "The Bank of New York Mellon",
        "coudl u add for thi stex t also": "The Bank of New York Mellon", 
        "healthequity inc": "HealthEquity Inc.",
        "optum bank inc": "Optum Bank Inc.",
        "fidelity investments hsa": "Fidelity Investments HSA",
        "hsa bank": "HSA Bank (Webster Bank N.A.)",
        "hsa bank webster bank": "HSA Bank (Webster Bank N.A.)",
        "hsa bank webster bank na": "HSA Bank (Webster Bank N.A.)",
        "lively hsa inc": "Lively HSA Inc.",
        "bank of america hsa services": "Bank of America HSA Services",
        "umb bank": "UMB Bank N.A.",
        "umb bank na": "UMB Bank N.A.",
        "first american bank": "First American Bank",
        "wells fargo bank": "Wells Fargo Bank N.A.",
        "wells fargo bank na": "Wells Fargo Bank N.A.",
        "jpmorgan chase bank": "JPMorgan Chase Bank N.A.",
        "jpmorgan chase bank na": "JPMorgan Chase Bank N.A.",
        "associated bank": "Associated Bank N.A.",
        "associated bank na": "Associated Bank N.A.",
        "fifth third bank": "Fifth Third Bank N.A.",
        "fifth third bank na": "Fifth Third Bank N.A.",
        "keybank": "KeyBank N.A.",
        "keybank na": "KeyBank N.A.",
        "payflex": "PayFlex (Aetna)",
        "payflex aetna": "PayFlex (Aetna)",
        "benefitwallet": "BenefitWallet (Conduent)",
        "benefitwallet conduent": "BenefitWallet (Conduent)",
        "bend hsa inc": "Bend HSA Inc.",
        "saturna capital": "Saturna Capital (HSA Investing)",
        "saturna capital hsa investing": "Saturna Capital (HSA Investing)",
        "further": "Further (Health Savings Admin by BCBS MN)",
        "further health savings admin": "Further (Health Savings Admin by BCBS MN)",
        "elements financial credit union": "Elements Financial Credit Union",
        "patelco credit union": "Patelco Credit Union",
        "digital federal credit union": "Digital Federal Credit Union (DCU)",
        "digital federal credit union dcu": "Digital Federal Credit Union (DCU)",
        "america first credit union": "America First Credit Union",
        "golden 1 credit union": "Golden 1 Credit Union",
        "truist bank": "Truist Bank",
        "pnc bank": "PNC Bank N.A.",
        "pnc bank na": "PNC Bank N.A.",
        "regions bank": "Regions Bank",
        "us bank": "U.S. Bank N.A.",
        "us bank na": "U.S. Bank N.A.",
        "comerica bank": "Comerica Bank",
        "citizens bank": "Citizens Bank N.A.",
        "citizens bank na": "Citizens Bank N.A.",
        "first horizon bank": "First Horizon Bank",
        "hancock whitney bank": "Hancock Whitney Bank",
        "zions bank": "Zions Bank N.A.",
        "zions bank na": "Zions Bank N.A.",
        "frost bank": "Frost Bank",
        "old national bank": "Old National Bank",
        "synovus bank": "Synovus Bank",
        "bok financial": "BOK Financial (Bank of Oklahoma)",
        "bok financial bank of oklahoma": "BOK Financial (Bank of Oklahoma)",
        "commerce bank": "Commerce Bank",
        "first interstate bank": "First Interstate Bank",
        "glacier bank": "Glacier Bank",
        "banner bank": "Banner Bank",
        "first citizens bank": "First Citizens Bank",
        "huntington national bank": "Huntington National Bank",
        "associated healthcare credit union": "Associated Healthcare Credit Union",
        "advia credit union": "Advia Credit Union",
        "premier america credit union": "Premier America Credit Union",
        "bethpage federal credit union": "Bethpage Federal Credit Union",
        "mountain america credit union": "Mountain America Credit Union",
        "alliant credit union": "Alliant Credit Union",
        "penfed credit union": "PenFed Credit Union",
        "navy federal credit union": "Navy Federal Credit Union",
        "schoolsfirst federal credit union": "SchoolsFirst Federal Credit Union",
        "boeing employees credit union": "Boeing Employees Credit Union (BECU)",
        "boeing employees credit union becu": "Boeing Employees Credit Union (BECU)",
        "space coast credit union": "Space Coast Credit Union",
        "redstone federal credit union": "Redstone Federal Credit Union",
        "desert financial credit union": "Desert Financial Credit Union",
        "gesa credit union": "Gesa Credit Union",
        "bellco credit union": "Bellco Credit Union",
        "ent credit union": "Ent Credit Union",
        "vystar credit union": "VyStar Credit Union",
        "randolph brooks federal credit union": "Randolph-Brooks Federal Credit Union (RBFCU)",
        "randolph brooks federal credit union rbfcu": "Randolph-Brooks Federal Credit Union (RBFCU)",
        "american airlines federal credit union": "American Airlines Federal Credit Union",
        "delta community credit union": "Delta Community Credit Union",
        "state employees credit union": "State Employees’ Credit Union (SECU)",
        "vantage west credit union": "Vantage West Credit Union",
        "oregon community credit union": "Oregon Community Credit Union",
        "truwest credit union": "TruWest Credit Union",
        "lasso healthcare msa": "Lasso Healthcare MSA",
        "unitedhealthcare msa plans": "UnitedHealthcare MSA Plans",
        "humana msa plans": "Humana MSA Plans",
        "blue cross blue shield msa plans": "Blue Cross Blue Shield MSA Plans",
        "vibrant usa msa plans": "Vibrant USA MSA Plans",
        "healthsavings administrators": "HealthSavings Administrators",
        "connectyourcare": "ConnectYourCare (now Optum)",
        "connectyourcare now optum": "ConnectYourCare (now Optum)",
        "benefit resource inc": "Benefit Resource Inc.",
        "hsa authority": "HSA Authority (Old National Bank Division)",
        "hsa authority old national bank division": "HSA Authority (Old National Bank Division)",
        "selectaccount": "SelectAccount (HealthEquity)",
        "selectaccount healthequity": "SelectAccount (HealthEquity)",
        "starship hsa": "Starship HSA",
        "first bank and trust": "First Bank & Trust",
        "peoples bank midwest": "Peoples Bank Midwest",
        "choice bank": "Choice Bank",
        "midwestone bank": "MidWestOne Bank",
        "first financial bank": "First Financial Bank",
        "cadence bank": "Cadence Bank",
        "great southern bank": "Great Southern Bank",
        "independent bank": "Independent Bank",
        "origin bank": "Origin Bank",
        "texas capital bank": "Texas Capital Bank",
        "pinnacle financial partners": "Pinnacle Financial Partners",
        "columbia bank": "Columbia Bank",
        "townebank": "TowneBank",
        "bank ozk": "Bank OZK",
        "firstbank": "FirstBank (TN)",
        "firstbank tn": "FirstBank (TN)",
        "glacier hills credit union": "Glacier Hills Credit Union",
        "security health savings": "Security Health Savings",
        "bell bank": "Bell Bank",
        "banner life insurance co": "Banner Life Insurance Co.",
        "farmers and merchants bank": "Farmers & Merchants Bank",
        "first national bank of omaha": "First National Bank of Omaha",
        "arvest bank": "Arvest Bank",
        "bancorpsouth bank": "BancorpSouth Bank",
        "bank of tampa": "Bank of Tampa",
        "bank of the west": "Bank of the West",
        "bb&t": "BB&T (now Truist)",
        "bb&t now truist": "BB&T (now Truist)",
        "beneficial bank": "Beneficial Bank",
        "bmo harris bank": "BMO Harris Bank N.A.",
        "bmo harris bank na": "BMO Harris Bank N.A.",
        "california bank and trust": "California Bank & Trust",
        "cambridge trust company": "Cambridge Trust Company",
        "capital one bank": "Capital One Bank N.A.",
        "capital one bank na": "Capital One Bank N.A.",
        "centier bank": "Centier Bank",
        "central bank and trust co": "Central Bank & Trust Co.",
        "citizens equity first credit union": "Citizens Equity First Credit Union (CEFCU)",
        "citizens equity first credit union cefcu": "Citizens Equity First Credit Union (CEFCU)",
        "community america credit union": "Community America Credit Union",
        "community bank": "Community Bank N.A.",
        "community bank na": "Community Bank N.A.",
        "cornerstone community credit union": "Cornerstone Community Credit Union",
        "country bank for savings": "Country Bank for Savings",
        "credit human federal credit union": "Credit Human Federal Credit Union",
        "dearborn federal savings bank": "Dearborn Federal Savings Bank",
        "dedham savings bank": "Dedham Savings Bank",
        "deere employees credit union": "Deere Employees Credit Union",
        "denali federal credit union": "Denali Federal Credit Union",
        "dugood federal credit union": "DuGood Federal Credit Union",
        "elevations credit union": "Elevations Credit Union",
        "emprise bank": "Emprise Bank",
        "everence federal credit union": "Everence Federal Credit Union",
        "farm bureau bank": "Farm Bureau Bank FSB",
        "farm bureau bank fsb": "Farm Bureau Bank FSB",
        "first community bank": "First Community Bank",
        "first federal bank of the midwest": "First Federal Bank of the Midwest",
        "first merchants bank": "First Merchants Bank",
        "first mid bank and trust": "First Mid Bank & Trust",
        "first republic bank": "First Republic Bank",
        "first united bank and trust": "First United Bank & Trust Co.",
        "first united bank and trust co": "First United Bank & Trust Co.",
        "flagstar bank": "Flagstar Bank",
        "fulton bank": "Fulton Bank N.A.",
        "fulton bank na": "Fulton Bank N.A.",
        "gateway bank": "Gateway Bank",
        "georgias own credit union": "Georgia’s Own Credit Union",
        "great plains bank": "Great Plains Bank",
        "great western bank": "Great Western Bank",
        "greenstate credit union": "GreenState Credit Union",
        "guaranty bank and trust company": "Guaranty Bank & Trust Company",
        "heritage bank of commerce": "Heritage Bank of Commerce",
        "homestreet bank": "HomeStreet Bank",
        "intouch credit union": "InTouch Credit Union",
        "investors bank": "Investors Bank",
        "johnson financial group bank": "Johnson Financial Group Bank",
        "kinecta federal credit union": "Kinecta Federal Credit Union",
        "lake city bank": "Lake City Bank",
        "liberty bank": "Liberty Bank N.A.",
        "liberty bank na": "Liberty Bank N.A.",
        "lincoln savings bank": "Lincoln Savings Bank",
        "mainstreet credit union": "Mainstreet Credit Union",
        "marine federal credit union": "Marine Federal Credit Union",
        "marquette bank": "Marquette Bank",
        "mechanics bank": "Mechanics Bank",
        "merchants bank of indiana": "Merchants Bank of Indiana",
        "midfirst bank": "MidFirst Bank",
        "midland states bank": "Midland States Bank",
        "mutualone bank": "MutualOne Bank",
        "nicolet national bank": "Nicolet National Bank",
        "north island credit union": "North Island Credit Union",
        "north shore bank": "North Shore Bank",
        "northwest bank": "Northwest Bank",
        "old point national bank": "Old Point National Bank",
        "p1fcu": "P1FCU (Potlatch No. 1 Financial CU)",
        "pathfinder bank": "Pathfinder Bank",
        "patriot federal credit union": "Patriot Federal Credit Union",
        "peoples trust credit union": "Peoples Trust Credit Union",
        "provident bank of new jersey": "Provident Bank of New Jersey",
        "quorum federal credit union": "Quorum Federal Credit Union",
        "renasant bank": "Renasant Bank",
        "republic bank and trust company": "Republic Bank & Trust Company",
        "river city bank": "River City Bank",
        "rockland trust company": "Rockland Trust Company",
        "rocky mountain bank": "Rocky Mountain Bank",
        "rogue credit union": "Rogue Credit Union",
        "salem five bank": "Salem Five Bank",
        "san diego county credit union": "San Diego County Credit Union",
        "seattle bank": "Seattle Bank",
        "service credit union": "Service Credit Union",
        "shore united bank": "Shore United Bank",
        "simmons bank": "Simmons Bank",
        "south state bank": "South State Bank",
        "southern bank and trust co": "Southern Bank & Trust Co.",
        "space city credit union": "Space City Credit Union",
        "stellar one bank": "Stellar One Bank",
        "stockman bank of montana": "Stockman Bank of Montana",
        "summit credit union": "Summit Credit Union",
        "sunflower bank": "Sunflower Bank N.A.",
        "sunflower bank na": "Sunflower Bank N.A.",
        "tcf bank": "TCF Bank (now Huntington)",
        "tcf bank now huntington": "TCF Bank (now Huntington)",
        "texas bank and trust company": "Texas Bank and Trust Company",
        "the commerce bank of washington": "The Commerce Bank of Washington",
        "towpath credit union": "Towpath Credit Union",
        "tompkins trust company": "Tompkins Trust Company",
        "tower federal credit union": "Tower Federal Credit Union",
        "town and country bank": "Town & Country Bank",
        "tri counties bank": "Tri Counties Bank",
        "triad bank": "Triad Bank",
        "tricity credit union": "TriCity Credit Union",
        "tristate capital bank": "TriState Capital Bank",
        "trustco bank": "TrustCo Bank",
        "tulsa federal credit union": "Tulsa Federal Credit Union",
        "ufirst credit union": "UFirst Credit Union",
        "umb healthcare services": "UMB Healthcare Services",
        "unify financial credit union": "Unify Financial Credit Union",
        "union state bank": "Union State Bank",
        "united bank": "United Bank (WV)",
        "united bank wv": "United Bank (WV)",
        "united community bank": "United Community Bank (GA)",
        "united community bank ga": "United Community Bank (GA)",
        "united federal credit union": "United Federal Credit Union",
        "university federal credit union": "University Federal Credit Union (TX)",
        "university federal credit union tx": "University Federal Credit Union (TX)",
        "university of wisconsin credit union": "University of Wisconsin Credit Union",
        "usaa federal savings bank": "USAA Federal Savings Bank",
        "utah first credit union": "Utah First Credit Union",
        "valley strong credit union": "Valley Strong Credit Union",
        "veritex community bank": "Veritex Community Bank",
        "vermont federal credit union": "Vermont Federal Credit Union",
        "vibe credit union": "Vibe Credit Union",
        "virginia credit union": "Virginia Credit Union",
        "visions federal credit union": "Visions Federal Credit Union",
        "vystar credit union": "VyStar Credit Union",
        "wafd bank": "WaFd Bank (Washington Federal Bank)",
        "wafd bank washington federal bank": "WaFd Bank (Washington Federal Bank)",
        "wallis bank": "Wallis Bank",
        "waterstone bank": "WaterStone Bank",
        "waukesha state bank": "Waukesha State Bank",
        "webster five cents savings bank": "Webster Five Cents Savings Bank",
        "wesbanco bank": "WesBanco Bank Inc.",
        "wesbanco bank inc": "WesBanco Bank Inc.",
        "westfield bank": "Westfield Bank",
        "wheaton bank and trust": "Wheaton Bank & Trust",
        "whitefish credit union": "Whitefish Credit Union",
        "wilmington savings fund society": "Wilmington Savings Fund Society (WSFS Bank)",
        "wilmington savings fund society wsfs bank": "Wilmington Savings Fund Society (WSFS Bank)",
        "winchester savings bank": "Winchester Savings Bank",
        "wintrust financial corp": "Wintrust Financial Corp.",
        "wright patt credit union": "Wright-Patt Credit Union",
        "wyhy federal credit union": "WyHy Federal Credit Union",
        "xceed financial credit union": "Xceed Financial Credit Union",
        "abbybank": "AbbyBank",
        "adams bank and trust": "Adams Bank & Trust",
        "adirondack bank": "Adirondack Bank",
        "advantage bank": "Advantage Bank",
        "aimbank": "AIMBank",
        "alabama credit union": "Alabama Credit Union",
        "albina community bank": "Albina Community Bank",
        "alliance bank central texas": "Alliance Bank Central Texas",
        "alpine bank": "Alpine Bank",
        "amalgamated bank of chicago": "Amalgamated Bank of Chicago",
        "amboy bank": "Amboy Bank",
        "american bank and trust": "American Bank & Trust (SD)",
        "american bank and trust sd": "American Bank & Trust (SD)",
        "american bank and trust company": "American Bank & Trust Company (LA)",
        "american bank and trust company la": "American Bank & Trust Company (LA)",
        "american eagle financial credit union": "American Eagle Financial Credit Union",
        "american first credit union": "American First Credit Union",
        "american heritage bank": "American Heritage Bank",
        "american heritage credit union": "American Heritage Credit Union",
        "americu credit union": "AmeriCU Credit Union",
        "androscoggin bank": "Androscoggin Bank",
        "anstaff bank": "Anstaff Bank",
        "appalachian community fcu": "Appalachian Community FCU",
        "apple bank for savings": "Apple Bank for Savings",
        "aptiva bank": "Aptiva Bank",
        "arbor bank": "Arbor Bank",
        "arcola first bank": "Arcola First Bank",
        "armed forces bank": "Armed Forces Bank",
        "arrowhead credit union": "Arrowhead Credit Union",
        "artisans bank": "Artisans Bank",
        "ascentra credit union": "Ascentra Credit Union",
        "asheville savings bank": "Asheville Savings Bank",
        "atlantic city federal credit union": "Atlantic City Federal Credit Union",
        "atlantic federal credit union": "Atlantic Federal Credit Union (ME)",
        "atlantic federal credit union me": "Atlantic Federal Credit Union (ME)",
        "atlantic stewardship bank": "Atlantic Stewardship Bank",
        "auburn community federal credit union": "Auburn Community Federal Credit Union",
        "austin bank": "Austin Bank",
        "baker boyer bank": "Baker Boyer Bank",
        "ballston spa national bank": "Ballston Spa National Bank",
        "bank five nine": "Bank Five Nine",
        "bank iowa": "Bank Iowa",
        "bank midwest": "Bank Midwest (MN)",
        "bank midwest mn": "Bank Midwest (MN)",
        "bank of bozeman": "Bank of Bozeman",
        "bank of clarke county": "Bank of Clarke County",
        "bank of colorado": "Bank of Colorado",
        "bank of desoto": "Bank of Desoto",
        "bank of eastern oregon": "Bank of Eastern Oregon",
        "bank of george": "Bank of George",
        "bank of hawaii": "Bank of Hawaii (HSA Division)",
        "bank of hawaii hsa division": "Bank of Hawaii (HSA Division)",
        "bank of jackson hole": "Bank of Jackson Hole",
        "bank of little rock": "Bank of Little Rock",
        "bank of north carolina": "Bank of North Carolina (merged with Pinnacle)",
        "bank of north carolina merged with pinnacle": "Bank of North Carolina (merged with Pinnacle)",
        "bank of prairie du sac": "Bank of Prairie du Sac",
        "bank of san francisco": "Bank of San Francisco",
        "bank of tennessee": "Bank of Tennessee",
        "bank of travelers rest": "Bank of Travelers Rest",
        "bank of washington": "Bank of Washington",
        "bank rhode island": "Bank Rhode Island",
        "bankers trust company": "Bankers Trust Company",
        "bankfirst financial services": "BankFirst Financial Services",
        "banner county bank": "Banner County Bank",
        "baraboo state bank": "Baraboo State Bank",
        "bath savings institution": "Bath Savings Institution",
        "baxter credit union": "Baxter Credit Union (BECU subsidiary)",
        "baxter credit union becu subsidiary": "Baxter Credit Union (BECU subsidiary)",
        "bay federal credit union": "Bay Federal Credit Union",
        "baycoast bank": "BayCoast Bank",
        "bayvanguard bank": "BayVanguard Bank",
        "beacon credit union": "Beacon Credit Union",
        "beaumont community credit union": "Beaumont Community Credit Union",
        "belco community credit union": "Belco Community Credit Union",
        "bellwood cu": "Bellwood CU",
        "benchmark bank": "Benchmark Bank (TX)",
        "benchmark bank tx": "Benchmark Bank (TX)",
        "beneficial state bank": "Beneficial State Bank",
        "benton state bank": "Benton State Bank",
        "berkshire bank": "Berkshire Bank",
        "beverly bank": "Beverly Bank",
        "big horn federal savings bank": "Big Horn Federal Savings Bank",
        "black hills federal credit union": "Black Hills Federal Credit Union",
        "bluff view bank": "Bluff View Bank",
        "blue ridge bank": "Blue Ridge Bank N.A.",
        "blue ridge bank na": "Blue Ridge Bank N.A.",
        "bmi federal credit union": "BMI Federal Credit Union",
        "bogota savings bank": "Bogota Savings Bank",
        "boone bank and trust": "Boone Bank & Trust Co.",
        "boone bank and trust co": "Boone Bank & Trust Co.",
        "boston firefighters credit union": "Boston Firefighters Credit Union",
        "brannen bank": "Brannen Bank",
        "bridgewater credit union": "Bridgewater Credit Union",
        "brightstar credit union": "BrightStar Credit Union",
        "broadview federal credit union": "Broadview Federal Credit Union",
        "brookline bank": "Brookline Bank",
        "brotherhood credit union": "Brotherhood Credit Union",
        "buckeye state bank": "Buckeye State Bank",
        "buffalo federal bank": "Buffalo Federal Bank",
        "butte community bank": "Butte Community Bank",
        "cabot and company bankers": "Cabot & Company Bankers",
        "california credit union": "California Credit Union",
        "cambridge savings bank": "Cambridge Savings Bank",
        "camden national bank": "Camden National Bank",
        "canandaigua federal credit union": "Canandaigua Federal Credit Union",
        "cape ann savings bank": "Cape Ann Savings Bank",
        "capital city bank": "Capital City Bank",
        "capital community bank": "Capital Community Bank (CCBank)",
        "capital community bank ccbank": "Capital Community Bank (CCBank)",
        "capitol federal savings bank": "Capitol Federal Savings Bank",
        "carolina foothills federal credit union": "Carolina Foothills Federal Credit Union",
        "carter bank and trust": "Carter Bank & Trust",
        "cascade community credit union": "Cascade Community Credit Union",
        "cathay bank": "Cathay Bank",
        "cbs bank": "CB&S Bank",
        "zia credit union": "Zia Credit Union",
        "cbi bank and trust": "CBI Bank & Trust",
        "centennial bank": "Centennial Bank (AR)",
        "centennial bank ar": "Centennial Bank (AR)",
        "centerstate bank": "CenterState Bank",
        "centric bank": "Centric Bank",
        "central bank": "Central Bank (UT)",
        "central bank ut": "Central Bank (UT)",
        "central pacific bank": "Central Pacific Bank",
        "century bank": "Century Bank (MA)",
        "century bank ma": "Century Bank (MA)",
        "chambers bank": "Chambers Bank",
        "charles river bank": "Charles River Bank",
        "chelsea state bank": "Chelsea State Bank",
        "chemung canal trust company": "Chemung Canal Trust Company",
        "cherokee state bank": "Cherokee State Bank",
        "chesapeake bank": "Chesapeake Bank",
        "chittenden bank": "Chittenden Bank",
        "choiceone bank": "ChoiceOne Bank",
        "citizens bank of las cruces": "Citizens Bank of Las Cruces",
        "citizens bank of west virginia": "Citizens Bank of West Virginia",
        "citizens first bank": "Citizens First Bank (FL)",
        "citizens first bank fl": "Citizens First Bank (FL)",
        "citizens national bank of texas": "Citizens National Bank of Texas",
        "citizens state bank of loyal": "Citizens State Bank of Loyal",
        "city and county credit union": "City & County Credit Union",
        "city national bank of florida": "City National Bank of Florida",
        "clackamas county bank": "Clackamas County Bank",
        "classic bank": "Classic Bank N.A.",
        "classic bank na": "Classic Bank N.A.",
        "clayton bank and trust": "Clayton Bank & Trust",
        "clinton savings bank": "Clinton Savings Bank",
        "coastal community bank": "Coastal Community Bank",
        "coastal heritage bank": "Coastal Heritage Bank",
        "coastalstates bank": "CoastalStates Bank",
        "coeur d’alene bank": "Coeur d’Alene Bank",
        "colfax bank and trust": "Colfax Bank & Trust",
        "colony bank": "Colony Bank",
        "columbia state bank": "Columbia State Bank",
        "commonwealth community bank": "Commonwealth Community Bank",
        "community 1st credit union": "Community 1st Credit Union (IA)",
        "community 1st credit union ia": "Community 1st Credit Union (IA)",
        "community bank of pleasant hill": "Community Bank of Pleasant Hill",
        "community bank of raymore": "Community Bank of Raymore",
        "community first bank of indiana": "Community First Bank of Indiana",
        "community resource credit union": "Community Resource Credit Union",
        "community trust bank": "Community Trust Bank (KY)",
        "community trust bank ky": "Community Trust Bank (KY)",
        "communityamerica financial services": "CommunityAmerica Financial Services",
        "communitybank of texas": "CommunityBank of Texas N.A.",
        "communitybank of texas na": "CommunityBank of Texas N.A.",
        "consumers national bank": "Consumers National Bank",
        "cornerstone financial credit union": "Cornerstone Financial Credit Union",
        "corporate america credit union": "Corporate America Credit Union",
        "county bank": "County Bank (IA)",
        "county bank ia": "County Bank (IA)",
        "county national bank": "County National Bank (MI)",
        "county national bank mi": "County National Bank (MI)",
        "covenant bank": "Covenant Bank",
        "crescent credit union": "Crescent Credit Union",
        "cross river bank": "Cross River Bank",
        "crystal lake bank and trust": "Crystal Lake Bank & Trust",
        "cse federal credit union": "CSE Federal Credit Union",
        "cta bank and trust": "CTA Bank & Trust",
        "customers bank": "Customers Bank",
        "dakota community federal cu": "Dakota Community Federal CU",
        "dakota heritage bank": "Dakota Heritage Bank",
        "dallas capital bank": "Dallas Capital Bank",
        "danbury savings bank": "Danbury Savings Bank",
        "day air credit union": "Day Air Credit Union",
        "dedham institution for savings": "Dedham Institution for Savings",
        "delta bank": "Delta Bank",
        "denison state bank": "Denison State Bank",
        "deposit bank of frankfort": "Deposit Bank of Frankfort",
        "deseret first credit union": "Deseret First Credit Union",
        "diamond credit union": "Diamond Credit Union",
        "dime community bank": "Dime Community Bank",
        "dnb first bank": "DNB First Bank",
        "dorchester savings bank": "Dorchester Savings Bank",
        "dover federal credit union": "Dover Federal Credit Union",
        "drummond community bank": "Drummond Community Bank",
        "dupage credit union": "DuPage Credit Union",
        "dupaco community credit union": "Dupaco Community Credit Union",
        "durden bank and trust": "Durden Bank & Trust",
        "eagle community credit union": "Eagle Community Credit Union",
        "eagle federal credit union": "Eagle Federal Credit Union",
        "eagle savings bank": "Eagle Savings Bank",
        "east bank": "East Bank (East Chicago, IN)",
        "east bank east chicago": "East Bank (East Chicago, IN)",
        "east boston savings bank": "East Boston Savings Bank",
        "east cambridge savings bank": "East Cambridge Savings Bank",
        "east river federal credit union": "East River Federal Credit Union",
        "eastern savings bank": "Eastern Savings Bank (MD)",
        "eastern savings bank md": "Eastern Savings Bank (MD)",
        "eaton community bank": "Eaton Community Bank",
        "educators credit union": "Educators Credit Union (TX)",
        "educators credit union tx": "Educators Credit Union (TX)",
        "eecu credit union": "EECU Credit Union (TX)",
        "eecu credit union tx": "EECU Credit Union (TX)",
        "el paso area teachers federal credit union": "El Paso Area Teachers Federal Credit Union",
        "elevate bank": "Elevate Bank",
        "elk river bank": "Elk River Bank",
        "elmira savings bank": "Elmira Savings Bank",
        "embassy bank for the lehigh valley": "Embassy Bank for the Lehigh Valley",
        "empower federal credit union": "Empower Federal Credit Union",
        "endura financial credit union": "Endura Financial Credit Union",
        "enterprise bank and trust": "Enterprise Bank & Trust",
        "envista credit union": "Envista Credit Union",
        "equitable bank": "Equitable Bank (NE)",
        "equitable bank ne": "Equitable Bank (NE)",
        "erie federal credit union": "Erie Federal Credit Union",
        "evertrust bank": "EverTrust Bank",
        "exchange state bank": "Exchange State Bank",
        "excite credit union": "Excite Credit Union",
        "f&m bank": "F&M Bank (NC)",
        "f&m bank nc": "F&M Bank (NC)",
        "f&m trust": "F&M Trust (Franklin Co. PA)",
        "f&m trust franklin co pa": "F&M Trust (Franklin Co. PA)",
        "fairfield county bank": "Fairfield County Bank",
        "farmers and drovers bank": "Farmers & Drovers Bank",
        "farmers and merchants bank of central california": "Farmers & Merchants Bank of Central California",
        "farmers bank and trust": "Farmers Bank & Trust (AR)",
        "farmers bank and trust ar": "Farmers Bank & Trust (AR)",
        "farmers state bank in": "Farmers State Bank (IN)",
        "farmers state bank ia": "Farmers State Bank (IA)",
        "farmers state bank mt": "Farmers State Bank (MT)",
        "fayette county bank": "Fayette County Bank",
        "fidelity bank of florida": "Fidelity Bank of Florida",
        "fidelity deposit and discount bank": "Fidelity Deposit and Discount Bank",
        "financial partners credit union": "Financial Partners Credit Union",
        "finex credit union": "Finex Credit Union",
        "first alliance credit union": "First Alliance Credit Union",
        "first american trust fsb": "First American Trust FSB",
        "first arkansas bank and trust": "First Arkansas Bank & Trust",
        "first bank hampton": "First Bank Hampton",
        "first bank kansas": "First Bank Kansas",
        "first bank richmond": "First Bank Richmond",
        "first bankers trust company": "First Bankers Trust Company N.A.",
        "first bankers trust company na": "First Bankers Trust Company N.A.",
        "first basin credit union": "First Basin Credit Union",
        "first capital federal credit union": "First Capital Federal Credit Union",
        "first central state bank": "First Central State Bank",
        "first chatham bank": "First Chatham Bank",
        "first citizens national bank": "First Citizens National Bank (TN)",
        "first citizens national bank tn": "First Citizens National Bank (TN)",
        "first city credit union": "First City Credit Union",
        "first commerce credit union": "First Commerce Credit Union",
        "first community credit union": "First Community Credit Union (MO)",
        "first community credit union mo": "First Community Credit Union (MO)",
        "first community credit union tx": "First Community Credit Union (TX)",
        "first county bank": "First County Bank",
        "first dakota national bank": "First Dakota National Bank",
        "first eagle bank": "First Eagle Bank",
        "first enterprise bank": "First Enterprise Bank",
        "first federal bank": "First Federal Bank (KY)",
        "first federal bank ky": "First Federal Bank (KY)",
        "first federal savings bank of champaign urbana": "First Federal Savings Bank of Champaign-Urbana",
        "first financial bank": "First Financial Bank (OH)",
        "first financial bank oh": "First Financial Bank (OH)",
        "first financial northwest bank": "First Financial Northwest Bank",
        "first florida credit union": "First Florida Credit Union",
        "first freedom bank": "First Freedom Bank",
        "first hawaiian bank": "First Hawaiian Bank (HSA Division)",
        "first hawaiian bank hsa division": "First Hawaiian Bank (HSA Division)",
        "first hope bank": "First Hope Bank",
        "first independent bank": "First Independent Bank (NV)",
        "first independent bank nv": "First Independent Bank (NV)",
        "first international bank and trust": "First International Bank & Trust",
        "first interstate credit union": "First Interstate Credit Union",
        "first mid illinois bank and trust": "First Mid-Illinois Bank & Trust",
        "first midwest bank": "First Midwest Bank (IL)",
        "first midwest bank il": "First Midwest Bank (IL)",
        "first national bank in sioux falls": "First National Bank in Sioux Falls",
        "first national bank north": "First National Bank North",
        "first national bank of bastrop": "First National Bank of Bastrop",
        "first national bank of brookfield": "First National Bank of Brookfield",
        "first national bank of durango": "First National Bank of Durango",
        "first national bank of hutchinson": "First National Bank of Hutchinson",
        "first national bank of mcgregor": "First National Bank of McGregor",
        "first national bank of pennsylvania": "First National Bank of Pennsylvania",
        "first national bank of pulaski": "First National Bank of Pulaski",
        "first national bank of st louis": "First National Bank of St. Louis",
        "first national bank of waseca": "First National Bank of Waseca",
        "first national bank of winnsboro": "First National Bank of Winnsboro",
        "first national community bank": "First National Community Bank (GA)",
        "first national community bank ga": "First National Community Bank (GA)",
        "first northern credit union": "First Northern Credit Union",
        "first oklahoma bank": "First Oklahoma Bank",
        "first premier bank": "First PREMIER Bank",
        "first robinson savings bank": "First Robinson Savings Bank",
        "first savings bank": "First Savings Bank (IN)",
        "first savings bank in": "First Savings Bank (IN)",
        "first security bank": "First Security Bank (AR)",
        "first security bank ar": "First Security Bank (AR)",
        "first security bank of missoula": "First Security Bank of Missoula",
        "first service bank": "First Service Bank",
        "first southern bank": "First Southern Bank (IL)",
        "first southern bank il": "First Southern Bank (IL)",
        "first state bank": "First State Bank (IL)",
        "first state bank il": "First State Bank (IL)",
        "first state bank mi": "First State Bank (MI)",
        "first state bank tx": "First State Bank (TX)",
        "first state bank nebraska": "First State Bank Nebraska",
        "first state community bank": "First State Community Bank",
        "first state credit union": "First State Credit Union",
        "first tennessee bank": "First Tennessee Bank (now Truist)",
        "first tennessee bank now truist": "First Tennessee Bank (now Truist)",
        "first texas bank": "First Texas Bank",
        "first united bank": "First United Bank (OK)",
        "first united bank ok": "First United Bank (OK)",
        "first western bank and trust": "First Western Bank & Trust",
        "first western federal savings bank": "First Western Federal Savings Bank",
        "firstbank": "FirstBank (CO)",
        "firstbank co": "FirstBank (CO)",
        "firstbank of nebraska": "FirstBank of Nebraska",
        "five star bank": "Five Star Bank",
        "flagship bank minnesota": "Flagship Bank Minnesota",
        "fnb bank": "FNB Bank (KY)",
        "fnb bank ky": "FNB Bank (KY)",
        "fnbc bank": "FNBC Bank (AR)",
        "fnbc bank ar": "FNBC Bank (AR)",
        "foothill credit union": "Foothill Credit Union",
        "forest park bank": "Forest Park Bank",
        "fort knox federal credit union": "Fort Knox Federal Credit Union",
        "fort sill federal credit union": "Fort Sill Federal Credit Union",
        "forward bank": "Forward Bank",
        "fox communities credit union": "Fox Communities Credit Union",
        "freedom bank of virginia": "Freedom Bank of Virginia",
        "freedom credit union": "Freedom Credit Union (MA)",
        "freedom credit union ma": "Freedom Credit Union (MA)",
        "frontier bank": "Frontier Bank (NE)",
        "frontier bank ne": "Frontier Bank (NE)",
        "frontwave credit union": "Frontwave Credit Union",
        "fsnb national bank": "FSNB National Bank",
    
        "fulton bank of new jersey": "Fulton Bank of New Jersey",
        "g bank": "G Bank (Bank of Guam USA)",
        "g bank bank of guam usa": "G Bank (Bank of Guam USA)",
        "gainesville bank and trust": "Gainesville Bank & Trust",
        "gannon bank": "Gannon Bank",
        "generations bank": "Generations Bank",
        "generations credit union": "Generations Credit Union",
        "george d warthen bank": "George D. Warthen Bank",
        "georgia banking company": "Georgia Banking Company",
        "germantown trust and savings bank": "Germantown Trust & Savings Bank",
        "gnb bank": "GNB Bank",
        "goldenwest credit union": "Goldenwest Credit Union",
        "goodfield state bank": "Goodfield State Bank",
        "gorham savings bank": "Gorham Savings Bank",
        "grand ridge national bank": "Grand Ridge National Bank",
        "granite bank": "Granite Bank",
        "granite state credit union": "Granite State Credit Union",
        "great lakes credit union": "Great Lakes Credit Union",
        "great river federal credit union": "Great River Federal Credit Union",
        "greater nevada credit union": "Greater Nevada Credit Union",
        "greater texas credit union": "Greater Texas Credit Union",
        "green cove springs state bank": "Green Cove Springs State Bank",
        "green dot bank": "Green Dot Bank",
        "greenfield savings bank": "Greenfield Savings Bank",
        "greenleaf bank": "Greenleaf Bank",
        "greenville national bank": "Greenville National Bank",
        "greylock federal credit union": "Greylock Federal Credit Union",
        "guaranty bank and trust": "Guaranty Bank & Trust (IA)",
        "guaranty bank and trust ia": "Guaranty Bank & Trust (IA)",
        "gulf coast federal credit union": "Gulf Coast Federal Credit Union",
        "gulf winds credit union": "Gulf Winds Credit Union",
        "hancock county savings bank": "Hancock County Savings Bank",
        "hancock whitney bank": "Hancock Whitney Bank (HSA Dept.)",
        "hancock whitney bank hsa dept": "Hancock Whitney Bank (HSA Dept.)",
        "happy state bank": "Happy State Bank",
        "harborone bank": "HarborOne Bank",
        "harrison county bank": "Harrison County Bank",
        "hartford federal credit union": "Hartford Federal Credit Union",
        "hawaiiusa federal credit union": "HawaiiUSA Federal Credit Union",
        "heartland credit union": "Heartland Credit Union (WI)",
        "heartland credit union wi": "Heartland Credit Union (WI)",
        "heartland tri state bank": "Heartland Tri-State Bank",
        "helena community credit union": "Helena Community Credit Union",
        "heritage family credit union": "Heritage Family Credit Union",
        "heritage grove federal credit union": "Heritage Grove Federal Credit Union",
        "heritage south credit union": "Heritage South Credit Union",
        "heritage west credit union": "Heritage West Credit Union",
        "highland community bank": "Highland Community Bank",
        "hilltop national bank": "Hilltop National Bank",
        "hingham institution for savings": "Hingham Institution for Savings",
        "horizon bank": "Horizon Bank (MI)",
        "horizon bank mi": "Horizon Bank (MI)",
        "horizon community bank": "Horizon Community Bank (AZ)",
        "horizon community bank az": "Horizon Community Bank (AZ)",
        "horizon credit union": "Horizon Credit Union (WA)",
        "horizon credit union wa": "Horizon Credit Union (WA)",
        "horizon federal credit union": "Horizon Federal Credit Union (PA)",
        "horizon federal credit union pa": "Horizon Federal Credit Union (PA)",
        "houston federal credit union": "Houston Federal Credit Union",
        "howard county bank": "Howard County Bank",
        "hudson city savings bank": "Hudson City Savings Bank",
        "hudson heritage federal credit union": "Hudson Heritage Federal Credit Union",
        "hughes federal credit union": "Hughes Federal Credit Union",
        "huntingdon valley bank": "Huntingdon Valley Bank",
        "ic federal credit union": "IC Federal Credit Union",
        "idb bank": "IDB Bank (Industrial Bank of Israel)",
        "idb bank industrial bank of israel": "IDB Bank (Industrial Bank of Israel)",
        "ih mississippi valley credit union": "IH Mississippi Valley Credit Union",
        "illinois state credit union": "Illinois State Credit Union",
        "incrediblebank": "IncredibleBank",
        "industrial bank": "Industrial Bank (Washington DC)",
        "industrial bank washington dc": "Industrial Bank (Washington DC)",
        "inland northwest bank": "Inland Northwest Bank",
        "inspirus credit union": "Inspirus Credit Union",
        "integrity bank for business": "Integrity Bank for Business",
        "interamerican bank": "Interamerican Bank (Miami)",
        "interamerican bank miami": "Interamerican Bank (Miami)",
        "international bank of commerce": "International Bank of Commerce (IBC Bank)",
        "international bank of commerce ibc bank": "International Bank of Commerce (IBC Bank)",
        "investar bank": "Investar Bank N.A.",
        "investar bank na": "Investar Bank N.A.",
        "ion bank": "ION Bank",
        "iowa heartland credit union": "Iowa Heartland Credit Union",
        "iowa state bank and trust": "Iowa State Bank & Trust (Iowa City)",
        "iowa state bank and trust iowa city": "Iowa State Bank & Trust (Iowa City)",
        "iron bank": "Iron Bank (St. Louis)",
        "iron bank st louis": "Iron Bank (St. Louis)",
        "ironworkers bank": "Ironworkers Bank",
        "jersey shore state bank": "Jersey Shore State Bank",
        "john marshall bank": "John Marshall Bank",
        "johnson city bank": "Johnson City Bank",
        "joplin metro credit union": "Joplin Metro Credit Union",
        "jupiter miners bank": "Jupiter Miners Bank",
        "national financial services llc": "National Financial Services LLC",
        "national financial serves llc": "National Financial Services LLC",
        "bank of america": "Bank of America",
        "bark of america": "Bank of America",
        "bank of amerlca": "Bank of America",
        "bank of amerlca na": "Bank of America",

        # --- Major HSA / Financial Admins ---
        "healthequity corporate": "HealthEquity Corporate",
        "healthequity corp": "HealthEquity Corporate",
        "health equity corporate": "HealthEquity Corporate",
        "health equity corp": "HealthEquity Corporate",
        "healthequity": "HealthEquity Inc.",
        "healthequity inc": "HealthEquity Inc.",
        "optum bank": "Optum Bank Inc.",
        "optum bank inc": "Optum Bank Inc.",
        "fidelity investments": "Fidelity Investments",
        "webster bank": "Webster Bank N.A.",
        "webster bank n a": "Webster Bank N.A.",
        "lively hsa": "Lively HSA Inc.",
        "lively hsa inc": "Lively HSA Inc.",

        # --- Large Banks ---
        "umb bank": "UMB Bank N.A.",
        "umb bank n a": "UMB Bank N.A.",
        "first american bank": "First American Bank",
        "wells fargo": "Wells Fargo Bank N.A.",
        "wells fargo bank": "Wells Fargo Bank N.A.",
        "jpmorgan chase": "JPMorgan Chase Bank N.A.",
        "chase bank": "JPMorgan Chase Bank N.A.",
        "associated bank": "Associated Bank N.A.",
        "fifth third": "Fifth Third Bank N.A.",
        "keybank": "KeyBank N.A.",
        "bend hsa": "Bend HSA Inc.",
        "elements financial": "Elements Financial Credit Union",
        "patelco": "Patelco Credit Union",
        "digital federal credit union": "Digital Federal Credit Union (DCU)",
        "america first credit union": "America First Credit Union",
        "golden 1 credit union": "Golden 1 Credit Union",
        "truist": "Truist Bank",
        "pnc": "PNC Bank N.A.",
        "regions bank": "Regions Bank",
        "us bank": "US Bank N.A.",
        "comerica": "Comerica Bank",
        "citizens bank": "Citizens Bank N.A.",
        "first horizon": "First Horizon Bank",
        "hancock whitney": "Hancock Whitney Bank",
        "zions bank": "Zions Bank N.A.",
        "frost bank": "Frost Bank",
        "old national": "Old National Bank",
        "synovus": "Synovus Bank",
        "commerce bank": "Commerce Bank",
        "first interstate": "First Interstate Bank",
        "glacier bank": "Glacier Bank",
        "banner bank": "Banner Bank",
        "first citizens": "First Citizens Bank",
        "huntington national": "Huntington National Bank",

        # --- Credit Unions ---
        "associated healthcare credit union": "Associated Healthcare Credit Union",
        "advia credit union": "Advia Credit Union",
        "premier america credit union": "Premier America Credit Union",
        "bethpage federal credit union": "Bethpage Federal Credit Union",
        "mountain america credit union": "Mountain America Credit Union",
        "alliant credit union": "Alliant Credit Union",
        "penfed": "PenFed Credit Union",
        "navy federal": "Navy Federal Credit Union",
        "schoolsfirst": "SchoolsFirst Federal Credit Union",
        "becu": "Boeing Employees Credit Union (BECU)",
        "boeing employees credit union": "Boeing Employees Credit Union (BECU)",
        "space coast": "Space Coast Credit Union",
        "redstone federal": "Redstone Federal Credit Union",
        "desert financial": "Desert Financial Credit Union",
        "gesa credit union": "Gesa Credit Union",
        "bellco credit union": "Bellco Credit Union",
        "ent credit union": "Ent Credit Union",
        "vystar credit union": "VyStar Credit Union",
        "randolph brooks": "Randolph-Brooks Federal Credit Union",
        "american airlines federal credit union": "American Airlines Federal Credit Union",
        "delta community credit union": "Delta Community Credit Union",
        "state employees credit union": "State Employees’ Credit Union (SECU)",
        "vantage west": "Vantage West Credit Union",
        "oregon community": "Oregon Community Credit Union",
        "truwest": "TruWest Credit Union",

        # --- MSA / Health-related Plans ---
        "lasso healthcare": "Lasso Healthcare MSA",
        "unitedhealthcare": "UnitedHealthcare MSA Plans",
        "humana": "Humana MSA Plans",
        "blue cross blue shield": "Blue Cross Blue Shield MSA Plans",
        "vibrant usa": "Vibrant USA MSA Plans",
        "wex": "WEX Inc.",
                # --- Additional Financial Institutions (Extension Set) ---
        "pioneer trust bank": "Pioneer Trust Bank (ND)",
        "pioneer trust bank nd": "Pioneer Trust Bank (ND)",

        "planters first bank": "Planters First Bank",
        "platte valley bank": "Platte Valley Bank (NE)",
        "platte valley bank ne": "Platte Valley Bank (NE)",
        "platte valley national bank": "Platte Valley National Bank",

        "pnc financial services": "PNC Financial Services Group",
        "pnc financial services group": "PNC Financial Services Group",

        "point breeze credit union": "Point Breeze Credit Union (MD)",
        "point breeze credit union md": "Point Breeze Credit Union (MD)",
        "police and fire federal credit union": "Police and Fire Federal Credit Union",
        "popular bank": "Popular Bank (NY)",
        "popular bank ny": "Popular Bank (NY)",

        "port washington state bank": "Port Washington State Bank",
        "prairie bank": "Prairie Bank",
        "prairie mountain bank": "Prairie Mountain Bank",

        "premier bank": "Premier Bank (Rochester MN)",
        "premier bank rochester": "Premier Bank (Rochester MN)",
        "premier bank rochester mn": "Premier Bank (Rochester MN)",

        "premier members credit union": "Premier Members Credit Union (CO)",
        "premier members credit union co": "Premier Members Credit Union (CO)",

        "presidential bank": "Presidential Bank (FSB)",
        "presidential bank fsb": "Presidential Bank (FSB)",

        "primeway federal credit union": "PrimeWay Federal Credit Union (TX)",
        "primeway federal credit union tx": "PrimeWay Federal Credit Union (TX)",

        "princeton state bank": "Princeton State Bank",
        "professional bank": "Professional Bank (FL)",
        "professional bank fl": "Professional Bank (FL)",
        "progressive bank": "Progressive Bank (LA)",
        "progressive bank la": "Progressive Bank (LA)",
        "prosperity bank": "Prosperity Bank (TX)",
        "prosperity bank tx": "Prosperity Bank (TX)",

        "provident bank of maryland": "Provident Bank of Maryland",
        "provident credit union": "Provident Credit Union (CA)",
        "provident credit union ca": "Provident Credit Union (CA)",

        "ps bank": "PS Bank (Pa.)",
        "ps bank pa": "PS Bank (Pa.)",
        "public service credit union": "Public Service Credit Union (CO)",
        "public service credit union co": "Public Service Credit Union (CO)",

        "publix employees federal credit union": "Publix Employees Federal Credit Union",
        "puget sound bank": "Puget Sound Bank",

        "quad city bank": "Quad City Bank and Trust",
        "quad city bank and trust": "Quad City Bank and Trust",

        "queenstown bank of maryland": "Queenstown Bank of Maryland",
        "quincy state bank": "Quincy State Bank (FL)",
        "quincy state bank fl": "Quincy State Bank (FL)",

        "quorum federal credit union": "Quorum Federal Credit Union (NY)",
        "quorum federal credit union ny": "Quorum Federal Credit Union (NY)",

        "raccoon valley bank": "Raccoon Valley Bank",
        "randolph savings bank": "Randolph Savings Bank",

        "raymond james bank": "Raymond James Bank",
        "red river bank": "Red River Bank",
        "red river employees federal credit union": "Red River Employees Federal Credit Union",

        "redwood capital bank": "Redwood Capital Bank",
        "reliabank dakota": "Reliabank Dakota",
        "reliant community credit union": "Reliant Community Credit Union (NY)",
        "reliant community credit union ny": "Reliant Community Credit Union (NY)",

        "republic bank of arizona": "Republic Bank of Arizona",
        "republic bank of chicago": "Republic Bank of Chicago",

                # --- Additional Banks and Credit Unions (Requested) ---
        "republic first bank": "Republic First Bank (Philadelphia PA)",
        "republic first bank philadelphia": "Republic First Bank (Philadelphia PA)",
        "republic first bank philadelphia pa": "Republic First Bank (Philadelphia PA)",

        "resurgens bank": "Resurgens Bank",
        "ridgewood savings bank": "Ridgewood Savings Bank (NY)",
        "ridgewood savings bank ny": "Ridgewood Savings Bank (NY)",

        "rising community federal credit union": "Rising Community Federal Credit Union",
        "river bank": "River Bank (WI)",
        "river bank wi": "River Bank (WI)",
        "river city federal credit union": "River City Federal Credit Union (TX)",
        "river city federal credit union tx": "River City Federal Credit Union (TX)",
        "river falls state bank": "River Falls State Bank",
        "river valley credit union": "River Valley Credit Union (OH)",
        "river valley credit union oh": "River Valley Credit Union (OH)",
        "riverland federal credit union": "RiverLand Federal Credit Union (LA)",
        "riverland federal credit union la": "RiverLand Federal Credit Union (LA)",
        "riverset credit union": "Riverset Credit Union (PA)",
        "riverset credit union pa": "Riverset Credit Union (PA)",
        "riverview community bank": "Riverview Community Bank (WA)",
        "riverview community bank wa": "Riverview Community Bank (WA)",
        "rock canyon bank": "Rock Canyon Bank (UT)",
        "rock canyon bank ut": "Rock Canyon Bank (UT)",
        "rockland federal credit union": "Rockland Federal Credit Union (MA)",
        "rockland federal credit union ma": "Rockland Federal Credit Union (MA)",
        "rockville bank": "Rockville Bank",
        "rogue federal credit union": "Rogue Federal Credit Union (OR)",
        "rogue federal credit union or": "Rogue Federal Credit Union (OR)",
        "rolling hills bank": "Rolling Hills Bank and Trust (IA)",
        "rolling hills bank and trust": "Rolling Hills Bank and Trust (IA)",
        "rolling hills bank ia": "Rolling Hills Bank and Trust (IA)",
        "roundbank": "Roundbank (Fairbault MN)",
        "roundbank fairbault": "Roundbank (Fairbault MN)",
        "roundbank fairbault mn": "Roundbank (Fairbault MN)",
        "royal business bank": "Royal Business Bank (CA)",
        "royal business bank ca": "Royal Business Bank (CA)",
                "kahoka state bank": "Kahoka State Bank",
        "katahdin trust co": "Katahdin Trust Co. (HSA Dept.)",
        "katahdin trust co hsa dept": "Katahdin Trust Co. (HSA Dept.)",
        "kaw valley bank": "Kaw Valley Bank",
        "keystone bank": "Keystone Bank (Austin TX)",
        "keystone bank austin": "Keystone Bank (Austin TX)",
        "keystone bank austin tx": "Keystone Bank (Austin TX)",
        "kish bank": "Kish Bank",
        "kitsap credit union": "Kitsap Credit Union",
        "kodabank": "KodaBank",
        "kohler credit union": "Kohler Credit Union",
        "ks statebank": "KS StateBank",
        "la capitol federal credit union": "La Capitol Federal Credit Union",
        "la salle state bank": "La Salle State Bank",
        "labor credit union": "Labor Credit Union",
        "ladue bank": "Ladue Bank",
        "lake city federal bank": "Lake City Federal Bank",
        "lake sunapee bank": "Lake Sunapee Bank",
        "lakeland bank": "Lakeland Bank",
        "lakeside bank of salina": "Lakeside Bank of Salina",
        "lamar bank and trust": "Lamar Bank and Trust Co.",
        "lamar bank and trust co": "Lamar Bank and Trust Co.",
        "landmark national bank": "Landmark National Bank",
        "langley state bank": "Langley State Bank",
        "lansdale bank": "Lansdale Bank",
        "laramie plains federal credit union": "Laramie Plains Federal Credit Union",
        "laramie plains bank": "Laramie Plains Bank",
        "lawson bank": "Lawson Bank",
        "leader one bank": "Leader One Bank",
        "legacy community federal credit union": "Legacy Community Federal Credit Union",
        "legend bank": "Legend Bank",
        "lehigh valley educators credit union": "Lehigh Valley Educators Credit Union",
        "lewiston state bank": "Lewiston State Bank",
        "liberty bank": "Liberty Bank (CT)",
        "liberty bank ct": "Liberty Bank (CT)",
        "liberty national bank": "Liberty National Bank (OH)",
        "liberty national bank oh": "Liberty National Bank (OH)",
        "lincoln national bank": "Lincoln National Bank (Hodgenville KY)",
        "lincoln national bank hodgenville": "Lincoln National Bank (Hodgenville KY)",
        "lincoln national bank hodgenville ky": "Lincoln National Bank (Hodgenville KY)",
        "linn co op credit union": "Linn Co-op Credit Union",
        "lisbon bank and trust": "Lisbon Bank & Trust",
        "little horn state bank": "Little Horn State Bank",
        "lnb community bank": "LNB Community Bank",
        "logan bank and trust": "Logan Bank & Trust Co.",
        "logan bank and trust co": "Logan Bank & Trust Co.",
        "lone star credit union": "Lone Star Credit Union",
        "lormet community federal credit union": "LorMet Community Federal Credit Union",
        "los padres bank": "Los Padres Bank",
        "louisiana federal credit union": "Louisiana Federal Credit Union",
        "louisiana national bank": "Louisiana National Bank",
        "lowell five savings bank": "Lowell Five Savings Bank",
        "luther burbank savings": "Luther Burbank Savings",
        "lyons national bank": "Lyons National Bank",
        "macon bank and trust": "Macon Bank & Trust Co.",
        "macon bank and trust co": "Macon Bank & Trust Co.",
        "magnolia bank": "Magnolia Bank Inc.",
        "magnolia bank inc": "Magnolia Bank Inc.",
        "main street bank": "Main Street Bank (MA)",
        "main street bank ma": "Main Street Bank (MA)",
        "malvern bank": "Malvern Bank (National Association)",
        "malvern bank national association": "Malvern Bank (National Association)",
        "manasquan bank": "Manasquan Bank",
        "mansfield bank": "Mansfield Bank",
        "manufacturers bank of lewiston": "Manufacturers Bank of Lewiston",
        "marblehead bank": "Marblehead Bank",
        "marine midland bank": "Marine Midland Bank",
        "marion county bank": "Marion County Bank",
        "markesan state bank": "Markesan State Bank",
        "marquette bank of chicago": "Marquette Bank of Chicago",
        "marshall and ilsley bank": "Marshall & Ilsley Bank",
        "massmutual federal credit union": "MassMutual Federal Credit Union",
        "mayville state bank": "Mayville State Bank",
        "mcfarland state bank": "McFarland State Bank",
        "mcintosh county bank": "McIntosh County Bank",
        "mediapolis savings bank": "Mediapolis Savings Bank",
        "members 1st federal credit union": "Members 1st Federal Credit Union",
        "members choice credit union": "Members Choice Credit Union",
        "members heritage credit union": "Members Heritage Credit Union",
        "merrimack county savings bank": "Merrimack County Savings Bank",
        "metairie bank and trust": "Metairie Bank & Trust Co.",
        "metairie bank and trust co": "Metairie Bank & Trust Co.",
        "metro health services federal credit union": "Metro Health Services Federal Credit Union",
        "metropolitan commercial bank": "Metropolitan Commercial Bank",
        "meyers savings bank": "Meyers Savings Bank",
        "michigan schools and government credit union": "Michigan Schools & Government Credit Union",
        "midamerica credit union": "MidAmerica Credit Union",
        "midcountry federal credit union": "MidCountry Federal Credit Union",


        "midfirst credit union": "MidFirst Credit Union",


        "midland community credit union": "Midland Community Credit Union",


        "midminnesota federal credit union": "MidMinnesota Federal Credit Union",


        "midsouth bank": "MidSouth Bank",


        "midstate bank": "Midstate Bank",


        "midstates bank": "Midstates Bank N.A.",


        "midstates bank na": "Midstates Bank N.A.",


        "midwestone credit union": "MidWestOne Credit Union",


        "millbury federal credit union": "Millbury Federal Credit Union",


        "minnco credit union": "Minnco Credit Union",


        "minnesota bank and trust": "Minnesota Bank & Trust",


        "minnstar bank": "MinnStar Bank N.A.",


        "minnstar bank na": "MinnStar Bank N.A.",


        "mississippi federal credit union": "Mississippi Federal Credit Union",


        "modern woodmen bank": "Modern Woodmen Bank",


        "monroe bank and trust": "Monroe Bank & Trust",


        "monroe federal savings bank": "Monroe Federal Savings Bank",


        "montana credit union": "Montana Credit Union",


        "mountain valley bank": "Mountain Valley Bank (NH)",


        "mountain valley bank nh": "Mountain Valley Bank (NH)",


        "mountain west bank": "Mountain West Bank (ID)",


        "mountain west bank id": "Mountain West Bank (ID)",


        "mutual bank": "Mutual Bank (MA)",


        "mutual bank ma": "Mutual Bank (MA)",


        "mutual federal savings bank": "Mutual Federal Savings Bank",


        "nantucket bank": "Nantucket Bank",


        "national bank of commerce": "National Bank of Commerce (Duluth MN)",


        "national bank of commerce duluth": "National Bank of Commerce (Duluth MN)",


        "national bank of middlebury": "National Bank of Middlebury",


        "national exchange bank and trust": "National Exchange Bank & Trust",


        "national grid us federal credit union": "National Grid US Federal Credit Union",


        "national jersey bank": "National Jersey Bank",


        "national parks federal credit union": "National Parks Federal Credit Union",


        "nebraska bank": "Nebraska Bank",


        "nebraska energy federal credit union": "Nebraska Energy Federal Credit Union",


        "neighborhood national bank": "Neighborhood National Bank",


        "netbank federal savings bank": "NetBank Federal Savings Bank",


        "new alliance bank": "New Alliance Bank",


        "new century bank": "New Century Bank",


        "new dominion bank": "New Dominion Bank",


        "new haven county credit union": "New Haven County Credit Union",


        "new milford bank and trust": "New Milford Bank & Trust Co.",


        "new tripoli bank": "New Tripoli Bank",


        "new york community bank": "New York Community Bank",


        "newburyport five cents savings bank": "Newburyport Five Cents Savings Bank",


        "newtown savings bank": "Newtown Savings Bank",


        "nicolet federal credit union": "Nicolet Federal Credit Union",


        "nodaway valley bank": "Nodaway Valley Bank",


        "north american bank and trust": "North American Bank & Trust Co.",


        "north brookfield savings bank": "North Brookfield Savings Bank",


        "north community bank": "North Community Bank",


        "north country federal credit union": "North Country Federal Credit Union",


        "north easton savings bank": "North Easton Savings Bank",


        "north island federal credit union": "North Island Federal Credit Union",


        "north shore federal credit union": "North Shore Federal Credit Union",


        "north state bank": "North State Bank (NC)",


        "north state bank nc": "North State Bank (NC)",


        "northeast bank": "Northeast Bank (ME)",


        "northeast bank me": "Northeast Bank (ME)",


        "northern interstate bank": "Northern Interstate Bank N.A.",


        "northern interstate bank na": "Northern Interstate Bank N.A.",


        "northern skies federal credit union": "Northern Skies Federal Credit Union",


        "northern trust bank": "Northern Trust Bank",


        "northfield savings bank": "Northfield Savings Bank (VT)",


        "northfield savings bank vt": "Northfield Savings Bank (VT)",


        "northland area federal credit union": "Northland Area Federal Credit Union",


        "northwest community credit union": "Northwest Community Credit Union (OR)",


        "northwest community credit union or": "Northwest Community Credit Union (OR)",


        "northwest federal credit union": "Northwest Federal Credit Union (VA)",


        "northwest federal credit union va": "Northwest Federal Credit Union (VA)",


        "norway savings bank": "Norway Savings Bank",


        "notre dame federal credit union": "Notre Dame Federal Credit Union (IN)",


        "notre dame federal credit union in": "Notre Dame Federal Credit Union (IN)",


        "nuvision credit union": "NuVision Credit Union (CA)",


        "nuvision credit union ca": "NuVision Credit Union (CA)",


        "oak bank": "Oak Bank (WI)",


        "oak bank wi": "Oak Bank (WI)",


        "oakstar bank": "OakStar Bank",


        "ocean financial federal credit union": "Ocean Financial Federal Credit Union",


        "oceanfirst bank": "OceanFirst Bank (NJ)",


        "oceanfirst bank nj": "OceanFirst Bank (NJ)",


        "oceanview federal credit union": "OceanView Federal Credit Union",


        "ohio catholic federal credit union": "Ohio Catholic Federal Credit Union",


        "ohio savings bank": "Ohio Savings Bank",


        "old dominion national bank": "Old Dominion National Bank",


        "old point trust": "Old Point Trust and Financial Services",


        "old point trust and financial services": "Old Point Trust and Financial Services",


        "old second national bank": "Old Second National Bank (IL)",


        "old second national bank il": "Old Second National Bank (IL)",


        "old west federal credit union": "Old West Federal Credit Union",


        "olean area federal credit union": "Olean Area Federal Credit Union",


        "onpoint community credit union": "OnPoint Community Credit Union",


        "orange bank and trust": "Orange Bank & Trust Company",


        "orange bank and trust company": "Orange Bank & Trust Company",


        "oregon pacific bank": "Oregon Pacific Bank",


        "oriental bank": "Oriental Bank (Puerto Rico division excluded)",


        "oriental bank puerto rico": "Oriental Bank (Puerto Rico division excluded)",


        "orrstown bank": "Orrstown Bank",


        "oswego county federal credit union": "Oswego County Federal Credit Union",


        "ouachita valley federal credit union": "Ouachita Valley Federal Credit Union",


        "ozark bank": "Ozark Bank",


        "ozark federal credit union": "Ozark Federal Credit Union",


        "pacific crest federal credit union": "Pacific Crest Federal Credit Union",


        "pacific premier bank": "Pacific Premier Bank",


        "pacific service credit union": "Pacific Service Credit Union",


        "pacific valley bank": "Pacific Valley Bank",


        "palmetto citizens federal credit union": "Palmetto Citizens Federal Credit Union",


        "palo savings bank": "Palo Savings Bank",


        "park national bank": "Park National Bank",


        "parkway bank and trust": "Parkway Bank & Trust Co.",


        "parkway bank and trust co": "Parkway Bank & Trust Co.",


        "partners federal credit union": "Partners Federal Credit Union",


        "pathways financial credit union": "Pathways Financial Credit Union",


        "patriot bank": "Patriot Bank (Norwalk CT)",


        "patriot bank norwalk": "Patriot Bank (Norwalk CT)",


        "patriot bank norwalk ct": "Patriot Bank (Norwalk CT)",


        "paul federated credit union": "Paul Federated Credit Union",


        "peach state federal credit union": "Peach State Federal Credit Union",


        "peapack gladstone financial corp": "Peapack-Gladstone Financial Corp.",


        "pella state bank": "Pella State Bank",


        "penair federal credit union": "PenAir Federal Credit Union",


        "peninsula federal credit union": "Peninsula Federal Credit Union",


        "peoples bank": "Peoples Bank (Bellingham WA)",


        "peoples bank bellingham": "Peoples Bank (Bellingham WA)",


        "peoples bank bellingham wa": "Peoples Bank (Bellingham WA)",


        "peoples bank of alabama": "Peoples Bank of Alabama",


        "peoples bank of kankakee": "Peoples Bank of Kankakee County",


        "peoples bank of kankakee county": "Peoples Bank of Kankakee County",


        "peoples community bank": "Peoples Community Bank (MO)",


        "peoples community bank mo": "Peoples Community Bank (MO)",


        "peoples exchange bank": "Peoples Exchange Bank",


        "peoples national bank": "Peoples National Bank (TN)",


        "peoples national bank tn": "Peoples National Bank (TN)",


        "peoples state bank": "Peoples State Bank (IN)",


        "peoples state bank in": "Peoples State Bank (IN)",


        "peoples trust federal credit union": "Peoples Trust Federal Credit Union",


        "perkins state bank": "Perkins State Bank",


        "perpetual federal savings bank": "Perpetual Federal Savings Bank",


        "piedmont advantage credit union": "Piedmont Advantage Credit Union",


        "pima federal credit union": "Pima Federal Credit Union",


        "pinnacle bank": "Pinnacle Bank (NE)",


        "pinnacle bank ne": "Pinnacle Bank (NE)",


        "pioneer bank": "Pioneer Bank (NY)",


        "pioneer bank ny": "Pioneer Bank (NY)",
        "pioneer credit union": "Pioneer Credit Union",
        "pioneer federal credit union": "Pioneer Federal Credit Union (ID)",
        "pioneer federal credit union id": "Pioneer Federal Credit Union (ID)"

    }

   
    normalized_text = normalize_text(text)
    for key, val in OVERRIDES.items():
        if key in normalized_text:
            return val
    # ✅ Step 1: Remove known noisy prefixes before the real institution
    cleaned = re.sub(
        r"(?i)\b(do\s+not\s+cut.*?|separate\s+forms?\s+on\s+this\s+page.*?|see\s+instructions\s+on\s+back.*?)\b(?=[A-Z])",
        "",
        cleaned
    ).strip()

    # --- Step 2: Common OCR misreads for 'Optum Bank' ---
    ocr_variants = [
        r"\bOptum\s*Bank\b",
        r"\bOptum\s*Ban[kc]\b",
        r"\bOptun\s*Bank\b",
        r"\bOptm\s*Bank\b",
        r"\bO[t]um\s*Bank\b",
        r"\btum\s*Bank\b",
        r"\bOptum\s*Bamk\b",
    ]
    for pattern in ocr_variants:
        if re.search(pattern, cleaned, flags=re.IGNORECASE):
            return "Optum Bank"

    # --- Step 3: Handle glued 'OptumBank' or 'Optum Financial' ---
    if re.search(r"OptumBank", cleaned, re.IGNORECASE):
        return "Optum Bank"

    if re.search(r"Optum\s*Financial", cleaned, re.IGNORECASE):
        # Prefer Bank version if both words appear
        if "bank" in cleaned.lower():
            return "Optum Bank"
        else:
            return "Optum Financial"

    # --- Step 4: Look for any other trustee-like name (ConnectYourCare, HealthEquity, etc.) ---
    m = re.search(
        r"\b([A-Z][A-Za-z& ]{2,40}?(?:Care|Corporate|Corporation|Bank|Trust|LLC|Inc|Financial))\b",
        cleaned
    )
    if m:
        return m.group(1).strip()

    # --- Step 5: Backup: check lines after postal code header ---
    lines = text.splitlines()
    lower_lines = [L.lower() for L in lines]
    for i, header in enumerate(lower_lines):
        if "foreign postal code" in header and "telephone" in header:
            for cand in lines[i + 1:]:
                s = cand.strip()
                if not s:
                    continue
                # Skip numbers or contributions text
                if re.search(r"\d{2,}", s) or "contribution" in s.lower():
                    continue
                raw = re.sub(r"[^\w\s]+$", "", s)
                raw = re.split(
                    r"contributions\s+made\s+in\s+\d{4}.*",
                    raw, 1, flags=re.IGNORECASE
                )[0].strip()
                if raw:
                    return raw

    # --- Step 6: Fallback ---
    return "5498-SA"




#1098-T
def extract_1098t_bookmark(text: str) -> str:
    """
    Extract institution name for 1098-T forms.

    Rules:
    1. If any line contains "univ" or "university", return that full line (after cleaning).
    2. Otherwise: find a line after "foreign postal code ... qualified tuition"
       and take the next line if it looks like an institution.
    3. Fallback: scan for College, Institute, Academy, Board of Regents.
    4. If nothing found, return "1098-T".
    """

    import re
    lines = text.splitlines()

    # normalizer to fix OCR junk
    def normalize_institution(name: str) -> str:
        # Remove unwanted symbols and multiple spaces
        name = re.sub(r"[^\w\s.&-]", " ", name)
        name = re.sub(r"\s+", " ", name).strip()

        # Fix OCR artifacts and common typos
        name = re.sub(r"\bUniv\b", "University", name, flags=re.IGNORECASE)
        name = re.sub(r"\bTuiti\b", "Tuition", name, flags=re.IGNORECASE)
        name = re.sub(r"\bTution\b", "Tuition", name, flags=re.IGNORECASE)

        # --- Trim unwanted student/year/form fragments ---
        # Remove leading student info before " - University" or similar
        name = re.sub(r"^.*?-\s*(University|College|Institute|Academy|Board of Regents)", r"\1", name, flags=re.IGNORECASE)

        # Remove trailing year/form text like "2022 1098-T" or "Form 1098-T"
        name = re.sub(r"\b(19|20)\d{2}\b.*", "", name)              # remove trailing year + extras
        name = re.sub(r"\bForm\s*1098[-\s]*T.*", "", name, flags=re.IGNORECASE)
        name = re.sub(r"\b1098[-\s]*T.*", "", name, flags=re.IGNORECASE)

        return name.strip()

    KEYWORDS = r"(University|College|Institute|Academy|Univ|Board of Regents|State|Bursar|Penn State|Tuition|Tuiti|Tution)"


    # 🔹 Rule 1: any line with "univ" or "university"
    for line in lines:
        if re.search(r"\b(univ|university)\b", line, flags=re.IGNORECASE):
            return normalize_institution(line)

    lower_lines = [l.lower() for l in lines]

    # 🔹 Rule 2: look for header, then next line
    for i, L in enumerate(lower_lines):
        if "foreign postal code" in L and "qualified tuition" in L:
            if i + 1 < len(lines):
                cand = lines[i + 1].strip()
                if re.search(KEYWORDS, cand, flags=re.IGNORECASE):
                    return normalize_institution(cand)

    # 🔹 Rule 3: fallback scan for other institution markers
    for line in lines:
        if re.search(KEYWORDS, line, flags=re.IGNORECASE):
            return normalize_institution(line)

    # 🔹 Rule 4: nothing found
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
       
# ---------------------- Existing ------------------------


# ✅ ADD THIS RIGHT BELOW (new helper)
def cleanup_provider_name(name: str) -> str:
    """
    Trim addresses, ZIP codes, or EIN text from daycare/preschool names.
    Example:
      'STEMsteps 3281 Wexford Rd Gibsonia, PA 15044 EIN' -> 'STEMsteps'
    """
    import re
    if not name:
        return name

    cleaned = name.strip()
    cleaned = re.sub(r"\s+\d{3,}.*", "", cleaned)  # remove any address part
    cleaned = re.sub(
        r"\b(EIN|Zip|Address|Rd|Road|Street|St|Ave|Avenue|Blvd|Boulevard|Drive|Dr|PA|IL|TX|CA|NJ)\b.*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[,.\-]+$", "", cleaned).strip()
    return cleaned

   
def extract_daycare_bookmark(text: str) -> str:
    """
    Extract the daycare, preschool, or child care provider name
    from tuition/payment statements for Child Care Expenses.
    Returns a readable name like 'STEMsteps' or 'Kiddie Care'.
    """
    import re

    cleaned = text.replace("\n", " ").replace("  ", " ")
    lower = cleaned.lower()

    # 🔹 1) Kiddie Care override — detect by email or text
    if any(v in lower for v in ("mykiddiecare", "kiddiecare", "kiddecare", "kiddie care", "kidde care")):
        return "Kiddie Care"

    # 🔹 2) Provider Information header
    m = re.search(r"provider information[:\s]+([A-Z][A-Za-z0-9&\-,.' ]{2,60})", cleaned, re.IGNORECASE)
    if m:
        name = cleanup_provider_name(m.group(1))
        if name:
            return name

    # 🔹 3) Look for school/daycare-like institution names
    m = re.search(
        r"\b([A-Z][A-Za-z0-9&',.()\- ]{2,80}?(?:School|Schools|Academy|Learning|Center|Preschool|Daycare|Montessori|Care|Steps))\b",
        cleaned,
    )
    if m:
        return cleanup_provider_name(m.group(1))

    # 🔹 4) Fallback – scan for capitalized lines with “care”, “steps”, etc.
    lines = [L.strip() for L in text.splitlines() if L.strip()]
    for L in lines:
        if re.search(r"[A-Z][a-z]{2,}", L) and not re.search(r"\d{3,}", L):
            if any(x in L.lower() for x in ["school", "academy", "learning", "center", "care", "montessori", "steps"]):
                return cleanup_provider_name(L)

    # 🔹 5) Last resort – detect “Re:” or letterhead-style name
    for L in lines[:10]:
        if re.search(r"re:\s*(.+)", L, re.IGNORECASE):
            name = re.sub(r"re:\s*", "", L, flags=re.IGNORECASE).strip()
            return cleanup_provider_name(name)
        if re.search(r"public schools|academy|learning center|montessori|daycare|preschool|steps", L, re.IGNORECASE):
            return cleanup_provider_name(L)

    # 🔹 6) Final fallback
    return "Child Care Provider"



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
# SSN TP & SP
def detect_ssn_owner(text, tp_ssn, sp_ssn):
    clean = text.replace("-", "").replace(" ", "").replace("*", "").replace("•", "")

    if tp_ssn and tp_ssn in clean:
        return "TP"

    if sp_ssn and sp_ssn in clean:
        return "SP"

    return None

# ── Merge + bookmarks + cleanup
def merge_with_bookmarks(input_dir, output_pdf, meta_json, dummy=""):

    import json
    import sys


    # Default values
    tp_ssn = ""
    sp_ssn = ""
    tp_name = ""
    sp_name = ""

    # The server now sends JSON as 4th argument
    try:
        meta = json.loads(meta_json)
        tp_ssn = meta.get("tpSSN", "")
        sp_ssn = meta.get("spSSN", "")
        tp_name = meta.get("tpName", "")
        sp_name = meta.get("spName", "")

        print(f"[META] TP SSN={tp_ssn}, SP SSN={sp_ssn}", file=sys.stderr)

    except Exception as e:
        print(f"[META ERROR] Could not parse JSON: {e}", file=sys.stderr)
    # Prevent storing merged file inside input_dir
    abs_input = os.path.abspath(input_dir)
    abs_output = os.path.abspath(output_pdf)
    if abs_output.startswith(abs_input + os.sep):
        abs_output = os.path.join(os.path.dirname(abs_input), os.path.basename(abs_output))
        logger.warning(f"Moved output outside: {abs_output}")
    # ✅ Collect all candidate files
    all_files = sorted(
        f for f in os.listdir(abs_input)
        if f.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.tiff'))
        and f != os.path.basename(abs_output)
    )
    import hashlib

    # --- Detect duplicate PDFs by MD5 hash ---
    hash_map = {}         # md5 -> first filename
    duplicate_files = []  # list of duplicate filenames

    for f in all_files:
        path = os.path.join(abs_input, f)
        try:
            with open(path, "rb") as fh:
                md5 = hashlib.md5(fh.read()).hexdigest()
            if md5 in hash_map:
                duplicate_files.append(f)
            else:
                hash_map[md5] = f
        except Exception as e:
            print(f"⚠️ Could not hash {f}: {e}", file=sys.stderr)

    # Keep only unique files for processing
    files = sorted(hash_map.values())
    logger.info(f"Found {len(files)} unique files, {len(duplicate_files)} duplicates.")

   
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
    g1099_titles = {}
    r1099_titles = {}
    sa_titles = {}  
    mort_titles = {}
    prop_titles = {}
    sa5498_titles = {}
    t529_titles = {}
    t1098_titles = {}
    account_pages = {}  # {account_number: [(path, page_index, 'Consolidated-1099')]}
    account_names = {}
    # ✅ Track seen page text hashes to detect duplicate pages (within or across files)
    seen_pages = {}

    # --- Skip duplicates in main processing ---
    files = [f for f in files if f not in duplicate_files]

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
                    # --- 🆕 Detect duplicate pages across all PDFs ---
                    import hashlib

                    page_hash = hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()
                    if page_hash in seen_pages:
                        print(f"[DUPLICATE PAGE] {fname} p{i+1} matches {os.path.basename(seen_pages[page_hash][0])} p{seen_pages[page_hash][1]+1}", file=sys.stderr)
                        others.append((path, i, "Duplicate"))  # Move this page to Others → Duplicate
                        continue  # Skip classification for this duplicate page
                    else:
                        seen_pages[page_hash] = (path, i)

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
                    img = pdf_page_to_image(path, i, dpi=150)  # ✅ use your PyMuPDF helper
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
                    
                    if cat == 'Income' and ft == '1099-R':
                        title = extract_1099r_bookmark(txt)
                        if title and title != '1099-R':
                            r1099_titles[(path, i)] = title

                    if cat == 'Expenses' and ft == '1098-Mortgage':
                        title = extract_1098mortgage_bookmark(txt)
                        if title and title != '1098-Mortgage':
                            mort_titles[(path, i)] = title
                    if cat == 'Expenses' and ft == '5498-SA':
                        title = extract_5498sa_bookmark(txt)
                        if title and title != '5498-SA':
                            sa5498_titles[(path, i)] = title
                           
                    if cat == 'Expenses' and ft == '1098-T':
                        title = extract_1098t_bookmark(txt)
                        if title and title != '1098-T':
                            t1098_titles[(path, i)] = title
                    if cat == 'Expenses' and ft == '529-Plan':
                        title = extract_529_bookmark(txt)
                        if title and title != '529-Plan':
                            t529_titles[(path, i)] = title
                    

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
                acctnum = extract_account_number(tiered)
                lowertext = tiered.lower()

                # NEW: acct + Issuer Name
                if acctnum:
                    # --- Only add to Consolidated-1099 if it's truly a 1099 form ---
                    if '1099' in lowertext and not re.search(r'1098-t', lowertext, re.IGNORECASE):
                        # Check if this account already exists
                        if acctnum not in account_pages:  # ✅ FIXED: account_pages (with underscore)
                            # FIRST occurrence - add the full entry
                            account_pages[acctnum] = [(path, i, 'Consolidated-1099')]

                        # Capture issuer name if present
                            issuer = extract_consolidated_issuer(tiered)
                            if issuer:
                                account_names[acctnum] = issuer  # ✅ FIXED: account_names (with underscore)
            
                            print(f"DEBUG: {os.path.basename(path)} p{i+1} => NEW Consolidated-1099 (acct={acctnum})", file=sys.stderr)
                        else:
                # SUBSEQUENT pages with same account - just track them
                            account_pages[acctnum].append((path, i, 'Consolidated-1099'))
                            print(f"DEBUG: {os.path.basename(path)} p{i+1} => Added to EXISTING Consolidated-1099 (acct={acctnum})", file=sys.stderr)




# Always classify after account checks
                cat, ft = classify_text(tiered)
                # 🚫 Skip per-page bookmark creation for K-1 pages (will be grouped later)
                if cat == "Income" and ft == "K-1":
                    income.append((path, i, ft))
                    continue

               
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
    # --- Schedule K-1 (Form 1065) grouping ---
    # --- Schedule K-1 (Form 1065) grouping ---
# --- Schedule K-1 (Form 1065) grouping ---
    


    # merge & bookmarks
    merger = PdfMerger()
    page_num = 0
    stop_after_na = False
    import mimetypes
    #seen_pages = set()
    def append_and_bookmark(entry, parent, title, with_bookmark=True, owner_override="detect"):
        nonlocal page_num, seen_pages
        sig = (entry[0], entry[1])
        if sig in seen_pages:
            print(f"[DUPLICATE] Skipping {os.path.basename(entry[0])} page {entry[1]+1}", file=sys.stderr)
            return
        seen_pages[sig] = True

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

        # -------- INSERT THIS BLOCK INSIDE FUNCTION --------
        try:
            if owner_override is None:
                page_text = extract_text(p, idx)
                owner = detect_ssn_owner(page_text, tp_ssn, sp_ssn)
                if owner:
                    title = f"{title} – {owner}"

                print(f"[SSN Tag] {os.path.basename(p)} p{idx+1} → {owner}", file=sys.stderr)

        except Exception as e:
            print(f"[SSN Tag Error] {e}", file=sys.stderr)
        # ---------------------------------------------------

        if with_bookmark and title:
            merger.add_outline_item(title, page_num, parent=parent)

        page_num += 1


    # ── Bookmarks
   
    if income:
        root = merger.add_outline_item('Income', page_num)
        groups = group_by_type(income)
        for form, grp in sorted(groups.items(), key=lambda kv: get_form_priority(kv[0], 'Income')):
                # --- Add Schedule K-1 (Form 1065) hierarchy ---
            # --- Add Schedule K-1 (Form 1065) hierarchy once ---
            


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
                    base_label = issuer or f"Account {acct}"

        # ------------------------------------------------------------------
        #  COLLECT ALL REAL PAGES FOR THIS ACCOUNT (GUARANTEED TO WORK)
        # ------------------------------------------------------------------
                    real_entries = consolidated_payload.get(key, [])
                    owner = None

                    for rp in real_entries:
                        rp_path, rp_idx, _ = rp
                        txt = extract_text(rp_path, rp_idx)
                        who = detect_ssn_owner(txt, tp_ssn, sp_ssn)
                        if who:
                            owner = who
                            break

        # Build final account label
                    if owner:
                        account_label = f"{base_label} – {owner}"
                    else:
                        account_label = base_label

                    # Create the account bookmark
                    account_node = merger.add_outline_item(account_label, page_num, parent=cons_root)

        # ------------------------------------------------------------------
        #  ADD ALL PAGES BELOW THIS ACCOUNT
        # ------------------------------------------------------------------
                    for real_entry in real_entries:
                        page_text = extract_text(real_entry[0], real_entry[1])

            # Skip unused pages
                        if is_unused_page(page_text):
                            others.append((real_entry[0], real_entry[1], "Unused"))
                            continue

            # High-confidence detection
                        form_type = classify_div_int(page_text)

                        if form_type:
                            append_and_bookmark(real_entry, account_node, form_type, owner_override=None)
                            continue

                        # Multi-form fallback
                        form_matches = classify_text_multi(page_text)
                        if form_matches:
                            append_and_bookmark(real_entry, account_node, form_matches[0])
                        else:
                            append_and_bookmark(real_entry, account_node, "", with_bookmark=False)

                continue
  # <<< KEEP THIS

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
                
                elif form == '1099-R':
                    payer = r1099_titles.get((path, idx))
                    if payer:
                        lbl = payer

                # NEW: strip ", N.A" and stop after this bookmark
                if ", N.A" in lbl:
                    lbl = lbl.replace(", N.A", "")
                print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Income', Form='{form}', Title='{lbl}'", file=sys.stderr)
                   
                # normal case
                print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Income', Form='{form}', Title='{lbl}'", file=sys.stderr)
                # 🆕 Detect SSN owner for this page and label it
                page_text = extract_text(path, idx)
                
 
                #print(f"[SSN Tag] {os.path.basename(path)} p{idx+1} → {owner}", file=sys.stderr)
 
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
                        page_text = extract_text(path, idx)  # ✅ get text for this page
                        lbl = extract_1098t_bookmark(page_text)
                elif form == "Child Care Expenses":
                    page_text = extract_text(path, idx)
                    lower_page = page_text.lower()

                    # Check for key tax ID identifiers
                    has_taxid = any(
                        key.lower() in lower_page
                        for key in [
                            "federal employer id",
                            "fein",
                            "tax id",
                            "ein",
                            "federal tax id",
                        ]
                    )

                    if has_taxid:
                        provider = extract_daycare_bookmark(page_text)
                        lbl = provider if provider else "Child Care Provider"
                        append_and_bookmark(entry, node, lbl)
                        print(
                            f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Expenses', "
                            f"Form='Child Care Expenses', Title='{lbl}' (✅ has tax ID)",
                            file=sys.stderr
                        )
                    else:
        # Append page but without bookmark
                        append_and_bookmark(entry, node, "", with_bookmark=False)
                        print(
                            f"[No Bookmark] {os.path.basename(path)} p{idx+1} → Category='Expenses', "
                            f"Form='Child Care Expenses' (no tax ID keywords found)",
                            file=sys.stderr
                        )

                elif form == '529-Plan':
                    title = t529_titles.get((path, idx))
                    if title:
                        lbl = title
                elif form == 'Property Tax':
                    title = prop_titles.get((path, idx))
                    if title:
                        lbl = title


               
                # NEW: strip ", N.A" and stop
                if ", N.A" in lbl:
                    lbl = lbl.replace(", N.A", "")
                print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Expenses', Form='{form}', Title='{lbl}'", file=sys.stderr)
                   
                # normal case
                print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Expenses', Form='{form}', Title='{lbl}'", file=sys.stderr)
                page_text = extract_text(path, idx)
                
 
                #print(f"[SSN Tag] {os.path.basename(path)} p{idx+1} → {owner}", file=sys.stderr)
 
                append_and_bookmark(entry, node, lbl)
            if stop_after_na:
                break

# --- Add Others section with Unused and Duplicate pages ---
    if others or duplicate_files:
        root = merger.add_outline_item('Others', page_num)

        # Unused pages
        unused_pages = [e for e in others if e[2] == 'Unused']
        if unused_pages:
            node_unused = merger.add_outline_item('Unused', page_num, parent=root)
            for entry in unused_pages:
                append_and_bookmark(entry, node_unused, "", with_bookmark=False)
                print(f"[Bookmark] {os.path.basename(entry[0])} p{entry[1]+1} → Category='Others', Form='Unused'", file=sys.stderr)

    # 🆕 Duplicate pages or duplicate files
        # 🆕 Duplicate pages or duplicate files
        dup_pages = [e for e in others if e[2] == 'Duplicate']
        if dup_pages or duplicate_files:
            node_dupe = merger.add_outline_item('Duplicate', page_num, parent=root)

            # Page-level duplicates (append without bookmarks)
            for entry in dup_pages:
                append_and_bookmark(entry, node_dupe, "", with_bookmark=False)

            # File-level duplicates (append without bookmarks)
            for f in duplicate_files:
                dup_path = os.path.join(abs_input, f)
                try:
                    reader = PdfReader(dup_path)
                    for i in range(len(reader.pages)):
                        append_and_bookmark((dup_path, i, "Duplicate"), node_dupe, "", with_bookmark=False)
                    print(f"[Duplicate] Added file {f} under 'Others → Duplicate'", file=sys.stderr)
                except Exception as e:
                    print(f"⚠️ Failed to append duplicate file {f}: {e}", file=sys.stderr)
                # 1095-C forms
        c1095_pages = [e for e in others if e[2] == '1095-C']
        if c1095_pages:
            node_1095c = merger.add_outline_item('1095-C', page_num, parent=root)
            for entry in c1095_pages:
                path, idx, _ = entry
                page_text = extract_text(path, idx)
                lbl = extract_1095c_bookmark(page_text)
                append_and_bookmark(entry, node_1095c, lbl)
                print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Others', Form='1095-C', Title='{lbl}'", file=sys.stderr)




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
if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description="Merge PDFs with robust text extraction and TP/SP labeling")
    p.add_argument('input_dir', help="Folder containing PDFs to merge")
    p.add_argument('output_pdf', help="Path for the merged PDF (outside input_dir)")
    p.add_argument('tp_ssn', nargs='?', default='', help="Taxpayer SSN last 4 digits")
    p.add_argument('sp_ssn', nargs='?', default='', help="Spouse SSN last 4 digits")
    args = p.parse_args()
    merge_with_bookmarks(args.input_dir, args.output_pdf, args.tp_ssn, args.sp_ssn)
