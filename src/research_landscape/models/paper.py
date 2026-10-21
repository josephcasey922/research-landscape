from dataclasses import dataclass
from research_landscape.models.author import Author

@dataclass
class Paper:
    paper_id: str | None
    title: str
    authors: list[Author]
    year: int | None
    abstract: str | None
    citation_count: int | None
    pdf_url: str | None
    doi: str | None
    arxiv_id: str | None

