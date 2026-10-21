from research_landscape.models.paper import Paper
from research_landscape.storage.cache import (load_paper_from_cache,                                          save_paper_to_cache,
                                              save_papers_to_cache)
from research_landscape.models.author import Author
import requests
from dotenv import load_dotenv
import os

from research_landscape.storage.database import save_complete_paper, save_references, save_citations, \
    load_paper_from_database

load_dotenv()

BASE_URL = "https://api.semanticscholar.org/graph/v1"
PAPER_FIELDS = "title,authors,year,abstract,citationCount,openAccessPdf,externalIds"
API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY")

if API_KEY is None:
    raise ValueError("SEMANTIC_SCHOLAR_API_KEY is not set")

HEADERS = {
    "x-api-key": API_KEY
}

def parse_paper(data: dict) -> Paper:
    paper_id = data.get("paperId")
    year = data.get("year")
    title = data["title"]
    citation_count = data.get("citationCount")

    authors_data = data.get("authors", [])
    authors = [Author(
                    author_id=author.get("authorId"),
                    name = author["name"]
                )
                for author in authors_data
        ]


    pdf_data = data.get("openAccessPdf") or {}
    pdf_url = pdf_data.get("url")

    external_ids = data.get("externalIds") or {}
    doi = external_ids.get("DOI")
    arxiv_id = external_ids.get("ArXiv")

    paper = Paper(paper_id = paper_id,
                  title = title,
                  authors = authors,
                  year = year,
                  abstract = data.get("abstract"),
                  citation_count = citation_count,
                  pdf_url = pdf_url,
                  doi = doi,
                  arxiv_id = arxiv_id)
    return paper

def search_papers(query: str, limit: int) -> list[Paper]:
    url = f"{BASE_URL}/paper/search"

    params = {
        "query": query,
        "limit": limit,
        "fields": PAPER_FIELDS
    }

    response = requests.get(url, params=params, headers=HEADERS)
    response.raise_for_status()
    data = response.json()
    papers_data = data["data"]
    papers = [parse_paper(paper) for paper in papers_data]
    save_papers_to_cache(papers)
    return papers

def get_paper(paper_id: str) -> Paper:
    if (paper := load_paper_from_database(paper_id)) is not None:
        print("Loading paper from database. . .")
        return paper

    url = f"{BASE_URL}/paper/{paper_id}"

    params = {
        "fields": PAPER_FIELDS
    }
    response = requests.get(url, params=params, headers=HEADERS)
    response.raise_for_status()
    data = response.json()

    paper = parse_paper(data)
    save_complete_paper(paper)
    return paper

def get_references(paper_id: str, limit: int=100) -> list[Paper]:
    url = f"{BASE_URL}/paper/{paper_id}/references"

    params = {
        "fields": PAPER_FIELDS,
        "limit": limit
    }
    response = requests.get(url, params=params, headers=HEADERS)
    response.raise_for_status()
    raw_data = response.json()

    references_data = raw_data["data"]
    references = [parse_paper(reference.get("citedPaper")) for reference in references_data if reference.get("citedPaper") is not None]

    paper = get_paper(paper_id)
    save_references(paper, references)
    return references

def get_citations(paper_id: str, limit: int=100) -> list[Paper]:
    url = f"{BASE_URL}/paper/{paper_id}/citations"

    params = {
        "fields": PAPER_FIELDS,
        "limit": limit
    }

    response = requests.get(url, params=params, headers=HEADERS)
    response.raise_for_status()
    raw_data = response.json()
    citations_data = raw_data["data"]
    citations = [parse_paper(citation.get("citingPaper")) for citation in citations_data if citation.get("citingPaper") is not None]

    paper = get_paper(paper_id)
    save_citations(paper, citations)

    return citations