import sys
import os
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
import pytesseract
from pdf2image import convert_from_path #this uses poppler under the hood
from PIL import Image
import tempfile

def extract_text_with_ocr(pdf_path, page_num=None):
    """Extract text using OCR for scanned documents"""
    try:
        # Replace this with your actual poppler bin path
        POPPLER_PATH = r"C:\poppler\Library\bin"
        # Convert PDF to image(s)
        images = convert_from_path(pdf_path, poppler_path=POPPLER_PATH)

        if page_num is not None:
            if 0 <= page_num < len(images):
                return pytesseract.image_to_string(images[page_num])
            return ''
        
        text = ''
        for image in images:
            text += pytesseract.image_to_string(image) + '\n'
        return text

    except Exception as e:
        print(f"OCR processing failed for {pdf_path}: {e}", file=sys.stderr)
        print(f"📝 Page {page_num + 1} extracted text preview: {text.strip()[:150]}", file=sys.stderr)

        return ''

def extract_text_from_pdf(file_path, page_num=None):
    """Extract text from PDF using PyPDF2 with OCR fallback (using Poppler)"""
    text = ''
    POPPLER_PATH = r"C:\poppler\Library\bin"  # ✅ Ensure this matches your installation

    try:
        with open(file_path, 'rb') as file:
            reader = PdfReader(file)
            if page_num is not None:
                if 0 <= page_num < len(reader.pages):
                    # Try normal text extraction
                    try:
                        text = reader.pages[page_num].extract_text() or ''
                        if not text or len(text.strip()) < 50:
                            print(f"⚠️ No text on page {page_num + 1}, using OCR", file=sys.stderr)
                            try:
                                image = convert_from_path(
                                    file_path,
                                    first_page=page_num + 1,
                                    last_page=page_num + 1,
                                    poppler_path=POPPLER_PATH
                                )[0]
                                text = pytesseract.image_to_string(image)
                                print(f"OCR completed for page {page_num + 1}", file=sys.stderr)
                            except Exception as ocr_error:
                                print(f"OCR failed for page {page_num + 1}: {ocr_error}", file=sys.stderr)
                    except Exception as e:
                        print(f"Warning: Could not extract text from page: {e}", file=sys.stderr)
            else:
                for i in range(len(reader.pages)):
                    try:
                        page_text = reader.pages[i].extract_text() or ''
                        if not page_text or len(page_text.strip()) < 50:
                            print(f"⚠️ No text on page {i + 1}, using OCR", file=sys.stderr)
                            try:
                                image = convert_from_path(
                                    file_path,
                                    first_page=i + 1,
                                    last_page=i + 1,
                                    poppler_path=POPPLER_PATH
                                )[0]
                                page_text = pytesseract.image_to_string(image)
                                print(f"OCR completed for page {i + 1}", file=sys.stderr)
                            except Exception as ocr_error:
                                print(f"OCR failed for page {i + 1}: {ocr_error}", file=sys.stderr)
                        text += page_text + "\n"
                    except Exception as e:
                        print(f"Warning: Could not extract text from page {i + 1}: {e}", file=sys.stderr)

    except Exception as e:
        print(f"❌ OCR/Text extraction failed for {file_path}: {e}", file=sys.stderr)

    return text.lower()

def debug_text_extraction(file_path):
    """Debug text extraction for a specific file"""
    print(f"\nDEBUG: Text extraction for {file_path}", file=sys.stderr)
    
    try:
        # Test PDF opening
        with open(file_path, 'rb') as file:
            reader = PdfReader(file)
            print(f"Successfully opened PDF with {len(reader.pages)} pages", file=sys.stderr)
            
            # Test each page
            for i, page in enumerate(reader.pages):
                print(f"\nPage {i + 1}:", file=sys.stderr)
                try:
                    text = page.extract_text()
                    print(f"Text extraction successful. Length: {len(text)}", file=sys.stderr)
                    print(f"First 100 characters: {text[:100]}", file=sys.stderr)
                except Exception as e:
                    print(f"Text extraction failed: {e}", file=sys.stderr)
                
                # Try OCR on this page
                try:
                    ocr_text = extract_text_with_ocr(file_path, i)
                    print(f"OCR successful. Length: {len(ocr_text)}", file=sys.stderr)
                    print(f"First 100 characters from OCR: {ocr_text[:100]}", file=sys.stderr)
                except Exception as e:
                    print(f"OCR failed: {e}", file=sys.stderr)
    
    except Exception as e:
        print(f"Debug process failed: {e}", file=sys.stderr)

def classify_document(text):
    """Classify document type based on text content"""
    # Clean up the text by removing extra whitespace and normalizing
    text = ' '.join(text.lower().split())
    
    # Debug: Print first 200 characters of text being analyzed
    print(f"\nDEBUG - Text being analyzed: {text[:200]}", file=sys.stderr)
    
     # Income Documents - More specific patterns
    has_w2_label = 'w2' in text or 'w-2' in text
    # has_w2_structure = "these are substitute wage and tax statements and are acceptable for filing with your federal, state and local/city income tax returns." in text
    if has_w2_label:
        print("✅ Found W-2 label — classified as W-2 form", file=sys.stderr)
        return 'Income', 'W-2'
    elif ('w-2' in text or 'w2' in text) and (
        'wage and tax statement' in text or
        'employer identification number' in text or
        'box 1' in text or
        'social security wages' in text or
        'federal income tax withheld' in text
    ):
        print("✅ Matched W-2 form", file=sys.stderr)
        return 'Income', 'unused'
    elif ('1099-int' in text or 'interest income' in text) and not any(x in text for x in ['1098', 'mortgage']):
        print("DEBUG: Matched 1099-INT pattern", file=sys.stderr)
        return 'Income', '1099-INT'
    elif '1099-div' in text and 'dividends and distributions' in text:
        print("DEBUG: Matched 1099-DIV pattern", file=sys.stderr)
        return 'Income', '1099-DIV'
    elif '1099-r' in text and any(x in text for x in ['retirement', 'ira distribution']):
        print("DEBUG: Matched 1099-R pattern", file=sys.stderr)
        return 'Income', '1099-R'
    elif '1099-nec' in text and 'nonemployee compensation' in text:
        print("DEBUG: Matched 1099-NEC pattern", file=sys.stderr)
        return 'Income', '1099-NEC'
    elif '1099-misc' in text and 'miscellaneous income' in text:
        print("DEBUG: Matched 1099-MISC pattern", file=sys.stderr)
        return 'Income', '1099-MISC'
    elif '1099-patr' in text:
        print("DEBUG: Matched 1099-PATR pattern", file=sys.stderr)
        return 'Income', '1099-PATR'
    elif '1099-oid' in text and 'original issue discount' in text:
        print("DEBUG: Matched 1099-OID pattern", file=sys.stderr)
        return 'Income', '1099-OID'
    elif '1099-g' in text and 'certain government payments' in text:
        print("DEBUG: Matched 1099-G pattern", file=sys.stderr)
        return 'Income', '1099-G'
    elif '1099-q' in text:
        print("DEBUG: Matched 1099-Q pattern", file=sys.stderr)
        return 'Income', '1099-Q'
    elif 'k-1' in text and 'schedule k-1' in text:
        print("DEBUG: Matched K-1 pattern", file=sys.stderr)
        return 'Income', 'K-1'
    elif '1065' in text and 'partnership' in text:
        print("DEBUG: Matched 1065 pattern", file=sys.stderr)
        return 'Income', '1065'
    elif '1120-s' in text and 's corporation' in text:
        print("DEBUG: Matched 1120-S pattern", file=sys.stderr)
        return 'Income', '1120-S'
    elif '1041' in text and ('estate' in text or 'trust' in text):
        print("DEBUG: Matched 1041 pattern", file=sys.stderr)
        return 'Income', '1041'
    
    # Expense Documents
    elif '1098-t' in text and 'tuition statement' in text:
        print("DEBUG: Matched 1098-T pattern", file=sys.stderr)
        return 'Expenses', '1098-T'
    elif '1098' in text and 'mortgage interest' in text:
        print("DEBUG: Matched 1098-Mortgage pattern", file=sys.stderr)
        return 'Expenses', '1098-Mortgage'
    elif ('5498-sa' in text or 'hsa' in text) and 'health savings account' in text:
        print("DEBUG: Matched 5498-SA pattern", file=sys.stderr)
        return 'Expenses', '5498-SA'
    elif '1095-a' in text and 'health insurance marketplace' in text:
        print("DEBUG: Matched 1095-A pattern", file=sys.stderr)
        return 'Expenses', '1095-A'
    elif '1095-b' in text and 'health coverage' in text:
        print("DEBUG: Matched 1095-B pattern", file=sys.stderr)
        return 'Expenses', '1095-B'
    elif '1095-c' in text and 'employer-provided health insurance' in text:
        print("DEBUG: Matched 1095-C pattern", file=sys.stderr)
        return 'Expenses', '1095-C'
    elif 'property tax' in text or ('real estate tax' in text and 'statement' in text):
        print("DEBUG: Matched Property Tax pattern", file=sys.stderr)
        return 'Expenses', 'Property Tax'
    
    # Generic 1098/1099 Forms - with more specific checks
    elif '1098' in text and not any(x in text for x in ['1099', '1095']):
        print("DEBUG: Matched generic 1098 pattern", file=sys.stderr)
        return 'Expenses', '1098-Other'
    elif '1099' in text and not any(x in text for x in ['1098', '1095']):
        print("DEBUG: Matched generic 1099 pattern", file=sys.stderr)
        return 'Income', '1099-Other'
    
    # Debug information for unclassified documents
    print(f"DEBUG: Document not classified. Text sample: {text[:200]}", file=sys.stderr)
    return 'Unknown', 'Unknown Document'

def analyze_pdf_pages(file_path):
    """Analyze each page of the PDF and return classifications for each page"""
    try:
        reader = PdfReader(file_path)
        num_pages = len(reader.pages)
        page_classifications = []
        
        print(f"Analyzing {file_path} with {num_pages} pages", file=sys.stderr)
        
        # First try normal processing
        for page_num in range(num_pages):
            # Extract and classify text from this page
            text = extract_text_from_pdf(file_path, page_num)
            
            if not text.strip():
                print(f"No text found on page {page_num + 1}, running debug process", file=sys.stderr)
                debug_text_extraction(file_path)
                # Try OCR as fallback
                text = extract_text_with_ocr(file_path, page_num)
            
            if text.strip():
                category, doc_type = classify_document(text)
                page_classifications.append({
                    'page_num': page_num,
                    'category': category,
                    'type': doc_type
                })
                print(f"Page {page_num + 1}/{num_pages} classified as: {category} - {doc_type}", file=sys.stderr)
            else:
                print(f"Warning: Could not extract any text from page {page_num + 1}", file=sys.stderr)
        
        return page_classifications
        
    except Exception as e:
        print(f"Error analyzing PDF {file_path}: {e}", file=sys.stderr)
        return []

def format_bookmark_title(doc_type, page_num):
    """Format the bookmark title for a page"""
    return doc_type  # Now only returns the form type without page number

def get_form_priority(form_type, category):
    """Get the priority order for a form type within its category"""
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
        '1099-Other': 16
    }
    
    expense_priorities = {
        '5498-SA': 1,
        '1095-A': 2,
        '1095-B': 3,
        '1095-C': 4,
        '1098-Mortgage': 5,
        '1098-T': 6,
        'Property Tax': 7,
        '1098-Other': 8
    }
    
    if category == 'Income':
        return income_priorities.get(form_type, 999)  # Default high number for unknown forms
    elif category == 'Expenses':
        return expense_priorities.get(form_type, 999)
    return 999

def print_bookmarks(outline, level=0):
    """Print bookmark structure recursively"""
    if not outline:
        return
        
    if isinstance(outline, (list, tuple)):
        for item in outline:
            print_bookmarks(item, level)
    elif isinstance(outline, dict):
        # Handle dictionary-style bookmarks
        title = outline.get('/Title', 'Unknown')
        print("  " * level + f"- {title}", file=sys.stderr)
        
        # Handle nested bookmarks
        if '/First' in outline:
            print_bookmarks(outline['/First'], level + 1)
        if '/Next' in outline:
            print_bookmarks(outline['/Next'], level)
    else:
        # Handle direct bookmark objects
        try:
            if hasattr(outline, 'title'):
                print("  " * level + f"- {outline.title}", file=sys.stderr)
            elif hasattr(outline, 'get'):
                print("  " * level + f"- {outline.get('/Title', 'Unknown')}", file=sys.stderr)
            else:
                print("  " * level + "- <No Title>", file=sys.stderr)
                
            # Handle children if they exist
            if hasattr(outline, 'children') and outline.children:
                for child in outline.children:
                    print_bookmarks(child, level + 1)
        except Exception as e:
            print(f"Error printing bookmark: {str(e)}", file=sys.stderr)

def merge_pdfs_with_bookmarks(input_dir, output_path):
    """Merge PDFs and create bookmarks"""
    print("Starting PDF merge", file=sys.stderr)
    
    try:
        # First pass: Analyze all PDFs and store their information
        pdf_files = [f for f in os.listdir(input_dir) if f.lower().endswith('.pdf')]
        print(f"Found {len(pdf_files)} PDF files to process", file=sys.stderr)
        
        if not pdf_files:
            print("No PDF files found in the input directory", file=sys.stderr)
            return
        
        # Sort files to ensure consistent order
        pdf_files.sort()
        
        # Track document information
        all_documents = []
        
        # First analyze all documents
        for filename in pdf_files:
            file_path = os.path.join(input_dir, filename)
            print(f"\nAnalyzing file: {filename}", file=sys.stderr)
            
            try:
                # Open and validate PDF
                with open(file_path, 'rb') as file:
                    try:
                        reader = PdfReader(file)
                        if not reader.pages:
                            print(f"Skipping {filename} - empty PDF", file=sys.stderr)
                            continue
                    except Exception as e:
                        print(f"Skipping {filename} - invalid PDF: {e}", file=sys.stderr)
                        continue
                
                page_classifications = analyze_pdf_pages(file_path)
                
                if not page_classifications:
                    print(f"Skipping {filename} - no classifications found", file=sys.stderr)
                    continue
                
                for page_info in page_classifications:
                    doc_info = {
                        'file_path': file_path,
                        'page_num': page_info['page_num'],
                        'type': page_info['type'],
                        'category': page_info['category'],
                        'title': format_bookmark_title(page_info['type'], page_info['page_num']),
                        'priority': get_form_priority(page_info['type'], page_info['category'])
                    }
                    all_documents.append(doc_info)
                    print(f"Added document: {doc_info['title']} (Category: {doc_info['category']})", file=sys.stderr)
                    
            except Exception as e:
                print(f"Error processing {filename}: {e}", file=sys.stderr)
                continue
        
        if not all_documents:
            print("No valid documents found to process", file=sys.stderr)
            return
        
        # Sort documents by category and priority
        all_documents.sort(key=lambda x: (x['category'] != 'Income', x['priority']))
        
        # Group documents by category
        income_docs = [doc for doc in all_documents if doc['category'] == 'Income']
        expense_docs = [doc for doc in all_documents if doc['category'] == 'Expenses']
        
        print("\nDocument structure to be created:", file=sys.stderr)
        print("Income documents:", file=sys.stderr)
        for doc in income_docs:
            print(f"- {doc['title']} (Priority: {doc['priority']})", file=sys.stderr)
        print("\nExpense documents:", file=sys.stderr)
        for doc in expense_docs:
            print(f"- {doc['title']} (Priority: {doc['priority']})", file=sys.stderr)
        
        # Create new merger for output
        merger = PdfMerger(strict=False)
        current_page = 0
        
        try:
            # Process Income documents
            if income_docs:
                income_parent = merger.add_outline_item("Income", 0)
                print("Created Income parent bookmark", file=sys.stderr)
                
                for doc in income_docs:
                    with open(doc['file_path'], 'rb') as file:
                        reader = PdfReader(file)
                        if doc['page_num'] < len(reader.pages):
                            writer = PdfWriter()
                            writer.add_page(reader.pages[doc['page_num']])
            
                            temp_path = os.path.join(tempfile.gettempdir(), f"temp_{current_page}.pdf")
                            with open(temp_path, 'wb') as temp_file:
                                writer.write(temp_file)

                            try:
                                with open(temp_path, 'rb') as temp_file:
                                    merger.append(fileobj=temp_file)
                                    merger.add_outline_item(doc['title'], current_page, parent=income_parent)
                                    print(f"Added Income bookmark: {doc['title']} at page {current_page}", file=sys.stderr)                       
                            except Exception as e:
                                print(f"❌ Failed to add income page to merger: {e}", file=sys.stderr)
                            finally:
                                try:
                                    os.remove(temp_path)
                                except Exception as e:
                                    print(f"⚠️ Failed to delete temp file {temp_path}: {e}", file=sys.stderr)

                            current_page += 1

            # Process Expense documents
            if expense_docs:
                expense_parent = merger.add_outline_item("Expenses", current_page)
                print(f"Created Expenses parent bookmark at page {current_page}", file=sys.stderr)
                
                for doc in expense_docs:
                    with open(doc['file_path'], 'rb') as file:
                        reader = PdfReader(file)
                        if doc['page_num'] < len(reader.pages):
                            writer = PdfWriter()
                            writer.add_page(reader.pages[doc['page_num']])

                            temp_path = os.path.join(tempfile.gettempdir(), f"temp_{current_page}.pdf")

                            with open(temp_path, 'wb') as temp_file:
                                writer.write(temp_file)

                            try:
                                with open(temp_path, 'rb') as temp_file:
                                    merger.append(fileobj=temp_file)
                                    merger.add_outline_item(doc['title'], current_page, parent=expense_parent)
                                    print(f"Added Expense bookmark: {doc['title']} at page {current_page}", file=sys.stderr)
                            finally:
                                try:
                                    os.remove(temp_path)
                                except Exception as e:
                                    print(f"⚠️ Failed to delete temp file {temp_path}: {e}", file=sys.stderr)

                            current_page += 1

            # Write the final PDF
            print(f"\nWriting output to {output_path}", file=sys.stderr)
            with open(output_path, 'wb') as fout:
                merger.write(fout)

            # Close the merger
            merger.close()

            print("PDF merge complete", file=sys.stderr)

            # Verify the output
            print("\nVerifying output file...", file=sys.stderr)
            try:
                with open(output_path, 'rb') as f:
                    reader = PdfReader(f)
                    print(f"Output PDF has {len(reader.pages)} pages", file=sys.stderr)
                    if reader.outline:
                        print("Bookmarks found in output file:", file=sys.stderr)
                        print_bookmarks(reader.outline)
                    else:
                        print("Warning: No bookmarks found in output file", file=sys.stderr)
            except Exception as e:
                print(f"Error verifying output file: {e}", file=sys.stderr)
            
        except Exception as e:
            print(f"Error during PDF merging: {e}", file=sys.stderr)
            # Clean up merger
            merger.close()
            raise

    except Exception as e:
        print(f"Error in merge_pdfs_with_bookmarks: {e}", file=sys.stderr)
        raise

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python merge_with_bookmarks.py <input_folder> <output_file>", file=sys.stderr)
        sys.exit(1)
    
    input_folder = sys.argv[1]
    output_file = sys.argv[2]
    merge_pdfs_with_bookmarks(input_folder, output_file)


    
