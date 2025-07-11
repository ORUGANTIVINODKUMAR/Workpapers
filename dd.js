--------------------------------------------------------------------------------------------------

# 1) PyMuPDF
    try:
        doc = fitz.open(path)
        page = doc.load_page(page_index)
        text = page.get_text("text") or ""
        doc.close()
        log_extraction(path, "PyMuPDF", text)
    except Exception:
        traceback.print_exc()
    # 2) PDFMiner
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            t2 = pdfminer_extract(path, page_numbers=[page_index], laparams=PDFMINER_LA_PARAMS) or ""
            log_extraction(path, "PDFMiner", t2)
            if len(t2.strip()) > len(text):
                text = t2
        except Exception:
            traceback.print_exc()
    # 3) pdfplumber
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            with pdfplumber.open(path) as pdf:
                t3 = pdf.pages[page_index].extract_text() or ""
            log_extraction(path, "pdfplumber", t3)
            if len(t3.strip()) > len(text):
                text = t3
        except Exception:
            traceback.print_exc()
    # 4) PyPDF2
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            reader = PdfReader(path)
            t4 = reader.pages[page_index].extract_text() or ""
            log_extraction(path, "PyPDF2", t4)
            if len(t4.strip()) > len(text):
                text = t4
        except Exception:
            traceback.print_exc()
    # 5) Tesseract OCR
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            opts = {'poppler_path': POPPLER_PATH} if POPPLER_PATH else {}
            img = convert_from_path(path, first_page=page_index+1, last_page=page_index+1, **opts)[0]
            t5 = pytesseract.image_to_string(img, config="--psm 6") or ""
            log_extraction(path, "Tesseract", t5)
            if len(t5.strip()) > len(text):
                text = t5
        except Exception:
            traceback.print_exc()
    return text

--------------------------------------------------------------------------------------------------

import sys
import os
from PyPDF2 import PdfMerger, PdfReader
#from pdf2image import convert_from_path
#import pytesseract
#import platform 
import re
def extract_text_with_ocr(file_path, page_numbers=None):
    text = ''
    try:
        reader = PdfReader(file_path)
        pages_to_process = page_numbers if page_numbers is not None else range(len(reader.pages))
        
        for page_num in pages_to_process:
            if page_num < len(reader.pages):
                try:
                    page_text = reader.pages[page_num].extract_text()
                    if page_text.strip():  # Only add non-empty text
                        text += f"[Page {page_num + 1}]\n{page_text}\n"
                except Exception as e:
                    print(f"Warning: Could not extract text from page {page_num + 1}: {e}", file=sys.stderr)
                    continue
    except Exception as e:
        print(f"OCR failed for {file_path}: {e}", file=sys.stderr)
    return text

def extract_text_from_pdf(file_path, page_numbers=None):
    text = ''
    try:
        reader = PdfReader(file_path)
      
        pages_to_process = page_numbers if page_numbers is not None else range(len(reader.pages))
        
        for page_num in pages_to_process:
            if page_num < len(reader.pages):
                page_text = reader.pages[page_num].extract_text()
                if page_text.strip():  # Only add non-empty text
                    text += f"[Page {page_num + 1}]\n{page_text}\n"
    except Exception as e:
        print(f"PDF text extraction failed for {file_path}: {e}", file=sys.stderr)
    return text

def get_combined_text(file_path, page_numbers=None):
    # Get text from both PDF extraction and OCR
    pdf_text = extract_text_from_pdf(file_path, page_numbers)
    ocr_text = extract_text_with_ocr(file_path, page_numbers)
    # Combine both texts
    combined_text = pdf_text + "\n" + ocr_text
    print(f"Extracted text from {file_path} {'for pages ' + str(page_numbers) if page_numbers else ''}", file=sys.stderr)
    return combined_text

import re

def classify_bookmark(text):
    text = text.lower()

    if re.search(r'1098[\s\-]?t|tuition statement', text):
        return 'Expenses', '1098-T'
    elif re.search(r'1098[\s\-]?', text):
        if 'mortgage' in text:
            return 'Expenses', '1098-Mortgage'
        elif 'property tax' in text:
            return 'Expenses', 'Property Tax'
        else:
            return 'Expenses', '1098-Other'
    elif re.search(r'1099[\s\-]?int|interest income', text):
        return 'Income', '1099-INT'
    elif re.search(r'1099[\s\-]?div|dividends and distributions', text):
        return 'Income', '1099-DIV'
    elif re.search(r'1099[\s\-]?b|proceed from broker and barter exchange transactions', text):
        return 'Income', '1099-B'
    elif re.search(r'1099[\s\-]?r|distributions from pensions, annuities', text):
        return 'Income', '1099-R'
    elif re.search(r'1099[\s\-]?SA|distributions from an hsa, archer msa', text):
        return 'Income', '1099-SA'
    elif re.search(r'1099[\s\-]?k|payment card and third party', text):
        return 'Income', '1099-k'
    elif re.search(r'1099[\s\-]?s|proceeds from real estate transactions', text):
        return 'Income', '1099-S'
    elif re.search(r'1099[\s\-]?nec|nonemployee compensation', text):
        return 'Income', '1099-NEC'
    elif re.search(r'1099[\s\-]?patr|taxable distributions received from cooperatives', text):
        return 'Income', '1099-PATR'
    elif re.search(r'1099[\s\-]?misc|miscellaneous information', text):
        return 'Income', '1099-MISC'
    elif re.search(r'1099[\s\-]?oid|original issue discount', text):
        return 'Income', '1099-OID'
    elif re.search(r'1099[\s\-]?g|certain government payments', text):
        return 'Income', '1099-G'
    elif re.search(r'W[\s\-]?2g|certain gambling winnings', text):
        return 'Income', 'W-2G'
    elif re.search(r'(1065[\s\-]?)|(u\.s\. return of partnership income)', text):
        return 'Income', 'SCH-K', '1065'
    elif re.search(r'1120[\s\-]?S|u\.s\. income tax return for an s corporation', text):
        return 'Income', 'SCH-K', '1120-S'
    elif re.search(r'1041[\s\-]?|u\.s\. income tax return for estates and trusts', text):
        return 'Income', 'SCH-K', '1041'
    elif re.search(r'5498[\s\-]?SA|hsa contribution form|archer msa|medicare advantage msa', text):
        return 'Expenses', '5498-SA'
    elif re.search(r'1095[\s\-]?A|health insurance marketplace statement|obamacare form', text):
        return 'Insurance', '1095-A'
    elif re.search(r'1095[\s\-]?B|health coverage|irs form 1095-B', text):
        return 'Insurance', '1095-B'
    elif re.search(r'1095[\s\-]?C|employer-provided health insurance|irs form 1095-C', text):
        return 'Insurance', '1095-C'
    elif re.search(r'1099[\s\-]?q|distribution is from', text):
        return 'Income', '1099-Q'
    elif re.search(r'w[\s\-]?2|wage and tax statement', text):
        return 'Income', 'W-2'
    elif 'property tax' in text:
        return 'Expenses', 'Property Tax'
    else:
        return 'Unknown', 'Unknown Document'

def analyze_pdf(file_path):
    """Analyze each page of the PDF and return classifications for each page."""
    reader = PdfReader(file_path)
    num_pages = len(reader.pages)
    page_classifications = []
    
    print(f"Processing {file_path} with {num_pages} pages", file=sys.stderr)
    
    # Process pages in groups of 3 for efficiency
    for i in range(0, num_pages, 3):
        page_group = list(range(i, min(i + 3, num_pages)))
        text = get_combined_text(file_path, page_group)
        
        # Classify the text
        category, bookmark_name = classify_bookmark(text)
        
        # Store classification for each page in the group
        for page_num in page_group:
            page_classifications.append({
                'page_num': page_num,
                'category': category,
                'bookmark': bookmark_name
            })
            print(f"Page {page_num + 1} classified as: {category} - {bookmark_name}", file=sys.stderr)
    
    return page_classifications

def merge_pdfs_with_hierarchical_bookmarks(input_dir, output_path):
    print("Starting PDF merge", file=sys.stderr)

    merger = PdfMerger()
    files = sorted(os.listdir(input_dir))

    # Define Priority order
    priority_order = {
        #INCOME
        'W-2': 1,
        'W-2G': 2,
        '1099-INT': 3,
        '1099-DIV': 4,
        '1099-B': 5,
        '1099-NEC': 6,
        '1065': 7,
        '1120-S': 8,
        '1041': 9,
        '1099-R': 10,
        '1099-SA':11,
        '1099-MISC': 12,
        '1099-PATR': 13,
        '1099-OID': 14,
        '1099-Q': 15,
        '1099-G': 16,
        # EXPENSES
        '1098-Mortgage': 17,
        'Property Tax': 18,
        '5498-SA': 19,
        '1098-T': 20,
        '1095-A': 21,
        '1095-B': 22,
        '1095-C': 23,
        'Unknown Document': 24
    }

    docs_info = []

    # 1. Collect classification and info
    for filename in files:
        file_path = os.path.join(input_dir, filename)
        if os.path.isfile(file_path) and filename.lower().endswith('.pdf'):
            try:
                reader = PdfReader(file_path)
                   # Analyze each page of the PDF
                page_classifications = analyze_pdf(file_path)
                
                # Get the primary classification (using the first page)
                primary_category = page_classifications[0]['category']
                primary_bookmark = page_classifications[0]['bookmark']
                
                docs_info.append({
                    'path': file_path,
                    'category': primary_category,
                    'bookmark': primary_bookmark,
                    'priority': priority_order.get(primary_bookmark, 99),
                    'reader': reader,
                    'page_classifications': page_classifications
                })
            except Exception as e:
                print(f"Error processing {filename}: {e}", file=sys.stderr)
                continue

    # 2. Sort by defined priority
    docs_info.sort(key=lambda x: x['priority'])

    income_outline = []
    expense_outline = []

    # 3. Merge in order and assign bookmarks
    for doc in docs_info:
        with open(doc['path'], 'rb') as f:
            start_page_index = len(merger.pages)
            merger.append(f)
            # Create main document bookmark
            doc_bookmark = merger.add_outline_item(
                f"{doc['bookmark']} ({os.path.basename(doc['path'])})", 
                start_page_index
            )
            
            # Add page-specific bookmarks as children
            for page_class in doc['page_classifications']:
                page_num = page_class['page_num']
                page_bookmark = f"Page {page_num + 1}: {page_class['bookmark']}"
                merger.add_outline_item(
                    page_bookmark,
                    start_page_index + page_num,
                    parent=doc_bookmark
                )
            

            if doc['category'] == 'Income':
                  income_outline.append((doc['bookmark'], start_page_index))
            elif doc['category'] == 'Expenses':
                   expense_outline.append((doc['bookmark'], start_page_index))
                   
      # 4. Add category bookmarks
    if income_outline:
        income_parent = merger.add_outline_item("Income", income_outline[0][1])
        for name, idx in income_outline:
            merger.add_outline_item(name, idx, parent=income_parent)

    if expense_outline:
        expense_parent = merger.add_outline_item("Expenses", expense_outline[0][1])
        for name, idx in expense_outline:
            merger.add_outline_item(name, idx, parent=expense_parent)

    # 5. Write output
    with open(output_path, 'wb') as fout:
        merger.write(fout)
    print("PDF merge complete", file=sys.stderr)

    # 6. Clear uploads folder
    try:
        for file in os.listdir(input_dir):
            file_path = os.path.join(input_dir, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
                print(f"Deleted: {file_path}", file=sys.stderr)
    except Exception as e:
        print(f"Error clearing uploads folder: {e}", file=sys.stderr)

# Main runner
if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python merge_with_bookmarks.py <input_folder> <output_file>", file=sys.stderr)
        sys.exit(1)

    input_folder = sys.argv[1]
    output_file = sys.argv[2]
    merge_pdfs_with_hierarchical_bookmarks(input_folder, output_file)






    import sys
import os
from PyPDF2 import PdfMerger, PdfReader
import re

def extract_text_from_pdf(file_path, page_numbers=None):
    """Extract text from PDF using PyPDF2"""
    text = ''
    try:
        reader = PdfReader(file_path)
        pages_to_process = page_numbers if page_numbers is not None else range(len(reader.pages))
        
        for page_num in pages_to_process:
            if page_num < len(reader.pages):
                try:
                    page_text = reader.pages[page_num].extract_text()
                    if page_text.strip():  # Only add non-empty text
                        text += f"[Page {page_num + 1}]\n{page_text}\n"
                except Exception as e:
                    print(f"Warning: Could not extract text from page {page_num + 1}: {e}", file=sys.stderr)
                    continue
    except Exception as e:
        print(f"PDF text extraction failed for {file_path}: {e}", file=sys.stderr)
    return text

def classify_bookmark(text):
    """Classify document type based on text content"""
    text = text.lower()
    
    # Enhanced pattern matching
    patterns = [
        # Put W-2 first since it's most specific
        (r'w[\s\-]?2\b|wage.{0,10}tax.{0,10}statement|wages and tax statement|form w-2\b', ('Income', 'W-2')),
        (r'1098[\s\-]?t|tuition statement', ('Expenses', '1098-T')),
        (r'1098[\s\-]?(mortgage|mb)|mortgage interest|recipient.{0,30}mortgage', ('Expenses', '1098-Mortgage')),
        (r'1098[\s\-]?c|charitable contribution', ('Expenses', '1098-C')),
        (r'1099[\s\-]?int|interest income|interest statement', ('Income', '1099-INT')),
        (r'1099[\s\-]?div|dividends and distributions', ('Income', '1099-DIV')),
        (r'1099[\s\-]?q|distribution is from', ('Income', '1099-Q')),
        (r'1099[\s\-]?r|retirement|ira distribution', ('Income', '1099-R')),
        (r'property.{0,10}tax|real estate tax', ('Expenses', 'Property Tax')),
        (r'k[\s\-]?1|schedule k-1|partner.{0,10}share', ('Income', 'K-1'))
    ]
    
    # Try to match patterns
    for pattern, (category, doc_type) in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return category, doc_type
            
    # Check for form numbers in text
    form_numbers = re.findall(r'(1098|1099|w[\s\-]?2)[\s\-]([a-z]+)?', text, re.IGNORECASE)
    if form_numbers:
        form_num = form_numbers[0][0]
        if form_num.lower() == 'w2' or form_num.lower() == 'w-2':
            return 'Income', 'W-2'
        elif '1098' in form_num:
            return 'Expenses', '1098-Other'
        elif '1099' in form_num:
            return 'Income', '1099-Other'
    
    return 'Unknown', 'Unknown Document'

def analyze_pdf(file_path):
    """Analyze each page of the PDF and return classifications for each page."""
    try:
        reader = PdfReader(file_path)
        num_pages = len(reader.pages)
        page_classifications = []
        
        print(f"Processing {file_path} with {num_pages} pages", file=sys.stderr)
        
        # Process pages in groups of 3 for efficiency
        for i in range(0, num_pages, 3):
            page_group = list(range(i, min(i + 3, num_pages)))
            text = extract_text_from_pdf(file_path, page_group)
            
            # Try to classify based on extracted text
            category, bookmark_name = classify_bookmark(text)
            
            # Store classification for each page in the group
            for page_num in page_group:
                page_classifications.append({
                    'page_num': page_num,
                    'category': category,
                    'bookmark': bookmark_name
                })
                print(f"Page {page_num + 1} classified as: {category} - {bookmark_name}", file=sys.stderr)
        
        return page_classifications
    except Exception as e:
        print(f"Error analyzing PDF {file_path}: {e}", file=sys.stderr)
        return [{
            'page_num': 0,
            'category': 'Unknown',
            'bookmark': 'Unknown Document'
        }]

def merge_pdfs_with_hierarchical_bookmarks(input_dir, output_path):
    """Merge PDFs and create hierarchical bookmarks"""
    print("Starting PDF merge", file=sys.stderr)

    merger = PdfMerger()
    files = sorted(os.listdir(input_dir))

    # Define Priority order
    priority_order = {
        'W-2': 1,
        '1099-INT': 2,
        '1099-DIV': 3,
        '1099-R': 4,
        '1099-Q': 5,
        'K-1': 6,
        '1098-Mortgage': 7,
        'Property Tax': 8,
        '1098-T': 9,
        '1098-C': 10,
        '1098-Other': 11,
        '1099-Other': 12,
        'Unknown Document': 99
    }

    # Initialize category collections
    income_docs = []
    expense_docs = []
    other_docs = []
    current_page = 0  # Initialize page counter

    # Process each PDF file
    for filename in files:
        file_path = os.path.join(input_dir, filename)
        if os.path.isfile(file_path) and filename.lower().endswith('.pdf'):
            try:
                # Analyze the PDF
                page_classifications = analyze_pdf(file_path)
                
                # Get the primary classification (using the first page)
                primary_category = page_classifications[0]['category']
                primary_bookmark = page_classifications[0]['bookmark']
                
                doc_info = {
                    'path': file_path,
                    'category': primary_category,
                    'bookmark': primary_bookmark,
                    'priority': priority_order.get(primary_bookmark, 99),
                    'page_classifications': page_classifications,
                    'filename': filename
                }

                # Add to appropriate category list
                if primary_category == 'Income':
                    income_docs.append(doc_info)
                elif primary_category == 'Expenses':
                    expense_docs.append(doc_info)
                else:
                    other_docs.append(doc_info)

            except Exception as e:
                print(f"Error processing {filename}: {e}", file=sys.stderr)
                continue

    # Sort each category by priority
    income_docs.sort(key=lambda x: x['priority'])
    expense_docs.sort(key=lambda x: x['priority'])
    other_docs.sort(key=lambda x: x['priority'])

    try:
        # Create Income category and its documents
        if income_docs:
            income_parent = merger.add_outline_item("Income", current_page)
            
            for doc in income_docs:
                try:
                    with open(doc['path'], 'rb') as f:
                        # Add the document to the merged PDF
                        merger.append(f)
                        
                        # Create document bookmark under Income category
                        doc_bookmark = merger.add_outline_item(
                            f"{doc['bookmark']} - {doc['filename']}", 
                            current_page,
                            parent=income_parent
                        )
                        
                        # Add page-specific bookmarks if document has multiple pages
                        if len(doc['page_classifications']) > 1:
                            for page_class in doc['page_classifications']:
                                page_num = page_class['page_num']
                                page_bookmark = f"Page {page_num + 1}"
                                merger.add_outline_item(
                                    page_bookmark,
                                    current_page + page_num,
                                    parent=doc_bookmark
                                )
                        
                        current_page += len(doc['page_classifications'])
                except Exception as e:
                    print(f"Error merging {doc['path']}: {e}", file=sys.stderr)
                    continue

        # Create Expenses category and its documents
        if expense_docs:
            expense_parent = merger.add_outline_item("Expenses", current_page)
            
            for doc in expense_docs:
                try:
                    with open(doc['path'], 'rb') as f:
                        # Add the document to the merged PDF
                        merger.append(f)
                        
                        # Create document bookmark under Expenses category
                        doc_bookmark = merger.add_outline_item(
                            f"{doc['bookmark']} - {doc['filename']}", 
                            current_page,
                            parent=expense_parent
                        )
                        
                        # Add page-specific bookmarks if document has multiple pages
                        if len(doc['page_classifications']) > 1:
                            for page_class in doc['page_classifications']:
                                page_num = page_class['page_num']
                                page_bookmark = f"Page {page_num + 1}"
                                merger.add_outline_item(
                                    page_bookmark,
                                    current_page + page_num,
                                    parent=doc_bookmark
                                )
                        
                        current_page += len(doc['page_classifications'])
                except Exception as e:
                    print(f"Error merging {doc['path']}: {e}", file=sys.stderr)
                    continue

        # Add other documents (if any) without category
        for doc in other_docs:
            try:
                with open(doc['path'], 'rb') as f:
                    merger.append(f)
                    
                    # Create document bookmark at root level
                    doc_bookmark = merger.add_outline_item(
                        f"{doc['bookmark']} - {doc['filename']}", 
                        current_page
                    )
                    
                    # Add page-specific bookmarks if document has multiple pages
                    if len(doc['page_classifications']) > 1:
                        for page_class in doc['page_classifications']:
                            page_num = page_class['page_num']
                            page_bookmark = f"Page {page_num + 1}"
                            merger.add_outline_item(
                                page_bookmark,
                                current_page + page_num,
                                parent=doc_bookmark
                            )
                    
                    current_page += len(doc['page_classifications'])
            except Exception as e:
                print(f"Error merging {doc['path']}: {e}", file=sys.stderr)
                continue

        # Write the merged PDF
        with open(output_path, 'wb') as fout:
            merger.write(fout)
        print("PDF merge complete", file=sys.stderr)

        # Clear uploads folder
        for file in os.listdir(input_dir):
            file_path = os.path.join(input_dir, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
                print(f"Deleted: {file_path}", file=sys.stderr)

    except Exception as e:
        print(f"Error in PDF processing: {e}", file=sys.stderr)
        print("^^^^^^^^^^^^^", file=sys.stderr)
        raise

# Main runner
if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python merge_with_bookmarks.py <input_folder> <output_file>", file=sys.stderr)
        sys.exit(1)

    input_folder = sys.argv[1]
    output_file = sys.argv[2]
    merge_pdfs_with_hierarchical_bookmarks(input_folder, output_file)



    12-06-2025
import sys
import os
from PyPDF2 import PdfMerger, PdfReader

def extract_text_from_pdf(file_path, page_num=None):
    """Extract text from PDF using PyPDF2"""
    text = ''
    try:
        with open(file_path, 'rb') as file:
            reader = PdfReader(file)
            if page_num is not None:
                if 0 <= page_num < len(reader.pages):
                    try:
                        text = reader.pages[page_num].extract_text()
                    except Exception as e:
                        print(f"Warning: Could not extract text from page {page_num + 1}: {e}", file=sys.stderr)
            else:
                for page in reader.pages:
                    try:
                        text += page.extract_text() + "\n"
                    except Exception as e:
                        print(f"Warning: Could not extract text from page: {e}", file=sys.stderr)
    except Exception as e:
        print(f"PDF text extraction failed for {file_path}: {e}", file=sys.stderr)
    return text.lower()

def classify_document(text):
    """Classify document type based on text content"""
    # Income Documents
    if any(x in text for x in ['w-2', 'w2', 'wage', 'wages and tax statement']):   
        return 'Income', 'W-2'
    elif any(x in text for x in ['1099-int', 'interest income']):
        return 'Income', '1099-INT'
    elif any(x in text for x in ['1099-div', 'dividends and distributions']):
        return 'Income', '1099-DIV'
    elif any(x in text for x in ['1099-r', 'retirement', 'ira distribution']):
        return 'Income', '1099-R'
    elif any(x in text for x in ['1099-q', 'distribution is from']):
        return 'Income', '1099-Q'
    elif any(x in text for x in ['k-1', 'schedule k-1']):
        return 'Income', 'K-1'
    
    # Expense Documents
    elif any(x in text for x in ['1098-t', 'tuition statement']):
        return 'Expenses', '1098-T'
    elif any(x in text for x in ['1098', 'mortgage', 'mortgage interest']):
        return 'Expenses', '1098-Mortgage'
    elif any(x in text for x in ['property tax', 'real estate tax']):
        return 'Expenses', 'Property Tax'
    
    # Generic 1098/1099 Forms
    elif '1098' in text:
        return 'Expenses', '1098-Other'
    elif '1099' in text:
        return 'Income', '1099-Other'
    
    return 'Unknown', 'Unknown Document'

def analyze_pdf_pages(file_path):
    """Analyze each page of the PDF and return classifications for each page"""
    try:
        reader = PdfReader(file_path)
        num_pages = len(reader.pages)
        page_classifications = []
        
        print(f"Analyzing {file_path} with {num_pages} pages", file=sys.stderr)
        
        # Process each page individually
        for page_num in range(num_pages):
            # Extract and classify text from this page
            text = extract_text_from_pdf(file_path, page_num)
            category, doc_type = classify_document(text)
            
            # Add classification for this page
            page_classifications.append({
                'page_num': page_num,
                'category': category,
                'type': doc_type
            })
            
            print(f"Page {page_num + 1}/{num_pages} classified as: {category} - {doc_type}", file=sys.stderr)
        
        return page_classifications
        
    except Exception as e:
        print(f"Error analyzing PDF {file_path}: {e}", file=sys.stderr)
        return []

def format_bookmark_title(doc_type, page_num):
    """Format the bookmark title for a page"""
    return doc_type  # Now only returns the form type without page number

def merge_pdfs_with_bookmarks(input_dir, output_path):
    """Merge PDFs and create bookmarks"""
    print("Starting PDF merge", file=sys.stderr)
    
    # Initialize merger
    merger = PdfMerger()
    current_page = 0
    
    # Track processed files for debugging
    processed_files = []
    
    try:
        # Process each PDF file
        pdf_files = [f for f in os.listdir(input_dir) if f.lower().endswith('.pdf')]
        print(f"Found {len(pdf_files)} PDF files to process", file=sys.stderr)
        
        for filename in sorted(pdf_files):
            file_path = os.path.join(input_dir, filename)
            print(f"\nProcessing file: {filename}", file=sys.stderr)
            
            try:
                # Get page count before processing
                with open(file_path, 'rb') as file:
                    reader = PdfReader(file)
                    num_pages = len(reader.pages)
                    print(f"File {filename} has {num_pages} pages", file=sys.stderr)
                
                # Analyze pages
                page_classifications = analyze_pdf_pages(file_path)
                print(f"Found {len(page_classifications)} classifications", file=sys.stderr)
                
                if not page_classifications:
                    print(f"Skipping {filename} - no classifications found", file=sys.stderr)
                    continue
                
                # Create income and expense parent bookmarks if needed
                income_parent = None
                expense_parent = None
                
                # Append the PDF
                print(f"Current total pages before append: {current_page}", file=sys.stderr)
                merger.append(fileobj=file_path)
                processed_files.append({
                    'filename': filename,
                    'pages': num_pages,
                    'start_page': current_page
                })
                
                # Add bookmarks for each page
                for page_info in page_classifications:
                    page_num = page_info['page_num']
                    page_type = page_info['type']
                    category = page_info['category']
                    
                    print(f"Processing bookmark for page {page_num} of type {page_type}", file=sys.stderr)
                    
                    # Skip invalid page numbers
                    if page_num >= num_pages:
                        print(f"Skipping invalid page number {page_num}", file=sys.stderr)
                        continue
                    
                    # Create parent bookmarks if needed
                    if category == 'Income' and income_parent is None:
                        income_parent = merger.add_outline_item("Income", current_page)
                        print(f"Created Income parent bookmark at page {current_page}", file=sys.stderr)
                    elif category == 'Expenses' and expense_parent is None:
                        expense_parent = merger.add_outline_item("Expenses", current_page)
                        print(f"Created Expenses parent bookmark at page {current_page}", file=sys.stderr)
                    
                    # Calculate correct page number in merged document
                    merged_page_num = current_page + page_num
                    print(f"Adding bookmark at page {merged_page_num}", file=sys.stderr)
                    
                    # Add bookmark
                    bookmark_title = format_bookmark_title(page_type, page_num)
                    if category == 'Income':
                        merger.add_outline_item(bookmark_title, merged_page_num, parent=income_parent)
                    elif category == 'Expenses':
                        merger.add_outline_item(bookmark_title, merged_page_num, parent=expense_parent)
                    else:
                        merger.add_outline_item(bookmark_title, merged_page_num)
                
                # Update page counter
                current_page += num_pages
                print(f"Updated total pages to {current_page}", file=sys.stderr)
                
            except Exception as e:
                print(f"Error processing {filename}: {e}", file=sys.stderr)
                continue
        
        # Print summary before writing
        print("\nProcessing Summary:", file=sys.stderr)
        total_pages = 0
        for file_info in processed_files:
            print(f"File: {file_info['filename']}", file=sys.stderr)
            print(f"  Pages: {file_info['pages']}", file=sys.stderr)
            print(f"  Start Page: {file_info['start_page']}", file=sys.stderr)
            total_pages += file_info['pages']
        print(f"Total pages to be written: {total_pages}", file=sys.stderr)
        
        # Write the merged PDF
        try:
            print(f"Writing output to {output_path}", file=sys.stderr)
            with open(output_path, 'wb') as fout:
                merger.write(fout)
            print("PDF merge complete", file=sys.stderr)
            
            # Verify output file
            with open(output_path, 'rb') as f:
                reader = PdfReader(f)
                print(f"Output PDF has {len(reader.pages)} pages", file=sys.stderr)
                
        except Exception as e:
            print(f"Error writing output file: {e}", file=sys.stderr)
            raise
        finally:
            merger.close()
        
        # Clean up uploads folder
        for filename in os.listdir(input_dir):
            file_path = os.path.join(input_dir, filename)
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                    print(f"Deleted: {file_path}", file=sys.stderr)
                except Exception as e:
                    print(f"Error deleting {file_path}: {e}", file=sys.stderr)
                    continue
                
    except Exception as e:
        print(f"Error in PDF processing: {e}", file=sys.stderr)
        merger.close()
        raise

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python merge_with_bookmarks.py <input_folder> <output_file>", file=sys.stderr)
        sys.exit(1)
    
    input_folder = sys.argv[1]
    output_file = sys.argv[2]
    merge_pdfs_with_bookmarks(input_folder, output_file)





from pdf2image import convert_from_path
from PIL import Image
import pytesseract

def extract_text_from_pdf(file_path, page_num=None):
    """Extract text from PDF using PyPDF2 with OCR fallback"""
    text = ''
    try:
        with open(file_path, 'rb') as file:
            reader = PdfReader(file)
            if page_num is not None:
                if 0 <= page_num < len(reader.pages):
                    text = reader.pages[page_num].extract_text() or ''
                    if not text.strip():
                        # Use OCR fallback
                        image = convert_from_path(file_path, first_page=page_num+1, last_page=page_num+1)[0]
                        text = pytesseract.image_to_string(image)
            else:
                for i, page in enumerate(reader.pages):
                    page_text = page.extract_text() or ''
                    if not page_text.strip():
                        image = convert_from_path(file_path, first_page=i+1, last_page=i+1)[0]
                        page_text = pytesseract.image_to_string(image)
                    text += page_text + "\n"
    except Exception as e:
        print(f"PDF text extraction failed for {file_path}: {e}", file=sys.stderr)
    return text.lower()

for ocr reading  we are replacing this combined_text
def extract_text_from_pdf(file_path, page_num=None):
    """Extract text from PDF using PyPDF2"""
    text = ''
    try:
        with open(file_path, 'rb') as file:
            reader = PdfReader(file)
            if page_num is not None:
                if 0 <= page_num < len(reader.pages):
                    try:
                        text = reader.pages[page_num].extract_text()
                    except Exception as e:
                        print(f"Warning: Could not extract text from page {page_num + 1}: {e}", file=sys.stderr)
            else:
                for page in reader.pages:
                    try:
                        text += page.extract_text() + "\n"
                    except Exception as e:
                        print(f"Warning: Could not extract text from page: {e}", file=sys.stderr)
    except Exception as e:
        print(f"PDF text extraction failed for {file_path}: {e}", file=sys.stderr)
    return text.lower()

     if category == 'INCOME' and page_type != 'Unknown Document':
                    if page_type not in INCOME_types_added:
                        merger.add_outline_item(page_type, merged_page_num, parent=INCOME_parent)
                        INCOME_types_added[page_type] = merged_page_num
                elif category == 'EXPENSES' and page_type != 'Unknown Document':
                    if page_type not in expense_types_added:
                            merger.add_outline_item(page_type, merged_page_num, parent=expense_parent)
                            expense_types_added[page_type] = merged_page_num



                            if ('w-2' in text or 'w2' in text) and any(x in text for x in [
        'wage and tax statement',
        'wages, tips, other comp.',
        'federal income tax withheld',
        'social security wages',
        'medicare wages and tips',
        'medicare tax withheld',
    ]):
























































    
18-06-2025
import sys
import os
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
import pytesseract
from pdf2image import convert_from_path #this uses poppler under the hood
from PIL import Image
import tempfile
import pdfplumber

def extract_text_with_ocr(pdf_path, page_num=None):
    """Extract text using OCR for scanned documents"""
    try:
        # Replace this with your actual poppler bin path
        POPPLER_PATH = r"C:\poppler\Library\bin"
        # Convert PDF to image(s)
        images = convert_from_path(pdf_path, poppler_path=POPPLER_PATH)

        if page_num is not None:
            if 0 <= page_num < len(images):
                text = pytesseract.image_to_string(images[page_num])
                print(f"\n=== OCR TEXT FROM PAGE {page_num + 1} of {pdf_path} ===")
                print(text)
                print("=" * 60)
                return text
            return ''
        
        text = ''
        for i, image in enumerate(images):
            page_text = pytesseract.image_to_string(image)
            print(f"\n=== OCR TEXT FROM PAGE {i + 1} of {pdf_path} ===")
            print(page_text)
            print("=" * 60)
            text += page_text + '\n'
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
                        
                        # Print extracted text
                        print(f"\n=== EXTRACTED TEXT FROM PAGE {page_num + 1} of {file_path} ===")
                        if text.strip():
                            print(text)
                        else:
                            print("No text found with PyPDF2 extraction")
                        print("=" * 60)
                        
                        if not text or len(text.strip()) < 50:
                            print(f"⚠️ No text on page {page_num + 1}, using OCR", file=sys.stderr)
                            try:
                                image = convert_from_path(
                                    file_path,
                                    first_page=page_num + 1,
                                    last_page=page_num + 1,
                                    poppler_path=POPPLER_PATH
                                )[0]
                                ocr_text = pytesseract.image_to_string(image)
                                print(f"\n=== OCR TEXT FROM PAGE {page_num + 1} of {file_path} ===")
                                print(ocr_text)
                                print("=" * 60)
                                text = ocr_text
                                print(f"OCR completed for page {page_num + 1}", file=sys.stderr)
                            except Exception as ocr_error:
                                print(f"OCR failed for page {page_num + 1}: {ocr_error}", file=sys.stderr)
                    except Exception as e:
                        print(f"Warning: Could not extract text from page: {e}", file=sys.stderr)
            else:
                for i in range(len(reader.pages)):
                    try:
                        page_text = reader.pages[i].extract_text() or ''
                        
                        # Print extracted text for each page
                        print(f"\n=== EXTRACTED TEXT FROM PAGE {i + 1} of {file_path} ===")
                        if page_text.strip():
                            print(page_text)
                        else:
                            print("No text found with PyPDF2 extraction")
                        print("=" * 60)
                        
                        if not page_text or len(page_text.strip()) < 50:
                            print(f"⚠️ No text on page {i + 1}, using OCR", file=sys.stderr)
                            try:
                                image = convert_from_path(
                                    file_path,
                                    first_page=i + 1,
                                    last_page=i + 1,
                                    poppler_path=POPPLER_PATH
                                )[0]
                                ocr_text = pytesseract.image_to_string(image)
                                print(f"\n=== OCR TEXT FROM PAGE {i + 1} of {file_path} ===")
                                print(ocr_text)
                                print("=" * 60)
                                page_text = ocr_text
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
                    
                    # Print the full extracted text
                    print(f"\n=== DEBUG - FULL TEXT FROM PAGE {i + 1} ===")
                    print(text)
                    print("=" * 60)
                    
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
    print(f"\nDEBUG - Text being analyzed for classification: {text[:200]}", file=sys.stderr)
    
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
            print(f"\n{'='*80}")
            print(f"PROCESSING PAGE {page_num + 1} of {file_path}")
            print(f"{'='*80}")
            
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

            # ✅ CLEANUP ORIGINAL UPLOADED FILES
            print(f"\n🧹 Cleaning up uploaded files in {input_dir}", file=sys.stderr)
            try:
                for f in os.listdir(input_dir):
                    if f.lower().endswith('.pdf'):
                        file_to_remove = os.path.join(input_dir, f)
                        os.remove(file_to_remove)
                        print(f"✅ Deleted: {file_to_remove}", file=sys.stderr)
            except Exception as cleanup_error:
                print(f"⚠️ Failed to clean up uploaded files: {cleanup_error}", file=sys.stderr)

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



21-06-2025
import sys, os, io, tempfile
import traceback
from collections import defaultdict
from typing import Dict, List, Tuple
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
import pytesseract
from pdf2image import convert_from_path

# ---------- Unicode console on Windows -------------------
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# ---------- Configuration ---------------------------------
POPPLER_PATH = os.environ.get("POPPLER_PATH")  # e.g. "C:\\poppler\\Library\\bin"
OCR_MIN_CHARS = 50  # If extracted text length < this, fallback to OCR

# ---------- Priority Tables -------------------------------
income_priorities = {
    'W-2': 1, '1099-NEC': 2, '1099-PATR': 3, '1099-MISC': 4,
    '1099-OID': 5, '1099-G': 6, 'W-2G': 7, '1065': 8, '1120-S': 9,
    '1041': 10, '1099-INT': 11, '1099-DIV': 12, '1099-R': 13,
    '1099-Q': 14, 'K-1': 15, '1099-Other': 16,
}
expense_priorities = {
    '5498-SA': 1, '1095-A': 2, '1095-B': 3, '1095-C': 4,
    '1098-Mortgage': 5, '1098-T': 6, 'Property Tax': 7, '1098-Other': 8,
}

# ---------- Helpers ---------------------------------------
def get_form_priority(ftype: str, category: str) -> int:
    table = income_priorities if category == 'Income' else expense_priorities if category == 'Expenses' else {}
    return table.get(ftype, max(table.values()) + 1 if table else 9999)

# Log a snippet of extracted text for debugging
def log_extraction(src: str, method: str, text: str):
    snippet = text[:200].replace('\n', ' ') + ('...' if len(text) > 200 else '')
    print(f"[{method}] {os.path.basename(src)}: '{snippet}'")

# ---------- OCR Fallback -----------------------------------
def ocr_page(path: str, page_index: int) -> str:
    try:
        opts = {'poppler_path': POPPLER_PATH} if POPPLER_PATH else {}
        images = convert_from_path(path, first_page=page_index+1, last_page=page_index+1, **opts)
        if not images:
            return ''
        text = pytesseract.image_to_string(images[0])
        log_extraction(path, 'OCR', text)
        return text
    except Exception:
        print(f"OCR failed for {path} p{page_index+1}")
        traceback.print_exc()
        return ''

# ---------- Text Extraction with Error Handling -----------
def extract_text_safe(path: str, page_index: int) -> str:
    text = ''
    try:
        reader = PdfReader(path)
        try:
            text = reader.pages[page_index].extract_text() or ''
        except Exception:
            print(f"PyPDF2.extract_text failed at {path} p{page_index+1}")
            traceback.print_exc()
    except Exception:
        print(f"Cannot open {path}")
        traceback.print_exc()

    log_extraction(path, 'Extracted', text)
    if len(text.strip()) < OCR_MIN_CHARS:
        text = ocr_page(path, page_index)
    return text

# ---------- Classification -------------------------------
def classify_text(text: str) -> Tuple[str, str]:
    t = text.lower()
    if 'w-2' in t or 'w2' in t:
        return 'Income', 'W-2'
    if '1099-int' in t or 'interest income' in t:
        return 'Income', '1099-INT'
    if '1099-div' in t:
        return 'Income', '1099-DIV'
    if '1098' in t and 'mortgage' in t:
        return 'Expenses', '1098-Mortgage'
    if '1098-t' in t:
        return 'Expenses', '1098-T'
    if 'property tax' in t:
        return 'Expenses', 'Property Tax'
    if '1098' in t:
        return 'Expenses', '1098-Other'
    if '1099' in t:
        return 'Income', '1099-Other'
    return 'Unknown', 'Unused'

# Group entries by form type
def group_by_type(entries: List[Tuple[str,int,str]]) -> Dict[str, List[Tuple[str,int,str]]]:
    d = defaultdict(list)
    for e in entries:
        d[e[2]].append(e)
    return d

# ---------- Main Merge Function ---------------------------
def merge_with_bookmarks(input_dir: str, output_pdf: str):
    if not os.path.isdir(input_dir):
        print(f"Directory not found: {input_dir}")
        return
    files = sorted(f for f in os.listdir(input_dir) if f.lower().endswith('.pdf'))
    print(f"Processing {len(files)} PDFs...")

    # Collect pages by category
    income, expenses, others = [], [], []
    for fname in files:
        path = os.path.join(input_dir, fname)
        try:
            pages = len(PdfReader(path).pages)
        except Exception:
            print(f"Cannot read pages of {fname}")
            continue
        for i in range(pages):
            txt = extract_text_safe(path, i)
            cat, ftype = classify_text(txt)
            if cat == 'Income':
                income.append((path, i, ftype))
            elif cat == 'Expenses':
                expenses.append((path, i, ftype))
            else:
                others.append((path, i, 'Unused'))

    # Sort entries
    income.sort(key=lambda e: (get_form_priority(e[2], 'Income'), e[0], e[1]))
    expenses.sort(key=lambda e: (get_form_priority(e[2], 'Expenses'), e[0], e[1]))

    merger = PdfMerger()
    current = 0

    def append_and_bookmark(entry, parent, title):
        nonlocal current
        path, idx, _ = entry
        # write temp
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        w = PdfWriter()
        try:
            w.add_page(PdfReader(path).pages[idx])
            w.write(tmp)
        except Exception:
            print(f"Temp write failed for {path} p{idx+1}")
        tmp.close()
        # append
        with open(tmp.name, 'rb') as fh:
            merger.append(fileobj=fh)
        os.unlink(tmp.name)
        # bookmark
        merger.add_outline_item(title, current, parent=parent)
        current += 1

    # Income with nested by form
    if income:
        inc_root = merger.add_outline_item('Income', current)
        for form, group in group_by_type(income).items():
            form_node = merger.add_outline_item(form, current, parent=inc_root)
            for idx, entry in enumerate(group, 1):
                title = form if len(group)==1 else f"{form}#{idx}"
                append_and_bookmark(entry, form_node, title)

    # Expenses nested
    if expenses:
        exp_root = merger.add_outline_item('Expenses', current)
        for form, group in group_by_type(expenses).items():
            form_node = merger.add_outline_item(form, current, parent=exp_root)
            for idx, entry in enumerate(group, 1):
                title = form if len(group)==1 else f"{form}#{idx}"
                append_and_bookmark(entry, form_node, title)

    # Others -> Unused
    if others:
        oth_root = merger.add_outline_item('Others', current)
        unused_node = merger.add_outline_item('Unused', current, parent=oth_root)
        for idx, entry in enumerate(others, 1):
            title = 'Unused' if len(others)==1 else f"Unused#{idx}"
            append_and_bookmark(entry, unused_node, title)

    # write output
    with open(output_pdf, 'wb') as f:
        merger.write(f)
    merger.close()
    print(f"Merged PDF written to {output_pdf}")

# ------- CLI ----------------------------------------------
if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description='Merge and bookmark PDFs')
    p.add_argument('input_dir', help='Folder containing PDFs')
    p.add_argument('output_pdf', help='Output merged PDF path')
    args = p.parse_args()
    merge_with_bookmarks(args.input_dir, args.output_pdf)


    22-06-2025
    import sys, os, io, tempfile
import traceback
from collections import defaultdict
from typing import Dict, List, Tuple
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
import pytesseract
from pdf2image import convert_from_path

# ── Unicode console on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# ── Configuration
POPPLER_PATH = os.environ.get("POPPLER_PATH")  # e.g. "C:\\poppler\\Library\\bin"
OCR_MIN_CHARS = 50  # if extracted text < this, fallback to OCR

# ── Priority tables
income_priorities = {
    'W-2': 1, '1099-NEC': 2, '1099-PATR': 3, '1099-MISC': 4,
    '1099-OID': 5, '1099-G': 6, 'W-2G': 7, '1065': 8, '1120-S': 9,
    '1041': 10, '1099-INT': 11, '1099-DIV': 12, '1099-R': 13,
    '1099-Q': 14, 'K-1': 15, '1099-Other': 16,
}
expense_priorities = {
    '5498-SA': 1, '1095-A': 2, '1095-B': 3, '1095-C': 4,
    '1098-Mortgage': 5, '1098-T': 6, 'Property Tax': 7, '1098-Other': 8,
}

def get_form_priority(ftype: str, category: str) -> int:
    table = income_priorities if category == 'Income' else (
               expense_priorities if category == 'Expenses' else {})
    return table.get(ftype, max(table.values())+1 if table else 9999)

# ── Logging helper
def log_extraction(src: str, method: str, text: str):
    snippet = text[:100].replace('\n', ' ') + ('...' if len(text) > 100 else '')
    print(f"[{method}] {os.path.basename(src)} → '{snippet}'")

# ── OCR fallback
def ocr_page(path: str, page_index: int) -> str:
    try:
        opts = {'poppler_path': POPPLER_PATH} if POPPLER_PATH else {}
        images = convert_from_path(path, first_page=page_index+1, last_page=page_index+1, **opts)
        if not images:
            return ''
        text = pytesseract.image_to_string(images[0])
        log_extraction(path, 'OCR', text)
        return text
    except Exception:
        print(f"OCR failed for {path} p{page_index+1}")
        traceback.print_exc()
        return ''

# ── Safe text extraction (catching all errors)
def extract_text_safe(path: str, page_index: int) -> str:
    text = ''
    # Open and extract within try/except
    try:
        reader = PdfReader(path)
        try:
            page = reader.pages[page_index]
            try:
                text = page.extract_text() or ''
            except Exception:
                print(f"Error extracting text on {path} p{page_index+1}")
                traceback.print_exc()
                text = ''
        except IndexError:
            print(f"Page index {page_index} out of range for {path}")
            text = ''
    except Exception:
        print(f"Failed to open {path}")
        traceback.print_exc()
        text = ''

    log_extraction(path, 'Extracted', text)
    if len(text.strip()) < OCR_MIN_CHARS:
        text = ocr_page(path, page_index)
    return text

# ── Classification rules
def classify_text(text: str) -> Tuple[str, str]:
    t = text.lower()
    if 'w-2' in t or 'w2' in t: return 'Income', 'W-2'
    if '1099-int' in t or 'interest income' in t: return 'Income', '1099-INT'
    if '1099-div' in t: return 'Income', '1099-DIV'
    if '1098' in t and 'mortgage' in t: return 'Expenses', '1098-Mortgage'
    if '1098-t' in t: return 'Expenses', '1098-T'
    if 'property tax' in t: return 'Expenses', 'Property Tax'
    if '1098' in t: return 'Expenses', '1098-Other'
    if '1099' in t: return 'Income', '1099-Other'
    return 'Unknown', 'Unused'

# ── Group by form type
def group_by_type(entries: List[Tuple[str,int,str]]) -> Dict[str, List[Tuple[str,int,str]]]:
    d = defaultdict(list)
    for e in entries:
        d[e[2]].append(e)
    return d

# ── Merge + bookmarks
def merge_with_bookmarks(input_dir: str, output_pdf: str):
    if not os.path.isdir(input_dir):
        print(f"Directory not found: {input_dir}")
        return
    files = sorted([f for f in os.listdir(input_dir) if f.lower().endswith('.pdf')])
    print(f"Processing {len(files)} PDFs...")

    income, expenses, others = [], [], []
    for fname in files:
        full = os.path.join(input_dir, fname)
        try:
            total = len(PdfReader(full).pages)
        except Exception:
            print(f"Unreadable PDF: {fname}")
            continue
        for i in range(total):
            text = extract_text_safe(full, i)
            # Print full extracted text for verification
             # debug dump goes to stderr so Node can always see it
            print("="*60, file=sys.stderr, flush=True)
            print(f"📄 {fname} — PAGE {i+1} extracted text:", file=sys.stderr, flush=True)
            print((text if text.strip() else "[NO TEXT FOUND]"), file=sys.stderr, flush=True)
            print("="*60 + "\n", file=sys.stderr, flush=True)

            # End enhancement
            cat, ftype = classify_text(text)
            print(f"→ Classified {fname} p{i+1} as {cat}/{ftype}")
            entry = (full, i, ftype)
            if cat == 'Income':
                income.append(entry)
            elif cat == 'Expenses':
                expenses.append(entry)
            else:
                others.append(entry)

    # Sort entries
    income.sort(key=lambda e:(get_form_priority(e[2],'Income'), e[0], e[1]))
    expenses.sort(key=lambda e:(get_form_priority(e[2],'Expenses'), e[0], e[1]))

    merger = PdfMerger()
    page_num = 0

    def append_and_bookmark(entry, parent, label):
        nonlocal page_num
        path, idx, _ = entry
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        writer = PdfWriter()
        try:
            writer.add_page(PdfReader(path).pages[idx])
            writer.write(tmp)
        except Exception:
            print(f"Temp write failed: {path} p{idx+1}")
            traceback.print_exc()
        tmp.close()
        with open(tmp.name,'rb') as fh:
            merger.append(fileobj=fh)
        os.unlink(tmp.name)
        merger.add_outline_item(label, page_num, parent=parent)
        page_num += 1

    # Income nested by form
    if income:
        root = merger.add_outline_item('Income', page_num)
        for form, group in group_by_type(income).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, e in enumerate(group,1):
                lbl = form if len(group)==1 else f"{form}#{j}"
                append_and_bookmark(e, node, lbl)

    # Expenses nested
    if expenses:
        root = merger.add_outline_item('Expenses', page_num)
        for form, group in group_by_type(expenses).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, e in enumerate(group,1):
                lbl = form if len(group)==1 else f"{form}#{j}"
                append_and_bookmark(e, node, lbl)

    # Others → Unused
    if others:
        root = merger.add_outline_item('Others', page_num)
        node = merger.add_outline_item('Unused', page_num, parent=root)
        for j, e in enumerate(others,1):
            lbl = 'Unused' if len(others)==1 else f"Unused#{j}"
            append_and_bookmark(e, node, lbl)

    with open(output_pdf,'wb') as fout:
        merger.write(fout)
    merger.close()
    print(f"Merged PDF written to: {output_pdf}")

# ── CLI
if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description="Merge PDFs with nested bookmarks and robust text extraction")
    p.add_argument('input_dir',  help="Folder with PDFs to merge")
    p.add_argument('output_pdf', help="Destination merged PDF path")
    args = p.parse_args()
    merge_with_bookmarks(args.input_dir, args.output_pdf)





    22-06-2025
    import sys, os, io, tempfile
import traceback
from collections import defaultdict
from typing import Dict, List, Tuple
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
from pdfminer.high_level import extract_text as pdfminer_extract
import pytesseract
from pdf2image import convert_from_path

# ── Unicode console on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# ── Configuration
POPPLER_PATH = os.environ.get("POPPLER_PATH")  # e.g. "C:\\poppler\\Library\\bin"
OCR_MIN_CHARS = 50  # if extracted text < this, fallback to OCR

# ── Priority tables
income_priorities = {
    'W-2': 1, '1099-NEC': 2, '1099-PATR': 3, '1099-MISC': 4,
    '1099-OID': 5, '1099-G': 6, 'W-2G': 7, '1065': 8, '1120-S': 9,
    '1041': 10, '1099-INT': 11, '1099-DIV': 12, '1099-R': 13,
    '1099-Q': 14, 'K-1': 15, '1099-Other': 16,
}
expense_priorities = {
    '5498-SA': 1, '1095-A': 2, '1095-B': 3, '1095-C': 4,
    '1098-Mortgage': 5, '1098-T': 6, 'Property Tax': 7, '1098-Other': 8,
}

def get_form_priority(ftype: str, category: str) -> int:
    table = income_priorities if category == 'Income' else (
               expense_priorities if category == 'Expenses' else {})
    return table.get(ftype, max(table.values())+1 if table else 9999)

# ── Logging helper
def log_extraction(src: str, method: str, text: str):
    snippet = text[:200].replace('\n', ' ') + ('...' if len(text) > 200 else '')
    print(f"[{method}] {os.path.basename(src)} → '{snippet}'", file=sys.stderr, flush=True)

# ── OCR fallback
def ocr_page(path: str, page_index: int) -> str:
    try:
        opts = {'poppler_path': POPPLER_PATH} if POPPLER_PATH else {}
        images = convert_from_path(path, first_page=page_index+1, last_page=page_index+1, **opts)
        if not images:
            return ''
        text = pytesseract.image_to_string(images[0])
        log_extraction(path, 'OCR', text)
        return text
    except Exception:
        print(f"OCR failed for {path} p{page_index+1}", file=sys.stderr)
        traceback.print_exc()
        return ''

# ── Tiered text extraction: PDFMiner → PyPDF2 → OCR
def extract_text_safe(path: str, page_index: int) -> str:
    text = ''
    # 1) Try PDFMiner for layout-preserved text
    try:
        text = pdfminer_extract(path, page_numbers=[page_index]) or ''
        log_extraction(path, 'PDFMiner', text)
    except Exception:
        print(f"PDFMiner error at {path} p{page_index+1}", file=sys.stderr)
        traceback.print_exc()
        text = ''
    # If PDFMiner text is too short, try PyPDF2
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            reader = PdfReader(path)
            page = reader.pages[page_index]
            p_text = page.extract_text() or ''
            log_extraction(path, 'PyPDF2', p_text)
            text = p_text or text
        except Exception:
            print(f"PyPDF2 error at {path} p{page_index+1}", file=sys.stderr)
            traceback.print_exc()
    # If still too short or empty, fallback to OCR
    if len(text.strip()) < OCR_MIN_CHARS:
        text = ocr_page(path, page_index)
    return text

# ── Classification rules
def classify_text(text: str) -> Tuple[str, str]:
    t = text.lower()
    lower = text.lower()
     # If page matches any instruction patterns, classify as Others → Unused
    instruction_patterns = [
        # W2 instructions
        "box 1. enter this amount on the wages line of your tax return",
        "box 2. enter this amount on the federal income tax withheld line",
        "box 5. you may be required to report this amount on form 8959",
        "box 6. this amount includes the 1.45% medicare tax withheld",
        "box 8. this amount is not included in box 1, 3, 5, or 7",
        "you must file form 4137",
        "box 10. this amount includes the total dependent care benefits"
        "instructions for form 8949",
        "regulations section 1.6045-1",
        "recipient's taxpayer identification number",
        "fata filing requirement",
        "payer’s routing transit number",
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
        "boxes 15-17. state tax withheld"
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
        "future developments. for the latest information about developments related to form 1098-t"
    
    ]
    for pat in instruction_patterns:
        if pat in lower:
            return "Others", "Unused"

    if 'w-2' in t or 'w2' in t: return 'Income', 'W-2'
    if '1099-int' in t or 'interest income' in t: return 'Income', '1099-INT'
    if '1099-div' in t: return 'Income', '1099-DIV'
    if '1098' in t and 'mortgage' in t: return 'Expenses', '1098-Mortgage'
    if '1098-t' in t: return 'Expenses', '1098-T'
    if 'property tax' in t: return 'Expenses', 'Property Tax'
    if '1098' in t: return 'Expenses', '1098-Other'
    if '1099' in t: return 'Income', '1099-Other'
    return 'Unknown', 'Unused'

# ── Group helper
def group_by_type(entries: List[Tuple[str,int,str]]) -> Dict[str, List[Tuple[str,int,str]]]:
    d = defaultdict(list)
    for e in entries: d[e[2]].append(e)
    return d

# ── Merge + bookmarks + cleanup
def merge_with_bookmarks(input_dir: str, output_pdf: str):
    # Prevent storing merged file inside input_dir
    abs_input = os.path.abspath(input_dir)
    abs_output = os.path.abspath(output_pdf)
    if abs_output.startswith(abs_input + os.sep):
        abs_output = os.path.join(os.path.dirname(abs_input), os.path.basename(abs_output))
        print(f"Moved output outside upload folder: {abs_output}", file=sys.stderr)

    # Collect PDFs excluding any pre-existing output
    name_out = os.path.basename(abs_output)
    files = sorted(f for f in os.listdir(input_dir)
                   if f.lower().endswith('.pdf') and f != name_out)
    print(f"Merging {len(files)} PDFs...", file=sys.stderr)

    income, expenses, others = [], [], []
    for fname in files:
        path = os.path.join(input_dir, fname)
        try:
            total = len(PdfReader(path).pages)
        except Exception:
            print(f"Unreadable PDF: {fname}", file=sys.stderr)
            continue
        for i in range(total):
            text = extract_text_safe(path, i)
            print("" + "="*50, file=sys.stderr)
            print(f"📄 {fname} p{i+1} → {text or '[NO TEXT]'}", file=sys.stderr)
            print("" + "="*50, file=sys.stderr)
            cat, ftype = classify_text(text)
            entry = (path, i, ftype)
            if cat=='Income':    income.append(entry)
            elif cat=='Expenses': expenses.append(entry)
            else:                others.append(entry)

    # Sort
    income.sort(key=lambda e:(get_form_priority(e[2],'Income'), e[0], e[1]))
    expenses.sort(key=lambda e:(get_form_priority(e[2],'Expenses'), e[0], e[1]))

    merger = PdfMerger()
    page_num = 0
    def append_and_bookmark(entry, parent, title):
        nonlocal page_num
        p, idx, _ = entry
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            w = PdfWriter()
            try:
                w.add_page(PdfReader(p).pages[idx])
                w.write(tmp)
            except Exception:
                print(f"Temp write failed: {p} p{idx+1}", file=sys.stderr)
                traceback.print_exc()
            tmp_path = tmp.name
        with open(tmp_path,'rb') as fh:
            merger.append(fileobj=fh)
        os.unlink(tmp_path)
        merger.add_outline_item(title, page_num, parent=parent)
        page_num += 1

    # Bookmarks
    if income:
        root = merger.add_outline_item('Income', page_num)
        for form, grp in group_by_type(income).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j,e in enumerate(grp,1):
                lbl = form if len(grp)==1 else f"{form}#{j}"
                append_and_bookmark(e, node, lbl)
    if expenses:
        root = merger.add_outline_item('Expenses', page_num)
        for form, grp in group_by_type(expenses).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j,e in enumerate(grp,1):
                lbl = form if len(grp)==1 else f"{form}#{j}"
                append_and_bookmark(e, node, lbl)
    if others:
        root = merger.add_outline_item('Others', page_num)
        node = merger.add_outline_item('Unused', page_num, parent=root)
        for j,e in enumerate(others,1):
            lbl = 'Unused' if len(others)==1 else f"Unused#{j}"
            append_and_bookmark(e, node, lbl)

    # Write merged output
    os.makedirs(os.path.dirname(abs_output), exist_ok=True)
    with open(abs_output,'wb') as f:
        merger.write(f)
    merger.close()
    print(f"Merged PDF created at {abs_output}", file=sys.stderr)0

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




    22-06-2025 19:5
   import sys, os, io, tempfile
import traceback
from collections import defaultdict
from typing import Dict, List, Tuple
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
from pdfminer.high_level import extract_text as pdfminer_extract
from pdfminer.layout import LAParams
import pytesseract
from pdf2image import convert_from_path
import pdfplumber
from pdf2image import convert_from_path
import fitz # PyMuPDF

# ── Unicode console on Windows
def configure_unicode():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
configure_unicode()

# ── Configuration
POPPLER_PATH = os.environ.get("POPPLER_PATH")  # e.g. "C:\\poppler\\Library\\bin"
OCR_MIN_CHARS = 50
PDFMINER_LA_PARAMS = LAParams(line_margin=0.2, char_margin=2.0)

# ── Priority tables
income_priorities = {
    'W-2': 1, '1099-NEC': 2, '1099-PATR': 3, '1099-MISC': 4,
    '1099-OID': 5, '1099-G': 6, 'W-2G': 7, '1065': 8, '1120-S': 9,
    '1041': 10, '1099-INT': 11, '1099-DIV': 12, '1099-R': 13,
    '1099-Q': 14, 'K-1': 15, '1099-Other': 16,
}
expense_priorities = {
    '5498-SA': 1, '1095-A': 2, '1095-B': 3, '1095-C': 4,
    '1098-Mortgage': 5, '1098-T': 6, 'Property Tax': 7, '1098-Other': 8,
}

def get_form_priority(ftype: str, category: str) -> int:
    table = income_priorities if category=='Income' else (
            expense_priorities if category=='Expenses' else {})
    return table.get(ftype, max(table.values())+1 if table else 9999)

# ── Logging helper
def log_extraction(src: str, method: str, text: str):
    snippet = text[:200].replace('\n', ' ') + ('...' if len(text) > 200 else '')
    print(f"[{method}] {os.path.basename(src)} → '{snippet}'", file=sys.stderr, flush=True)


# ── Tiered text extraction: PDFMiner → pdfplumber → PyPDF2 → OCR
# ── Tiered text extraction
def extract_text(path: str, page_index: int) -> str:
    text = ''
    # 1) PDFMiner for layout-preserved text
    try:
        text = pdfminer_extract(path, page_numbers=[page_index], laparams=PDFMINER_LA_PARAMS)
    except Exception:
        traceback.print_exc()
    if len(text.strip()) < OCR_MIN_CHARS:
        # 2) pdfplumber for table-friendly text
        try:
            with pdfplumber.open(path) as pdf:
                page = pdf.pages[page_index]
                t2 = page.extract_text(x_tolerance=1, y_tolerance=1)
                if t2 and len(t2.strip()) > len(text):
                    text = t2
        except Exception:
            traceback.print_exc()
    if len(text.strip()) < OCR_MIN_CHARS:
        # 3) PyPDF2 fallback
        try:
            reader = PdfReader(path)
            page = reader.pages[page_index]
            t3 = page.extract_text() or ''
            if len(t3.strip()) > len(text):
                text = t3
        except Exception:
            traceback.print_exc()
    if len(text.strip()) < OCR_MIN_CHARS:
        # 4) OCR fallback
        try:
            opts = {'poppler_path': POPPLER_PATH} if POPPLER_PATH else {}
            img = convert_from_path(path, first_page=page_index+1, last_page=page_index+1, **opts)[0]
            text = pytesseract.image_to_string(img, config='--psm 6')
        except Exception:
            traceback.print_exc()
    return text

# ── Classification rules
def classify_text(text: str) -> Tuple[str, str]:
    t = text.lower()
    lower = text.lower()
     # If page matches any instruction patterns, classify as Others → Unused
    instruction_patterns = [
        # W2 instructions
        "box 1. enter this amount on the wages line of your tax return",
        "box 2. enter this amount on the federal income tax withheld line",
        "box 5. you may be required to report this amount on form 8959",
        "box 6. this amount includes the 1.45% medicare tax withheld",
        "box 8. this amount is not included in box 1, 3, 5, or 7",
        "you must file form 4137",
        "box 10. this amount includes the total dependent care benefits"
        "instructions for form 8949",
        "regulations section 1.6045-1",
        "recipient's taxpayer identification number",
        "fata filing requirement",
        "payer’s routing transit number",
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
        "boxes 15-17. state tax withheld"
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
        "future developments. for the latest information about developments related to form 1098-t"
    
    ]
    for pat in instruction_patterns:
        if pat in lower:
            return "Others", "Unused"

    if 'w-2' in t or 'w2' in t: return 'Income', 'W-2'
    if '1099-int' in t or 'interest income' in t: return 'Income', '1099-INT'
    if '1099-div' in t: return 'Income', '1099-DIV'
    if '1098' in t and 'mortgage' in t: return 'Expenses', '1098-Mortgage'
    if '1098-t' in t: return 'Expenses', '1098-T'
    if 'property tax' in t: return 'Expenses', 'Property Tax'
    if '1098' in t: return 'Expenses', '1098-Other'
    if '1099' in t: return 'Income', '1099-Other'
    return 'Unknown', 'Unused'

# ── Group helper
def group_by_type(entries: List[Tuple[str,int,str]]) -> Dict[str, List[Tuple[str,int,str]]]:
    d = defaultdict(list)
    for e in entries: d[e[2]].append(e)
    return d

# ── Merge + bookmarks + cleanup
def merge_with_bookmarks(input_dir: str, output_pdf: str):
    # Prevent storing merged file inside input_dir
    abs_input = os.path.abspath(input_dir)
    abs_output = os.path.abspath(output_pdf)
    if abs_output.startswith(abs_input + os.sep):
        abs_output = os.path.join(os.path.dirname(abs_input), os.path.basename(abs_output))
        print(f"Moved output outside upload folder: {abs_output}", file=sys.stderr)

    # Collect PDFs excluding any pre-existing output
    name_out = os.path.basename(abs_output)
    files = sorted(f for f in os.listdir(input_dir)
                   if f.lower().endswith('.pdf') and f != name_out)
    print(f"Merging {len(files)} PDFs...", file=sys.stderr)

    income, expenses, others = [], [], []
    for fname in files:
        path = os.path.join(input_dir, fname)
        try:
            total = len(PdfReader(path).pages)
        except Exception:
            print(f"Unreadable PDF: {fname}", file=sys.stderr)
            continue
        for i in range(total):
            text = extract_text(path, i)
            print("" + "="*50, file=sys.stderr)
            print(f"📄 {fname} p{i+1} → {text or '[NO TEXT]'}", file=sys.stderr)
            print("" + "="*50, file=sys.stderr)
            cat, ftype = classify_text(text)
            entry = (path, i, ftype)
            if cat=='Income':    income.append(entry)
            elif cat=='Expenses': expenses.append(entry)
            else:                others.append(entry)

    # Sort
    income.sort(key=lambda e:(get_form_priority(e[2],'Income'), e[0], e[1]))
    expenses.sort(key=lambda e:(get_form_priority(e[2],'Expenses'), e[0], e[1]))
    # merge & bookmarks
    merger = PdfMerger()
    page_num = 0
    def append_and_bookmark(entry, parent, title):
        nonlocal page_num
        p, idx, _ = entry
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            w = PdfWriter()
            try:
                w.add_page(PdfReader(p).pages[idx])
                w.write(tmp)
            except Exception:
                print(f"Temp write failed: {p} p{idx+1}", file=sys.stderr)
                traceback.print_exc()
            tmp_path = tmp.name
        with open(tmp_path,'rb') as fh:
            merger.append(fileobj=fh)
        os.unlink(tmp_path)
        merger.add_outline_item(title, page_num, parent=parent)
        page_num += 1

    # Bookmarks
    if income:
        root = merger.add_outline_item('Income', page_num)
        for form, grp in group_by_type(income).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j,e in enumerate(grp,1):
                lbl = form if len(grp)==1 else f"{form}#{j}"
                append_and_bookmark(e, node, lbl)
    if expenses:
        root = merger.add_outline_item('Expenses', page_num)
        for form, grp in group_by_type(expenses).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j,e in enumerate(grp,1):
                lbl = form if len(grp)==1 else f"{form}#{j}"
                append_and_bookmark(e, node, lbl)
    if others:
        root = merger.add_outline_item('Others', page_num)
        node = merger.add_outline_item('Unused', page_num, parent=root)
        for j,e in enumerate(others,1):
            lbl = 'Unused' if len(others)==1 else f"Unused#{j}"
            append_and_bookmark(e, node, lbl)

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
  


    27-06-2025  

# ── Tiered text extraction: PDFMiner → pdfplumber → PyPDF2 → OCR
# ── Tiered text extraction
def extract_text(path: str, page_index: int) -> str:
    text = ""
    # 1) PyMuPDF
    try:
        doc = fitz.open(path)
        page = doc.load_page(page_index)
        text = page.get_text("text") or ""
        doc.close()
        log_extraction(path, "PyMuPDF", text)
    except Exception:
        traceback.print_exc()
    # 2) PDFMiner
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            t2 = pdfminer_extract(path, page_numbers=[page_index], laparams=PDFMINER_LA_PARAMS) or ""
            log_extraction(path, "PDFMiner", t2)
            if len(t2.strip()) > len(text):
                text = t2
        except Exception:
            traceback.print_exc()
    # 3) pdfplumber
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            with pdfplumber.open(path) as pdf:
                t3 = pdf.pages[page_index].extract_text() or ""
            log_extraction(path, "pdfplumber", t3)
            if len(t3.strip()) > len(text):
                text = t3
        except Exception:
            traceback.print_exc()
    # 4) PyPDF2
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            reader = PdfReader(path)
            t4 = reader.pages[page_index].extract_text() or ""
            log_extraction(path, "PyPDF2", t4)
            if len(t4.strip()) > len(text):
                text = t4
        except Exception:
            traceback.print_exc()
    # 5) Tesseract OCR
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            opts = {'poppler_path': POPPLER_PATH} if POPPLER_PATH else {}
            img = convert_from_path(path, first_page=page_index+1, last_page=page_index+1, **opts)[0]
            t5 = pytesseract.image_to_string(img, config="--psm 6") or ""
            log_extraction(path, "Tesseract", t5)
            if len(t5.strip()) > len(text):
                text = t5
        except Exception:
            traceback.print_exc()
    return text    




    27-06-2025   20:12 
    def print_w2_summary(info: Dict[str,str]):
    print("\n=== W-2 Summary ===\n")
    print("Employer information (Name, address, EIN):")
    print("Employer information (Name, address, EIN):")
    print("Employer information (Name, address, EIN):")
    print("Employer information (Name, address, EIN):")
    print("Employer information (Name, address, EIN):")
    print("Employer information (Name, address, EIN):")
    print("Employer information (Name, address, EIN):")
    print("Employer information (Name, address, EIN):")
    print("Employer information (Name, address, EIN):")
    print("Employer information (Name, address, EIN):")
    print(f"• {info['employer_name']}, {info['employer_address']} (EIN: {info['ein']})\n")
    print("Employee information:")
    print(f"• {info['employee_name']}, {info['employee_address']}")
    print(f"• SSN: {info['ssn']}\n")
    print("Wage and tax details:\n")
    print(f"Wages, tips, other compensation: {info['wages']}")
    print(f"Federal income tax withheld: {info['fed_tax']}")
    print(f"Social Security wages: {info['ss_wages']} / tax withheld {info['ss_tax']}")
    print(f"Medicare wages and tips: {info['med_wages']} / tax withheld {info['med_tax']}")
    print(f"State ({info['state_code']}) wages/tax: {info['state_wages']} / {info['state_tax']} (State ID {info['state_id']})")
    print("\n===================\n")

-----------------------------------------------------------------------------------------------------------------------------

# reading the w2 employer num_pages
#!/usr/bin/env python3
import sys, os, io, tempfile, traceback, re
from collections import defaultdict
from typing import Dict, List, Tuple

from PyPDF2 import PdfMerger, PdfReader, PdfWriter
from pdfminer.high_level import extract_text as pdfminer_extract
from pdfminer.layout import LAParams
import pytesseract
from pdf2image import convert_from_path
import fitz  # PyMuPDF

# ── Unicode console on Windows
def configure_unicode():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
configure_unicode()

# ── Configuration
POPPLER_PATH = os.environ.get("POPPLER_PATH")  # e.g. "C:\\poppler\\Library\\bin"
OCR_MIN_CHARS = 50
PDFMINER_LA_PARAMS = LAParams(line_margin=0.2, char_margin=2.0)

# ── Priority tables
income_priorities = {
    'W-2': 1, '1099-NEC': 2, '1099-PATR': 3, '1099-MISC': 4,
    '1099-OID': 5, '1099-G': 6, 'W-2G': 7, '1065': 8, '1120-S': 9,
    '1041': 10, '1099-INT': 11, '1099-DIV': 12, '1099-R': 13,
    '1099-Q': 14, 'K-1': 15, '1099-Other': 16,
}
expense_priorities = {
    '5498-SA': 1, '1095-A': 2, '1095-B': 3, '1095-C': 4,
    '1098-Mortgage': 5, '1098-T': 6, 'Property Tax': 7, '1098-Other': 8,
}

def get_form_priority(ftype: str, category: str) -> int:
    table = income_priorities if category=='Income' else (
            expense_priorities if category=='Expenses' else {})
    return table.get(ftype, max(table.values())+1 if table else 9999)

# ── Logging helper
def log_extraction(src: str, method: str, text: str):
    snippet = text[:200].replace('\n',' ') + ('...' if len(text)>200 else '')
    print(f"[{method}] {os.path.basename(src)} → '{snippet}'", file=sys.stderr, flush=True)

# ── Tiered text extraction
def extract_text(path: str, page_index: int) -> str:
    text = ""
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            reader = PdfReader(path)
            t4 = reader.pages[page_index].extract_text() or ""
            log_extraction(path, "PyPDF2", t4)
            if len(t4.strip()) > len(text):
                text = t4
        except Exception:
            traceback.print_exc()
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            opts = {'poppler_path': POPPLER_PATH} if POPPLER_PATH else {}
            img = convert_from_path(path, first_page=page_index+1, last_page=page_index+1, **opts)[0]
            t5 = pytesseract.image_to_string(img, config="--psm 6") or ""
            log_extraction(path, "Tesseract", t5)
            if len(t5.strip()) > len(text):
                text = t5
        except Exception:
            traceback.print_exc()
    return text
# ── Classification rules
def classify_text(text: str) -> Tuple[str, str]:
    t = text.lower()
    lower = text.lower()
     # If page matches any instruction patterns, classify as Others → Unused
    instruction_patterns = [
        # W2 instructions
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
        "boxes 15-17. state tax withheld"
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
        "future developments. for the latest information about developments related to form 1098-t"
    
    ]
    for pat in instruction_patterns:
        if pat in lower:
            return "Others", "Unused"

    if 'w-2' in t or 'w2' in t: return 'Income', 'W-2'
    if '1099-int' in t or 'interest income' in t: return 'Income', '1099-INT'
    if '1099-div' in t: return 'Income', '1099-DIV'
    if '1098' in t and 'mortgage' in t: return 'Expenses', '1098-Mortgage'
    if '1098-t' in t: return 'Expenses', '1098-T'
    if 'property tax' in t: return 'Expenses', 'Property Tax'
    if '1098' in t: return 'Expenses', '1098-Other'
    if '1099' in t: return 'Income', '1099-Other'
    if 'donation' in t: return 'Expenses', 'Donation'
    return 'Unknown', 'Unused'

# ── Parse out W-2 fields
def parse_w2(text: str) -> Dict[str,str]:
    m = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", text)
    ssn = m.group(1) if m else "N/A"
    m = re.search(r"\b(\d{2}-\d{7})\b", text)
    ein = m.group(1) if m else "N/A"
    lines = text.splitlines()
    employer_name = employer_addr = "N/A"
    for i, L in enumerate(lines):
        if "Employer" in L and "name" in L:
            Low = L.lower()
            chunk = lines[i+1:i+3]
            if len(chunk)>=1: employer_name = chunk[0].strip()
            if len(chunk)>=2: employer_addr  = chunk[1].strip()
            break
    employee_name = employee_addr = "N/A"
    for i, L in enumerate(lines):
        if "Employee" in L and "name" in L:
            chunk = lines[i+1:i+3]
            if len(chunk)>=1: employee_name = chunk[0].strip()
            if len(chunk)>=2: employee_addr  = chunk[1].strip()
            break
    return {
        'ssn': ssn, 'ein': ein,
        'employer_name': employer_name, 'employer_address': employer_addr,
        'employee_name': employee_name, 'employee_address': employee_addr
    }

# ── Print summary
def print_w2_summary(info: Dict[str,str]):
    print("\n=== W-2 Summary ===\n")
    print("Employer information (Name, address, EIN):")
    print(f"• {info['employer_name']}, {info['employer_address']} (EIN: {info['ein']})\n")
    print("Employee information:")
    print(f"• {info['employee_name']}, {info['employee_address']}")
    print(f"• SSN: {info['ssn']}\n")
    print("\n===================\n")

# ── Group helper
def group_by_type(entries: List[Tuple[str,int,str]]) -> Dict[str,List[Tuple[str,int,str]]]:
    d = defaultdict(list)
    for e in entries: d[e[2]].append(e)
    return d

# ── Merge + bookmarks + summary printing
def merge_with_bookmarks(input_dir: str, output_pdf: str):
    abs_input  = os.path.abspath(input_dir)
    abs_output = os.path.abspath(output_pdf)
    if abs_output.startswith(abs_input + os.sep):
        abs_output = os.path.join(os.path.dirname(abs_input), os.path.basename(abs_output))
        print(f"Moved output outside upload folder: {abs_output}", file=sys.stderr)

    files = sorted(f for f in os.listdir(input_dir)
                   if f.lower().endswith('.pdf') and f!=os.path.basename(abs_output))
    print(f"Merging {len(files)} PDFs...", file=sys.stderr)

    income, expenses, others = [], [], []
    w2_titles = {}  # map (path, page) to employer name for W-2

    for fname in files:
        path = os.path.join(input_dir, fname)
        try:
            total = len(PdfReader(path).pages)
        except Exception:
            print(f"Unreadable PDF: {fname}", file=sys.stderr)
            continue
        for i in range(total):
            text = extract_text(path, i)
            cat, ftype = classify_text(text)
            if cat=='Income' and ftype=='W-2':
                info = parse_w2(text)
                w2_titles[(path, i)] = info['employer_name']
                print_w2_summary(info)
            entry = (path, i, ftype)
            if cat=='Income':    income.append(entry)
            elif cat=='Expenses':expenses.append(entry)
            else:                others.append(entry)

    income.sort(key=lambda e:(get_form_priority(e[2],'Income'), e[0], e[1]))
    expenses.sort(key=lambda e:(get_form_priority(e[2],'Expenses'), e[0], e[1]))

    merger = PdfMerger()
    page_num = 0
    def append_and_bookmark(entry, parent, title):
        nonlocal page_num
        p, idx, _ = entry
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            w = PdfWriter(); w.add_page(PdfReader(p).pages[idx]); w.write(tmp)
            tmp_path = tmp.name
        with open(tmp_path,'rb') as fh: merger.append(fileobj=fh)
        os.unlink(tmp_path)
        merger.add_outline_item(title, page_num, parent=parent)
        page_num += 1

    if income:
        root = merger.add_outline_item('Income', page_num)
        for form, grp in group_by_type(income).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, e in enumerate(grp,1):
                p, idx, _ = e
                if form=='W-2': lbl = w2_titles.get((p,idx), 'W-2')
                else: lbl = form if len(grp)==1 else f"{form}#{j}"
                append_and_bookmark(e, node, lbl)
    if expenses:
        root = merger.add_outline_item('Expenses', page_num)
        for form, grp in group_by_type(expenses).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j,e in enumerate(grp,1):
                lbl = form if len(grp)==1 else f"{form}#{j}"
                append_and_bookmark(e, node, lbl)
    if others:
        root = merger.add_outline_item('Others', page_num)
        node = merger.add_outline_item('Unused', page_num, parent=root)
        for j,e in enumerate(others,1):
            lbl = 'Unused' if len(others)==1 else f"Unused#{j}"
            append_and_bookmark(e, node, lbl)

    os.makedirs(os.path.dirname(abs_output), exist_ok=True)
    with open(abs_output,'wb') as f: merger.write(f)
    merger.close()
    print(f"Merged PDF created at {abs_output}", file=sys.stderr)

    for fname in files:
        try: os.remove(os.path.join(input_dir, fname))
        except: pass

# ── CLI
if __name__=='__main__':
    import argparse
    p = argparse.ArgumentParser(description="Merge PDFs with robust text extraction, W-2 summaries, and employer bookmarks")
    p.add_argument('input_dir', help="Folder containing PDFs to merge")
    p.add_argument('output_pdf', help="Path for the merged PDF (outside input_dir)")
    args = p.parse_args()
    merge_with_bookmarks(args.input_dir, args.output_pdf)



# ── Parse out W-2 fields
def parse_w2(text: str) -> Dict[str,str]:
    m = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", text)
    ssn = m.group(1) if m else "N/A"
    m = re.search(r"\b(\d{2}-\d{7})\b", text)
    ein = m.group(1) if m else "N/A"
    lines = text.splitlines()
    employer_name = employer_addr = "N/A"
    for i, L in enumerate(lines):
        if "Employer" in L and "name" in L:
            Low = L.lower()
            chunk = lines[i+1:i+3]
            if len(chunk)>=1: employer_name = chunk[0].strip()
            if len(chunk)>=2: employer_addr  = chunk[1].strip()
            break
    employee_name = employee_addr = "N/A"
    for i, L in enumerate(lines):
        if "Employee" in L and "name" in L:
            chunk = lines[i+1:i+3]
            if len(chunk)>=1: employee_name = chunk[0].strip()
            if len(chunk)>=2: employee_addr  = chunk[1].strip()
            break
    return {
        'ssn': ssn, 'ein': ein,
        'employer_name': employer_name, 'employer_address': employer_addr,
        'employee_name': employee_name, 'employee_address': employee_addr
    }

# ── Print summary
def print_w2_summary(info: Dict[str,str]):
    print("\n=== W-2 Summary ===\n")
    print("Employer information (Name, address, EIN):")
    print(f"• {info['employer_name']}, {info['employer_address']} (EIN: {info['ein']})\n")
    print("Employee information:")
    print(f"• {info['employee_name']}, {info['employee_address']}")
    print(f"• SSN: {info['ssn']}\n")
    print("\n===================\n")



    const express = require('express');
    const multer = require('multer');
    const cors = require('cors');
    const { spawn } = require('child_process');
    const fs = require('fs');
    const path = require('path');
    
    const app = express();
    const PORT = process.env.PORT || 3001;
    
    //const PORT = process.env.PORT || 3001;
    app.use(cors());
    app.use(express.static('public')); 
    
    //const upload = multer({ dest: 'uploads/' }); replaced this code with 16 -- 25 code
    // To fix the PDF corruption issue,
    // Fixed: Storage config with proper filename formatting 
    const storage = multer.diskStorage({
      destination: function (req,file, cd){
        cd(null, 'uploads/');
      },
      filename: function (req, file, cd){
        //const originalExt = path.extname(file.originalname) || '.pdf'; // Default to .pdf 
    const safeName = `${Date.now()}-${file.originalname}`;
    
        cd(null, safeName);
      }
    })
    
    const upload = multer({ storage: storage });
    
    app.post('/merge', upload.array('pdfs'), (req, res) => {
      const inputDir = 'uploads';
      const outputPath = path.join('merged', `merged_${Date.now()}.pdf`);
    
      //  Log uploaded files (optional, for debugging)
      console.log("Uploaded files:");
      req.files.forEach(file => {
        console.log(file.path);
      });
      
      const pythonPath = 'C:\\Python312\\python.exe';
      const python = spawn('python', ['merge_with_bookmarks.py', inputDir, outputPath]);
    
      python.stdout.on('data', data => {
        console.log(`[PY-OUT] ${data}`.trim());
      });
      python.stderr.on('data', data => {
        console.error(`[PY-ERR] ${data}`.trim());
      });
    
    
      python.on('close', (code) => {
        if (code === 0) {
          res.download(outputPath, () => {
            // Cleanup
            //fs.readdirSync(inputDir).forEach(file => fs.unlinkSync(path.join(inputDir, file)));
            //fs.unlinkSync(outputPath);
          });
        } else {
          res.status(500).send('Failed to merge PDFs with bookmarks');
        }
      });
    }
    
    );
    
    app.post('/merge', upload.array('pdfs'), (req, res) => {
      console.log("Uploaded files:");
      req.files.forEach(file => {
        console.log(file.path); // This is safe here
      });
    
      // ... rest of your code
    });
    
    
    app.listen(PORT, () => {
      console.log(`Server is running at http://localhost:${PORT}`);
    });
    
    




    3

def merge_with_bookmarks(input_dir: str, output_pdf: str):
    abs_in = os.path.abspath(input_dir)
    abs_out= os.path.abspath(output_pdf)
    if abs_out.startswith(abs_in+os.sep): abs_out = os.path.join(os.path.dirname(abs_in),os.path.basename(abs_out)); logger.warning(f"Moved output outside: {abs_out}")
    files=sorted(f for f in os.listdir(input_dir) if f.lower().endswith(('.pdf','.png','.jpg','.jpeg','.tiff')) and f!=os.path.basename(abs_out))
    logger.info(f"Found {len(files)} files in {input_dir}")
    income,expenses,others=[],[],[]
    w2_titles={}  # (path,page)->label
    for fname in files:
        path=os.path.join(input_dir,fname)
        if fname.lower().endswith('.pdf'):
            total=len(PdfReader(path).pages)
            for i in range(total):
                print(f"\n=== {fname} Page {i+1} ===")
                # extract via each method
                extracts={}
                # PDFMiner
                try: extracts['PDFMiner']=pdfminer_extract(path,page_numbers=[i],laparams=PDFMINER_LA_PARAMS) or ""
                except: extracts['PDFMiner']=''
                # PyPDF2
                try: extracts['PyPDF2']=PdfReader(path).pages[i].extract_text() or ""
                except: extracts['PyPDF2']=''
                # Tesseract
                try:
                    img=convert_from_path(path,first_page=i+1,last_page=i+1,poppler_path=POPPLER_PATH or None)[0]
                    extracts['Tesseract']=pytesseract.image_to_string(img,config="--psm 6") or ""
                except: extracts['Tesseract']=''
                # Full PDF
                extracts['FullPDF']=extract_text_from_pdf(path)
                # pdfplumber
                try:
                    with pdfplumber.open(path) as pdf:
                        extracts['pdfplumber']=pdf.pages[i].extract_text() or ""
                except: extracts['pdfplumber']=''
                # PyMuPDF
                try:
                    doc=fitz.open(path)
                    extracts['PyMuPDF']=doc.loadPage(i).get_text()
                    doc.close()
                except: extracts['PyMuPDF']=''
                # print each
                for mnm,txt in extracts.items():
                    print(f"--- {mnm} Extract ---")
                    print(txt)
                # collect employer names
                info_by_method={}
                names=[]
                for mnm,txt in extracts.items():
                    cat,ft=classify_text(txt)
                    if cat=='Income' and ft=='W-2':
                        info=parse_w2(txt)
                        if info and info['employer_name']!='N/A':
                            info_by_method[mnm]=info
                            names.append(info['employer_name'])
                if names:
                    common=Counter(names).most_common(1)[0][0]
                    # pick first method with this name
                    chosen_method=next(m for m,nm in info_by_method.items() if nm['employer_name']==common)
                    chosen_info=info_by_method[chosen_method]
                    print(f"--- Chosen employer ({chosen_method}): {common} ---")
                    print_w2_summary(chosen_info)
                    w2_titles[(path,i)]=common
                # classification for grouping
                tiered=extract_text(path,i)
                cat,ft=classify_text(tiered)
                entry=(path,i,ft)
                if cat=='Income': income.append(entry)
                elif cat=='Expenses': expenses.append(entry)
                else: others.append(entry)
        else:
            # image
            print(f"\n=== Image {fname} ===")
            oi=extract_text_from_image(path)
            print("--- OCR Image ---")
            print(oi)
            cat,ft=classify_text(oi)
            entry=(path,0,ft)
            if cat=='Income': income.append(entry)
            elif cat=='Expenses': expenses.append(entry)
            else: others.append(entry)
    # sort
    income.sort(key=lambda e:(get_form_priority(e[2],'Income'),e[0],e[1]))
    expenses.sort(key=lambda e:(get_form_priority(e[2],'Expenses'),e[0],e[1]))



    ----------------=================-=-=--------------------------------------------====================
    #!/usr/bin/env python3
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
    snippet = text[:200].replace('\n',' ') + ('...' if len(text)>200 else '')
    logger.info(f"[{method}] {os.path.basename(src)} → '{snippet}'")

# ── Tiered text extraction for PDF pages
def extract_text(path: str, page_index: int) -> str:
    text = ""
    # PDFMiner
    try:
        t1 = pdfminer_extract(path, page_numbers=[page_index], laparams=PDFMINER_LA_PARAMS) or ""
        log_extraction(path, "PDFMiner", t1)
        if len(t1.strip()) > len(text): text = t1
    except Exception:
        traceback.print_exc()
    # PyPDF2 fallback
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            reader = PdfReader(path)
            t2 = reader.pages[page_index].extract_text() or ""
            log_extraction(path, "PyPDF2", t2)
            if len(t2.strip()) > len(text): text = t2
        except Exception:
            traceback.print_exc()
    # OCR fallback
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            opts = {'poppler_path': POPPLER_PATH} if POPPLER_PATH else {}
            img = convert_from_path(path, first_page=page_index+1, last_page=page_index+1, **opts)[0]
            t3 = pytesseract.image_to_string(img, config="--psm 6") or ""
            log_extraction(path, "Tesseract", t3)
            if len(t3.strip()) > len(text): text = t3
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
                    text += f"\n--- Page {i+1} ---\n" + pt
                    logger.info(f"Full PDF Page {i+1} text: {pt[:100]}...")
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
        if et.strip(): text = f"\n--- OCR Image {os.path.basename(file_path)} ---\n" + et; logger.info(f"Image OCR {file_path}: {et[:100]}...")
        else: text = f"No text in image: {os.path.basename(file_path)}"
    except Exception as e:
        logger.error(f"Error OCR image {file_path}: {e}")
        text = f"Error OCR image: {e}"
    return text

def classify_text(text: str) -> Tuple[str, str]:
    t = text.lower()
    lower = text.lower()
     # If page matches any instruction patterns, classify as Others → Unused
    instruction_patterns = [
        # W2 instructions
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
        "boxes 15-17. state tax withheld"
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
        "future developments. for the latest information about developments related to form 1098-t"
    
    ]
    for pat in instruction_patterns:
        if pat in lower:
            return "Others", "Unused"

    if 'w-2' in t or 'w2' in t: return 'Income', 'W-2'
    if '1099-int' in t or 'interest income' in t: return 'Income', '1099-INT'
    if '1099-div' in t: return 'Income', '1099-DIV'
    if '1098' in t and 'mortgage' in t: return 'Expenses', '1098-Mortgage'
    if '1098-t' in t: return 'Expenses', '1098-T'
    if 'property tax' in t: return 'Expenses', 'Property Tax'
    if '1098' in t: return 'Expenses', '1098-Other'
    if '1099' in t: return 'Income', '1099-Other'
    if 'donation' in t: return 'Expenses', 'Donation'
    return 'Unknown', 'Unused'

# ── Parse W-2 fields
def parse_w2(text: str) -> Dict[str,str]:
    m = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", text)
    ssn = m.group(1) if m else "N/A"
    m = re.search(r"\b(\d{2}-\d{7})\b", text)
    ein = m.group(1) if m else "N/A"
    lines = text.splitlines()
    emp_name = emp_addr = "N/A"
    for i,L in enumerate(lines):
        if "Employer" in L and "name" in L:
            chk = lines[i+1:i+3]
            if chk: emp_name = chk[0].strip()
            if len(chk)>1: emp_addr = chk[1].strip()
            break
    return {'ssn':ssn,'ein':ein,'employer_name':emp_name,'employer_address':emp_addr,'employee_name':'N/A','employee_address':'N/A'}

def print_w2_summary(info: Dict[str,str]):
    print("\n=== W-2 Summary ===\n")
    print(f"Employer: {info['employer_name']}, Address: {info['employer_address']}, EIN: {info['ein']}")
    print("===================\n")

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

    files = sorted(
        f for f in os.listdir(abs_input)
        if f.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.tiff'))
        and f != os.path.basename(abs_output)
    )
    logger.info(f"Found {len(files)} files in {abs_input}")

    income, expenses, others = [], [], []
    w2_titles = {}

    for fname in files:
        path = os.path.join(abs_input, fname)
        if fname.lower().endswith('.pdf'):
            total = len(PdfReader(path).pages)
            for i in range(total):
                # ── New: print extraction header like in your past code
                print("=" * 50, file=sys.stderr)
                text = extract_text(path, i)
                print(f"📄 {fname} p{i+1} → {text or '[NO TEXT]'}", file=sys.stderr)
                print("=" * 50, file=sys.stderr)

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

                for method, txt in extracts.items():
                    print(f"--- {method} Extract ---", file=sys.stderr)
                    print(txt, file=sys.stderr)

                # Collect W-2 employer names across methods
                info_by_method, names = {}, []
                for method, txt in extracts.items():
                    cat, ft = classify_text(txt)
                    if cat == 'Income' and ft == 'W-2':
                        info = parse_w2(txt)
                        if info['employer_name'] != 'N/A':
                            info_by_method[method] = info
                            names.append(info['employer_name'])
                if names:
                    common = Counter(names).most_common(1)[0][0]
                    chosen = next(m for m,i in info_by_method.items() if i['employer_name'] == common)
                    print(f"--- Chosen employer ({chosen}): {common} ---", file=sys.stderr)
                    print_w2_summary(info_by_method[chosen])
                    w2_titles[(path, i)] = common

                # Classification & grouping
                tiered = extract_text(path, i)
                cat, ft = classify_text(tiered)
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
    def append_and_bookmark(entry, parent, title):
        nonlocal page_num
        p, idx, _ = entry
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            w = PdfWriter()
            try:
                w.add_page(PdfReader(p).pages[idx])
                w.write(tmp)
            except Exception:
                print(f"Temp write failed: {p} p{idx+1}", file=sys.stderr)
                traceback.print_exc()
            tmp_path = tmp.name
        with open(tmp_path,'rb') as fh:
            merger.append(fileobj=fh)
        os.unlink(tmp_path)
        merger.add_outline_item(title, page_num, parent=parent)
        page_num += 1

    # Bookmarks
    if income:
        root = merger.add_outline_item('Income', page_num)
        for form, grp in group_by_type(income).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j,e in enumerate(grp,1):
                lbl = form if len(grp)==1 else f"{form}#{j}"
                append_and_bookmark(e, node, lbl)
    if expenses:
        root = merger.add_outline_item('Expenses', page_num)
        for form, grp in group_by_type(expenses).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j,e in enumerate(grp,1):
                lbl = form if len(grp)==1 else f"{form}#{j}"
                append_and_bookmark(e, node, lbl)
    if others:
        root = merger.add_outline_item('Others', page_num)
        node = merger.add_outline_item('Unused', page_num, parent=root)
        for j,e in enumerate(others,1):
            lbl = 'Unused' if len(others)==1 else f"Unused#{j}"
            append_and_bookmark(e, node, lbl)

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
  



03-07-2025    17:12
#!/usr/bin/env python3
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

# ── Bracket regex
EMP_BRACKET_RE = re.compile(r"Employer's name, address, and ZIP code.*?\[(.*?)\]", re.IGNORECASE | re.DOTALL)

# ── Priority tables
income_priorities = {'W-2':1,'1099-NEC':2,'1099-PATR':3,'1099-MISC':4,'1099-OID':5,'1099-G':6,'W-2G':7,'1065':8,'1120-S':9,'1041':10,'1099-INT':11,'1099-DIV':12,'1099-R':13,'1099-Q':14,'K-1':15,'1099-Other':16}
expense_priorities = {'5498-SA':1,'1095-A':2,'1095-B':3,'1095-C':4,'1098-Mortgage':5,'1098-T':6,'Property Tax':7,'1098-Other':8}

def get_form_priority(ftype: str, category: str) -> int:
    table = income_priorities if category=='Income' else (expense_priorities if category=='Expenses' else {})
    return table.get(ftype, max(table.values())+1 if table else 9999)

# ── Logging helper
def log_extraction(src: str, method: str, text: str):
    snippet = text[:200].replace('\n',' ') + ('...' if len(text)>200 else '')
    logger.info(f"[{method}] {os.path.basename(src)} → '{snippet}'")

# ── Tiered text extraction for PDF pages
def extract_text(path: str, page_index: int) -> str:
    text = ""
    # PDFMiner
    try:
        t1 = pdfminer_extract(path, page_numbers=[page_index], laparams=PDFMINER_LA_PARAMS) or ""
        log_extraction(path, "PDFMiner", t1)
        if len(t1.strip()) > len(text): text = t1
    except Exception:
        traceback.print_exc()
    # PyPDF2 fallback
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            reader = PdfReader(path)
            t2 = reader.pages[page_index].extract_text() or ""
            log_extraction(path, "PyPDF2", t2)
            if len(t2.strip()) > len(text): text = t2
        except Exception:
            traceback.print_exc()
    # OCR fallback
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            opts = {'poppler_path': POPPLER_PATH} if POPPLER_PATH else {}
            img = convert_from_path(path, first_page=page_index+1, last_page=page_index+1, **opts)[0]
            t3 = pytesseract.image_to_string(img, config="--psm 6") or ""
            log_extraction(path, "Tesseract", t3)
            if len(t3.strip()) > len(text): text = t3
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
                    text += f"\n--- Page {i+1} ---\n" + pt
                    logger.info(f"Full PDF Page {i+1} text: {pt[:100]}...")
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
        if et.strip(): text = f"\n--- OCR Image {os.path.basename(file_path)} ---\n" + et; logger.info(f"Image OCR {file_path}: {et[:100]}...")
        else: text = f"No text in image: {os.path.basename(file_path)}"
    except Exception as e:
        logger.error(f"Error OCR image {file_path}: {e}")
        text = f"Error OCR image: {e}"
    return text

def classify_text(text: str) -> Tuple[str, str]:
    t = text.lower()
    lower = text.lower()
     # If page matches any instruction patterns, classify as Others → Unused
    instruction_patterns = [
        # W2 instructions
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
        "boxes 15-17. state tax withheld"
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
        "future developments. for the latest information about developments related to form 1098-t"
    
    ]
    for pat in instruction_patterns:
        if pat in lower:
            return "Others", "Unused"

    if 'w-2' in t or 'w2' in t: return 'Income', 'W-2'
    if '1099-int' in t or 'interest income' in t: return 'Income', '1099-INT'
    if '1099-div' in t: return 'Income', '1099-DIV'
    if '1098' in t and 'mortgage' in t: return 'Expenses', '1098-Mortgage'
    if '1098-t' in t: return 'Expenses', '1098-T'
    if 'property tax' in t: return 'Expenses', 'Property Tax'
    if '1098' in t: return 'Expenses', '1098-Other'
    if '1099' in t: return 'Income', '1099-Other'
    if 'donation' in t: return 'Expenses', 'Donation'
    return 'Unknown', 'Unused'

# ── Parse W-2 fields
def parse_w2(text: str) -> Dict[str,str]:
    m = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", text)
    ssn = m.group(1) if m else "N/A"
    m = re.search(r"\b(\d{2}-\d{7})\b", text)
    ein = m.group(1) if m else "N/A"
    lines = text.splitlines()
    emp_name = emp_addr = "N/A"
    for i,L in enumerate(lines):
        if "Employer" in L and "name" in L:
            chk = lines[i+1:i+3]
            if chk: emp_name = chk[0].strip()
            if len(chk)>1: emp_addr = chk[1].strip()
            break
    return {'ssn':ssn,'ein':ein,'employer_name':emp_name,'employer_address':emp_addr,'employee_name':'N/A','employee_address':'N/A'}

def print_w2_summary(info: Dict[str,str]):
    print("\n=== W-2 Summary ===\n")
    print(f"Employer: {info['employer_name']}, Address: {info['employer_address']}, EIN: {info['ein']}")
    print("===================\n")

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

    files = sorted(
        f for f in os.listdir(abs_input)
        if f.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.tiff'))
        and f != os.path.basename(abs_output)
    )
    logger.info(f"Found {len(files)} files in {abs_input}")

    income, expenses, others = [], [], []
    w2_titles = {}

    for fname in files:
        path = os.path.join(abs_input, fname)
        if fname.lower().endswith('.pdf'):
            total_pages = len(PdfReader(path).pages)
            for i in range(total_pages):
                # ── New: print extraction header like in your past code
                print("=" * 50, file=sys.stderr)
                text = extract_text(path, i)
                print("=" * 50, file=sys.stderr)
                print(f"📄 {fname} p{i+1} → {text or '[NO TEXT]'}", file=sys.stderr)
                print("=" * 50, file=sys.stderr)

                # Multi-method extraction
                extracts = {}
                extracts['PDFMiner'] = pdfminer_extract(path, page_numbers=[i], laparams=PDFMINER_LA_PARAMS) or ""
                extracts['PyPDF2']   = PdfReader(path).pages[i].extract_text() or ""
                try:
                    img = convert_from_path(path, first_page=i+1, last_page=i+1, poppler_path=POPPLER_PATH or None)[0]
                    extracts['Tesseract'] = pytesseract.image_to_string(img, config="--psm 6") or ""
                except:
                    extracts['Tesseract'] = ""
                extracts['FullPDF'] = extract_text_from_pdf(path)
                try:
                    with pdfplumber.open(path) as pdf:
                        page = pdf.pages[i]
                    # fall back directly to a stream‐like, high-tolerance "table"
                        tables = page.extract_tables(table_settings={
                            "vertical_strategy":   "text",
                            "horizontal_strategy": "text",
                            "intersection_tolerance": 20,    # try 10 or even 20
                            "snap_tolerance":         5,     # allow little mis-alignments
                        })
                        if tables:
                            # flatten first table
                            rows = tables[0]
                            for ridx, row in enumerate(rows, start=1):
                                print(f"Row {ridx}: " + " | ".join(cell or "" for cell in row), file=sys.stderr)
                            else:
                                print("[Still no table detected]", file=sys.stderr)
                except:
                    extracts['pdfplumber'] = ""
                # ── DEBUG: show raw output from each tool
                
                for method, txt in extracts.items():
                    snippet = txt.strip().replace("\n", " ")
                    print(f"[Extract][{method}] → {repr(snippet[:2000])}", file=sys.stderr)
                try:
                    doc = fitz.open(path)
                    extracts['PyMuPDF'] = doc.load_page(i).get_text()
                    doc.close()
                except:
                    extracts['PyMuPDF'] = ""
                

                                # … after you fill extracts dict …

               # 1) DEBUG: print raw text from each method
                # ── Structured‐preview of each extractor’s layout ──
                for method, txt in extracts.items():
                    print(f"\n--- {method} Output ---", file=sys.stderr)

                    if method == 'pdfplumber':
                        with pdfplumber.open(path) as pdf:
                            tables = pdf.pages[i].extract_tables()
                        if tables:
                            for ridx, row in enumerate(tables[0], start=1):
                                print(f"Row {ridx}: " + " | ".join(cell or "" for cell in row), file=sys.stderr)
                        else:
                            print("[No tables found]", file=sys.stderr)

                    elif method in ('PyPDF2', 'Tesseract'):
                        for lidx, line in enumerate(txt.splitlines(), start=1):
                                print(f"Line {lidx}: {line}", file=sys.stderr)

                        else:
                            snippet = txt.strip() or "[No text]"
                            print(snippet, file=sys.stderr)
# ── end structured preview ──

                # Identify bracketed names on true W-2 pages
                names = []
                for method, txt in extracts.items():
                   # 2) DEBUG: show which methods we think are W-2 pages
                    cat, ft = classify_text(txt)
                    if cat=='Income' and ft=='W-2':
                        snippet = txt.strip().replace("\n"," ")
                        print(f"[W2-Page][{method}] text → {repr(snippet[:100])}", file=sys.stderr)
                    if cat == 'Income' and ft == 'W-2':
                        m = EMP_BRACKET_RE.search(txt)
                        if m:
                            name = re.sub(r'\s+', ' ', m.group(1).strip())
                            names.append(name)
                if names:
                   # 3) DEBUG: list of all bracketed names found
                    print(f"[W2-Names] collected → {names}", file=sys.stderr)
                    common_name, _ = Counter(names).most_common(1)[0]
                   # 4) DEBUG: which bracketed name we chose
                    print(f"[W2-Choose] using → {common_name}", file=sys.stderr)
                    logger.info(f"Chosen bracketed employer: {common_name} on {fname} p{i+1}")
                    w2_titles[(path, i)] = common_name

                # Classification & grouping
                combined = extract_text(path, i)
                cat, ft = classify_text(combined)
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

    # Sort by priority then filename/page
    income.sort(key=lambda e:(get_form_priority(e[2],'Income'), e[0], e[1]))
    expenses.sort(key=lambda e:(get_form_priority(e[2],'Expenses'), e[0], e[1]))
    # merge & bookmarks
    merger = PdfMerger()
    page_num = 0
    def append_and_bookmark(entry, parent, title):
        nonlocal page_num
        p, idx, _ = entry
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            w = PdfWriter()
            try:
                w.add_page(PdfReader(p).pages[idx])
                w.write(tmp)
            except Exception:
                print(f"Temp write failed: {p} p{idx+1}", file=sys.stderr)
                traceback.print_exc()
            tmp_path = tmp.name
        with open(tmp_path,'rb') as fh:
            merger.append(fileobj=fh)
        os.unlink(tmp_path)
         # DEBUG: show which bookmark title and at what page index
        print(f"[Bookmark] Considering '{title}' at output page #{page_num}", file=sys.stderr)
        merger.add_outline_item(title, page_num, parent=parent)
        page_num += 1

    # Bookmarks
    if income:
        root = merger.add_outline_item('Income', page_num)
        for form, grp in group_by_type(income).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j,e in enumerate(grp,1):
                lbl = form if len(grp)==1 else f"{form}#{j}"
                append_and_bookmark(e, node, lbl)
    if expenses:
        root = merger.add_outline_item('Expenses', page_num)
        for form, grp in group_by_type(expenses).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j,e in enumerate(grp,1):
                lbl = form if len(grp)==1 else f"{form}#{j}"
                append_and_bookmark(e, node, lbl)
    if others:
        root = merger.add_outline_item('Others', page_num)
        node = merger.add_outline_item('Unused', page_num, parent=root)
        for j,e in enumerate(others,1):
            lbl = 'Unused' if len(others)==1 else f"Unused#{j}"
            append_and_bookmark(e, node, lbl)

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
  

03-07-2025
#!/usr/bin/env python3
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

# ── Bracket regex
EMP_BRACKET_RE = re.compile(r"Employer's name, address, and ZIP code.*?\[(.*?)\]", re.IGNORECASE | re.DOTALL)

# ── Priority tables
income_priorities = {'W-2':1,'1099-NEC':2,'1099-PATR':3,'1099-MISC':4,'1099-OID':5,'1099-G':6,'W-2G':7,'1065':8,'1120-S':9,'1041':10,'1099-INT':11,'1099-DIV':12,'1099-R':13,'1099-Q':14,'K-1':15,'1099-Other':16}
expense_priorities = {'5498-SA':1,'1095-A':2,'1095-B':3,'1095-C':4,'1098-Mortgage':5,'1098-T':6,'Property Tax':7,'1098-Other':8}

def get_form_priority(ftype: str, category: str) -> int:
    table = income_priorities if category=='Income' else (expense_priorities if category=='Expenses' else {})
    return table.get(ftype, max(table.values())+1 if table else 9999)

# ── Logging helper
def log_extraction(src: str, method: str, text: str):
    snippet = text[:200].replace('\n',' ') + ('...' if len(text)>200 else '')
    logger.info(f"[{method}] {os.path.basename(src)} → '{snippet}'")
#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------    
# ── Structured PDFMiner
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextBoxHorizontal, LAParams as LMParams
def pdfminer_structured(path: str, page_index: int) -> str:
    lap = LMParams(line_margin=0.1, char_margin=2.0, word_margin=0.5, boxes_flow=0.5)
    chunks = []
    for pg in extract_pages(path, page_numbers=[page_index], laparams=lap):
        for el in pg:
            if isinstance(el, LTTextBoxHorizontal):
                chunks.append(el.get_text().strip())
    return "\n".join(chunks)

# ── Structured PyPDF2
def pypdf2_structured(path: str, page_index: int) -> str:
    rdr = PdfReader(path)
    txt = (rdr.pages[page_index].extract_text() or "").splitlines()
    return "\n".join(ln.strip() for ln in txt if ln.strip())

# ── Structured FullPDF
from pdfminer.high_level import extract_text as pdfminer_full
def fullpdf_structured(path: str) -> str:
    lap = LMParams(line_margin=0.1, char_margin=2.0, word_margin=0.5, boxes_flow=0.5)
    return pdfminer_full(path, laparams=lap)
# ── Structured Tesseract
def tesseract_original(path: str, page_index: int) -> str:
    """
    Exactly your existing OCR fallback:
    """
    opts = {'poppler_path': POPPLER_PATH} if POPPLER_PATH else {}
    img = convert_from_path(path, first_page=page_index+1, last_page=page_index+1, **opts)[0]
    return pytesseract.image_to_string(img, config="--psm 6") or ""
# ── Structured PyMuPDF
def pymupdf_structured(path: str, page_index: int) -> str:
    doc = fitz.open(path)
    blk = doc.load_page(page_index).get_text("dict")["blocks"]
    out = []
    for b in blk:
        if b["type"]==0:
            for ln in b["lines"]:
                txt = "".join(s["text"] for s in ln["spans"]).strip()
                if txt: out.append(txt)
    doc.close()
    return "\n".join(out)

# ── Structured pdfplumber
def pdfplumber_structured(path: str, page_index: int) -> str:
    with pdfplumber.open(path) as pdf:
        pg = pdf.pages[page_index]
        tables = pg.extract_tables()
        if not tables:
            tables = pg.extract_tables(table_settings={
                "vertical_strategy":"text",
                "horizontal_strategy":"text",
                "intersection_tolerance":10,
                "snap_tolerance":5
            })
        if tables:
            rows = tables[0]
            return "\n".join(f"Row {i+1}: " + " | ".join(cell or "" for cell in row)
                             for i,row in enumerate(rows))
        return pg.extract_text() or ""
#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# ── Tiered text extraction for PDF pages
def extract_text(path: str, page_index: int) -> str:
    text = ""
    # PDFMiner
    try:
        t1 = pdfminer_extract(path, page_numbers=[page_index], laparams=PDFMINER_LA_PARAMS) or ""
        log_extraction(path, "PDFMiner", t1)
        if len(t1.strip()) > len(text): text = t1
    except Exception:
        traceback.print_exc()
    # PyPDF2 fallback
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            reader = PdfReader(path)
            t2 = reader.pages[page_index].extract_text() or ""
            log_extraction(path, "PyPDF2", t2)
            if len(t2.strip()) > len(text): text = t2
        except Exception:
            traceback.print_exc()
    # OCR fallback
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            opts = {'poppler_path': POPPLER_PATH} if POPPLER_PATH else {}
            img = convert_from_path(path, first_page=page_index+1, last_page=page_index+1, **opts)[0]
            t3 = pytesseract.image_to_string(img, config="--psm 6") or ""
            log_extraction(path, "Tesseract", t3)
            if len(t3.strip()) > len(text): text = t3
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
                    text += f"\n--- Page {i+1} ---\n" + pt
                    logger.info(f"Full PDF Page {i+1} text: {pt[:100]}...")
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
        if et.strip(): text = f"\n--- OCR Image {os.path.basename(file_path)} ---\n" + et; logger.info(f"Image OCR {file_path}: {et[:100]}...")
        else: text = f"No text in image: {os.path.basename(file_path)}"
    except Exception as e:
        logger.error(f"Error OCR image {file_path}: {e}")
        text = f"Error OCR image: {e}"
    return text

def classify_text(text: str) -> Tuple[str, str]:
    t = text.lower()
    lower = text.lower()
     # If page matches any instruction patterns, classify as Others → Unused
    instruction_patterns = [
        # W2 instructions
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
        "boxes 15-17. state tax withheld"
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
        "future developments. for the latest information about developments related to form 1098-t"
    
    ]
    for pat in instruction_patterns:
        if pat in lower:
            return "Others", "Unused"

    if 'w-2' in t or 'w2' in t: return 'Income', 'W-2'
    if '1099-int' in t or 'interest income' in t: return 'Income', '1099-INT'
    if '1099-div' in t: return 'Income', '1099-DIV'
    if '1098' in t and 'mortgage' in t: return 'Expenses', '1098-Mortgage'
    if '1098-t' in t: return 'Expenses', '1098-T'
    if 'property tax' in t: return 'Expenses', 'Property Tax'
    if '1098' in t: return 'Expenses', '1098-Other'
    if '1099' in t: return 'Income', '1099-Other'
    if 'donation' in t: return 'Expenses', 'Donation'
    return 'Unknown', 'Unused'

# ── Parse W-2 fields
def parse_w2(text: str) -> Dict[str,str]:
    m = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", text)
    ssn = m.group(1) if m else "N/A"
    m = re.search(r"\b(\d{2}-\d{7})\b", text)
    ein = m.group(1) if m else "N/A"
    lines = text.splitlines()
    emp_name = emp_addr = "N/A"
    for i,L in enumerate(lines):
        if "Employer" in L and "name" in L:
            chk = lines[i+1:i+3]
            if chk: emp_name = chk[0].strip()
            if len(chk)>1: emp_addr = chk[1].strip()
            break
    return {'ssn':ssn,'ein':ein,'employer_name':emp_name,'employer_address':emp_addr,'employee_name':'N/A','employee_address':'N/A'}

def print_w2_summary(info: Dict[str,str]):
    print("\n=== W-2 Summary ===\n")
    print(f"Employer: {info['employer_name']}, Address: {info['employer_address']}, EIN: {info['ein']}")
    print("===================\n")

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

    files = sorted(
        f for f in os.listdir(abs_input)
        if f.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.tiff'))
        and f != os.path.basename(abs_output)
    )
    logger.info(f"Found {len(files)} files in {abs_input}")

    income, expenses, others = [], [], []
    w2_titles = {}

    for fname in files:
        path = os.path.join(abs_input, fname)
        if fname.lower().endswith('.pdf'):
            total_pages = len(PdfReader(path).pages)
            for i in range(total_pages):
                # ── New: print extraction header like in your past code
                print("=" * 50, file=sys.stderr)
                text = extract_text(path, i)
                print("=" * 50, file=sys.stderr)
                print(f"📄 {fname} p{i+1} → {text or '[NO TEXT]'}", file=sys.stderr)
                print("=" * 50, file=sys.stderr)

                # Multi-method extraction
                # Multi-method extraction (UPGRADED)
                extracts = {
                    'PDFMiner':   pdfminer_structured(path, i),
                    'PyPDF2':     pypdf2_structured(path, i),
                    'Tesseract':  tesseract_original(path, i),
                    'FullPDF':    fullpdf_structured(path),
                    'PyMuPDF':    pymupdf_structured(path, i),
                    'pdfplumber': pdfplumber_structured(path, i),
                }
                
                                # … after you fill extracts dict …

               # 1) DEBUG: print raw text from each method
                # ── Structured‐preview of each extractor’s layout ──
                for method, txt in extracts.items():
                    print(f"\n--- {method} Output ---", file=sys.stderr)

                    if method == 'pdfplumber':
                        with pdfplumber.open(path) as pdf:
                            tables = pdf.pages[i].extract_tables()
                        if tables:
                            for ridx, row in enumerate(tables[0], start=1):
                                print(f"Row {ridx}: " + " | ".join(cell or "" for cell in row), file=sys.stderr)
                        else:
                            print("[No tables found]", file=sys.stderr)

                    elif method in ('PyPDF2', 'Tesseract'):
                        for lidx, line in enumerate(txt.splitlines(), start=1):
                                print(f"Line {lidx}: {line}", file=sys.stderr)

                        else:
                            snippet = txt.strip() or "[No text]"
                            print(snippet, file=sys.stderr)
# ── end structured preview ──

                # Identify bracketed names on true W-2 pages
                names = []
                for method, txt in extracts.items():
                   # 2) DEBUG: show which methods we think are W-2 pages
                    cat, ft = classify_text(txt)
                    if cat=='Income' and ft=='W-2':
                        snippet = txt.strip().replace("\n"," ")
                        print(f"[W2-Page][{method}] text → {repr(snippet[:100])}", file=sys.stderr)
                    if cat == 'Income' and ft == 'W-2':
                        m = EMP_BRACKET_RE.search(txt)
                        if m:
                            name = re.sub(r'\s+', ' ', m.group(1).strip())
                            names.append(name)
                if names:
                   # 3) DEBUG: list of all bracketed names found
                    print(f"[W2-Names] collected → {names}", file=sys.stderr)
                    common_name, _ = Counter(names).most_common(1)[0]
                   # 4) DEBUG: which bracketed name we chose
                    print(f"[W2-Choose] using → {common_name}", file=sys.stderr)
                    logger.info(f"Chosen bracketed employer: {common_name} on {fname} p{i+1}")
                    w2_titles[(path, i)] = common_name

                # Classification & grouping
                combined = extract_text(path, i)
                cat, ft = classify_text(combined)
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

    # Sort by priority then filename/page
    income.sort(key=lambda e:(get_form_priority(e[2],'Income'), e[0], e[1]))
    expenses.sort(key=lambda e:(get_form_priority(e[2],'Expenses'), e[0], e[1]))
    # merge & bookmarks
    merger = PdfMerger()
    page_num = 0
    def append_and_bookmark(entry, parent, title):
        nonlocal page_num
        p, idx, _ = entry
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            w = PdfWriter()
            try:
                w.add_page(PdfReader(p).pages[idx])
                w.write(tmp)
            except Exception:
                print(f"Temp write failed: {p} p{idx+1}", file=sys.stderr)
                traceback.print_exc()
            tmp_path = tmp.name
        with open(tmp_path,'rb') as fh:
            merger.append(fileobj=fh)
        os.unlink(tmp_path)
         # DEBUG: show which bookmark title and at what page index
        print(f"[Bookmark] Considering '{title}' at output page #{page_num}", file=sys.stderr)
        merger.add_outline_item(title, page_num, parent=parent)
        page_num += 1

    # Bookmarks
    if income:
        root = merger.add_outline_item('Income', page_num)
        for form, grp in group_by_type(income).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j,e in enumerate(grp,1):
                lbl = form if len(grp)==1 else f"{form}#{j}"
                append_and_bookmark(e, node, lbl)
    if expenses:
        root = merger.add_outline_item('Expenses', page_num)
        for form, grp in group_by_type(expenses).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j,e in enumerate(grp,1):
                lbl = form if len(grp)==1 else f"{form}#{j}"
                append_and_bookmark(e, node, lbl)
    if others:
        root = merger.add_outline_item('Others', page_num)
        node = merger.add_outline_item('Unused', page_num, parent=root)
        for j,e in enumerate(others,1):
            lbl = 'Unused' if len(others)==1 else f"Unused#{j}"
            append_and_bookmark(e, node, lbl)

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
  

    
04-07-2025
<------------------------------------------------------------------------------------------------------------------------------------------>
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
    snippet = text[:200].replace('\n',' ') + ('...' if len(text)>200 else '')
    logger.info(f"[{method}] {os.path.basename(src)} → '{snippet}'")

# ── Tiered text extraction for PDF pages
def extract_text(path: str, page_index: int) -> str:
    text = ""
    # PDFMiner
    try:
        t1 = pdfminer_extract(path, page_numbers=[page_index], laparams=PDFMINER_LA_PARAMS) or ""
        log_extraction(path, "PDFMiner", t1)
        if len(t1.strip()) > len(text): text = t1
    except Exception:
        traceback.print_exc()
    # PyPDF2 fallback
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            reader = PdfReader(path)
            t2 = reader.pages[page_index].extract_text() or ""
            log_extraction(path, "PyPDF2", t2)
            if len(t2.strip()) > len(text): text = t2
        except Exception:
            traceback.print_exc()
    # OCR fallback
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            opts = {'poppler_path': POPPLER_PATH} if POPPLER_PATH else {}
            img = convert_from_path(path, first_page=page_index+1, last_page=page_index+1, **opts)[0]
            t3 = pytesseract.image_to_string(img, config="--psm 6") or ""
            log_extraction(path, "Tesseract", t3)
            if len(t3.strip()) > len(text): text = t3
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
                    text += f"\n--- Page {i+1} ---\n" + pt
                    logger.info(f"Full PDF Page {i+1} text: {pt[:100]}...")
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
        if et.strip(): text = f"\n--- OCR Image {os.path.basename(file_path)} ---\n" + et; logger.info(f"Image OCR {file_path}: {et[:100]}...")
        else: text = f"No text in image: {os.path.basename(file_path)}"
    except Exception as e:
        logger.error(f"Error OCR image {file_path}: {e}")
        text = f"Error OCR image: {e}"
    return text

def classify_text(text: str) -> Tuple[str, str]:
    t = text.lower()
    lower = text.lower()
     # If page matches any instruction patterns, classify as Others → Unused
    instruction_patterns = [
        # W2 instructions
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
        "boxes 15-17. state tax withheld"
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
        "future developments. for the latest information about developments related to form 1098-t"
    
    ]
    for pat in instruction_patterns:
        if pat in lower:
            return "Others", "Unused"

    if 'w-2' in t or 'w2' in t: return 'Income', 'W-2'
    if '1099-int' in t or 'interest income' in t: return 'Income', '1099-INT'
    if '1099-div' in t: return 'Income', '1099-DIV'
    if '1098' in t and 'mortgage' in t: return 'Expenses', '1098-Mortgage'
    if '1098-t' in t: return 'Expenses', '1098-T'
    if 'property tax' in t: return 'Expenses', 'Property Tax'
    if '1098' in t: return 'Expenses', '1098-Other'
    if '1099' in t: return 'Income', '1099-Other'
    if 'donation' in t: return 'Expenses', 'Donation'
    return 'Unknown', 'Unused'

# ── Parse W-2 fields
def parse_w2(text: str) -> Dict[str,str]:
    m = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", text)
    ssn = m.group(1) if m else "N/A"
    m = re.search(r"\b(\d{2}-\d{7})\b", text)
    ein = m.group(1) if m else "N/A"
    lines = text.splitlines()
    emp_name = emp_addr = "N/A"
    for i,L in enumerate(lines):
        if "Employer" in L and "name" in L:
            chk = lines[i+1:i+3]
            if chk: emp_name = chk[0].strip()
            if len(chk)>1: emp_addr = chk[1].strip()
            break
    return {'ssn':ssn,'ein':ein,'employer_name':emp_name,'employer_address':emp_addr,'employee_name':'N/A','employee_address':'N/A'}

def print_w2_summary(info: Dict[str,str]):
    print("\n=== W-2 Summary ===\n")
    print(f"Employer: {info['employer_name']}, Address: {info['employer_address']}, EIN: {info['ein']}")
    print("===================\n")

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

    files = sorted(
        f for f in os.listdir(abs_input)
        if f.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.tiff'))
        and f != os.path.basename(abs_output)
    )
    logger.info(f"Found {len(files)} files in {abs_input}")

    income, expenses, others = [], [], []
    w2_titles = {}

    for fname in files:
        path = os.path.join(abs_input, fname)
        if fname.lower().endswith('.pdf'):
            total = len(PdfReader(path).pages)
            for i in range(total):
                # ── New: print extraction header like in your past code
                print("=" * 50, file=sys.stderr)
                text = extract_text(path, i)
                print(f"📄 {fname} p{i+1} → {text or '[NO TEXT]'}", file=sys.stderr)
                print("=" * 50, file=sys.stderr)

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

                for method, txt in extracts.items():
                    print(f"--- {method} Extract ---", file=sys.stderr)
                    print(txt, file=sys.stderr)

                # Collect W-2 employer names across methods
                info_by_method, names = {}, []
                for method, txt in extracts.items():
                    cat, ft = classify_text(txt)
                    if cat == 'Income' and ft == 'W-2':
                        info = parse_w2(txt)
                        if info['employer_name'] != 'N/A':
                            info_by_method[method] = info
                            names.append(info['employer_name'])
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
                    f"snippet='{tiered[:80].strip().replace(chr(10),' ')}…'",
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
    def append_and_bookmark(entry, parent, title):
        nonlocal page_num
        p, idx, _ = entry
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            w = PdfWriter()
            try:
                w.add_page(PdfReader(p).pages[idx])
                w.write(tmp)
            except Exception:
                print(f"Temp write failed: {p} p{idx+1}", file=sys.stderr)
                traceback.print_exc()
            tmp_path = tmp.name
        with open(tmp_path,'rb') as fh:
            merger.append(fileobj=fh)
        os.unlink(tmp_path)
        merger.add_outline_item(title, page_num, parent=parent)
        page_num += 1

    # Bookmarks
    if income:
        root = merger.add_outline_item('Income', page_num)
        for form, grp in group_by_type(income).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, entry in enumerate(grp, 1):
                path, idx, _ = entry

            # build the label
                lbl = form if len(grp) == 1 else f"{form}#{j}"
                if form == 'W-2':
                    emp = w2_titles.get((path, idx))
                    if emp:
                        lbl = f"{form} ({emp})"

            # NEW: log every bookmark about to be created
                print(
                    f"[Bookmark] {os.path.basename(path)} p{idx+1} → "
                    f"Category='Income', Form='{form}', Title='{lbl}'",
                    file=sys.stderr
                )

                append_and_bookmark(entry, node, lbl)


    # Expenses
    if expenses:
        root = merger.add_outline_item('Expenses', page_num)
        for form, grp in group_by_type(expenses).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, entry in enumerate(grp,1):
                path, idx, _ = entry
                lbl = form if len(grp)==1 else f"{form}#{j}"

            # NEW:
                print(
                    f"[Bookmark] {os.path.basename(path)} p{idx+1} → "
                    f"Category='Expenses', Form='{form}', Title='{lbl}'",
                    file=sys.stderr
                )

            append_and_bookmark(entry, node, lbl)
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
  
<------------------------------------------------------------------------------------------------------------------------------------------>

17:37 
04-07-2025
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
    snippet = text[:400].replace('\n',' ') + ('...' if len(text)>400 else '')
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
            log_extraction(path, "Tesseract", t3)
            if len(t3.strip()) > len(text): text = t3
        except Exception:
            traceback.print_exc()
    # PDFMiner
    try:
        t1 = pdfminer_extract(path, page_numbers=[page_index], laparams=PDFMINER_LA_PARAMS) or ""
        log_extraction(path, "PDFMiner", t1)
        if len(t1.strip()) > len(text): text = t1
    except Exception:
        traceback.print_exc()
    # PyPDF2 fallback
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            reader = PdfReader(path)
            t2 = reader.pages[page_index].extract_text() or ""
            log_extraction(path, "PyPDF2", t2)
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
                    text += f"\n--- Page {i+1} ---\n" + pt
                    logger.info(f"Full PDF Page {i+1} text: {pt[:400]}...")
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
        if et.strip(): text = f"\n--- OCR Image {os.path.basename(file_path)} ---\n" + et; logger.info(f"Image OCR {file_path}: {et[:400]}...")
        else: text = f"No text in image: {os.path.basename(file_path)}"
    except Exception as e:
        logger.error(f"Error OCR image {file_path}: {e}")
        text = f"Error OCR image: {e}"
    return text

def classify_text(text: str) -> Tuple[str, str]:
    t = text.lower()
    lower = text.lower()
     # If page matches any instruction patterns, classify as Others → Unused
    instruction_patterns = [
        # W2 instructions
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
        "boxes 15-17. state tax withheld"
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
        "future developments. for the latest information about developments related to form 1098-t"
    
    ]
    for pat in instruction_patterns:
        if pat in lower:
            return "Others", "Unused"
    # Detect W-2 pages by their header phrases
    if 'wage and tax statement' in t or ("employer's name" in t and 'address' in t):
        return 'Income', 'W-2'
    #3) fallback form detectors
    if 'w-2' in t or 'w2' in t: return 'Income', 'W-2'
    if '1099-int' in t or 'interest income' in t: return 'Income', '1099-INT'
    if '1099-div' in t: return 'Income', '1099-DIV'
    if '1098' in t and 'mortgage' in t: return 'Expenses', '1098-Mortgage'
    if '1098-t' in t: return 'Expenses', '1098-T'
    if 'property tax' in t: return 'Expenses', 'Property Tax'
    if '1098' in t: return 'Expenses', '1098-Other'
    if '1099' in t: return 'Income', '1099-Other'
    if 'donation' in t: return 'Expenses', 'Donation'
    return 'Unknown', 'Unused'

# ── Parse W-2 fields
def parse_w2(text: str) -> Dict[str,str]:
    m = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", text)
    ssn = m.group(1) if m else "N/A"
    m = re.search(r"\b(\d{2}-\d{7})\b", text)
    ein = m.group(1) if m else "N/A"
    lines = text.splitlines()
    emp_name = emp_addr = "N/A"
    for i,L in enumerate(lines):
        if "Employer" in L and "name" in L:
            chk = lines[i+1:i+3]
            if chk: emp_name = chk[0].strip()
            if len(chk)>1: emp_addr = chk[1].strip()
            break
    return {'ssn':ssn,'ein':ein,'employer_name':emp_name,'employer_address':emp_addr,'employee_name':'N/A','employee_address':'N/A'}

def print_w2_summary(info: Dict[str,str]):
    print("\n=== W-2 Summary ===\n")
    print(f"Employer: {info['employer_name']}, Address: {info['employer_address']}, EIN: {info['ein']}")
    print("===================\n")

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

    files = sorted(
        f for f in os.listdir(abs_input)
        if f.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.tiff'))
        and f != os.path.basename(abs_output)
    )
    logger.info(f"Found {len(files)} files in {abs_input}")

    income, expenses, others = [], [], []
    w2_titles = {}

    for fname in files:
        path = os.path.join(abs_input, fname)
        if fname.lower().endswith('.pdf'):
            total = len(PdfReader(path).pages)
            for i in range(total):
                # ── New: print extraction header like in your past code
                print("=" * 400, file=sys.stderr)
                text = extract_text(path, i)
                print(f"📄 {fname} p{i+1} → {text or '[NO TEXT]'}", file=sys.stderr)
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

                for method, txt in extracts.items():
                    print(f"--- {method} Extract ---", file=sys.stderr)
                    print(txt, file=sys.stderr)

                # Collect W-2 employer names across methods
                info_by_method, names = {}, []
                for method, txt in extracts.items():
                    cat, ft = classify_text(txt)
                    if cat == 'Income' and ft == 'W-2':
                        info = parse_w2(txt)
                        if info['employer_name'] != 'N/A':
                            info_by_method[method] = info
                            names.append(info['employer_name'])
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
    def append_and_bookmark(entry, parent, title):
        nonlocal page_num
        p, idx, _ = entry
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            w = PdfWriter()
            try:
                w.add_page(PdfReader(p).pages[idx])
                w.write(tmp)
            except Exception:
                print(f"Temp write failed: {p} p{idx+1}", file=sys.stderr)
                traceback.print_exc()
            tmp_path = tmp.name
        with open(tmp_path,'rb') as fh:
            merger.append(fileobj=fh)
        os.unlink(tmp_path)
        merger.add_outline_item(title, page_num, parent=parent)
        page_num += 1

    # Bookmarks
    if income:
        root = merger.add_outline_item('Income', page_num)
        for form, grp in group_by_type(income).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, entry in enumerate(grp, 1):
                path, idx, _ = entry

            # build the label
                lbl = form if len(grp) == 1 else f"{form}#{j}"
                if form == 'W-2':
                    emp = w2_titles.get((path, idx))
                    if emp:
                        lbl = f"{emp}"

            # NEW: log every bookmark about to be created
                print(
                    f"[Bookmark] {os.path.basename(path)} p{idx+1} → "
                    f"Category='Income', Form='{form}', Title='{lbl}'",
                    file=sys.stderr
                )

                append_and_bookmark(entry, node, lbl)


    # Expenses
    if expenses:
        root = merger.add_outline_item('Expenses', page_num)
        for form, grp in group_by_type(expenses).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, entry in enumerate(grp,1):
                path, idx, _ = entry
                lbl = form if len(grp)==1 else f"{form}#{j}"

            # NEW:
                print(
                    f"[Bookmark] {os.path.basename(path)} p{idx+1} → "
                    f"Category='Expenses', Form='{form}', Title='{lbl}'",
                    file=sys.stderr
                )

            append_and_bookmark(entry, node, lbl)
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

# Add the helper at the 
PHRASE = "Employer's name, address, and ZIP code"

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
    snippet = text[:400].replace('\n',' ') + ('...' if len(text)>400 else '')
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
            print_phrase_context(t3)
            if len(t3.strip()) > len(text): text = t3
        except Exception:
            traceback.print_exc()
    # PDFMiner
    try:
        t1 = pdfminer_extract(path, page_numbers=[page_index], laparams=PDFMINER_LA_PARAMS) or ""
        print_phrase_context(t1)
        if len(t1.strip()) > len(text): text = t1
    except Exception:
        traceback.print_exc()
    # PyPDF2 fallback
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            reader = PdfReader(path)
            t2 = reader.pages[page_index].extract_text() or ""
            print_phrase_context(t2)
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

def classify_text(text: str) -> Tuple[str, str]:
    t = text.lower()
    lower = text.lower()
     # If page matches any instruction patterns, classify as Others → Unused
    instruction_patterns = [
        # W2 instructions
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
        "boxes 15-17. state tax withheld"
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
        "future developments. for the latest information about developments related to form 1098-t"
    
    ]
    for pat in instruction_patterns:
        if pat in lower:
            return "Others", "Unused"
    # Detect W-2 pages by their header phrases
    if 'wage and tax statement' in t or ("employer's name" in t and 'address' in t):
        return 'Income', 'W-2'
    #3) fallback form detectors
    if 'w-2' in t or 'w2' in t: return 'Income', 'W-2'
    if '1099-int' in t or 'interest income' in t: return 'Income', '1099-INT'
    if '1099-div' in t: return 'Income', '1099-DIV'
    if '1098' in t and 'mortgage' in t: return 'Expenses', '1098-Mortgage'
    if '1098-t' in t: return 'Expenses', '1098-T'
    if 'property tax' in t: return 'Expenses', 'Property Tax'
    if '1098' in t: return 'Expenses', '1098-Other'
    if '1099' in t: return 'Income', '1099-Other'
    if 'donation' in t: return 'Expenses', 'Donation'
    return 'Unknown', 'Unused'

# ── Parse W-2 fields
def parse_w2(text: str) -> Dict[str,str]:
    m = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", text)
    ssn = m.group(1) if m else "N/A"
    m = re.search(r"\b(\d{2}-\d{7})\b", text)
    ein = m.group(1) if m else "N/A"
    lines = text.splitlines()
    emp_name = emp_addr = "N/A"
    for i,L in enumerate(lines):
        if "Employer" in L and "name" in L:
            chk = lines[i+1:i+3]
            if chk: emp_name = chk[0].strip()
            if len(chk)>1: emp_addr = chk[1].strip()
            break
    return {'ssn':ssn,'ein':ein,'employer_name':emp_name,'employer_address':emp_addr,'employee_name':'N/A','employee_address':'N/A'}

def print_w2_summary(info: Dict[str,str]):
    print("\n=== W-2 Summary ===\n")
    print(f"Employer: {info['employer_name']}, Address: {info['employer_address']}, EIN: {info['ein']}")
    print("===================\n")

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

    files = sorted(
        f for f in os.listdir(abs_input)
        if f.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.tiff'))
        and f != os.path.basename(abs_output)
    )
    logger.info(f"Found {len(files)} files in {abs_input}")

    income, expenses, others = [], [], []
    w2_titles = {}

    for fname in files:
        path = os.path.join(abs_input, fname)
        if fname.lower().endswith('.pdf'):
            total = len(PdfReader(path).pages)
            for i in range(total):
                # ── New: print extraction header like in your past code
                print("=" * 400, file=sys.stderr)
                text = extract_text(path, i)
                print(f"📄 {fname} p{i+1} → {text or '[NO TEXT]'}", file=sys.stderr)

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

                for method, txt in extracts.items():
                    # only dump the slice around our employer-info phrase
                    print_phrase_context(txt)


                # Collect W-2 employer names across methods
                info_by_method, names = {}, []
                for method, txt in extracts.items():
                    cat, ft = classify_text(txt)
                    if cat == 'Income' and ft == 'W-2':
                        info = parse_w2(txt)
                        if info['employer_name'] != 'N/A':
                            info_by_method[method] = info
                            names.append(info['employer_name'])
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
    def append_and_bookmark(entry, parent, title):
        nonlocal page_num
        p, idx, _ = entry
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            w = PdfWriter()
            try:
                w.add_page(PdfReader(p).pages[idx])
                w.write(tmp)
            except Exception:
                print(f"Temp write failed: {p} p{idx+1}", file=sys.stderr)
                traceback.print_exc()
            tmp_path = tmp.name
        with open(tmp_path,'rb') as fh:
            merger.append(fileobj=fh)
        os.unlink(tmp_path)
        merger.add_outline_item(title, page_num, parent=parent)
        page_num += 1

    # Bookmarks
    if income:
        root = merger.add_outline_item('Income', page_num)
        for form, grp in group_by_type(income).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, entry in enumerate(grp, 1):
                path, idx, _ = entry

            # build the label
                lbl = form if len(grp) == 1 else f"{form}#{j}"
                if form == 'W-2':
                    emp = w2_titles.get((path, idx))
                    if emp:
                        lbl = f"{emp}"

            # NEW: log every bookmark about to be created
                print(
                    f"[Bookmark] {os.path.basename(path)} p{idx+1} → "
                    f"Category='Income', Form='{form}', Title='{lbl}'",
                    file=sys.stderr
                )

                append_and_bookmark(entry, node, lbl)


    # Expenses
    if expenses:
        root = merger.add_outline_item('Expenses', page_num)
        for form, grp in group_by_type(expenses).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, entry in enumerate(grp,1):
                path, idx, _ = entry
                lbl = form if len(grp)==1 else f"{form}#{j}"

            # NEW:
                print(
                    f"[Bookmark] {os.path.basename(path)} p{idx+1} → "
                    f"Category='Expenses', Form='{form}', Title='{lbl}'",
                    file=sys.stderr
                )

            append_and_bookmark(entry, node, lbl)
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


    07-07-2025
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
    snippet = text[:400].replace('\n',' ') + ('...' if len(text)>400 else '')
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
            print_phrase_context(t3)
            if len(t3.strip()) > len(text): text = t3
        except Exception:
            traceback.print_exc()
    # PDFMiner
    try:
        t1 = pdfminer_extract(path, page_numbers=[page_index], laparams=PDFMINER_LA_PARAMS) or ""
        print_phrase_context(t1)
        if len(t1.strip()) > len(text): text = t1
    except Exception:
        traceback.print_exc()
    # PyPDF2 fallback
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            reader = PdfReader(path)
            t2 = reader.pages[page_index].extract_text() or ""
            print_phrase_context(t2)
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
        # W2 instructions
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
        "boxes 15-17. state tax withheld"
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
        "future developments. for the latest information about developments related to form 1098-t"
    
    ]
    for pat in instruction_patterns:
        if pat in lower:
            return "Others", "Unused"
    # Detect W-2 pages by their header phrases
    if 'wage and tax statement' in t or ("employer's name" in t and 'address' in t):
        return 'Income', 'W-2'
    #3) fallback form detectors
    if 'w-2' in t or 'w2' in t: return 'Income', 'W-2'
    if '1099-int' in t or 'interest income' in t: return 'Income', '1099-INT'
    if '1099-div' in t: return 'Income', '1099-DIV'
    if '1098' in t and 'mortgage' in t: return 'Expenses', '1098-Mortgage'
    if '1098-t' in t: return 'Expenses', '1098-T'
    if 'property tax' in t: return 'Expenses', 'Property Tax'
    if '1098' in t: return 'Expenses', '1098-Other'
    if '1099' in t: return 'Income', '1099-Other'
    if 'donation' in t: return 'Expenses', 'Donation'
    return 'Unknown', 'Unused'

# ── Parse W-2 fields bookmarks
def parse_w2(text: str) -> Dict[str,str]:
    m = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", text)
    ssn = m.group(1) if m else "N/A"
    m = re.search(r"\b(\d{2}-\d{7})\b", text)
    ein = m.group(1) if m else "N/A"

    lines = text.splitlines()
    emp_name = emp_addr = "N/A"

    for i, line in enumerate(lines):
        if "employer" in line.lower() and "name" in line.lower():
            # advance past any blank lines
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1

            # first non-blank → employer name
            if j < len(lines):
                emp_name = lines[j].strip()
                j += 1

            # then skip any further blanks to find the address
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                emp_addr = lines[j].strip()
            break

    return {
        'ssn': ssn,
        'ein': ein,
        'employer_name': emp_name,
        'employer_address': emp_addr,
        'employee_name': 'N/A',
        'employee_address': 'N/A'
    }


def print_w2_summary(info: Dict[str,str]):
    print("\n=== W-2 Summary ===\n")
    print(f"Employer: {info['employer_name']}, Address: {info['employer_address']}, EIN: {info['ein']}")
    print("===================\n")



# ___ 1099-INTBookmark helper

def extract_1099int_bookmark(text: str) -> str:
    """
    Extracts the line after 'Interest income Income' to use as the bookmark title for 1099-INT forms.
    """
    lines = text.splitlines()
    patterns = [
        "Interest income Income",
        "ZIP or foreign postal code, and telephone no.",
        "Federal ID Number: 13-4994650"
    ]
    for i, line in enumerate(lines):
        if any(pat in line for pat in patterns):
            # Return the next non-empty line after the match
            for j in range(i+1, len(lines)):
                next_line = lines[j].strip()
                if next_line:
                    # 1) remove the literal suffix
                    cleaned = re.sub(r"\s*reel Form 1099-INT.*$", "", next_line)
                    # 2) remove the literal suffix# version using curly quote (if your text really has it):
                    cleaned = re.sub(r'\s*,\s*N\.A\s*“i.*$','',next_line)

                # 2) strip any trailing spaces, commas or dots
                    cleaned = cleaned.rstrip(" .,")
                
                    return cleaned
                    return next_line
    return '1099-INT'



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

    files = sorted(
        f for f in os.listdir(abs_input)
        if f.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.tiff'))
        and f != os.path.basename(abs_output)
    )
    logger.info(f"Found {len(files)} files in {abs_input}")

    income, expenses, others = [], [], []
    w2_titles = {}
    int_titles = {}   # <-- Add this line
    for fname in files:
        path = os.path.join(abs_input, fname)
        if fname.lower().endswith('.pdf'):
            total = len(PdfReader(path).pages)
            for i in range(total):
                # ── New: print extraction header like in your past code
                print("=" * 400, file=sys.stderr)
                text = extract_text(path, i)
                print(f"📄 {fname} p{i+1} → {text or '[NO TEXT]'}", file=sys.stderr)

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

                for method, txt in extracts.items():
                    # only dump the slice around our employer-info phrase
                    print_phrase_context(txt)


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
            tmp_path = tmp.name
        with open(tmp_path,'rb') as fh:
            merger.append(fileobj=fh)
        os.unlink(tmp_path)
        merger.add_outline_item(title, page_num, parent=parent)
        page_num += 1

    # Bookmarks
    if income:
        root = merger.add_outline_item('Income', page_num)
        for form, grp in group_by_type(income).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, entry in enumerate(grp, 1):
                path, idx, _ = entry

            # build the label for W2 Employer
                lbl = form if len(grp) == 1 else f"{form}#{j}"
                if form == 'W-2':
                    emp = w2_titles.get((path, idx))
                    if emp:
                        lbl = f"{emp}"
                elif form == '1099-INT':
                    payer = int_titles.get((path, idx))
                    if payer:
                        lbl = payer


            # NEW: log every bookmark about to be created
                print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Income', Form='{form}', Title='{lbl}'", file=sys.stderr)
                append_and_bookmark(entry, node, lbl)


    # Expenses
    if expenses:
        root = merger.add_outline_item('Expenses', page_num)
        for form, grp in group_by_type(expenses).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, entry in enumerate(grp,1):
                path, idx, _ = entry
                lbl = form if len(grp)==1 else f"{form}#{j}"

            # NEW:
                print(
                    f"[Bookmark] {os.path.basename(path)} p{idx+1} → "
                    f"Category='Expenses', Form='{form}', Title='{lbl}'",
                    file=sys.stderr
                )

            append_and_bookmark(entry, node, lbl)
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


def parse_w2(text: str) -> Dict[str, str]:
    """
    Parses SSN/EIN and pulls out employer_name and employer_address,
    normalizing duplicate employer names.
    """
    # SSN & EIN extraction
    ssn_m = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", text)
    ssn = ssn_m.group(1) if ssn_m else "N/A"
    ein_m = re.search(r"\b(\d{2}-\d{7})\b", text)
    ein = ein_m.group(1) if ein_m else "N/A"

    lines = text.splitlines()
    emp_name = emp_addr = "N/A"
    for i, line in enumerate(lines):
        if "employer" in line.lower() and "name" in line.lower():
            # Advance to the first non-blank line for the name(s)
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1

            if j < len(lines):
                # Split the line by '|' and scan for the first valid company name
                possible_names = [part.strip() for part in re.split(r'[|]', lines[j])]
                for name in possible_names:
                    # Accept if it has letters and is not just numbers
                    if name and re.search(r'[A-Z]', name, re.IGNORECASE) and not re.match(r'^\d+(\.\d+)?$', name):
                        emp_name = normalize_entity_name(name)
                        break
                j += 1

            # Skip blank lines to find address
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                emp_addr = lines[j].strip()
            break

    # to remove duplicate names in bookmarks    
    if emp_name != "N/A":
        # Split by space, remove consecutive duplicates
        words = emp_name.split()
        seen = set()
        unique_words = []
        for word in words:
            if word not in seen:
                unique_words.append(word)
                seen.add(word)
        emp_name = " ".join(unique_words)
        # --------- ADD THIS LINE TO REMOVE TRAILING BACKSLASHES ---------
        emp_name = emp_name.rstrip("\\/")
        # -----------------------------------------------------------------         

    return {
        'ssn': ssn,
        'ein': ein,
        'employer_name': emp_name,
        'employer_address': emp_addr,
        'employee_name': 'N/A',
        'employee_address': 'N/A'
    }






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
    snippet = text[:400].replace('\n',' ') + ('...' if len(text)>400 else '')
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
            print_phrase_context(t3)
            if len(t3.strip()) > len(text): text = t3
        except Exception:
            traceback.print_exc()
    # PDFMiner
    try:
        t1 = pdfminer_extract(path, page_numbers=[page_index], laparams=PDFMINER_LA_PARAMS) or ""
        print_phrase_context(t1)
        if len(t1.strip()) > len(text): text = t1
    except Exception:
        traceback.print_exc()
    # PyPDF2 fallback
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            reader = PdfReader(path)
            t2 = reader.pages[page_index].extract_text() or ""
            print_phrase_context(t2)
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
        # W2 instructions
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
        "boxes 15-17. state tax withheld"
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
        "future developments. for the latest information about developments related to form 1098-t"
    
    ]
    for pat in instruction_patterns:
        if pat in lower:
            return "Others", "Unused"
    # Detect W-2 pages by their header phrases
    if 'wage and tax statement' in t or ("employer's name" in t and 'address' in t):
        return 'Income', 'W-2'
    #3) fallback form detectors
    if 'w-2' in t or 'w2' in t: return 'Income', 'W-2'
    if '1099-int' in t or 'interest income' in t: return 'Income', '1099-INT'
    if '1099-div' in t: return 'Income', '1099-DIV'
    if '1098' in t and 'mortgage' in t: return 'Expenses', '1098-Mortgage'
    if '1098-t' in t: return 'Expenses', '1098-T'
    if 'property tax' in t: return 'Expenses', 'Property Tax'
    if '1098' in t: return 'Expenses', '1098-Other'
    if '1099' in t: return 'Income', '1099-Other'
    if 'donation' in t: return 'Expenses', 'Donation'
    return 'Unknown', 'Unused'

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
    """
    # SSN & EIN extraction
    ssn_m = re.search(r"\b(\d{3}-\d{2}-\d{4})\b", text)
    ssn = ssn_m.group(1) if ssn_m else "N/A"
    ein_m = re.search(r"\b(\d{2}-\d{7})\b", text)
    ein = ein_m.group(1) if ein_m else "N/A"

    lines = text.splitlines()
    emp_name = emp_addr = "N/A"
    for i, line in enumerate(lines):
        if "employer" in line.lower() and "name" in line.lower():
            # Advance to the first non-blank line for the name(s)
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1

            if j < len(lines):
                # Split the line by '|' and scan for the first valid company name
                possible_names = [part.strip() for part in re.split(r'[|]', lines[j])]
                for name in possible_names:
                    # Accept if it has letters and is not just numbers
                    if name and re.search(r'[A-Z]', name, re.IGNORECASE) and not re.match(r'^\d+(\.\d+)?$', name):
                        emp_name = normalize_entity_name(name)
                        break
                j += 1

            # Skip blank lines to find address
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                emp_addr = lines[j].strip()
            break
            
    # to remove duplicate names in bookmarks    
    if emp_name != "N/A":
        # Split by space, remove consecutive duplicates
        words = emp_name.split()
        seen = set()
        unique_words = []
        for word in words:
            if word not in seen:
                unique_words.append(word)
                seen.add(word)
        emp_name = " ".join(unique_words)
        emp_name = emp_name.rstrip("\\/")
    else:
        # --- NEW FEATURE: fallback for PAYROL line ---
        for i, line in enumerate(lines):
            if "0000000845 - PAYROL" in line:
                # Find the next non-empty line
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    next_line = lines[j].strip()
                    first_word = next_line.split()[0] if next_line else None
                    if first_word:
                        emp_name = first_word
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
    1) BANK OF AMERICA override
    2) Otherwise, after one of your trigger lines:
       – skip blank lines
       – skip any line containing 'TIN' or 'RTN'
       – if underscores-only, return that line
       – else:
           • strip 'reel Form 1099-INT' + anything after
           • strip ', N.A' (with optional period)
           • strip trailing punctuation/quotes
           • return the result
    """
    lines: List[str] = text.splitlines()
    lower_text = text.lower()

    # 1) BANK OF AMERICA override
    if "bank of america" in lower_text:
        for line in lines:
            if "bank of america" in line.lower():
                # strip any trailing punctuation or quotes
                return re.sub(r'[^\w\s]+$', '', line.strip())

    # 2) Trigger patterns
    patterns = [
        "Interest income Income",
        "ZIP or foreign postal code, and telephone no.",
        "Federal ID Number:",
    ]

    for i, line in enumerate(lines):
        if any(pat.lower() in line.lower() for pat in patterns):
            # scan forward for the next meaningful line
            for j in range(i + 1, len(lines)):
                stripped = lines[j].strip()
                if not stripped:
                    continue               # skip blank lines
                low = stripped.lower()
                if "tin" in low or "rtn" in low:
                    continue               # skip TIN/RTN noise
                if set(stripped) == {"_"}:
                    return stripped        # pure underscores

                # 1) remove trailing "reel Form 1099-INT" + anything after
                cleaned = re.sub(
                    r"(?i)\s*reel\s+form\s+1099-?int\b.*$",
                    "",
                    stripped
                )
                # 2) remove trailing ", N.A" (with optional period)
                cleaned = re.sub(
                    r",\s*n\.a\.?$",
                    "",
                    cleaned,
                    flags=re.IGNORECASE
                )
                # 3) strip leftover punctuation or stray quotes
                cleaned = re.sub(r"[^\w\s]+$", "", cleaned)

                return cleaned.strip()

    # fallback if nothing matched
    return "1099-INT"




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

    files = sorted(
        f for f in os.listdir(abs_input)
        if f.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.tiff'))
        and f != os.path.basename(abs_output)
    )
    logger.info(f"Found {len(files)} files in {abs_input}")

    income, expenses, others = [], [], []
    w2_titles = {}
    int_titles = {}   # <-- Add this line
    for fname in files:
        path = os.path.join(abs_input, fname) 
        if fname.lower().endswith('.pdf'):
            total = len(PdfReader(path).pages)
            for i in range(total):
                # ── New: print extraction header like in your past code
                print("=" * 400, file=sys.stderr)
                text = extract_text(path, i)
                print(f"📄 {fname} p{i+1} → {text or '[NO TEXT]'}", file=sys.stderr)

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

                for method, txt in extracts.items():
                    # only dump the slice around our employer-info phrase
                    print_phrase_context(txt)


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
            tmp_path = tmp.name
        with open(tmp_path,'rb') as fh:
            merger.append(fileobj=fh)
        os.unlink(tmp_path)
        merger.add_outline_item(title, page_num, parent=parent)
        page_num += 1

    # Bookmarks
    if income:
        root = merger.add_outline_item('Income', page_num)
        for form, grp in group_by_type(income).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, entry in enumerate(grp, 1):
                path, idx, _ = entry

            # build the label for W2 Employer
                lbl = form if len(grp) == 1 else f"{form}#{j}"
                if form == 'W-2':
                    emp = w2_titles.get((path, idx))
                    if emp:
                        lbl = f"{emp}"
                elif form == '1099-INT':
                    payer = int_titles.get((path, idx))
                    if payer:
                        lbl = payer


            # NEW: log every bookmark about to be created
                print(f"[Bookmark] {os.path.basename(path)} p{idx+1} → Category='Income', Form='{form}', Title='{lbl}'", file=sys.stderr)
                append_and_bookmark(entry, node, lbl)


    # Expenses
    if expenses:
        root = merger.add_outline_item('Expenses', page_num)
        for form, grp in group_by_type(expenses).items():
            node = merger.add_outline_item(form, page_num, parent=root)
            for j, entry in enumerate(grp,1):
                path, idx, _ = entry
                lbl = form if len(grp)==1 else f"{form}#{j}"

            # NEW:
                print(
                    f"[Bookmark] {os.path.basename(path)} p{idx+1} → "
                    f"Category='Expenses', Form='{form}', Title='{lbl}'",
                    file=sys.stderr
                )

            append_and_bookmark(entry, node, lbl)
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




    -----
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
    snippet = text[:400].replace('\n',' ') + ('...' if len(text)>400 else '')
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
            print_phrase_context(t3)
            if len(t3.strip()) > len(text): text = t3
        except Exception:
            traceback.print_exc()
    # PDFMiner
    try:
        t1 = pdfminer_extract(path, page_numbers=[page_index], laparams=PDFMINER_LA_PARAMS) or ""
        print_phrase_context(t1)
        if len(t1.strip()) > len(text): text = t1
    except Exception:
        traceback.print_exc()
    # PyPDF2 fallback
    if len(text.strip()) < OCR_MIN_CHARS:
        try:
            reader = PdfReader(path)
            t2 = reader.pages[page_index].extract_text() or ""
            print_phrase_context(t2)
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
        # W2 instructions
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
        "boxes 15-17. state tax withheld"
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
        "future developments. for the latest information about developments related to form 1098-t"
    
    ]
    for pat in instruction_patterns:
        if pat in lower:
            return "Others", "Unused"
    # Detect W-2 pages by their header phrases
    if 'wage and tax statement' in t or ("employer's name" in t and 'address' in t):
        return 'Income', 'W-2'
    #3) fallback form detectors
    if 'w-2' in t or 'w2' in t: return 'Income', 'W-2'
    if '1099-int' in t or 'interest income' in t: return 'Income', '1099-INT'
    if '1099-div' in t: return 'Income', '1099-DIV'
    if '1098' in t and 'mortgage' in t: return 'Expenses', '1098-Mortgage'
    if '1098-t' in t: return 'Expenses', '1098-T'
    if 'property tax' in t: return 'Expenses', 'Property Tax'
    if '1098' in t: return 'Expenses', '1098-Other'
    if '1099' in t: return 'Income', '1099-Other'
    if 'donation' in t: return 'Expenses', 'Donation'
    return 'Unknown', 'Unused'

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

import re
from typing import Dict, List

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
        "¢ Employer’s name, address, and ZIP code "
        "¢ Employer's name, address, and ZIP code "
        "¢ Employer's name, address, and ZIP code"
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
    1) BANK OF AMERICA override
    2) After your trigger patterns:
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

    # 1) BANK OF AMERICA override
    if "bank of america" in lower:
        for L in lines:
            if "bank of america" in L.lower():
                return re.sub(r"[^\w\s]+$", "", L.strip())

    # 2) trigger patterns
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
                # b) strip trailing “, N.A” (with or without dot)
                cleaned = re.sub(r",\s*n\.a\.?$", "", cleaned, flags=re.IGNORECASE)
                # c) strip leftover punctuation or stray quotes
                cleaned = re.sub(r"[^\w\s]+$", "", cleaned)
                # d) **new**: drop any final single-character token
                cleaned = re.sub(r"\b\w\b$", "", cleaned).strip()

                return cleaned

    # fallback
    return "1099-INT"

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

    files = sorted(
        f for f in os.listdir(abs_input)
        if f.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.tiff'))
        and f != os.path.basename(abs_output)
    )
    logger.info(f"Found {len(files)} files in {abs_input}")

    income, expenses, others = [], [], []
    w2_titles = {}
    int_titles = {}   # <-- Add this line
    for fname in files:
        path = os.path.join(abs_input, fname) 
        if fname.lower().endswith('.pdf'):
            total = len(PdfReader(path).pages)
            for i in range(total):
                # ── New: print extraction header like in your past code
                print("=" * 400, file=sys.stderr)
                text = extract_text(path, i)
                print(f"📄 {fname} p{i+1} → {text or '[NO TEXT]'}", file=sys.stderr)

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

                for method, txt in extracts.items():
                    # only dump the slice around our employer-info phrase
                    print_phrase_context(txt)


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
    ----