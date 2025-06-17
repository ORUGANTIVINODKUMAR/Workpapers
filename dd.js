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
