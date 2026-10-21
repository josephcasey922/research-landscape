from research_landscape.models import *
from research_landscape.processing.pdf_extraction import extract_pdf_text
from research_landscape.retrieval.pdf import download_pdf
from research_landscape.retrieval.semantics_scholar import get_paper, get_references, get_citations
from research_landscape.storage.database import save_complete_paper, load_paper_from_database, \
    load_citations_from_database
from pathlib import Path
from research_landscape.processing.pdf_extraction import extract_pdf_text

#paper_id = "204e3073870fae3d05bcbc2f6a8e263d9b72e776"
#paper = load_paper_from_database("fake")

# citations = load_citations_from_database(paper_id)
#
# for paper in citations:
#     print(f"\n{paper.title}")
#     print(f"Authors: {[author.name for author in paper.authors]}")

# paper = get_paper(paper_id)
# paper.pdf_url = "https://arxiv.org/pdf/1706.03762"
# print(f"Paper: {paper.title}")
# print(f"PDF URL: {paper.pdf_url!r}")
#
# pdf_path = download_pdf(paper, Path("data/pdfs"))
#
#
# print(pdf_path)

pdf_path = Path("data/pdfs/c58bdb5a22eef5020abd9c2f1ea04462ca1def227abd55ca8d7b5e3239e32f09.pdf")

text = extract_pdf_text(pdf_path)

print(f"Extracted {len(text):,} characters")
print(f"Contains references: {'References' in text}")
print(f"Contains experiments: {'Experiments' in text}")
print(text[-1000:])