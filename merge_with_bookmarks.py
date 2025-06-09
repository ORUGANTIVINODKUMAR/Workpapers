import sys
import os
from PyPDF2 import PdfMerger, PdfReader

def classify_bookmark(text):
    text = text.lower()
    if 'form 1098-t' in text or 'tuition statement' in text:
        return 'Expenses', '1098-T'
    elif 'form 1098' in text or 'mortgage interest statement' in text:
        if 'mortgage' in text:
            return 'Expenses', '1098-Mortgage'
        elif 'property tax' in text:
            return 'Expenses', 'Property Tax'
        else:
            return 'Expenses', '1098-Other'
    elif 'form 1099-int' in text or 'interest income' in text:
        return 'Income', '1099-INT'
    elif 'form 1099-div' in text or 'dividends and distributions' in text:
        return 'Income', '1099-DIV'
    elif 'form 1099-q' in text or 'distribution is from' in text:
        return 'Income', '1099-Q'
    elif 'form w-2' in text or 'wage and tax statement' in text:
        return 'Income', 'W-2'
    elif 'property tax' in text:
        return 'Expenses', 'Property Tax'
    else:
        return 'Unknown', 'Unknown Document'

def merge_pdfs_with_hierarchical_bookmarks(input_dir, output_path):
    print("Starting PDF merge", file=sys.stderr)

    merger = PdfMerger()
    files = sorted(os.listdir(input_dir))

    # Define Priority order
    priority_order = {
        'W-2': 1,
        '1099-INT': 2,
        '1099-DIV': 3,
        '1099-Q': 4,
        '1098-Mortgage': 5,
        'Property Tax': 6,
        '1098-T': 7,
        '1098-Other': 8,
        'Unknown Document': 99
    }

    docs_info = []

    # 1. Collect classification and info
    for filename in files:
        file_path = os.path.join(input_dir, filename)
        if os.path.isfile(file_path) and filename.lower().endswith('.pdf'):
            try:
                reader = PdfReader(file_path)
                text = ''
                for page in reader.pages[:2]:
                    text += page.extract_text() or ''
                category, bookmark_name = classify_bookmark(text)
            except Exception as e:
                category, bookmark_name = 'Unknown', 'Unreadable Document'
                print(f"Error reading {filename}: {e}", file=sys.stderr)
                reader = PdfReader(file_path)

            docs_info.append({
                'path': file_path,
                'category': category,
                'bookmark': bookmark_name,
                'priority': priority_order.get(bookmark_name, 99),
                'reader': reader
            })

    # 2. Sort by defined priority
    docs_info.sort(key=lambda x: x['priority'])

    income_outline = []
    expense_outline = []

    # 3. Merge in order and assign bookmarks
    for doc in docs_info:
        with open(doc['path'], 'rb') as f:
            merger.append(f)
            page_index = len(merger.pages) - len(doc['reader'].pages)

            if doc['category'] == 'Income':
                income_outline.append((doc['bookmark'], page_index))
            elif doc['category'] == 'Expenses':
                expense_outline.append((doc['bookmark'], page_index))
            else:
                merger.add_outline_item(doc['bookmark'], page_index)

    # 4. Add nested bookmarks
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
