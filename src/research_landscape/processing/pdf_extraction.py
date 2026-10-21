from pathlib import Path
import pymupdf

def extract_pdf_text(pdf_path: Path) -> str:
    pages_list = []
    with pymupdf.open(pdf_path) as document:
        for page in document:
            text = page.get_text("text")
            pages_list.append(text)

    return "\n\n".join(pages_list)