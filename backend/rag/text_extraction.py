from pathlib import Path

from pypdf import PdfReader


def extract_text_from_pdf(file_path: str) -> list[dict]:
    """Extract text from a PDF file."""
    reader = PdfReader(file_path)
    pages = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text and text.strip():
            pages.append({
                "page_number": i + 1,
                "text": text.strip(),
            })

    return pages


def extract_text_from_txt(file_path: str) -> list[dict]:
    """Extract text from a plain text or markdown file."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    if not text.strip():
        return []

    return [{"page_number": 1, "text": text.strip()}]


def extract_text_from_docx(file_path: str) -> list[dict]:
    """Extract text from a Word document."""
    from docx import Document

    doc = Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    text = "\n".join(paragraphs)

    if not text.strip():
        return []

    return [{"page_number": 1, "text": text.strip()}]


def extract_text_from_excel(file_path: str) -> list[dict]:
    """Extract text from an Excel spreadsheet."""
    import openpyxl
    import csv

    ext = Path(file_path).suffix.lower()
    pages = []

    if ext == ".csv":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            rows = []
            for row in reader:
                rows.append(" | ".join(row))
            text = "\n".join(rows)
            if text.strip():
                pages.append({"page_number": 1, "text": text.strip()})
    else:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        for sheet_num, sheet in enumerate(wb.worksheets, 1):
            rows = []
            for row in sheet.iter_rows(values_only=True):
                cell_values = [str(cell) if cell is not None else "" for cell in row]
                row_text = " | ".join(cell_values)
                if row_text.strip(" |"):
                    rows.append(row_text)
            text = "\n".join(rows)
            if text.strip():
                pages.append({
                    "page_number": sheet_num,
                    "text": text.strip(),
                })
        wb.close()

    return pages


def extract_text(file_path: str) -> list[dict]:
    """Extract text from a file based on its extension."""
    ext = Path(file_path).suffix.lower()

    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext in (".txt", ".md"):
        return extract_text_from_txt(file_path)
    elif ext in (".docx", ".doc"):
        return extract_text_from_docx(file_path)
    elif ext in (".xlsx", ".xls", ".csv"):
        return extract_text_from_excel(file_path)
    else:
        return []
