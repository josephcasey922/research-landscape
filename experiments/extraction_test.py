from pathlib import Path

from research_landscape.llm.local_model import LocalLLM
from research_landscape.processing.methodology_extraction import extract_methodology, create_evidence_blocks, \
    format_evidence_blocks
from research_landscape.processing.pdf_extraction import extract_pdf_text
from research_landscape.processing.text_chunking import chunk_text

PROJECT_ROOT = Path(__file__).resolve().parents[1]

pdf_path = (
    PROJECT_ROOT
    / "data"
    / "pdfs"
    / "c58bdb5a22eef5020abd9c2f1ea04462ca1def227abd55ca8d7b5e3239e32f09.pdf"
)

text = extract_pdf_text(pdf_path)
chunks = chunk_text(text, max_chars=1500)

llm = LocalLLM()

test_indices = [0, 5, 12, 22, 30]

for i in test_indices:
    result = extract_methodology(
        passage=chunks[i],
        llm=llm,
        paper_title="Attention Is All You Need"
    )

    print(f"\n{'=' * 60}")
    print(f"CHUNK {i}")
    print(f"Parsing succeeded: {result.parse_success}")
    print(f"Number of claims: {len(result.claims)}")

    for claim in result.claims:
        print(f"\nDescription: {claim.description}")
        print(f"Evidence: {claim.evidence}")
        print(f"Source located: {claim.verified}")

    print("\nSOURCE PASSAGE:")
    print(chunks[i])