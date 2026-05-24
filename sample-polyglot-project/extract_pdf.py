import sys

try:
    import pdfplumber
    with pdfplumber.open('/Users/motonishikoudai/Downloads/26_CS2B_課題1.pdf') as pdf:
        text = '\n'.join([page.extract_text() for page in pdf.pages if page.extract_text()])
        print(text)
except ImportError:
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader('/Users/motonishikoudai/Downloads/26_CS2B_課題1.pdf')
        text = '\n'.join([page.extract_text() for page in reader.pages])
        print(text)
    except ImportError:
        print("ERROR: Neither pdfplumber nor PyPDF2 is installed.")
    except Exception as e:
        print(f"ERROR: PyPDF2 failed: {e}")
except Exception as e:
    print(f"ERROR: pdfplumber failed: {e}")
