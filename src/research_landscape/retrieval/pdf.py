import os
from pathlib import Path
import requests
from research_landscape.models.paper import Paper
import hashlib

def download_pdf(paper: Paper, output_dir: Path) -> Path | None:
    if not paper.pdf_url:
        return None
    if paper.paper_id is None:
        raise ValueError("Cannot save paper with no paper id")

    url = paper.pdf_url
    response = requests.get(url)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").lower()

    if "application/pdf" not in content_type:
        raise ValueError(f"Expected PDF, received {content_type}")

    filename = hashlib.sha256(paper.paper_id.encode()).hexdigest() + ".pdf"

    output_path = output_dir / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_bytes(response.content)

    return output_path