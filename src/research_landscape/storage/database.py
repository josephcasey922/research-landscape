import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
import os
from research_landscape.models.paper import Paper
from research_landscape.models.author import Author


load_dotenv()

DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_USER = os.getenv("DB_USER")
DB_NAME = os.getenv("DB_NAME")
DB_PORT = os.getenv("DB_PORT")
DB_HOST = os.getenv("DB_HOST")


def get_connection():
    try:
        connection = psycopg.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            dbname=DB_NAME,
            port=DB_PORT
        )
        #print(f"Connected to PostgreSQL database: {DB_NAME}")
        return connection
    except psycopg.Error as e:
        print(f"Error connecting to PostgreSQL database: {e}")
        raise

def save_paper(cursor, paper: Paper) -> None:
    if paper.paper_id is None:
        raise ValueError("Cannot save paper with no paper id")

    sql = """
            INSERT INTO papers (paper_id, title, year, abstract, citation_count, pdf_url, doi, arxiv_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            
            ON CONFLICT (paper_id)
            DO UPDATE SET
                title = EXCLUDED.title,
                year = EXCLUDED.year,
                abstract = EXCLUDED.abstract,
                citation_count = EXCLUDED.citation_count,
                pdf_url = EXCLUDED.pdf_url,
                doi = EXCLUDED.doi,
                arxiv_id = EXCLUDED.arxiv_id
        """
    cursor.execute(sql, (paper.paper_id, paper.title, paper.year, paper.abstract, paper.citation_count, paper.pdf_url, paper.doi, paper.arxiv_id))

def save_author(cursor, author: Author) -> None:
    if author.author_id is None:
        raise ValueError("Cannot save author with no author id")

    sql = """
        INSERT INTO authors (author_id, name)
        VALUES (%s, %s)
        ON CONFLICT (author_id)
        DO UPDATE SET
            name = EXCLUDED.name
    """
    cursor.execute(sql, (author.author_id, author.name))

def save_paper_author(cursor, paper_id: str, author_id: str) -> None:

    sql = """
        INSERT INTO paper_authors (paper_id, author_id)
        VALUES (%s, %s)
        ON CONFLICT (paper_id, author_id)
        DO NOTHING;
    """
    cursor.execute(sql, (paper_id, author_id))

def save_complete_paper(paper: Paper) -> None:
    connection = get_connection()
    cursor = connection.cursor()

    try:
        save_paper_data(cursor, paper)
        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()

def save_paper_data(cursor, paper: Paper) -> None:
    save_paper(cursor, paper)

    for author in paper.authors:
        if author.author_id is None:
            continue

        save_author(cursor, author)
        save_paper_author(cursor, paper.paper_id, author.author_id)

def save_citation(cursor, citing_paper_id: str, cited_paper_id: str) -> None:

    sql = """
        INSERT INTO citations (citing_paper_id, cited_paper_id)
        VALUES (%s, %s)
        ON CONFLICT (citing_paper_id, cited_paper_id)
        DO NOTHING;
    """
    cursor.execute(sql, (citing_paper_id, cited_paper_id))

def save_references(paper: Paper, references: list[Paper]) -> None:
    if paper.paper_id is None:
        raise ValueError("Cannot save references for paper without a paper ID")

    connection = get_connection()
    cursor = connection.cursor()

    try:
        save_paper_data(cursor, paper)

        for reference in references:
            if reference.paper_id is None:
                continue
            save_paper_data(cursor, reference)
            save_citation(cursor, paper.paper_id, reference.paper_id)

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()

def save_citations(paper: Paper, citations: list[Paper]) -> None:
    if paper.paper_id is None:
        raise ValueError("Cannot save citations for paper without a paper ID")

    connection = get_connection()
    cursor = connection.cursor()

    try:
        save_paper_data(cursor, paper)

        for citation in citations:
            if citation.paper_id is None:
                continue

            save_paper_data(cursor, citation)

            # The returned paper cites our target paper:
            # citation -> paper
            save_citation(cursor, citation.paper_id, paper.paper_id)

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()

def load_paper_from_database(paper_id: str) -> Paper | None:
    sql = """
        SELECT paper_id, title, year, abstract, citation_count, pdf_url, doi, arxiv_id
        FROM papers
        WHERE paper_id = %s;
    """
    connection = get_connection()
    cursor = connection.cursor(row_factory=dict_row)

    cursor.execute(sql, (paper_id,))
    row = cursor.fetchone()

    if row is None:
        cursor.close()
        connection.close()
        return None


    author_sql = """
        SELECT a.author_id, a.name
        FROM paper_authors pa
        JOIN authors a
            ON pa.author_id = a.author_id
        WHERE pa.paper_id = %s;
    """

    cursor.execute(author_sql, (paper_id,))
    author_rows = cursor.fetchall()

    authors = [Author(**row) for row in author_rows]

    row["authors"] = authors

    cursor.close()
    connection.close()

    return Paper(**row)

def load_references_from_database(paper_id: str) -> list[Paper]:
    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            sql = """
                SELECT 
                    p.paper_id,
                    p.title,
                    p.year,
                    p.abstract,
                    p.citation_count,
                    p.pdf_url,
                    p.doi,
                    p.arxiv_id 
                FROM citations c
                JOIN papers p
                    ON p.paper_id = c.cited_paper_id
                WHERE c.citing_paper_id = %s;
            """

            cursor.execute(sql, (paper_id,))
            rows = cursor.fetchall()

            author_sql = """
                SELECT 
                    pa.paper_id,
                    a.author_id,
                    a.name
                FROM citations c
                JOIN paper_authors pa
                    ON pa.paper_id = c.cited_paper_id
                JOIN authors a
                    ON a.author_id = pa.author_id
                WHERE c.citing_paper_id = %s;
            """
            cursor.execute(author_sql, (paper_id,))
            author_rows = cursor.fetchall()

            authors_by_paper: dict[str, list[Author]] = {}
            for row in author_rows:
                reference_id = row["paper_id"]
                author = Author(author_id=row["author_id"], name=row["name"])
                if reference_id not in authors_by_paper:
                    authors_by_paper[reference_id] = []
                authors_by_paper[reference_id].append(author)

            for row in rows:
                reference_id = row["paper_id"]
                row["authors"] = authors_by_paper.get(reference_id, [])

            references = [Paper(**row) for row in rows]
            return references

def load_citations_from_database(paper_id: str) -> list[Paper]:
    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            sql = """
                SELECT
                    p.paper_id,
                    p.title,
                    p.year,
                    p.abstract,
                    p.citation_count,
                    p.pdf_url,
                    p.doi,
                    p.arxiv_id 
                FROM citations c
                JOIN papers p
                    ON p.paper_id = c.citing_paper_id
                WHERE c.cited_paper_id = %s;
            """
            cursor.execute(sql, (paper_id,))
            rows = cursor.fetchall()

            author_sql = """
                SELECT
                    pa.paper_id,
                    a.author_id,
                    a.name
                FROM citations c
                JOIN paper_authors pa
                    ON pa.paper_id = c.citing_paper_id
                JOIN authors a
                    ON a.author_id = pa.author_id
                WHERE c.cited_paper_id = %s;
            """
            cursor.execute(author_sql, (paper_id,))
            author_rows = cursor.fetchall()

            authors_by_paper: dict[str, list[Author]] = {}
            for row in author_rows:
                citing_paper_id = row["paper_id"]
                author = Author(author_id=row["author_id"], name=row["name"])
                if citing_paper_id not in authors_by_paper:
                    authors_by_paper[citing_paper_id] = []
                authors_by_paper[citing_paper_id].append(author)

            for row in rows:
                citing_paper_id = row["paper_id"]
                row["authors"] = authors_by_paper.get(citing_paper_id, [])

            citations = [Paper(**row) for row in rows]
            return citations

def list_papers_from_database() -> list[dict]:
    sql = """
        SELECT paper_id, title, year, citation_count, pdf_url
        FROM papers
        ORDER BY title ASC;
    """

    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(sql)
            return cursor.fetchall()