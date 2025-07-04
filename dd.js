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

