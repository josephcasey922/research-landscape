"""Acquire PDFs on demand for selected PostgreSQL papers.

Does not change the existing database schema. PDF overrides are explicitly
selected by the user; all resolved PDFs are saved against a stable paper-ID key.
"""
from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MAX_PDF_BYTES = 40 * 1024 * 1024


def pdf_cache_path(root: Path, paper_id: str) -> Path:
    fingerprint = hashlib.sha256(paper_id.encode("utf-8")).hexdigest()[:20]
    return root / "data" / "pdfs" / f"paper_{fingerprint}.pdf"


def _check_pdf(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {path}")
    if path.stat().st_size > MAX_PDF_BYTES:
        raise ValueError("PDF exceeds the 40 MB safety limit.")
    with path.open("rb") as file:
        header = file.read(1024)
    if b"%PDF-" not in header:
        raise ValueError(f"File is not a readable PDF download: {path.name}")


def candidate_pdf_urls(paper) -> list[str]:
    urls: list[str] = []
    original = getattr(paper, "pdf_url", None)
    if original:
        urls.append(str(original))
    arxiv_id = (getattr(paper, "arxiv_id", None) or "").strip()
    if arxiv_id:
        arxiv_id = arxiv_id.removeprefix("arXiv:")
        urls.append(f"https://arxiv.org/pdf/{arxiv_id}")
    return list(dict.fromkeys(urls))


def _download_pdf(url: str, destination: Path) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Only HTTPS PDF links are supported.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "ResearchLandscape/0.1 (academic prototype)"})
    temp_path: Path | None = None
    try:
        with urlopen(request, timeout=30) as response:
            # Followed redirects must also remain HTTPS.
            final_url = response.geturl()
            if urlparse(final_url).scheme != "https":
                raise ValueError("PDF URL redirected to a non-HTTPS address.")
            with tempfile.NamedTemporaryFile("wb", delete=False, dir=destination.parent, suffix=".pdf") as temp:
                temp_path = Path(temp.name)
                total = 0
                while True:
                    block = response.read(1024 * 256)
                    if not block:
                        break
                    total += len(block)
                    if total > MAX_PDF_BYTES:
                        raise ValueError("PDF download exceeds the 40 MB safety limit.")
                    temp.write(block)
        _check_pdf(temp_path)
        temp_path.replace(destination)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def acquire_paper_pdf(
    paper,
    root: Path,
    local_override: Path | None = None,
    upload: bytes | None = None,
) -> tuple[Path, str]:
    """Return (cached_path, how_resolved). Priority: upload > override > cache > URL.

    Paper must have `.paper_id` and may have `.pdf_url` and `.arxiv_id`.
    """
    paper_id = getattr(paper, "paper_id", None)
    if not paper_id:
        raise ValueError("The selected database paper has no paper_id.")
    dest = pdf_cache_path(root, str(paper_id))
    dest.parent.mkdir(parents=True, exist_ok=True)

    if upload is not None:
        if len(upload) > MAX_PDF_BYTES:
            raise ValueError("Uploaded PDF exceeds 40 MB.")
        tmp = dest.with_suffix(".uploaded.part")
        try:
            tmp.write_bytes(upload)
            _check_pdf(tmp)
            tmp.replace(dest)
        finally:
            tmp.unlink(missing_ok=True)
        return dest, "uploaded PDF"

    if local_override is not None:
        local_override = Path(local_override).resolve()
        _check_pdf(local_override)
        if local_override != dest.resolve():
            tmp = dest.with_suffix(".local.part")
            try:
                shutil.copyfile(local_override, tmp)
                _check_pdf(tmp)
                tmp.replace(dest)
            finally:
                tmp.unlink(missing_ok=True)
        return dest, "selected local PDF"

    if dest.exists():
        _check_pdf(dest)
        return dest, "cached PDF"

    errors: list[str] = []
    for url in candidate_pdf_urls(paper):
        try:
            _download_pdf(url, dest)
            return dest, "downloaded PDF"
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")

    detail = "\n".join(errors) if errors else "No PDF URL or arXiv ID is saved for this paper."
    raise FileNotFoundError(
        f"Could not obtain the PDF for '{getattr(paper, 'title', paper_id)}'. "
        "Choose an existing local PDF or upload one under 'PDF sources'.\n" + detail
    )
