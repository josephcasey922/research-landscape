import json
from dataclasses import asdict
from research_landscape.models.paper import Paper
from research_landscape.models.author import Author

def save_papers(papers: list[Paper], filepath: str) -> None:
    paper_dicts = [asdict(paper) for paper in papers]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(paper_dicts, f, indent=4)

def load_papers(filepath: str) -> list[Paper]:
    with open(filepath, "r", encoding="utf-8") as f:
        paper_dicts = json.load(f)

    papers_list = []
    for paper_dict in paper_dicts:
        paper_dict["authors"] = [
            Author(**author)
            for author in paper_dict["authors"]
        ]
        paper = Paper(**paper_dict)
        papers_list.append(paper)
    return papers_list