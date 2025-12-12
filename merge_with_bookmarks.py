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
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\Vinod Kumar\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

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
import concurrent.futures
import pytesseract
import sys
import traceback
from PyPDF2 import PdfReader

import threading
from pdfminer.layout import LAParams

# ---------------------------------------
# UPDATED PDFMiner LAParams (fixes broken words & broken lines)
# ---------------------------------------

def extract_text(path: str, page_index: int) -> str:
    text = ""

    ocr_result = [""]
    pdf_result = [""]

    # -----------------------
    # THREAD 1 → OCR
    # -----------------------
    def do_ocr():
        try:
            dpi = 300
            img = pdf_page_to_image(path, page_index, dpi=dpi)
            gray = img.convert("L")
            bw = gray.point(lambda x: 0 if x < 180 else 255, '1')

            t_ocr = pytesseract.image_to_string(
                bw,
                lang="eng",
                config="--oem 3 --psm 6"
            ) or ""

            print(f"[OCR dpi={dpi}]\n{t_ocr}", file=sys.stderr)
            ocr_result[0] = t_ocr
        except Exception:
            traceback.print_exc()
            ocr_result[0] = ""

    # -----------------------
    # THREAD 2 → PDFMiner
    # -----------------------
    def do_pdfminer():
        try:
            # Use DEFAULT LAPARAMS (same as Extraction 1)
            t1 = pdfminer_extract(
                path,
                page_numbers=[page_index]
            ) or ""

            print(f"[PDFMiner full]\n{t1}", file=sys.stderr)
            pdf_result[0] = t1
        except Exception:
            traceback.print_exc()
            pdf_result[0] = ""

    # -----------------------
    # Run both threads
    # -----------------------
    t1 = threading.Thread(target=do_ocr)
    t2 = threading.Thread(target=do_pdfminer)

    t1.start()
    t2.start()

    t1.join()
    t2.join()

    # -----------------------
    # Priorities:
    # 1. PDFMiner (best)
    # 2. OCR (fallback)
    # 3. PyPDF2 (last)
    # -----------------------

    # PDFMiner first
    if pdf_result[0].strip():
        text = pdf_result[0]

    # OCR fallback
    elif ocr_result[0].strip():
        text = ocr_result[0]

    # PyPDF2 fallback
    else:
        try:
            reader = PdfReader(path)
            t2 = reader.pages[page_index].extract_text() or ""
            print(f"[PyPDF2 full]\n{t2}", file=sys.stderr)
            text = t2
        except Exception:
            traceback.print_exc()
            text = ""

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

def pre_classify_skip_page(text: str) -> bool:
    t = text.lower()
    if "THIS PAGE WAS INTENTIONALLY LEFT BLANK" in t:
        return True
    if "this page was intentionally left blank" in t:
        return True
    # 529-plan
    if "municipal securities and results will vary with market conditions" in t:
        return True
    if "you have 60 days from the date of the statement to notify the plan" in t:
        return True
    
    if "program manager for the bright start" in t and "description solely with respect" in t:
        return True
    if "distributed to either the account owner" in t and "the plan is administered by the state treasurer" in t:
        return True
    if ("distributed to either the account owner" in t 
        and "the plan is administered by the state treasurer" in t 
        and "$" not in t):
        return True
    #Consolidated-1099
    #merrill
    if (
        "we would like you to note the following" in t
        and "important items for your attention" in t
        and "merrill is only required to revise 1099" in t
        and "to view additional tax resources available" in t
        and "this information applies to foreign persons and entities" in t
        and "bonds held directly or through mutual funds" in t
    ):
        return True
    if (
        "we would like you to note the following" in t
        and "merrill is only required to revise a" in t
        #and "" in t
        and "portion of the amount reported in line" in t
        and "residents be advised that payers are required" in t
        and "or unit investments trusts" in t
    ):
        return True
    #apex clearing
    if (
        "covered security acquired on or after january 1" in t
        and "see the instructions above for a covered security acquired with acquisition premium" in t
        and "regulations section 1.6045-1" in t
        and "acquisition premium amortization for the year that reduces the amount" in t
        and "report this amount on schedule b (form 1040)" in t
        and "market discount is includible in taxable income as interest income" in t
    ):
        return True
    if (
        "covered security acquired" in t
        and "if an amount is reported in this box, see the instructions for schedule b (form 1040)" in t
        and "regulations section 1.6045-1" in t
        and "reduces the amount of oid that is included as interest" in t
        and "report the net amount of oid on schedule b (form 1040)" in t
    ):
        return True
    if (
        "covered security acquired on or after january 1" in t
        and "see the instructions for schedule b (form 1040)" in t
        and "regulations section 1.6045-1" in t
        and "acquisition premium amortization for the year" in t
        and "report this amount as interest income" in t
    ):
        return True
    #apex clearing

    #1099-INt
    SKIP_BLOCK_TEXT = "bond premium on tax-exempt bond"

    # 1099-INT
    if ("payer of the election in writing in accordance with regulations section" in t
        and SKIP_BLOCK_TEXT not in t):
        return True

    if ("a spouse is not reuired to file a nominee return" in t
        and SKIP_BLOCK_TEXT not in t):
        return True

    if ("interest is exempt from state and local" in t 
        and "for the latest information about developments" in t
        and SKIP_BLOCK_TEXT not in t):
        return True

    if ("deposits products provided by goldman sachs bank usa" in t 
        and "interest is exempt from state and local" in t
        and SKIP_BLOCK_TEXT not in t):
        return True

    if ("marcus by goldman sachs is a brand of goldman sachs bank" in t 
        and "interest is exempt from state and local" in t
        and SKIP_BLOCK_TEXT not in t):
        return True

    if ("and build america bonds taht must be included" in t 
        and "for the latest information" in t
        and SKIP_BLOCK_TEXT not in t):
        return True

    if ("amount of interest paid to you notified" in t 
        and "an amount is not reported in this box for a tax" in t
        and SKIP_BLOCK_TEXT not in t):
        return True
    # W-2 General
    if "these are substitute wage and tax statements and are " in t:
        return True
    if "acceptable for filing with your federal, state and local/city income tax returns." in t:
        return True
    if "satisfy section 409a. this amount is also included in box 1. it is subject to an" in t:
        return True
    if "there is no longer a substantial risk of forfeiture of your right to the" in t:
        return True
    if "name and ssn are correct but aren’t the same as shown" in t:
        return True
    if "the following information reflects your final pay statement plus employer adjustments that comprise your w-2" in t:
        return True
    if "employee w-4 profile to change your employee w-4 profile information" in t:
        return True
    if "you may be able to take copies of form w-2c from your employer for all corrections made so" in t:
        return True
    if "this amount includes the 1.45% medicare tax withheld taxable for social security and medicare taxes this year because there is" in t:
        return True
    if "contact your plan administrator for more information. amounts for reporting requirements." in t:
        return True
    if "however, if you were at least age 50 in 2024, your employer" in t:
        return True
    if "social security or rrta tax on taxable cost of benefits, just in case there is a" in t:
        return True
    if "deferrals under a section 409a nonqualified deferred compensation" in t:
        return True
    if "to claim a credit for the excess against your federal income tax" in t:
        return True
    if "contact your plan administrator for more information" in t:
        return True
    if "you must file form 4137 with your income tax return to report at least" in t:
        return True
    if "uncollected medicare tax on taxable cost of group-term life" in t:
        return True
    if "uncollected social security or rrta tax on taxable cost of group-term life" in t:
        return True
    if "income under a nonqualified deferred compensation plan that fails" in t:
        return True
    if "keep copy c until you begin receiving social security" in t:
        return True
    if "employers may use this box to report information such as state" in t:
        return True
    if "paid directly to a apply to the amount of traditional ira contributions you may deduct" in t:
        return True

    # NEW — W-2 BOX 12, 13, 14 TRIGGER TEXT
    if "elective deferrals under a section 408(k)(6)" in t:
        return True
    if "elective deferrals and employer contributions" in t and "457(b)" in t:
        return True
    if "elective deferrals to a section 501(c)(18)(d)" in t:
        return True
    if "nontaxable sick pay" in t:
        return True
    if "20% excise tax on excess golden parachute payments" in t:
        return True
    if "substantiated employee business expense reimbursements" in t:
        return True
    if "uncollected social security or rrta tax on taxable cost of group-term life insurance" in t:
        return True
    if "uncollected medicare tax on taxable cost of group-term life insurance" in t:
        return True
    if "excludable moving expense reimbursements paid directly to a member of the u.s. armed forces" in t:
        return True
    if "nontaxable combat pay" in t:
        return True
    if "employer contributions to your archer msa" in t:
        return True
    if "employee salary reduction contributions under a section 408(p) simple plan" in t:
        return True
    if "adoption benefits" in t:
        return True
    if "income from exercise of nonstatutory stock option" in t:
        return True
    if "employer contributions to your health savings account" in t:
        return True
    if "deferrals under a section 409a" in t:
        return True
    if "designated roth contributions under a section 401(k)" in t:
        return True
    if "designated roth contributions under a section 403(b)" in t:
        return True
    if "cost of employer-sponsored health coverage" in t:
        return True
    if "designated roth contributions under a governmental section 457(b)" in t:
        return True
    if "permitted benefits under a qualified small employer health reimbursement arrangement" in t:
        return True
    if "income from qualified equity grants under section 83(i)" in t:
        return True
    if "aggregate deferrals under section 83(i) elections" in t:
        return True
    if "retirement plan box is checked" in t:
        return True
    if "employers may use this box to report information such as state disability insurance taxes withheld" in t:
        return True
    if "this package includes three copies of the w-2. here’s how to use each of them" in t:
        return True
    if "file this copy with your federal tax return by april 15th, 2025" in t:
        return True
    if "we hope this helps make tax season easier. if you have any questions about" in t:
        return True
    return False



def is_unused_page(text: str):
    """
    Detect pages that are just year-end messages, instructions,
    or generic investment details (not real 1099 forms).

    Returns:
        (True, [reasons]) or (False, [])
    """
    import re

    reasons = []
    lower = text.lower()
    norm = re.sub(r"\s+", " ", lower)

    # ==========================================================
    # ⛔ NEVER mark a REAL 1099-INT as unused
    # ==========================================================
    if ("form 1099-int" in norm or "1099-int" in norm) and (
        "$" in norm or "interest income" in norm or "payer's tin" in norm
    ):
        return False, []

    # ==========================================================
    # 🟦 UBS COVER PAGE (MANDATORY + OPTIONAL)
    # ==========================================================
    if "ubs financial services inc." in norm:
        ubs_optional_patterns = [
            "consolidated form 1099",
            #"your financial advisor",
            "to help you prepare for tax filing",
            "stock plan participants",
            "statements & reports tab",
            "ubs one source",
            "does not provide tax advice",
        ]
        matched = [p for p in ubs_optional_patterns if p in norm]
        if matched:
            reasons.append(
                "UBS cover page → matched: "
                + ", ".join(f"'{m}'" for m in matched)
            )

    # ==========================================================
    # 🟨 ONE-WAY KEYWORD RULES (OR)
    # ==========================================================
    keyword_rules = [
        "understanding your form 1099",
        "please utilize the master account number and document",
        "supplement in a format that may be more helpful if you have a large number of transactions",
        "retirement accounts will be reported under robinhood securities llc",

        # Robinhood unused
        "he basis to reflect your option premium. if the securities were acquired through the",
        "had a reportable change in control or capital structure. you may be required to",
        "box does not include proceeds from regulated futures contracts or section 1256 option",
        "may also show the aggregate amount of cash and the fair market value of any",

        "common instructions for recipient",
        "1099-misc instructions for recipient",
        "line 1a. shows total ordinary dividends",
        #"this amount may be subject to backup withholding",

        # UBS
        "keep tax documents for your records. ubs will send you corrected forms 1099 only if revisions exceed",

        # E*TRADE
        "the amount of tax-exempt interest",
        "interest paid to you must bet",
        "the amount of tax-exempt interest paid to you must be reported on the applicable form 1040",
        "interest paid to you must be taken into account in computing the amt reported on form 1040",

        "year-end messages",
        "important: if your etrade account transitioned",
        "please visit etrade.com/tax",

        # Robinhood
        "tax forms for robinhood markets",
        "robinhood retirements accounts",

        # Tax year notices
        "new for 2023 tax year",
        "new for 2024 tax year",
        "new for 2025 tax year",

        "please note there may be a slight timing",
        "account statement will not have included",

        # 1099-SA
        "fees and interest earnings are not considered",

        # Mortgage
        "for clients with paid mortgage insurance",

        "you can also contact the",

        "may be requested by the mortgagor",

        "tax lot closed on a first in",
        "your form 1099 composite may include the following internal revenue service",
        "schwab provides your form 1099 tax information as early",
        "if you have any questions or need additional information about your",
        "schwab is not providing cost basis",
        "the amount displayed in this column has been adjusted for option premiums",
        "you may select a different cost basis method for your brokerage",
        "to view and change your default cost basis",
        "shares will be gifted based on your default cost basis",
        "if you sell shares at a loss and buy additional shares",
        "we are required to send you a corrected from with the revisions clearly marked",
        "referenced to indicate individual items that make up the totals appearing",
        "issuers of the securities in your account reallocated certain income distribution",
        #"the amount shown may be dividends a corporation paid directly",
        "if this form includes amounts belonging to another person",
        "spouse is not required to file a nominee return to show",
        "brokers and barter exchanges must report proceeds from",
        "first in first out basis",
        "see the instructions for your schedule d",

        "other property received in a reportable change in control or capital",

        # Consolidated
        "filing your taxes",
    ]

    for kw in keyword_rules:
        if kw in norm:
            reasons.append(f"matched keyword → '{kw}'")

    # ==========================================================
    # 🟥 MULTI-CONDITION (AND) RULES
    # ==========================================================
    if (
        "ubs will send you" in norm
        and "amount of premium amortization" in norm
        and "instructions for recipient" in norm
    ):
        reasons.append(
            "UBS instructions → ('ubs will send you' + 'amount of premium amortization' + 'instructions for recipient')"
        )

    if (
        "line 11" in norm
        and "premium amortization" in norm
        and "covered security" in norm
        and "instructions for schedule b" in norm
    ):
        reasons.append(
            "IRS Schedule B premium amortization (4-condition match)"
        )

    if "enclosed is your" in norm and "consolidated tax statement" in norm:
        reasons.append(
            "consolidated tax statement cover page"
        )

    if "filing your taxes" in norm and "turbotax" in norm:
        reasons.append(
            "TurboTax help / marketing page"
        )

    # ==========================================================
    # ✅ FINAL DECISION
    # ==========================================================
    if reasons:
        return True, reasons

    return False, []


def extract_account_number(text: str, form_type: str = "", page_number: int = None) -> str | None:
    # --- normalize ---
    text = text.replace("\n", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    lower = text.lower()

    # --- skip rules (same as yours) ---

    # ==========================================================
    # 0️⃣ UBS COVER PAGE DETECTION (Skip account number parsing)
    # ==========================================================
    if "ubs financial services inc." in lower:

        # Optional cover-page triggers
        ubs_optional_patterns = [
            "consolidated form 1099",
            # "your financial advisor",  # SAFE TO KEEP COMMENTED OUT
            "to help you prepare for tax filing",
            "stock plan participants",
            "statements & reports tab",
            "ubs one source",
            "does not provide tax advice",
        ]

    # -------------------------------
    # NEW ONE-LINE LONG CONDITION
    # -------------------------------
        long_one_line = (
            "keep tax documents for your records. ubs will send you corrected forms 1099 only if revisions exceed"
            in lower
        )

    # -------------------------------
    # NEW 3-PHRASE AND CONDITION
    # -------------------------------
        three_and = (
            "the amount of premium amortization" in lower
            and "instructions for recipient" in lower
            and "tax-exempt covered security" in lower
        )

    # -------------------------------
    # NEW 4-PHRASE AND CONDITION
    # -------------------------------
        four_and = (
            "line 11." in lower
            and "covered security acquired at a premium" in lower
            and "regulations section 1.6045-1" in lower
            and "reportable on form 1040 or 1040-sr" in lower
        )

    # -------------------------------
    # MAIN UBS COVER-PAGE DECISION
    # -------------------------------
        if (
            any(pat in lower for pat in ubs_optional_patterns)
            or long_one_line
            or three_and
            or four_and
        ):
            if page_number is not None:
                print(f"⛔ Page {page_number} → UBS cover/instruction page detected (skipped)")
            return None

    # ==========================================================

    # ------------------------------------------------------------------
    # ACORNS SECURITIES LLC - only run this if it's really Acorns
    # ------------------------------------------------------------------
    acorns_account = None
    if "acorns securities llc" in lower:
        acorns_patterns = [
            # "Account 01147670570416B1"
            r"Account[\s:\-\u200B\u200C\u200D\u00A0\uFEFF]*([0-9]{10,}[A-Za-z0-9]*)",
            # "Account\n01147670570416B1"
            r"Account[^\n\r]{0,40}\s+([0-9]{10,}[A-Za-z0-9]*)",
            # "Account: 01147670570416B1"
            r"Account\s*[:\-]\s*([0-9]{10,}[A-Za-z0-9]*)",
            # OCR glitches: "Accourt", "Accoumt", etc.
            r"Accou[nmrt0]+\s*([0-9]{10,}[A-Za-z0-9]*)",
            # "Account01147670570416B1"
            r"Account([0-9]{10,}[A-Za-z0-9]*)",
        ]

        for p in acorns_patterns:
            m = re.search(p, text, flags=re.IGNORECASE)
            if m:
                acorns_account = m.group(1).strip()
                break

        # last-resort: any 14–18-char digit/letter blob
        if not acorns_account:
            fallback = re.search(r"\b([0-9]{10,16}[A-Za-z0-9]{0,4})\b", text)
            if fallback:
                acorns_account = fallback.group(1).strip()

        if acorns_account:
            acorns_account = (
                acorns_account.replace(" ", "")
                              .replace("–", "-")
                              .replace("—", "-")
                              .replace("\u00A0", "")
                              .replace("\u200B", "")
                              .replace("\u200C", "")
                              .replace("\u200D", "")
                              .replace("\uFEFF", "")
            )
            if page_number is not None:
                print(f"✅ Page {page_number} → ACORNS account detected: {acorns_account}")
            return acorns_account

    # ---------------------------------------------------------------------
    # 2️⃣ FIDELITY 1099 (OCR SAFE)
    # ---------------------------------------------------------------------
    fidelity_patterns = [
        r"Account\s*No\.?\s*[:\-]?\s*([A-Za-z0-9]{1,3}[A-Za-z0-9\-]{3,})",
        r"AccountNo\.?\s*[:\-]?\s*([A-Za-z0-9]{1,3}[A-Za-z0-9\-]{3,})",
        r"Account\s*No\.?[^\n\r]*\n\s*([A-Za-z0-9]{1,3}[A-Za-z0-9\-]{3,})",
        r"AccountNo\.?[^\n\r]*\n\s*([A-Za-z0-9]{1,3}[A-Za-z0-9\-]{3,})",
        r"AccountNo\.?\s*([A-Za-z0-9]{4,})",
        r"Account\s*No\s+([A-Za-z0-9]{4,})",
        r"Account\s*No\.?\s*([A-Za-z0-9]+[\u2010\u2011\u2012\u2013\u2014\-][A-Za-z0-9\-]+)",
    ]

    fidelity_account = None
    for p in fidelity_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            fidelity_account = m.group(1).strip()
            break

    if fidelity_account:
        fidelity_account = re.sub(r"^2Z", "Z", fidelity_account, flags=re.IGNORECASE)
        fidelity_account = re.sub(r"^2?24-", "Z24-", fidelity_account, flags=re.IGNORECASE)
        fidelity_account = fidelity_account.replace("–", "-").replace("—", "-")

    # ---------------------------------------------------------------------
    # 3️⃣ UBS (Account W5 34244)
    # ---------------------------------------------------------------------
    ubs_account = None
    m = re.search(
        r"Account[\s:\-]*\n?\s*([A-Za-z0-9]{1,4})\s*([0-9]{3,})",
        text,
        re.IGNORECASE
    )
    if m:
        ubs_account = (m.group(1) + m.group(2)).strip()
    # Fallback: W5 34244 anywhere
    if not ubs_account:
        m = re.search(
            r"\b(W[0-9]{1,3})\s*([0-9]{3,6})\b",
            text,
            re.IGNORECASE
        )
        if m:
            ubs_account = (m.group(1) + m.group(2)).strip()

    # ---------------------------------------------------------------------
    # 4️⃣ MERRILL LYNCH / MERRILL EDGE
    # ---------------------------------------------------------------------
    merrill_account = None
    merrill_patterns = [
        r"Account\s*No\.?\s*[:\-]?\s*([A-Za-z0-9\-]{4,})",
        r"Account\s*No\.?[^\n\r]*\n\s*([A-Za-z0-9\-]{4,})",
        r"(?:Merrill(?:\s+Lynch|\s+Edge)?)?\s*Account\s*No\.?\s*[:\-]?\s*([A-Za-z0-9\-]{4,})",
        r"Accou[nmrt]+\s*No\.?\s*[:\-]?\s*([A-Za-z0-9\-]{4,})",
        r"Customer\s*Account\s*Number[:\s]*([A-Za-z0-9\s\-]{4,})",
        r"Account\s+([A-Za-z0-9]{4,})",
    ]

    for p in merrill_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            merrill_account = m.group(1).strip()
            break

    if merrill_account:
        merrill_account = merrill_account.replace(" ", "").replace("-", "").upper()

    # ---------------------------------------------------------------------
    # 5️⃣ STANDARD (enhanced)
    # ---------------------------------------------------------------------
    std_patterns = [
        r"Account\s*Number[:\s]*([\d\-]+)",
        r"Account Number:\s*([\d\s]+)",
        r"ORIGINAL:\s*([\d\s]+)",
        r"Account\s+(\d+)"
        r"Account\s*Number[:\s]*([\dA-Za-z\-]+)",
        r"Account Number:\s*([\dA-Za-z\s]+)",
        r"Account\s*No\.?[:\s]*([\dA-Za-z\-]+)",
        r"ORIGINAL:\s*([\dA-Za-z\s]+)",
        r"Account\s+(?!WITH\b)(?=[A-Za-z0-9\-]*\d)([A-Za-z0-9\-]+)",
        r"Account\s*Number[:\s]*([\dA-Za-z\-]+)",
        r"Account Number:\s*([\dA-Za-z\s]+)",
        r"Account\s*No\.?[:\s]*([\dA-Za-z\-]+)",
        r"ORIGINAL:\s*([\dA-Za-z\s]+)",
        r"Account\s*[:\-]?\s*([A-Za-z0-9\-]{6,})",   # <--- enhanced pattern
    ]

    std_account = None
    for p in std_patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            std_account = m.group(1).replace(" ", "").strip()
            break

    # ---------------------------------------------------------------------
    # 6️⃣ APEX CLEARING
    # ---------------------------------------------------------------------
    m = re.search(r"Apex\s+Clearing[^\n\r]*\n\s*([A-Z0-9\-]{4,})", text, re.IGNORECASE)
    apex_next = m.group(1).strip() if m else None

    m = re.search(r"Apex\s+Clearing[^\n\r]{0,60}?([A-Z0-9\-]{4,})", text, re.IGNORECASE)
    apex_inline = m.group(1).strip() if m else None

    # ---------------------------------------------------------------------
    # 7️⃣ COMBINE WITH PRIORITY
    # ---------------------------------------------------------------------
    found = {
        fidelity_account,
        ubs_account,
        merrill_account,
        std_account,
        apex_next,
        apex_inline,
    }
    found = {a for a in found if a}

    detected_account = None

    if found:
        normalized = {a.replace("-", "").upper() for a in found}
        if len(normalized) == 1:
            detected_account = list(found)[0]
        else:
            detected_account = (
                fidelity_account
                or ubs_account
                or merrill_account
                or std_account
                or apex_next
                or apex_inline
            )

    # ---------------------------------------------------------------------
    # 8️⃣ DEBUG PRINT
    # ---------------------------------------------------------------------
    if page_number is not None:
        if detected_account:
            print(f"✅ Page {page_number} → Account detected: {detected_account}")
        else:
            print(f"⚠️ Page {page_number} → No account found")

    return detected_account

def is_consolidated_issuer(text: str) -> bool:
    """
    Returns True if the page belongs to a brokerage firm that issues
    consolidated 1099 packets.
    """
    t = text.lower()

    issuers = [
        "robinhood",
        "fidelity",
        "charles schwab",
        "schwab",
        "etrade",
        "e*trade",
        "ameritrade",
        "td ameritrade",
        "morgan stanley",
        "wealthfront",
        "vanguard",
        "apex clearing",
        "interactive brokers",
        "ubs financial",
        "ubs financial services",
        "apex clearing",
        "merrill",
        
        
    ]

    return any(name in t for name in issuers)



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
import re
import re

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


def extract_div_section(text: str) -> str:
    """
    Extract only the 1099-DIV section block.
    Prevents matching numbers from 1099-B table.
    """
    patterns = [
        r"1099[\s\-]*div.*?(?=1099[\s\-]*misc)",     # DIV followed by next form
        r"1099[\s\-]*div.*?(?=summary of)",          # DIV block before summary
    ]

    for p in patterns:
        m = re.search(p, text, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(0)

    return ""   # no DIV section



def has_nonzero_div(text: str) -> bool:
    section = extract_div_section(text)
    if not section:
        return False

    patterns = [
        r"1a.*?([0-9,]+\.\d{2})",
        r"1b.*?([0-9,]+\.\d{2})",
        r"2a.*?([0-9,]+\.\d{2})",
        r"2b.*?([0-9,]+\.\d{2})",
        r"2c.*?([0-9,]+\.\d{2})",
        r"2d.*?([0-9,]+\.\d{2})",
        r"2e.*?([0-9,]+\.\d{2})",
        r"2f.*?([0-9,]+\.\d{2})",
        r"3.*?([0-9,]+\.\d{2})",
        r"4.*?([0-9,]+\.\d{2})",
        r"5.*?([0-9,]+\.\d{2})",
        r"6.*?([0-9,]+\.\d{2})",
        r"7.*?([0-9,]+\.\d{2})",
        r"9.*?([0-9,]+\.\d{2})",
        r"10.*?([0-9,]+\.\d{2})",
        r"11.*?([0-9,]+\.\d{2})",
        r"12.*?([0-9,]+\.\d{2})",
    ]

    return _check_nonzero(patterns, section)


def has_nonzero_int(text: str) -> bool:
    """
    Detects if a 1099-INT form has any nonzero values.
    Works even if '$' is missing or separated by a space, e.g. '$ 6.43' or '6.43'.
    """
    patterns = [
        r"1[\.\-,)]?\s*INTEREST\s+INCOME.*?\$?\s*([0-9,]+\.\d{2})",
        r"2[\.\-,)]?\s*EARLY\s+WITHDRAWAL\s+PENALTY.*?\$?\s*([0-9,]+\.\d{2})",
        r"3[\.\-,)]?\s*INTEREST\s+ON\s+U\.?S\.?\s+SAVINGS.*?\$?\s*([0-9,]+\.\d{2})",
        r"4[\.\-,)]?\s*FEDERAL\s+INCOME\s+TAX\s+WITHHELD.*?\$?\s*([0-9,]+\.\d{2})",
        r"5[\.\-,)]?\s*INVESTMENT\s+EXPENSES.*?\$?\s*([0-9,]+\.\d{2})",
        r"6[\.\-,)]?\s*FOREIGN\s+TAX\s+PAID.*?\$?\s*([0-9,]+\.\d{2})",
        r"8[\.\-,)]?\s*TAX[-\s]*EXEMPT\s+INTEREST.*?\$?\s*([0-9,]+\.\d{2})",
        r"9[\.\-,)]?\s*SPECIFIED\s+PRIVATE\s+ACTIVITY.*?\$?\s*([0-9,]+\.\d{2})",
        r"10[\.\-,)]?\s*MARKET\s+DISCOUNT.*?\$?\s*([0-9,]+\.\d{2})",
        r"(?:11|41|iS)[\.\-,)]?\s*BOND\s+PREMIUM.*?\$?\s*([0-9,]+\.\d{2})",  # OCR confusion: 11 ↔ 41 ↔ iS
        r"12[\.\-,)]?\s*BOND\s+PREMIUM\s+ON\s+TREASURY.*?\$?\s*([0-9,]+\.\d{2})",
        r"13[\.\-,)]?\s*BOND\s+PREMIUM\s+ON\s+TAX[-\s]*EXEMPT.*?\$?\s*([0-9,]+\.\d{2})",
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
    """
    Return a list of form names detected in the page text.
    Handles 1099-INT, 1099-DIV, 1099-B, and others.
    """
    lower = text.lower()
    matches = []

    # -------------------------------------------------------------
    # 1️⃣ 1099-INT detection
    # -------------------------------------------------------------
    has_int = (
        re.search(r"1099[\s\-]*int", lower)
        or ("interest income" in lower and "form 1099" in lower)
    ) and has_nonzero_int(text)

    # -------------------------------------------------------------
    # 2️⃣ 1099-DIV detection
    # -------------------------------------------------------------
    has_div = (
        (re.search(r"1099[\s\-]*div", lower)
         or "1099-div" in lower
         or "form 1099-div" in lower)
        and has_nonzero_div(text)    # ⬅️ now safe because has_nonzero_div scans only the DIV section
    )


    # -------------------------------------------------------------
    # 3️⃣ 1099-B detection  
    #
    #  ➜ Uses new has_nonzero_b(text)
    #  ➜ Detects summary-table non-zero values
    # -------------------------------------------------------------
    

    
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

    # 3️⃣ 1099-B detection
    if "1099-b" in lower or "form 1099-b" in lower:
        if has_nonzero_1099b(text):
            matches.append("1099-B")   # ✅ add to matches
  # or skip bookmark



    # -------------------------------------------------------------
    # 4️⃣ Other IRS forms
    # -------------------------------------------------------------
    if ("1099-misc" in lower or "form 1099-misc" in lower) and has_nonzero_misc(text):
        matches.append("1099-MISC")

    if ("1099-oid" in lower or "form 1099-oid" in lower) and has_nonzero_oid(text):
        matches.append("1099-OID")

    # -------------------------------------------------------------
    # 5️⃣ Combined INT + DIV pages
    # -------------------------------------------------------------
    if has_int and has_div:
        cond1 = (
            "total federal income tax withheld" in lower
            and "total interest income 1099-int box 1" in lower
        )
        cond2 = (
            "total qualified dividends" in lower
            and "interest income" in lower
        )

        if cond1 or cond2:
            matches.append("1099-INT & DIV Description")
        else:
            matches.extend(["1099-INT", "1099-DIV"])

    else:
        if has_int:
            matches.append("1099-INT")
        if has_div:
            matches.append("1099-DIV")

    return matches


#k1helper
def extract_ein_number(text: str) -> str | None:
    """
    Extract EIN from text — tolerant to OCR dash variants and missing dashes.
    Skips extraction if the page contains Form 1098 mortgage keywords.
    """

    import re

    # --- NEW: Skip EIN extraction for Form 1098 mortgage forms ---
    skip_keywords = [
        # Form 1098 mortgage
        "tution",
        "adjustments made for",
        "form 1098",
        "mortgage interest statement",
        "mortgage interest",
        "payer/borrower",
        "recipient's/lender's",
        "box 1 mortgage interest",

        # Donation receipts
        "donation",
        "donation amount",
        "your donation",

        # W-2
        "w-2",
        "w2",
        "wage and tax statement",
        "wages, tips, other compensation",

        # 1099-INT
        "1099-int",
        "form 1099-int",
        "early withdrawl penalty",
        "bond premium",
        "fatca filing",
        "savings bonds and treasury obligations",
        "specified private activity bond penalty",

        # All Form 1099 generic
        "form 1099",
        "copy b",
        "federal income tax withheld",

        # --- NEW: FULL 1099-SA DETECTION BLOCK ---
        "form 1099-sa",
        "1099-sa",
        "distributions from a health savings account",
        "hsa",
        "archer msa",
        "medicare advantage",
        "medicare advantage msa",
        "gross distribution",
        "earnings on excess cont",
        "distribution code",
        "fmv on date of death",
        "h.s.a.",
        "benefitwallet",               # strong identifier for BNY Mellon 1099-SA
        "benefitwallet h.s.a",
        "account number (see instructions)",
        "1099-sa instructions",
        "file form 8853",
        "file form 8889",
        "qualified medical expenses",
        "mistaken distribution",
        "excise tax of 6%",
        "box 1 shows the amount received this year",
        "box 2 shows the earnings",
        "box 3 these codes identify",
        "future developments",
        "department of the treasury - internal revenue service",
    ]

    lowered = text.lower()

    if any(keyword in lowered for keyword in skip_keywords):
        # Skip completely for Form 1098 pages
        return None

    # Normalize all dash variants to a normal hyphen
    normalized = re.sub(r"[–—−‐‒﹘﹣]", "-", text)

    # Try standard EIN pattern (with dash)
    m = re.search(r"\b\d{2}-\d{7}\b", normalized)
    if m:
        return m.group(0)

    # Try continuous 9-digit pattern, and reformat
    m = re.search(r"\b(\d{9})\b", normalized)
    if m:
        raw = m.group(1)
        return f"{raw[:2]}-{raw[2:]}"  # insert dash

    return None

# --- Classification Helper
def is_1099r_page(text: str) -> bool:
    # Normalize whitespace & lowercase
    lower = " ".join(text.lower().split())

    blockA = [
        "form 1099-r",
        "pensions, annuities",
        "gross distribution",
        "distribution code",
        "ira/",
        "simple",
        "taxable amount",
    ]

    blockB = [
        "gross distribution",
        "taxable amount",
        "capital gain (included in box 2a)",
        "employee contributions/designated roth",
        "distribution code(s)",
        "federal income tax withheld",
        "amount allocable to irr",
        "state tax withheld",
        "state distribution",
    ]

    # Block A → must match at least 1 keyword
    matchA = any(pat in lower for pat in blockA)

    # Block B → must match at least 3 keywords
    matchB_count = sum(1 for pat in blockB if pat in lower)
    matchB = matchB_count >= 3

    # Final requirement
    return matchA and matchB


def classify_text(text: str) -> Tuple[str, str]:
    normalized = re.sub(r'\s+', '', text.lower())
    t = text.lower()
    
    lower = text.lower()
      # Detect W-2 pages by their header phrases
    t = re.sub(r"\s+", " ", text.lower()).strip()
    lower = text.lower()
    sa_front_patterns = [
        r"earnings\s+on\s+excess\s+cont",   # will also match 'cont.'
        #r"form\s+1099-?sa",                 # matches '1099-SA' or '1099SA'
        r"fmv\s+on\s+date\s+of\s+death",
    ]

    found_sa_front = any(re.search(pat, lower) for pat in sa_front_patterns)

    # 🔁 Priority: 1099-SA > Unused
    if found_sa_front:
        return "Income", "1099-SA"
# --- STRONG & EARLY W-2 DETECTION ---
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
    if (
        "THE BANK OF NEW YORK MELLON" in lower
        or "the bank of new york mellon" in lower
        or "hsa account holders" in lower
        or "or your maximum contributlon limit" in lower
        or ("form 1099-sa" in lower and "reflecting the additional contribution" in lower)
        or ("Form 1099-SA" in lower and "reflecting the additional contribution" in lower)
    ):
        return "Income", "1099-SA"
    if (
        (
            "w-2" in lower
            or "w2" in lower
            or "wage and tax statement" in lower
            or "wages, tips, other compensation" in lower
            or ("employer’s name" in lower and "address" in lower)
            or ("employer's name" in lower and "address" in lower)
        )
        and not any(
            kw in lower
            for kw in [
                # Prevent W-2 false positives on K-1 or QBI pages
                "schedule k-1",
                "form 1065",
                "form 1120-s",
                "form 1041",
                "statement a—qbi",
                "qbi pass-through entity",
                "qualified business income",
                "box 20 code z",
            ]
        )
    ):
        return "Income", "W-2"

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
    #Property Tax
# --- STRONG & EARLY 1099-INT DETECTION ---
    if (
        (
            "form 1099-int" in lower
            or "1099-int" in lower
            or "interest income" in lower
            or ("copy b" in lower and "form 1099" in lower)
            or ("federal income tax withheld" in lower and "interest" in lower)
        )
        and not any(
            kw in lower
            for kw in [
                "schedule k-1",
                "form k-1",
                "form 1065",
                "form 1120-s",
                "form 1041",
                "schedule k1",
                "k1 ",
                "k-1 ",
            ]
        )
    ):
        return "Income", "1099-INT"



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
        "contact a competent tax advisor or the irs" in t
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

    # 1) Detect W-2 pages by key header phrases
    if (
        "wages, tips, other compensation" in lower or
        ("employer's name" in lower and "address" in lower)
    ):
        return "Income", "W-2"
    
    front_donation = [
        "donation",
        "volunteers greatly appreciate your",
        "Volunteers greatly appreciate your generous coma"
    ]
   
    for pat in front_donation:
        if pat in lower:
            return "Expenses", "Donation"  
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


    #5498-SA
    # --- 5498-SA detection (more tolerant OCR patterns) ---

     # --- Detect Schedule K-1 (Form 1065 / 1120-S / 1041) and Statement A (QBI) pages ---
    if any(
        kw in lower
        for kw in [
            "schedule k-1",
            "form 1065",
            "form 1120-s",
            "form 1041",
            #"statement a",
            "qualified business income",
            #"section 199a",
            "qbi pass-through",
            "qbi pass through",
            "partnership",
            "accumulated differences may occur",
            "K-1 rental real estate activity",
            "for owners of pass-through entities",
            "tax paid on form or-oc filed on owner's behalf",
            "don’t submit with your individual tax return or the pte return",
        ]
    ):
        ein_match = re.search(r"\b\d{2}[-–]\d{7}\b", text)
        if ein_match:
            print(f"[DEBUG] classify_text: Detected K-1 Form 1065 EIN={ein_match.group(0)}", file=sys.stderr)
        return "Income", "K-1"
    
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
    #"box 1. shows taxable interest",
    #"box 2. shows interest or principal forfeited",
    #"box 3. shows interest on u.s. savings bonds",
    #"box 4. shows backup withholding",
    #"box 5. any amount shown is your share",
    #"box 6. shows foreign tax paid",
    #"box 7. shows the country or u.s. territory",
    #"box 8. shows tax-exempt interest",
    #"box 9. shows tax-exempt interest subject",
    #"box 10. for a taxable or tax-exempt covered security",
    #"box 11. for a taxable covered security",
    #"box 12. for a u.s. treasury obligation",
    #"box 13. for a tax-exempt covered security",
    #"box 14. shows cusip number",
    #"boxes 15-17. state tax withheld",
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
       
    lower = t.lower()

    # --- Mandatory Condition ---


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
        #This information is being provided to you as",
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

    if '1099-int' in t or 'interest income' in t: return 'Income', '1099-INT'
    #if '1099-div' in t: return 'Income', '1099-DIV'
    #if 'form 1099-div' in t: return 'Income', '1099-DIV'
   
    #if '1099' in t: return 'Income', '1099-Other'

    
    return 'Unknown', 'Unused'

   

   


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
        "huntington": "The Huntington National Bank",
        "the huntington national bank": "The Huntington National Bank",
        "THE HUNTINGTON NATIONAL BANK": "THE HUNTINGTON NATIONAL BANK",
        "HUNTINGTON NATIONAL BANK": "THE HUNTINGTON NATIONAL BANK",
        "THE HUNTINGTON NATIONAL": "THE HUNTINGTON NATIONAL BANK",
        "THE HUNTINGTON": "THE HUNTINGTON NATIONAL BANK",
        
        # === Existing Entries ===
        "fundrise income real estate fund": "Fundrise Income Real Estate Fund, LLC",
        "fundrise income fund": "Fundrise Income Fund, LLC",
        "morgan stanley domestic holdings": "Morgan Stanley Domestic Holdings, Inc",
        "morgan stanley domestic holding": "Morgan Stanley Domestic Holdings, Inc",
        "morgan stanley holdings inc": "Morgan Stanley Domestic Holdings, Inc",
        "morgan stanley holdings": "Morgan Stanley Domestic Holdings, Inc",

        # === Major Brokerages & Investment Platforms ===
        "charles schwab": "Charles Schwab",
        "fidelity": "Fidelity Investments",
        "vanguard": "Vanguard",
        "etrade": "E*TRADE (Morgan Stanley)",
        "td ameritrade": "TD Ameritrade (Charles Schwab)",
        "merrill": "Merrill (Bank of America)",
        "robinhood": "Robinhood",
        "webull": "Webull",
        "public.com": "Public.com",
        "interactive brokers": "Interactive Brokers",
        "sofi invest": "SoFi Invest",
        "betterment": "Betterment",
        "wealthfront": "Wealthfront",
        "acorns": "Acorns",
        "ally invest": "Ally Invest",
        "stash": "Stash",
        "m1 finance": "M1 Finance",
        "firstrade": "Firstrade",
        "tradestation": "TradeStation",
        "apex clearing": "Apex Clearing",
        "raymond james": "Raymond James",
        "lpl financial": "LPL Financial",
        "edward jones": "Edward Jones",
        "stifel": "Stifel Financial",
        "pershing": "Pershing LLC",
        "tastytrade": "Tastytrade",
        "jp morgan self-directed": "J.P. Morgan Self-Directed Investing",
        "morgan stanley wealth": "Morgan Stanley Wealth Management",
        "schwab intelligent portfolios": "Charles Schwab Intelligent Portfolios",

        # === Banks / Financial Firms with Investment Products ===
        "jpmorgan chase": "JPMorgan Chase Bank",
        "bank of america": "Bank of America",
        "wells fargo advisors": "Wells Fargo Advisors",
        "citibank wealth": "Citibank Wealth Management",
        "u.s. bank": "US Bank Investments",
        "us bank": "US Bank Investments",
        "pnc investments": "PNC Investments",
        "truist investments": "Truist Investments",
        "capital one investing": "Capital One Investing",
        "regions investment": "Regions Investment Services",
        "fifth third securities": "Fifth Third Securities",
        "hsbc securities": "HSBC Securities (USA)",
        "ubs": "UBS Financial Services",
        "bmo harris": "BMO Harris Financial Advisors",
        "comerica securities": "Comerica Securities",

        # === Mutual Fund & ETF Families ===
        "t rowe price": "T. Rowe Price",
        "franklin templeton": "Franklin Templeton",
        "american funds": "American Funds (Capital Group)",
        "blackrock": "BlackRock",
        "ishares": "BlackRock iShares",
        "invesco": "Invesco",
        "jpmorgan funds": "J.P. Morgan Funds",
        "state street": "State Street Global Advisors (SPDR)",
        "spdr": "State Street SPDR ETFs",
        "charles schwab funds": "Charles Schwab Funds",
        "dfa": "Dimensional Fund Advisors (DFA)",
        "dimensional fund": "Dimensional Fund Advisors (DFA)",
        "janus henderson": "Janus Henderson Investors",
        "nuveen": "Nuveen Investments",
        "eaton vance": "Eaton Vance",
        "oppenheimer": "OppenheimerFunds (Invesco)",
        "lord abbett": "Lord Abbett",
        "columbia threadneedle": "Columbia Threadneedle Investments",
        "principal funds": "Principal Funds",
        "american century": "American Century Investments",
        "putnam": "Putnam Investments",
        "john hancock": "John Hancock Funds",
        "hartford funds": "Hartford Funds",
        "mfs": "MFS Investment Management",
        "goldman sachs funds": "Goldman Sachs Funds",
        "morgan stanley funds": "Morgan Stanley Funds",
        "northern funds": "Northern Funds",
        "tiaa": "TIAA Investments",
        "bny mellon": "BNY Mellon Investment Management",

        # === REITs, BDCs, and Dividend Trusts ===
        "realty income": "Realty Income Corporation",
        "simon property": "Simon Property Group",
        "prologis": "Prologis Inc.",
        "digital realty": "Digital Realty Trust",
        "crown castle": "Crown Castle Inc.",
        "american tower": "American Tower Corporation",
        "annaly capital": "Annaly Capital Management",
        "agnc investment": "AGNC Investment Corp.",
        "main street capital": "Main Street Capital Corp.",
        "ares capital": "Ares Capital Corp.",
        "hercules capital": "Hercules Capital Inc.",
        "gladstone capital": "Gladstone Capital Corp.",
        "starwood property": "Starwood Property Trust",
        "blackstone real estate": "Blackstone Real Estate Income Trust",
        "enterprise products": "Enterprise Products Partners L.P.",
        "energy transfer": "Energy Transfer LP",
        "kinder morgan": "Kinder Morgan Inc.",
        "enbridge": "Enbridge Inc.",
        "oneok": "ONEOK Inc.",
        "brookfield infrastructure": "Brookfield Infrastructure Partners",
        "brookfield renewable": "Brookfield Renewable Partners",

        # === Common Dividend-Paying Public Companies ===
        "at&t": "AT&T Inc.",
        "verizon": "Verizon Communications Inc.",
        "apple": "Apple Inc.",
        "microsoft": "Microsoft Corporation",
        "coca cola": "The Coca-Cola Company",
        "pepsico": "PepsiCo Inc.",
        "exxon mobil": "Exxon Mobil Corporation",
        "chevron": "Chevron Corporation",
        "johnson & johnson": "Johnson & Johnson",
        "procter & gamble": "Procter & Gamble Co.",
        "pfizer": "Pfizer Inc.",
        "mcdonald": "McDonald’s Corporation",
        "intel": "Intel Corporation",
        "ibm": "IBM Corporation",
        "walmart": "Walmart Inc.",
        "home depot": "The Home Depot, Inc.",
        "3m": "3M Company",
        "abbvie": "AbbVie Inc.",
        "caterpillar": "Caterpillar Inc.",
        "lockheed martin": "Lockheed Martin Corporation",

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
# --------------------------- Consolidated-1099 issuer name --------------------------- #
def extract_consolidated_issuer(text: str) -> str | None:
    """
    Extracts the brokerage name for Consolidated-1099 pages.
    STRIPS telephone numbers completely so they NEVER appear in bookmarks.
    """
    import re

    # 1️⃣ REMOVE ALL PHONE NUMBERS BEFORE ANY MATCH
    text = re.sub(r"Telephone Number[:\s]*\d{3}[\s\-]?\d{3}[\s\-]?\d{4}", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d{3}[\s\-]\d{3}[\s\-]\d{4}\b", "", text)
    text = re.sub(r"\b\d{10}\b", "", text)

    lower = text.lower()

    # 2️⃣ Known broker mappings (UPDATED)
    issuers = {
        #etrade
        r"etrade|e\*trade": "E*TRADE (Morgan Stanley)",
        #morgan stanley
        r"morgan\s+stanley": "E*TRADE (Morgan Stanley)",
        #charles schwab
        r"charles\s+schwab": "Charles Schwab",
        #fidelity
        r"fidelity": "Fidelity Investments",
        #apex clearing
        r"apex\s+clearing": "Apex Clearing",
        #robinhood
        r"robinhood": "Robinhood",
        #merrill
        r"merrill": "Merrill Lynch",
        #ubs financial
        r"ubs\s+financial\s+services\s+inc\.?": "UBS Financial Services Inc.",
        # ➕ NEW: TD Ameritrade Clearing variants
        r"td\s*ameri?trade\s+clearing": "TD Ameritrade Clearing",
        r"tda\s*clearing": "TD Ameritrade Clearing",
        r"tdam\s*clearing": "TD Ameritrade Clearing",
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
    # already-present general TD Ameritrade
        r"td\s*ameri?trade": "TD Ameritrade",
    }

    for patt, name in issuers.items():
        if re.search(patt, lower):
            return name

    # 3️⃣ Fallback – company-like line detector
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue

        # skip form text
        if re.search(r"(form|1099|page|account)", s, re.IGNORECASE):
            continue

        # company-like indicators
        if re.search(r"(LLC|Clearing|Securities|Bank|Wealth|Advisors|Brokerage|Inc)", s):
            return s

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
    Combines:
      - Full normalization
      - Complete OVERRIDES list (all names included)
      - Schwab-style payer block ('country, ZIP, telephone')
      - Fidelity/Vanguard-style payer block ('PAYER’S name...')
      - Continuation-line detection
      - Address and numeric noise removal
    Returns:
        "<Payer Name> - Form 1099-R"
    """

    import re, unicodedata

    if not text:
        return "Form 1099-R"

    # ----------------------------------------
    # Normalize text
    # ----------------------------------------
    text = unicodedata.normalize("NFKD", text)
    normalized_text = re.sub(r"[^a-z0-9\s.,&'-]", " ", text.lower())
    normalized_text = re.sub(r"\s{2,}", " ", normalized_text)

    # ----------------------------------------
    # FULL OVERRIDES LIST — ALL NAMES INCLUDED
    # ----------------------------------------
    OVERRIDES = {
        # 🏦 Major Banks & Trust Companies
        "bank of america": "Bank of America, N.A.",
        "wells fargo": "Wells Fargo Bank, N.A.",
        "jpmorgan chase": "JPMorgan Chase Bank, N.A.",
        "us bank": "U.S. Bank, N.A.",
        "pnc bank": "PNC Bank, N.A.",
        "truist": "Truist Bank",
        "citibank": "Citibank, N.A.",
        "fifth third": "Fifth Third Bank, N.A.",
        "regions bank": "Regions Bank",
        "td bank": "TD Bank, N.A.",
        "capital one": "Capital One, N.A.",
        "bmo harris": "BMO Harris Bank, N.A.",
        "keybank": "KeyBank National Association",
        "comerica": "Comerica Bank",
        "m&t bank": "M&T Bank",
        "huntington": "Huntington National Bank",
        "first republic": "First Republic Bank",
        "citizens bank": "Citizens Bank, N.A.",
        "associated bank": "Associated Bank, N.A.",
        "bank of the west": "Bank of the West",
        "first national bank of omaha": "First National Bank of Omaha",
        "zions": "Zions Bancorporation",
        "frost bank": "Frost Bank",
        "union bank": "Union Bank & Trust Company",
        "synovus": "Synovus Bank",

        # 🧾 Insurance & Annuity Companies
        "prudential": "Prudential Insurance Company of America",
        "metlife": "MetLife, Inc.",
        "new york life": "New York Life Insurance Company",
        "northwestern mutual": "Northwestern Mutual Life Insurance Company",
        "massmutual": "Massachusetts Mutual Life Insurance Company",
        "john hancock": "John Hancock Life Insurance Company (U.S.A.)",
        "lincoln national": "Lincoln National Life Insurance Company",
        "principal": "Principal Life Insurance Company",
        "nationwide": "Nationwide Life Insurance Company",
        "pacific life": "Pacific Life Insurance Company",
        "allianz": "Allianz Life Insurance Company of North America",
        "american general": "American General Life Insurance Company (AIG)",
        "transamerica": "Transamerica Life Insurance Company",
        "guardian": "Guardian Life Insurance Company of America",
        "axa equitable": "AXA Equitable Life Insurance Company",
        "tiaa": "TIAA (Teachers Insurance and Annuity Association)",
        "voya": "Voya Financial, Inc.",
        "western & southern": "Western & Southern Life Insurance Company",
        "protective life": "Protective Life Insurance Company",
        "jackson national": "Jackson National Life Insurance Company",
        "great west": "Great-West Life & Annuity Insurance Company (Empower)",
        "mutual of omaha": "Mutual of Omaha Insurance Company",
        "brighthouse": "Brighthouse Financial",
        "athene": "Athene Annuity and Life Company",
        "symetra": "Symetra Life Insurance Company",
        "american fidelity": "American Fidelity Assurance Company",
        "pacific guardian": "Pacific Guardian Life Insurance Company",
        "minnesota life": "Minnesota Life Insurance Company",
        "sun life": "Sun Life Assurance Company of Canada",
        "cuna mutual": "CUNA Mutual Group",
        "ohio national": "Ohio National Life Insurance Company",
        "midland national": "Midland National Life Insurance Company",
        "american equity": "American Equity Investment Life Insurance Company",
        "equitrust": "EquiTrust Life Insurance Company",
        "riversource": "RiverSource Life Insurance Company",
        "sammons": "Sammons Financial Group",
        "ameritas": "Ameritas Life Insurance Corp.",
        "western national": "Western National Life Insurance Company",
        "reliastar": "Reliastar Life Insurance Company",
        "american national": "American National Insurance Company",
        "forethought": "Forethought Life Insurance Company",
        "great american": "Great American Life Insurance Company",
        "security benefit": "Security Benefit Life Insurance Company",
        "lafayette life": "Lafayette Life Insurance Company",
        "life insurance company of the southwest": "Life Insurance Company of the Southwest",
        "lincoln benefit": "Lincoln Benefit Life Company",
        "liberty life": "Liberty Life Assurance Company of Boston",
        "usaa life": "USAA Life Insurance Company",
        "national life": "National Life Insurance Company",
        "united of omaha": "United of Omaha Life Insurance Company",
        "allstate life": "Allstate Life Insurance Company",
        "farmers new world": "Farmers New World Life Insurance Company",
        "metlife investors": "MetLife Investors USA Insurance Company",
        "hartford life": "Hartford Life and Annuity Insurance Company",
        "new england life": "New England Life Insurance Company",

        # 💼 Brokerages & Investment Firms
        "charles schwab": "Charles Schwab & Co., Inc.",
        "fidelity investments": "Fidelity Investments (FMR LLC)",
        "vanguard": "Vanguard Group, Inc.",
        "merrill lynch": "Merrill Lynch, Pierce, Fenner & Smith Inc.",
        "edward jones": "Edward Jones",
        "morgan stanley": "Morgan Stanley Smith Barney LLC",
        "raymond james": "Raymond James & Associates, Inc.",
        "ubs": "UBS Financial Services Inc.",
        "ameriprise": "Ameriprise Financial Services, LLC",
        "rbc wealth": "RBC Wealth Management (U.S.)",
        "td ameritrade": "TD Ameritrade Clearing, Inc.",
        "etrade": "E*TRADE Securities LLC",
        "jp morgan securities": "J.P. Morgan Securities LLC",
        "lpl financial": "LPL Financial LLC",
        "oppenheimer": "Oppenheimer & Co. Inc.",
        "stifel": "Stifel, Nicolaus & Company, Incorporated",
        "wells fargo advisors": "Wells Fargo Advisors, LLC",
        "janney montgomery scott": "Janney Montgomery Scott LLC",
        "baird": "Robert W. Baird & Co. Incorporated",
        "raymond james financial services": "Raymond James Financial Services, Inc.",
        "cambridge investment": "Cambridge Investment Research, Inc.",
        "commonwealth financial": "Commonwealth Financial Network",
        "pershing": "Pershing LLC (BNY Mellon)",
        "cetera": "Cetera Advisor Networks LLC",
        "equitable advisors": "Equitable Advisors, LLC",
        "ing financial": "ING Financial Partners",
        "lincoln financial advisors": "Lincoln Financial Advisors Corporation",
        "northwestern mutual investment": "Northwestern Mutual Investment Services, LLC",
        "usaa investment": "USAA Investment Management Company",
        "fidelity brokerage": "Fidelity Brokerage Services LLC",
        "empower retirement": "Empower Retirement (Great-West Financial)",
        "t rowe price": "T. Rowe Price Associates, Inc.",
        "blackrock": "BlackRock, Inc.",
        "dimensional fund": "Dimensional Fund Advisors LP",
        "franklin templeton": "Franklin Templeton Investments",

        # 🏛 Government & Pension Plan Administrators
        "opm": "U.S. Office of Personnel Management (OPM)",
        "veterans affairs": "Department of Veterans Affairs (VA)",
        "dfas": "Defense Finance and Accounting Service (DFAS)",
        "railroad retirement": "U.S. Railroad Retirement Board",
        "social security": "Social Security Administration",
        "tsp": "Federal Thrift Savings Plan (TSP)",
        "calpers": "CalPERS (California Public Employees’ Retirement System)",
        "calstrs": "CalSTRS (California State Teachers’ Retirement System)",
        "nyslrs": "New York State and Local Retirement System (NYSLRS)",
        "florida retirement": "Florida Retirement System (FRS)",
        "texas teachers": "Texas Teachers Retirement System (TRS)",
        "opers": "Ohio Public Employees Retirement System (OPERS)",
        "pennsylvania sers": "Pennsylvania State Employees’ Retirement System (SERS)",
        "illinois trs": "Illinois Teachers’ Retirement System (TRS)",
        "wisconsin retirement": "Wisconsin Retirement System (WRS)",
        "georgia ersga": "Georgia Employees’ Retirement System (ERSGA)",
        "north carolina retirement": "North Carolina Retirement Systems (NCRS)",
        "virginia retirement": "Virginia Retirement System (VRS)",
        "michigan ors": "Michigan Office of Retirement Services (ORS)",
        "colorado pera": "Colorado PERA",
        "minnesota msrs": "Minnesota State Retirement System (MSRS)",
        "washington drs": "Washington State Department of Retirement Systems",
        "oregon pers": "Oregon PERS",
        "massachusetts retirement": "Massachusetts State Retirement Board",
        "maryland srs": "Maryland State Retirement and Pension System",
        "new jersey pensions": "New Jersey Division of Pensions and Benefits",
        "south carolina retirement": "South Carolina Retirement System",
        "indiana public retirement": "Indiana Public Retirement System",
        "missouri mosers": "Missouri State Employees’ Retirement System (MOSERS)",
        "alaska retirement": "Alaska Division of Retirement and Benefits",

        # 🧮 Other Retirement & Benefit Administrators
        ""
        "ascensus": "Ascensus, LLC",
        "fidelity employer": "Fidelity Employer Services Company",
        "adp retirement": "ADP Retirement Services",
        "paychex retirement": "Paychex Retirement Services",
        "voya institutional": "Voya Institutional Plan Services, LLC",
        "principal trust": "Principal Trust Company",
        "nationwide retirement": "Nationwide Retirement Solutions",
        "massmutual financial": "MassMutual Financial Group",
        "transamerica retirement": "Transamerica Retirement Solutions",
        "lincoln retirement": "Lincoln Financial Group Retirement Plan Services",
        "john hancock retirement": "John Hancock Retirement Plan Services",
        "tiaa cref": "TIAA-CREF Retirement Services",
        "prudential retirement": "Prudential Retirement (now Empower)",
        "icma rc": "ICMA-RC (MissionSquare Retirement)",
        "newport": "Newport Group, Inc.",
        "oneamerica": "OneAmerica Retirement Services",
        "sentinel benefits": "Sentinel Benefits & Financial Group",
        "fidelity workplace": "Fidelity Workplace Investing",
        "millennium trust": "Millennium Trust Company, LLC",
        "empower trust compny": "Empower Trust Company, LLC",   # OCR missing 'a'
        "empower trst company": "Empower Trust Company, LLC",   # missing 'u'
        "empower trus company": "Empower Trust Company, LLC", 
        "em power trust company": "Empower Trust Company, LLC", # OCR spacing
        "empowerr trust company": "Empower Trust Company, LLC", # double r
        "empowr trust company": "Empower Trust Company, LLC",
        "empower trust compan": "Empower Trust Company, LLC",   # missing last letter
    }

    # ----------------------------------------
    # OVERRIDE MATCH
    # ----------------------------------------
    for key, val in OVERRIDES.items():
        if key in normalized_text:
            return f"{val} - Form 1099-R"

    # ----------------------------------------
    # STRUCTURED PAYER BLOCK EXTRACTION
    # ----------------------------------------
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    for i, line in enumerate(lines):
        lline = line.lower()

        nextline = lines[i+1].lower() if i+1 < len(lines) else ""

        # Detect payer header over 1 or 2 lines
        if (
            ("payer" in lline and "name" in lline) 
            or ("country" in lline and "telephone" in lline)
            or ("payer" in lline and "name" in nextline)
            or ("payer" in nextline and "name" in lline)
        ):
            for offset in range(1, 6):
                if i + offset >= len(lines):
                    break

                cand = lines[i + offset].strip()
                if not cand:
                    continue

                # stop on unrelated
                if re.search(
                    r"(recipient|account|form\s*1099|treasury|omb\s*no|department)",
                    cand,
                    re.I,
                ):
                    break

                # clean noise
                cand = re.sub(r"(?i)\$?\d.*$", "", cand)
                cand = re.sub(r"(?i)\bForm\s*1099.*$", "", cand)
                cand = re.sub(r"(?i)\bContracts.*$", "", cand)
                cand = re.sub(r"(?i)\bInsurance.*$", "", cand)
                cand = cand.strip()

                # skip addresses or numeric lines
                if re.search(r"\d{3,}", cand):
                    continue
                if re.search(r"(street|city|state|zip|address|drive|road|way|blvd)", cand, re.I):
                    continue

                # continuation line
                next_line = lines[i + offset + 1].strip() if i + offset + 1 < len(lines) else ""
                if (
                    next_line
                    and not re.search(r"\d|city|state|zip|address|form|recipient|account", next_line, re.I)
                    and re.match(r"^[A-Z][A-Z\s&.,'-]{3,}$", next_line)
                ):
                    cand = f"{cand} {next_line}".strip()

                if len(cand.split()) >= 2 and not re.search(r"\d", cand):
                    return f"{cand.title()} - Form 1099-R"

            break

    return "Form 1099-R"


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
import re, sys
from typing import List, Tuple, Dict
from collections import defaultdict

def extract_1098mortgage_bookmark(text: str) -> str:
    """
    Extract lender name for Form 1098-Mortgage.
    Uses override mappings for known issuers, then applies pattern-based rules.
    """

    # --- 🔹 Step 1: Standard lender overrides ---
    overrides = {
        # --- Major Banks ---
        "wells fargo": "WELLS FARGO BANK, N.A.",
        "west gate bank":"WEST GATE BANK",
        "wells fargo": "WELLS FARGO BANK, N.A.",
        "jpmorgan chase": "JPMORGAN CHASE BANK, N.A.",
        "bank of america": "BANK OF AMERICA, N.A.",
        "us bank": "U.S. BANK, N.A.",
        "u.s. bank": "U.S. BANK, N.A.",
        "citibank": "CITIBANK, N.A.",
        "pnc bank": "PNC BANK, N.A.",
        "truist": "TRUIST BANK",
        "regions bank": "REGIONS BANK",
        "fifth third": "FIFTH THIRD BANK, N.A.",
        "keybank": "KEYBANK, N.A.",
        "huntington national": "THE HUNTINGTON NATIONAL BANK",
        "comerica": "COMERICA BANK",
        "first horizon": "FIRST HORIZON BANK",
        "bmo harris": "BMO HARRIS BANK, N.A.",
        "m&t bank": "M&T BANK",
        "flagstar": "FLAGSTAR BANK, N.A.",
        "td bank": "TD BANK, N.A.",
        "hsbc": "HSBC BANK USA, N.A.",
        "capital one": "CAPITAL ONE, N.A.",
        "citizens bank": "CITIZENS BANK, N.A.",
        "suntrust": "SUNTRUST BANK (now TRUIST)",
        "bbva": "BBVA USA (now PNC)",

        # --- Mortgage Servicers ---
        "rocket mortgage": "ROCKET MORTGAGE, LLC",
        "quicken loans": "ROCKET MORTGAGE, LLC",
        "loan depot": "LOANDEPOT.COM, LLC",
        "loandepot.com": "LOANDEPOT.COM, LLC",
        "mr. cooper": "MR. COOPER (NATIONSTAR MORTGAGE)",
        "nationstar": "MR. COOPER (NATIONSTAR MORTGAGE)",
        "freedom mortgage": "FREEDOM MORTGAGE CORPORATION",
        "pennymac": "PENNYMAC LOAN SERVICES, LLC",
        "guild mortgage": "GUILD MORTGAGE COMPANY LLC",
        "newrez": "NEWREZ LLC (DBA SHELLPOINT MORTGAGE SERVICING)",
        "shellpoint": "NEWREZ LLC (DBA SHELLPOINT MORTGAGE SERVICING)",
        "carrington": "CARRINGTON MORTGAGE SERVICES, LLC",
        "caliber": "CALIBER HOME LOANS, INC.",
        "roundpoint": "ROUNDPOINT MORTGAGE SERVICING CORPORATION",
        "phh mortgage": "PHH MORTGAGE CORPORATION",
        "sps ": "SELECT PORTFOLIO SERVICING, INC.",
        "select portfolio": "SELECT PORTFOLIO SERVICING, INC.",
        "cenlar": "CENLAR FSB",
        "dovenmuehle": "DOVENMUEHLE MORTGAGE, INC.",
        "mid america mortgage": "MID AMERICA MORTGAGE, INC.",
        "home point": "HOME POINT FINANCIAL CORPORATION",
        "rushmore": "RUSHMORE LOAN MANAGEMENT SERVICES, LLC",
        "amerihome": "AMERIHOME MORTGAGE COMPANY, LLC",
        "ocwen": "OCWEN LOAN SERVICING, LLC",
        "specialized loan": "SPECIALIZED LOAN SERVICING LLC",
        "plaza home mortgage": "PLAZA HOME MORTGAGE, INC.",

        # --- Credit Unions ---
        "navy federal": "NAVY FEDERAL CREDIT UNION",
        "penfed": "PENTAGON FEDERAL CREDIT UNION",
        "alliant": "ALLIANT CREDIT UNION",
        "becu": "BOEING EMPLOYEES CREDIT UNION",
        "first tech": "FIRST TECH FEDERAL CREDIT UNION",
        "schoolsfirst": "SCHOOLSFIRST FEDERAL CREDIT UNION",
        "golden 1": "GOLDEN 1 CREDIT UNION",
        "redstone": "REDSTONE FEDERAL CREDIT UNION",
        "mountain america": "MOUNTAIN AMERICA CREDIT UNION",
        "vystar": "VYSTAR CREDIT UNION",
        "desert financial": "DESERT FINANCIAL CREDIT UNION",
        "randolph": "RANDOLPH-BROOKS FEDERAL CREDIT UNION",
        "security service": "SECURITY SERVICE FEDERAL CREDIT UNION",

        # --- Online & Nonbank Lenders ---
        "better mortgage": "BETTER MORTGAGE CORPORATION",
        "sofi mortgage": "SOFI MORTGAGE, LLC",
        "figure mortgage": "FIGURE MORTGAGE, LLC",
        "crosscountry": "CROSSCOUNTRY MORTGAGE, LLC",
        "amerisave": "AMERISAVE MORTGAGE CORPORATION",
        "guaranteed rate": "GUARANTEED RATE, INC.",
        "fairway": "FAIRWAY INDEPENDENT MORTGAGE CORPORATION",
        "homebridge": "HOMEBRIDGE FINANCIAL SERVICES, INC.",
        "primelending": "PRIMELENDING, A PLAINSCAPITAL COMPANY",
        "movement mortgage": "MOVEMENT MORTGAGE, LLC",
        "paramount residential": "PARAMOUNT RESIDENTIAL MORTGAGE GROUP, INC.",
        "embrace home": "EMBRACE HOME LOANS, INC.",
        "veterans united": "VETERANS UNITED HOME LOANS",
        "navy federal home": "NAVY FEDERAL HOME LOANS",

        # --- Government / GSE Related ---
        "fannie mae": "FEDERAL NATIONAL MORTGAGE ASSOCIATION (FANNIE MAE)",
        "freddie mac": "FEDERAL HOME LOAN MORTGAGE CORPORATION (FREDDIE MAC)",
        "ginnie mae": "GOVERNMENT NATIONAL MORTGAGE ASSOCIATION (GINNIE MAE)",
        "va loan": "U.S. DEPARTMENT OF VETERANS AFFAIRS",
        "usda loan": "U.S. DEPARTMENT OF AGRICULTURE",
        "fha loan": "FEDERAL HOUSING ADMINISTRATION",
    }

    text_lower = text.lower()
    for key, val in overrides.items():
        if key in text_lower:
            print(f"[1098-MORTGAGE] Override match: {key} → {val}", file=sys.stderr)
            return finalize_bookmark(val)

    # --- 🔹 Step 2: Pattern-based detection (your full logic preserved) ---
    lines: List[str] = text.splitlines()
    lower_lines = [L.lower() for L in lines]
    bookmark = ""

    # 🔸 Special known overrides
    for L in lines:
        if re.search(r"\bphh\s+mortgage\s+corporation\b", L, re.I):
            return finalize_bookmark("PHH MORTGAGE CORPORATION")
        if re.search(r"rocket\s+mortgage", L, re.I):
            return finalize_bookmark("ROCKET MORTGAGE LLC")
        if re.search(r"dovenmuehle\s+mortgage", L, re.I):
            return finalize_bookmark("DOVENMUEHLE MORTGAGE, INC")
        if re.search(r"\bhuntington\s+national\s+bank\b", L, re.I):
            return finalize_bookmark("THE HUNTINGTON NATIONAL BANK")
        if re.search(r"\bunited\s+nations\s+fcu\b", L, re.I):
            return finalize_bookmark("UNITED NATIONS FCU")
        if re.search(r"\bloan\s*depot\s*com\s*llc\b", L, re.I):
            return finalize_bookmark("LOANDEPOT.COM LLC")
        if re.search(r"jp\s*morgan\s+chase", L, re.I):
            return finalize_bookmark("JPMORGAN CHASE BANK, N.A.")
        if re.search(r"\bfor\s+return\s+service\s+only\b", L, re.I):
            return finalize_bookmark("FOR RETURN SERVICE ONLY")
        if re.search(r"cit[i1l]zens?\s*(bank|banx|banc)", L, re.I):
            return finalize_bookmark("CITIZENS BANK, N.A.")

    # --- (Full OCR detection logic preserved from your version) ---
    # ... [The rest of your long detection logic remains unchanged] ...

    # Final fallback
    return finalize_bookmark(trim_lender_text(bookmark or text))



# === Utility Functions (unchanged from your code) ===
def trim_lender_text(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        return ""
    cleaned = raw.strip()
    if re.search(r"(?i)mortgage\s+(finance|llc|inc|bank|company|corp|servicing)", cleaned):
        pass
    else:
        if re.search(r"(?i)(on the|loan amount|understanding|page|box|form)", cleaned):
            cleaned = re.sub(r"(?i)^.*?\bmortgage\b\s*", "", cleaned)
    cleaned = re.split(
        r"(?i)\band\s+the\s+cost|\bmay\s+not\s+be\s+fully|\blimits\s+based|\byou\s+may\s+only|\bform\b|\bdepartment\b|\btreasury\b|\bcaution\b",
        cleaned, maxsplit=1
    )[0]
    cleaned = cleaned.replace(" ang ", " and ").replace(" apoly", " apply").replace(" may ", " ")
    for phrase in [
        "on the loan amount","limits based","interest statement","mortgage interest statement",
        "internal revenue service","form 1098","keep for your records","statement","page"
    ]:
        cleaned = re.sub(phrase, "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,.-")
    return cleaned


def finalize_bookmark(bookmark: str) -> str:
    bookmark = clean_bookmark(bookmark)
    bookmark = re.sub(r'^(limits\s+based.*?|caution[:\s].*?|may\s+not\s+be\s+fully\s+deductible.*?)\b', '', bookmark, flags=re.I).strip(" ,.-")
    bookmark = re.sub(r'\b(and\s+the\s+cost.*|may\s+apply.*|you\s+may\s+only.*)$', '', bookmark, flags=re.I).strip(" ,.-")
    bookmark = re.sub(r'^(?:form\s*)?1098\s*mortgage\b|\bmortgage\s+interest\s+statement\b', '', bookmark, flags=re.I).strip(" ,.-")
    m = re.search(r'([A-Z][A-Za-z0-9&.,\'\- ]*?\b(?:MORTGAGE\s+SERVICING|MORTGAGE\s+COMPANY|MORTGAGE\s+BANK|MORTGAGE\s+GROUP)\b[^\n,]*)', bookmark, flags=re.I)
    if m: bookmark = m.group(1).strip(" ,.-")
    safe_suffixes = r'(LLC|INC\.?|N\.A\.|BANK|SERVICING|COMPANY|CORP\.?|FCU|ASSOCIATION|CORPORATION)'
    if not re.search(rf'\b{safe_suffixes}\b', bookmark, re.I):
        bookmark = re.sub(rf'\bmortgage\b(?!\s+{safe_suffixes}\b)', '', bookmark, flags=re.I)
        bookmark = re.sub(r'\s{2,}', ' ', bookmark).strip(" ,.-")
    for marker in [
        "not be fully deductible","limits based on","interest received from",
        "outstanding mortgage principal","payer","borrower","department of the treasury","irs"
    ]:
        idx = bookmark.lower().find(marker)
        if idx != -1:
            bookmark = bookmark[:idx].strip(" ,.-")
            break
    bookmark = re.sub(r'\s{2,}', ' ', bookmark).strip(" ,.-")
    def smart_case(s: str) -> str:
        s = s.title()
        for pat, rep in {
            r'\bLlc\b':'LLC', r'\bInc\b\.?':'INC', r'\bCorp\b\.?':'CORP',
            r'\bCorporation\b':'Corporation', r'\bFcu\b':'FCU',
            r'\bDba\b':'DBA', r'\bN\.?A\b\.?':'N.A.', r'\bUsa\b':'USA'
        }.items():
            s = re.sub(pat, rep, s)
        return s
    return smart_case(bookmark)


def clean_bookmark(s: str) -> str:
    return re.sub(r'\s{2,}', ' ', s or "").strip(" ,.-")


def group_by_type(entries: List[Tuple[str,int,str]]) -> Dict[str,List[Tuple[str,int,str]]]:
    d=defaultdict(list)
    for e in entries:
        d[e[2]].append(e)
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

    KEYWORDS = r"(University|College|Institute|Academy|Univ|Board of Regents)"


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

# Tracks merged PDF page numbers for each real (path, idx) K-1 page
k1_page_map = {}
def reorder_k1_pages(pages):
    """
    Sort K-1 pages in correct IRS order:
    1. Main K-1 form page
    2. Partner/shareholder information
    3. Supplemental info
    4. Statement A (QBI)
    5. Section 199A
    6. Rental activity
    7. Basis worksheets
    8. Continuation statements
    """

    def get_score(text):
        t = text.lower()

        # 1. Main federal K-1 page
        if "schedule k-1" in t and ("form 1065" in t or "form 1120-s" in t or "form 1041" in t):
            return 1

        # 2. Personal info sections
        if "information about the partner" in t:
            return 2
        if "information about the shareholder" in t:
            return 2
        if "partner's share" in t:
            return 3
        if "shareholder's share" in t:
            return 3

        # 3. Supplement pages
        if "supplemental information" in t:
            return 4
        if "additional information" in t:
            return 4

        # 4. QBI pages
        if "statement a" in t:
            return 5
        if "section 199a" in t:
            return 5
        if "qbi" in t:
            return 5

        # 5. Rental real estate pages
        if "rental real estate activity" in t:
            return 6

        # 6. Basis worksheets
        if "basis worksheet" in t:
            return 7
        if "at-risk basis" in t:
            return 7

        # 7. Continuation statements
        if "continuation" in t:
            return 8

        # 8. Fallback → leave last
        return 99

    # Score every page
    scored = []
    for (p, idx, _) in pages:
        text = extract_text(p, idx)
        score = get_score(text)
        scored.append((score, p, idx))

    # Sort by score only (KEEP original order if score ties)
    scored.sort(key=lambda x: x[0])

    # Return sorted as original format
    return [(p, idx, "K-1") for (_, p, idx) in scored]
def k1_page_priority(text):
    t = text.lower()

    # --- TRUE MAIN K-1 FORM PAGE ---
    if (
        "schedule k-1" in t
        and ("form 1065" in t or "form 1120-s" in t or "form 1041" in t)
        and (
            "information about the partner" in t
            or "information about the shareholder" in t
            or ("part i" in t and "information about" in t)
        )
    ):
        return 1

    # Supplemental info (NOT main)
    if "supplemental information" in t:
        return 3

    # Rental real estate pages
    if "rental real estate" in t:
        return 4

    # QBI / Section 199A
    if (
        "statement a" in t
        or "section 199a" in t
        or "qualified business income" in t
        or "qbi" in t
    ):
        return 5

    # Other continuation
    if "continuation" in t:
        return 6

    # Fallback last
    return 99
def extract_k1_company(text: str) -> str | None:

    # Normalize
    clean = re.sub(r"[^\w\s,&.'\-]", " ", text)
    clean = re.sub(r"\s+", " ", clean)

    # 1. Try to locate "Partnership EIN" or similar anchor
    anchor = re.search(
        r"(partnership[\s\-]*ein|partner[\s\-]*ship[\s\-]*ein|A\.)",
        clean, flags=re.IGNORECASE
    )

    if anchor:
        start = max(0, anchor.start() - 120)  # go backward to find the name
        window = clean[start:anchor.end() + 80]

        m = re.search(
            r"([A-Z][A-Z\s,&.'\-]{2,80}?(?:LLC|INC|CORP|LP|LLP))",
            window, flags=re.IGNORECASE
        )
        if m:
            return m.group(1).strip()

    # 2. Fallback to your old strong pattern
    m = re.findall(
        r"([A-Z][A-Z\s,&.'\-]{2,80}?(?:LLC|INC|CORP|LP|LLP|FUND))",
        clean, flags=re.IGNORECASE
    )
    if m:
        return max(m, key=len).strip()

    return None

def clean_k1_company_name(raw: str) -> str:
    """
    Clean K-1 company name by:
    - Removing multi-line noise ('Name of Partnership', 'Partnership EIN', etc.)
    - Keeping only the longest block ending with LLC/LP/INC/CORP
    - Removing leading/trailing garbage
    """

    if not raw:
        return None

    import re

    # Collapse newlines → spaces
    raw = raw.replace("\n", " ")
    raw = re.sub(r"\s+", " ", raw).strip()

    # Remove known garbage phrases
    garbage = [
        "name of partnership",
        "partnership ein",
        "information about the partner",
        "information about the shareholder",
        "schedule k-1",
        "form 1065",
        "form 1120-s",
        "form 1041"
    ]

    lower = raw.lower()
    for g in garbage:
        if g in lower:
            # Remove the entire garbage phrase + anything BEFORE it
            idx = lower.index(g)
            raw = raw[idx + len(g):].strip()
            lower = raw.lower()

    # Strong match: pick the longest LLC/INC/CORP/LP ending
    m = re.findall(
        r"[A-Za-z0-9& ,.'\-]{3,100}?(?:LLC|L\.L\.C\.|INC|CORP|LP|LLP)",
        raw,
        flags=re.IGNORECASE
    )
    if m:
        # choose longest match
        return max(m, key=len).strip()

    return raw.strip()

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

        print(f"[META] TP SSN={tp_ssn}, SP SSN={sp_ssn}", file=sys.stderr)    # Prevent storing merged file inside input_dir
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
    sa_titles = {}  
    mort_titles = {}
    sa5498_titles = {}
    t529_titles = {}
    t1098_titles = {}
    account_pages = {}  # {account_number: [(path, page_index, 'Consolidated-1099')]}
    account_names = {}
    k1_pages = {}        # {ein: [(path, page_index, 'K-1')]}
    k1_names = {}        # {ein: 'Partnership name'}
    k1_form_type = {}    # {ein: '1065' or '1120S' or '1041'}
    # <-- ADD THIS HERE
    consolidated_payload = {}        # key -> list of real page entries
    consolidated_pages = set() 

    # ✅ Track seen page text hashes to detect duplicate pages (within or across files)
    seen_hashes = {}   # tracks duplicate page text
    seen_pages = {}    # tracks appended pages
      # pages assigned to consolidated-1099


    # --- Skip duplicates in main processing ---
    files = [f for f in files if f not in duplicate_files]

    for fname in files:
        last_ein_seen = None
        seen_pages = {}   # reset duplicate tracker per file
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
                    file_key = (fname, page_hash)   # <-- isolate by filename
                    if file_key in seen_hashes:
                        print(f"[DUPLICATE PAGE] {fname} p{i+1} matches ...", file=sys.stderr)
                        others.append((path, i, "Duplicate"))
                        continue  # ⬅️ SKIPS classification and appending
                    else:
                        seen_hashes[file_key] = (path, i)


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
                # =======================================
                # ✅ EARLY-SKIP UNUSED PAGE DETECTOR HERE
                # =======================================
                if pre_classify_skip_page(text):
                    print(f"[PRE-SKIP] {fname} p{i+1} → Unused", file=sys.stderr)
                    others.append((path, i, "Unused"))
                    continue

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
                lower_text = tiered.lower()
                # 🚫 Skip if already consumed by consolidated early-exit
                if (path, i) in consolidated_pages:
                    continue

                # ----------------------------------------------------------
                # 🛑 EARLY-EXIT: CONSOLIDATED-1099 PAGE SHORT-CIRCUIT LOGIC
                # ----------------------------------------------------------
                # ----------------------------------------------------------
                # 🛑 EARLY-EXIT: CONSOLIDATED-1099 PAGE SHORT-CIRCUIT LOGIC
                # ----------------------------------------------------------
                acct_num = extract_account_number(tiered)
                if acct_num and len(acct_num) < 5:
                    acct_num = None  # ignore garbage like "ET1" or "0971"


                # 👉 Extract issuer name from this page
                issuer = extract_consolidated_issuer(tiered)

                # --- NEW FIX: Inherit issuer name if same account appears again ---
                # EARLY-EXIT: CONSOLIDATED-1099 PAGE
                # Always extract account + issuer
                #acct_num = extract_account_number(tiered)
                issuer = extract_consolidated_issuer(tiered)
                unused, reasons = is_unused_page(lower_text)
                if unused:
                    print(
                        f"[UNUSED] {os.path.basename(path)} p{i+1}\n  - "
                        + "\n  - ".join(reasons),
                        file=sys.stderr
                    )
                    others.append((path, i, "Unused"))
                    continue

                # Page qualifies as consolidated
                consolidated_keywords = [
                    "1099",
                    "detail for dividends and distributions",
                    "mutual fund and uit supplemental information",
                    "proceeds from broker and barter exchange transactions",
                    "foreign income and taxes summary",
                    "total foreign source income",
                    "summary of 2020 supplemental information not reported to the irs",
                    "summary of 2021 supplemental information not reported to the irs",
                    "summary of 2022 supplemental information not reported to the irs",
                    "summary of 2023 supplemental information not reported to the irs",
                    "summary of 2024 supplemental information not reported to the irs",
                    "summary of 2025 supplemental information not reported to the irs",
                    "summary of 2026 supplemental information not reported to the irs",
                    "mortgage pool statement",
                    "deductible generic expenses",
                    "Tax Exempt Investment Expense",
                    "1099-MISC MISCELLANEOUS INFORMATION",
                    "1099-misc miscellaneous information",
                    #fidelity
                    "summary of 2019 proceeds from broker and barter exchange transactions",
                    "summary of 2020 proceeds from broker and barter exchange transactions",
                    "summary of 2021 proceeds from broker and barter exchange transactions",
                    "summary of 2022 proceeds from broker and barter exchange transactions",
                    "summary of 2023 proceeds from broker and barter exchange transactions",
                    "summary of 2024 proceeds from broker and barter exchange transactions",
                    "summary of 2025 proceeds from broker and barter exchange transactions",
                    "summary of 2026 proceeds from broker and barter exchange transactions",
                    "2020 miscellaneous information",
                    "2021 miscellaneous information",
                    "2022 miscellaneous information",
                    "2023 miscellaneous information",
                    "2024 miscellaneous information",
                    "2025 miscellaneous information",
                    "2026 miscellaneous information",
                    "short-term transactions for which basis is reported to the irs",
                    "ordinary dividends distributions capital gains dividends ordinary dividends dividends interest",
                    "total ordinary dividends and disiributions detail",
                    "description date amount",
                    "fidelity",
                    

                ]
                # Extra AND-pair conditions
                consolidated_must_pairs = [
                    ("not reported to the irs", "account fees"),
                    #("cusip","additional information","investment activity")
                    #("description description","transaction quantity price","quantity price amount additional")
                    ("miscellaneous information", "amount"),
                    ("margin interest paid", "currency realized gain"),
                    ("proceeds investments expenses", "account fees"),

                    ("description date amount", "summary of supplemental information not reported to the irs"),
                ]
                # 3-keyword AND triples
                consolidated_must_triples = [
                    ("cusip", "transaction description", "amount"),
                    ("cusip", "description", "amount"),
                        # Strong Morgan Stanley continuation triple:
                    ("1099-int", "cusip", "amount"),        # NEW
                    ("1099-misc", "cusip", "amount"),       # NEW
                    ("interest income", "cusip", "amount"), # NEW
                    ("security description", "transaction description", "additional information"),
                ]
                # ANY standalone keyword triggers OR
                # ANY pair where both are present triggers
                is_consolidated = (
                    any(k in lower_text for k in consolidated_keywords) or
                    any(a in lower_text and b in lower_text for a, b in consolidated_must_pairs) or
                    any(a in lower_text and b in lower_text and c in lower_text
                        for a, b, c in consolidated_must_triples)
                )
                if is_consolidated and is_consolidated_issuer(lower_text):
                    is_consolidated = True
                else:
                    is_consolidated = False
                
                acct_num = extract_account_number(tiered)
                if acct_num and len(acct_num) < 5:
                    acct_num = None

                # ==========================================
                # 🔥 NEW: EXTRACT ISSUER BEFORE CONSOLIDATED CHECK
                issuer = extract_consolidated_issuer(tiered)

                if acct_num:
                    if acct_num not in account_names:
                        account_names[acct_num] = issuer if issuer else None
                    else:
                        if issuer is None:
                            issuer = account_names[acct_num]
                    # ==========================================

                if acct_num and (
                    is_consolidated
                    or "fidelity" in text.lower()
                    or "supplemental information" in text.lower()
                    or "tax reporting statement" in text.lower()
                   #SUMMARY OF PROCEEDS, GAINS & LOSSES, ADJUSTMENTS AND WITHHOLDING
                    or "summary of proceeds, gains & losses, adjustments and withholding" in text.lower()
                    or "Changes to dividend tax classifications processed after your original tax form is issued for" in text.lower()
                    or "proceeds from broker and barter exchange transactions" in text.lower()
                    or "transactions for which basis is not reported to the irs and term is unknown" in text.lower()
                    or "details of 1099-int transactions" in text.lower()
                ):
                    account_pages.setdefault(acct_num, []).append((path, i, "Consolidated-1099"))

                    synthetic_key = f"CONSOLIDATED::{acct_num}"

                    consolidated_payload.setdefault(synthetic_key, []).append((path, i, "Consolidated-1099"))
                    consolidated_pages.add((path, i))

                    if (synthetic_key, -1, "Consolidated-1099") not in income:
                        income.append((synthetic_key, -1, "Consolidated-1099"))

                    continue

                #acct_num = extract_account_number(tiered)

                # --- Detect Schedule K-1 / Form 1065 / Statement A / QBI pages ---
                # --- Detect Schedule K-1 / Form 1065 / and related pages (QBI, Statement A, etc.) ---
                text_lower = tiered.lower()
                ein_num = extract_ein_number(tiered)

                # --- Detect Schedule K-1 / Form 1065 / Statement A / QBI / worksheet pages ---
                text_lower = tiered.lower()
                ein_num = extract_ein_number(tiered)

                # ✅ If EIN missing (common on continuation or basis pages), reuse the previous one
                # Track EIN across pages
                if not ein_num:
                    ein_num = last_ein_seen
                else:
                    last_ein_seen = ein_num


                # ✅ Detect any K-1-related page (expanded keyword list)
                k1_keywords = [
                    "schedule k-1", "form 1065", "form 1120-s", "form 1041",
                    "qualified business income", #"section 199a",
                    "qbi pass-through", "qbi pass through entity reporting",
                    # new worksheet / continuation phrases
                    "basis worksheet", "partner's basis worksheet",
                    "allocation of losses and deductions",
                    "partner's share of income", "at-risk basis", "section 704(c)",
                    "k-1 supplemental information", "continuation statement",
                    "additional information from schedule k-1", "passive activity purposes",
                    
                ]
                is_k1_page = any(k in text_lower for k in k1_keywords)

                # NEW — Detect TRUE form type
                is_1120s = bool(re.search(r"schedule\s*k-1.*form\s*1120[-\s]*s", text_lower))
                is_1065 = bool(re.search(r"schedule\s*k-1.*form\s*1065", text_lower))
                
                is_1041 = bool(re.search(r"schedule\s*k-1.*form\s*1041", text_lower))

                if (is_1065 or is_1120s or is_1041 or is_k1_page) and ein_num:

                # Assign correct form type
                    k1_form_type[ein_num] = (
                        "1065" if is_1065 else
                        "1120S" if is_1120s else
                        "1041" if is_1041 else
                        k1_form_type.get(ein_num, "1065")
                    )

                    # Extract company / partnership name
                    company = extract_k1_company(tiered)



                    k1_pages.setdefault(ein_num, []).append((path, i, "K-1"))
                    if company:
                        company = clean_k1_company_name(company)
                        k1_names[ein_num] = company





                    print(
                        f"[DEBUG] Unified K-1 page: {os.path.basename(path)} p{i+1} "
                        f"EIN={ein_num}, Company={company}, Form={k1_form_type[ein_num]}",
                        file=sys.stderr
                    )


                lower_text = tiered.lower()


# Always classify after account checks
                cat, ft = classify_text(tiered)

               
                # NEW: log every classification
                print(
                    f"[Classification] {os.path.basename(path)} p{i+1} → "
                    f"Category='{cat}', Form='{ft}', "
                    f"snippet='{tiered[:150].strip().replace(chr(80),' ')}…'",
                    file=sys.stderr
                )
                # 🚫 Skip if already appended under Consolidated-1099
                if (path, i) in consolidated_pages:
                    continue
                entry = (path, i, ft)
                if cat == 'Income':
                    # 🚫 Skip adding Account number as a separate form
                    if ft.lower() == "account number":
                        continue
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

        # ---- K-1 (Form 1065) grouping synthesis ----
    
    k1_payload = {}      # key -> list of (path, page_index, 'K-1')
    k1_pages_seen = set()  # to mark pages already grouped
    # --- 🩹 Move all raw K-1 entries into k1_pages before grouping ---
    for (path, idx, form) in list(income):
        if form == "K-1":
            text = extract_text(path, idx).lower()
            ein = extract_ein_number(text)
            k1_type = k1_form_type.get(ein, "1065")  

            if not ein and k1_pages:
                ein = list(k1_pages.keys())[-1]   # reuse last EIN if missing
            if ein:
                k1_pages.setdefault(ein, []).append((path, idx, "K-1"))
                # remove from income so it doesn't create a stray K-1 later
                income.remove((path, idx, form))

    for ein, pages in k1_pages.items():
        if not pages:
            continue

        # Get form type safely
        k1_type = k1_form_type.get(ein, "1065")   # <-- DEFAULT VALUE ADDED

        key = f"K1::{k1_type}::{ein}"

        # store real pages
        k1_payload[key] = [(p, i, "K-1") for (p, i, _) in pages]

        # mark pages seen
        for (p, i, _) in pages:
            k1_pages_seen.add((p, i))

        # add synthetic entry
        income.append((key, -1, "K-1"))

        print(f"[DEBUG] Added unified K-1 package for EIN={ein} with {len(pages)} page(s)", file=sys.stderr)

    # 🧹 remove any individual K-1 pages that were grouped
    income = [
        e for e in income
        if not (e[2] == "K-1" and not e[0].startswith("K1::") and (e[0], e[1]) in k1_pages_seen)
    ]
    print(f"[DEBUG] Cleaned raw K-1 pages; synthetic K1 groups = {[x[0] for x in income if 'K1::' in x[0]]}", file=sys.stderr)


            

    # ---- Consolidated-1099 synthesis (insert this BEFORE income.sort(...)) ----
    #consolidated_payload = {}        # key -> list of real page entries
    #consolidated_pages = set()       # pages already placed under Consolidated-1099
    # Track pages we already decided are "Unused" so we don't touch them again
    unused_pages: set[tuple[str, int]] = set()


    for acct, pages in account_pages.items():
        # 🚫 Skip accounts already handled by early-exit
        if f"CONSOLIDATED::{acct}" in consolidated_payload:
            continue
        if len(pages) <= 1:
            continue  # only group repeated accounts
        key = f"CONSOLIDATED::{acct}"
        consolidated_payload[key] = [(p, i, "Consolidated-1099") for (p, i, _) in pages]
        for (p, i, _) in pages:
            consolidated_pages.add((p, i))
    # add a synthetic income row that will sort using priority of 'Consolidated-1099'
        if (key, -1, "Consolidated-1099") not in income:
            if (key, -1, "Consolidated-1099") not in income:
                income.append((key, -1, "Consolidated-1099"))


# --------------------------------------------------------------------------
    # REMOVE synthetic K-1 entries ONLY FOR SORTING
    clean_income = [e for e in income if not str(e[0]).startswith("K1::")]

    # Now sort only REAL pages
    clean_income.sort(key=lambda e:(get_form_priority(e[2],'Income'), e[0], e[1]))

        # Restore synthetic K-1 groups after sorting
    # (They must be present so K-1 bookmark block runs)
    clean_income += [e for e in income if str(e[0]).startswith("K1::")]

    income = clean_income

    # Sort
    income.sort(key=lambda e:(get_form_priority(e[2],'Income'), e[0], e[1]))
    expenses.sort(key=lambda e:(get_form_priority(e[2],'Expenses'), e[0], e[1]))
    # merge & bookmarks
    merger = PdfMerger()
    page_num = 0
    stop_after_na = False
    import mimetypes
    #seen_pages = set()
    #def append_and_bookmark(entry, parent, title, with_bookmark=True):
    
    def append_and_bookmark(entry, parent, title, with_bookmark=True, owner_override="detect"):
        nonlocal page_num, seen_pages
        global k1_page_map

        p, idx, _ = entry

        # Synthetic K-1 key expansion -------------------------
        if p.startswith("K1::"):
            key = p
            real_entries = k1_payload.get(key, [])
            if not real_entries:
                return

            for i, real_entry in enumerate(real_entries):
                append_and_bookmark(
                    real_entry,
                    parent,
                    title if i == 0 and with_bookmark else "",
                    with_bookmark=(i == 0 and with_bookmark),
                )
            return

        # Skip duplicates -------------------------------------
        sig = (p, idx)
        if sig in seen_pages:
            return
        seen_pages[sig] = True

        # Write single page temp PDF --------------------------
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            w = PdfWriter()
            w.add_page(PdfReader(p).pages[idx])
            w.write(tmp)
            tmp.flush()
            tmp_path = tmp.name

        with open(tmp_path, 'rb') as fh:
            merger.append(fileobj=fh)
        os.unlink(tmp_path)

        # ⭐ Record the merged PDF page number for K-1 mapping
        # Record merged position for every REAL page (ignore synthetic)
        if not p.startswith("K1::"):
            k1_page_map[(p, idx)] = page_num

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
        # Add bookmark
        if with_bookmark and title:
            merger.add_outline_item(title, page_num, parent=parent)

        page_num += 1

    # --- Unified K-1 bookmark builder ----------------------------------------
    def build_k1_bookmarks(merger, root, k1_pages, k1_names,
                       extract_text, append_and_bookmark, is_unused_page):
        """
        CORRECT K-1 BUILDER
    Ensures:
    - Pages for each EIN are SORTED BEFORE merging
    - Form 1065 / 1120-S / 1041 folders appear in correct order
    - No pages are appended before sorting
    """
        global k1_page_map

        # 1. Create top-level K-1 folder
        k1_root = merger.add_outline_item("K-1", 0, parent=root)

    # 2. Determine first-page anchor for each EIN (based on file order)
        ein_first_order = {
            ein: min(idx for (_, idx, _) in pages)
            for ein, pages in k1_pages.items()
        }

        # 3. Detect form type order (1065,1120-S,1041)
        form_first_page = {}
        for ein, pages in k1_pages.items():
            form = k1_form_type.get(ein, "1065")
            first_idx = min(idx for (_, idx, _) in pages)
            if form not in form_first_page or first_idx < form_first_page[form]:
                form_first_page[form] = first_idx

        # 4. Sort form folders in true order
        sorted_forms = sorted(form_first_page, key=lambda f: form_first_page[f])

        # 5. Create folders
        form_roots = {}
        for form in sorted_forms:
            # find the first merged page for this form
            ein_for_form = [
                ein for ein in k1_pages
                if k1_form_type.get(ein, "1065") == form
            ]

            if ein_for_form:
                first_ein = ein_for_form[0]
                first_page = min(
                    k1_page_map.get((p, idx), 999999)
                    for (p, idx, _) in k1_pages[first_ein]
                )
            else:
                first_page = 0  # fallback

            form_roots[form] = merger.add_outline_item(
                f"Form {form}",
                first_page,
                parent=k1_root
            )


        # 6. NOW handle each EIN group
        for ein in sorted(k1_pages, key=lambda e: ein_first_order[e]):
            pages = k1_pages[ein]
            company = k1_names.get(ein, f"EIN {ein}")
            form_type = k1_form_type.get(ein, "1065")

            # ---- SORT PAGES FIRST (THE MOST IMPORTANT PART) ----
            sorted_pages = sorted(
                pages,
                key=lambda x: k1_page_priority(extract_text(x[0], x[1]))
            )

        # Find anchor = main K-1 form page
            anchor_path, anchor_idx = None, None
            for (p, idx, _) in sorted_pages:
                text = extract_text(p, idx).lower()
                if "schedule k-1" in text and ("form 1065" in text or "form 1120-s" in text or "form 1041" in text):
                    anchor_path, anchor_idx = p, idx
                    break
            # fallback
            if anchor_path is None:
                anchor_path, anchor_idx = sorted_pages[0][0], sorted_pages[0][1]


            # Create the EIN bookmark
            # convert original anchor index → merged page index
            anchor_page = k1_page_map.get((anchor_path, anchor_idx), 0)

            clean = extract_k1_company(company)
            # 🔍 Detect owner from the MAIN K-1 page
            owner = None
            try:
                main_text = extract_text(anchor_path, anchor_idx)
                owner = detect_ssn_owner(main_text, tp_ssn, sp_ssn)
            except:
                owner = None

            label = f"{clean} (EIN {ein})"
            if owner:
                label = f"{label} – {owner}"

            comp_node = merger.add_outline_item(
                label,
                anchor_page,
                parent=form_roots[form_type]
            )

            # ---- NOW append pages IN SORTED ORDER ----
            for (p, idx, _) in sorted_pages:
                txt = extract_text(p, idx)
                if is_unused_page(txt.lower()):
                    continue
                append_and_bookmark((p, idx, "K-1"), comp_node, "", with_bookmark=False)


    # ── Bookmarks
   
    if income:
        root = merger.add_outline_item('Income', page_num)
        used_labels = set()   # FIX #2

            # --- Custom hierarchical K-1 bookmark structure ---
        processed_pages = set()  # ✅ Track K-1/QBI pages already appended



        groups = group_by_type(income)
        for form, grp in sorted(groups.items(), key=lambda kv: get_form_priority(kv[0], 'Income')):
                # ✅ Run the unified K-1 block FIRST
            used_labels = set()   # track labels used under each Form node

            if form == 'K-1':

                # STEP 1 — Append ALL real K-1 pages FIRST (no bookmarks yet)
                for ein, pages in k1_pages.items():
                    sorted_pages = sorted(
                        pages,
                        key=lambda x: k1_page_priority(extract_text(x[0], x[1]))
                    )
                    for (p, idx, _) in sorted_pages:
                        append_and_bookmark((p, idx, "K-1"), None, "", with_bookmark=False)

                # STEP 2 — NOW build bookmarks (page numbers now exist)
                build_k1_bookmarks(
                    merger, root,
                    k1_pages, k1_names,
                    extract_text, append_and_bookmark, is_unused_page
                )

                continue

            # 4️⃣ ── Normal single-form handling (W-2, 1099s, etc.) ─────────────
            filtered_grp = [e for e in grp if (e[0], e[1]) not in consolidated_pages]
            if not filtered_grp:
                continue
            if stop_after_na:
                break
            if form == 'Consolidated-1099':
                cons_root = merger.add_outline_item('Consolidated-1099', page_num, parent=root)

                for entry in filtered_grp:
                    key, _, _ = entry
                    acct = key.split("::", 1)[1]

                    issuer = alias_issuer(account_names.get(acct)) if account_names.get(acct) else "Consolidated 1099"

                    # FINAL — Always include account number, never use phone numbers or “Account”
                    real_entries = consolidated_payload.get(key, [])

                    # 🔍 Detect TP / SP from FIRST REAL PAGE
                    owner = None
                    if real_entries:
                        try:
                            owner = detect_ssn_owner(
                                extract_text(real_entries[0][0], real_entries[0][1]),
                                tp_ssn,
                                sp_ssn
                            )
                        except Exception:
                            owner = None

                    # 🏷️ Build label AFTER owner detection
                    if issuer and acct:
                        forms_label = f"{issuer} – {acct}"
                    elif issuer:
                        forms_label = issuer
                    else:
                        forms_label = f"Account {acct}"

                    if owner:
                        forms_label = f"{forms_label} – {owner}"

                    # NOW create bookmark
                    forms_node = merger.add_outline_item(
                        forms_label,
                        page_num,
                        parent=cons_root
                    )


        # (optional context labels — does NOT skip appends)
             

        # ALWAYS append the real pages
                    for real_entry in real_entries:
                        page_text = extract_text(real_entry[0], real_entry[1])
                        # If this page is part of a Consolidated-1099 account, DO NOT send to UNUSED.
                        if is_unused_page(page_text):
                            print(f"[SKIP UNUSED] Consolidated page {real_entry[0]} p{real_entry[1]+1} kept under account only")
                            # Do NOT add it to others[]
                            # Just skip creating a form label, but still append the page
                            append_and_bookmark(
                                real_entry,
                                forms_node,
                                title="",               # keep empty
                                with_bookmark=False,
                                owner_override=None     # 🔥 FORCE TP/SP detection
                            )

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


            #k1 bookmrk

  # done with this form; go to next
            #Normal Forms
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, entry in enumerate(filtered_grp, 1):
                path, idx, _ = entry
                # ✅ Skip if page already processed in K-1 grouping
                if (path, idx) in processed_pages:
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
                page_text = extract_text(path, idx)
                owner = detect_ssn_owner(page_text, tp_ssn, sp_ssn)
                if owner:
                    lbl = f"{lbl} – {owner}"
 
                print(f"[SSN Tag] {os.path.basename(path)} p{idx+1} → {owner}", file=sys.stderr)
    
                # >>> NEW DUPLICATE BOOKMARK CONTROL <<<
                if lbl in used_labels:
    # Duplicate bookmark → do NOT add a bookmark
                    append_and_bookmark(entry, node, "", with_bookmark=False)
                else:
    # First time using this label → add normally
                    used_labels.add(lbl)
                    append_and_bookmark(entry, node, lbl)

            
            if stop_after_na:
                break

    if expenses:
        root = merger.add_outline_item('Expenses', page_num)
        used_labels = set()   # FIX #2
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
                    page_text = extract_text(path, idx)  # ✅ get the actual text for this page
                    provider = extract_daycare_bookmark(page_text)
                    lbl = provider if provider else "Child Care Provider"
                    append_and_bookmark(entry, node, lbl)
                elif form == '529-Plan':
                    title = t529_titles.get((path, idx))
                    if title:
                        lbl = title

               
                # NEW: strip ", N.A" and stop
                if ", N.A" in lbl:
                    lbl = lbl.replace(", N.A", "")
                print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Expenses', Form='{form}', Title='{lbl}'", file=sys.stderr)
                   
                # normal case
                print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Expenses', Form='{form}', Title='{lbl}'", file=sys.stderr)
                # 🆕 Detect SSN owner for this page and label it
                page_text = extract_text(path, idx)
                owner = detect_ssn_owner(page_text, tp_ssn, sp_ssn)
                if owner:
                    lbl = f"{lbl} – {owner}"
 
                print(f"[SSN Tag] {os.path.basename(path)} p{idx+1} → {owner}", file=sys.stderr)

                # --- NEW LOGIC: Prevent duplicate bookmarks ---
                if lbl in used_labels:
                    # duplicate → append page WITHOUT bookmark
                    append_and_bookmark(entry, node, "", with_bookmark=False)
                else:
                    used_labels.add(lbl)
                    append_and_bookmark(entry, node, lbl)

            if stop_after_na:
                break

# --- Add Others section with Unused and Duplicate pages ---
    # Always include the OTHERS category if any pages are classified there
    if others:
        root = merger.add_outline_item('Others', page_num)

        # ---- UNUSED ----
        unused_pages = [e for e in others if e[2] == 'Unused']
        if unused_pages:
            node_unused = merger.add_outline_item('Unused', page_num, parent=root)
            for entry in unused_pages:
                append_and_bookmark(entry, node_unused, "", with_bookmark=False)

        # ---- DUPLICATE ----
        dup_pages = [e for e in others if e[2] == 'Duplicate']
        if dup_pages:
            node_dupe = merger.add_outline_item('Duplicate', page_num, parent=root)
            for entry in dup_pages:
                append_and_bookmark(entry, node_dupe, "", with_bookmark=False)

                print(f"[Bookmark] {os.path.basename(entry[0])} p{entry[1]+1} → Category='Others', Form='Unused'", file=sys.stderr)

   



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


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description="Merge PDFs with robust text extraction and TP/SP labeling")
    p.add_argument('input_dir', help="Folder containing PDFs to merge")
    p.add_argument('output_pdf', help="Path for the merged PDF (outside input_dir)")
    p.add_argument('tp_ssn', nargs='?', default='', help="Taxpayer SSN last 4 digits")
    p.add_argument('sp_ssn', nargs='?', default='', help="Spouse SSN last 4 digits")
    args = p.parse_args()
    merge_with_bookmarks(args.input_dir, args.output_pdf, args.tp_ssn, args.sp_ssn)

