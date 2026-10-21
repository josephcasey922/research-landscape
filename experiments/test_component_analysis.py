"""Run once from the project root: python experiments/test_component_analysis.py"""
import argparse
import json
from dataclasses import asdict
from pathlib import Path

from research_landscape.llm.local_model import LocalLLM
from research_landscape.processing.component_analysis import analyze_coverage
from research_landscape.processing.pdf_extraction import extract_pdf_text


def detect(folder: Path, keywords: tuple[str, ...]) -> Path | None:
    candidates = sorted(folder.glob("*.pdf"))
    for keyword in keywords:
        for path in candidates:
            if keyword in path.name.lower():
                return path
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, default=None, help="Target PDF path")
    parser.add_argument("--source", type=Path, default=None, help="Source PDF path")
    args = parser.parse_args()
    folder = Path("data/pdfs")
    target_path = args.target or detect(folder, ("attention", "1706.03762", "transformer"))
    source_path = args.source or detect(folder, ("bert", "1810.04805"))
    if not target_path or not source_path or not target_path.is_file() or not source_path.is_file():
        print("Couldn't identify both PDF paths. Available PDFs:")
        for path in sorted(folder.glob("*.pdf")):
            print("  ", path)
        print('Specify filenames using --target "data/pdfs/your_attention.pdf" '
              '--source "data/pdfs/your_bert.pdf"')
        raise SystemExit(1)
    if target_path.resolve() == source_path.resolve():
        raise SystemExit("Target and source must be different PDFs.")
    print(f"TARGET: {target_path}\nSOURCE: {source_path}")
    target_text = extract_pdf_text(target_path)
    source_text = extract_pdf_text(source_path)
    print(f"PDF text extracted: target={len(target_text):,} chars; source={len(source_text):,} chars")
    if min(len(target_text), len(source_text)) < 500:
        raise SystemExit("Too little extractable text: verify PDF paths and that PDFs contain selectable text.")
    llm = LocalLLM()
    result = analyze_coverage(llm, target_text, source_text)

    print("\n=== TARGET COMPONENTS ===")
    for item in result.target:
        print(f"[{item.component}] {item.label}  ({item.section}; {item.origin})")
    print("\n=== SOURCE COMPONENTS ===")
    for item in result.source:
        print(f"[{item.component}] {item.label}  ({item.section}; {item.origin})")
    print("\n=== POTENTIAL SOURCE -> TARGET COVERAGE ADDITIONS ===")
    for item in result.contributions:
        print(f"\n[{item.component}] {item.approach} ({item.relevance}; {item.origin})")
        print(f"Reason: {item.explanation}")
        print(f"Evidence: {item.evidence}")
    if not result.contributions:
        print("No confidently identified additions. This does NOT imply full target coverage.")
    if result.already_covered:
        print("\n=== SOURCE APPROACHES ALREADY REPRESENTED IN TARGET ===")
        for label in result.already_covered:
            print("-", label)
    if result.undecided:
        print(f"\nUndecided comparisons: {len(result.undecided)}")
    if result.target_warnings or result.source_warnings:
        print("\nWarnings:")
        for warning in result.target_warnings + result.source_warnings:
            print("-", warning)
    dest = Path("data/coverage_comparison.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({
        "target_pdf": str(target_path),
        "source_pdf": str(source_path),
        **asdict(result)
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved results to {dest}")
    print("NOTE: These are possible additions, not adoption or paper-quality scores.")


if __name__ == "__main__":
    main()
