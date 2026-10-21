"""Versioned pair-level report cache; distinct from per-paper component cache."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from research_landscape.processing.component_analysis import VERSION


def report_path(root: Path, target_id: str, source_id: str, target_pdf: Path, source_pdf: Path) -> Path:
    fingerprint = hashlib.sha256()
    for text in (VERSION, target_id, source_id):
        fingerprint.update(text.encode("utf-8"))
        fingerprint.update(b"\0")
    for pdf in (target_pdf, source_pdf):
        # Fingerprint the actual file bytes, so replacements invalidate old reports.
        with pdf.open("rb") as reader:
            for block in iter(lambda: reader.read(1024 * 1024), b""):
                fingerprint.update(block)
        fingerprint.update(b"\0")
    pair = hashlib.sha256(f"{target_id}\0{source_id}".encode("utf-8")).hexdigest()[:16]
    return root / "data" / "coverage_reports" / f"{pair}_{fingerprint.hexdigest()[:20]}.json"


def save_report(path: Path, target, source, result, target_pdf: Path, source_pdf: Path) -> dict:
    payload = {
        "version": VERSION,
        "target_id": str(target.paper_id),
        "source_id": str(source.paper_id),
        "target_title": target.title,
        "source_title": source.title,
        "target_pdf": str(target_pdf),
        "source_pdf": str(source_pdf),
        **asdict(result),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def read_report(path: Path) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or not all(k in report for k in ("target", "source", "contributions")):
        raise ValueError("The saved report does not match the expected format.")
    return report


def latest_report(root: Path, target_id: str, source_id: str) -> dict | None:
    """Show last saved result for a pair, clearly labeled as saved analysis."""
    pair = hashlib.sha256(f"{target_id}\0{source_id}".encode("utf-8")).hexdigest()[:16]
    folder = root / "data" / "coverage_reports"
    if not folder.exists():
        return None
    for file in sorted(folder.glob(f"{pair}_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = read_report(file)
            if (data.get("target_id") == target_id and data.get("source_id") == source_id
                    and data.get("version") == VERSION):
                return data
        except (OSError, ValueError):
            continue
    return None
