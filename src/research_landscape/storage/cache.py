from research_landscape.models.paper import Paper
from research_landscape.models.author import Author
from dataclasses import asdict
import json
from pathlib import Path

CACHE_DIR = Path("data/cache")
PAPER_CACHE_DIR = CACHE_DIR / "papers"


def save_paper_to_cache(paper: Paper) -> None:
    if paper.paper_id is None:
        raise ValueError(...)
    PAPER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(PAPER_CACHE_DIR / f"{paper.paper_id}.json", "w", encoding="utf-8") as f:
        json.dump(asdict(paper), f, indent=4)

def load_paper_from_cache(paper_id: str) -> Paper | None:
    filepath = PAPER_CACHE_DIR / f"{paper_id}.json"
    if not filepath.exists():
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["authors"] = [
        Author(**author)
        for author in data["authors"]
    ]

    return Paper(**data)

def save_papers_to_cache(papers: list[Paper]) -> None:
    for paper in papers:
        if paper.paper_id is not None:
            save_paper_to_cache(paper)