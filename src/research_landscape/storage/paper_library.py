"""Read-only PostgreSQL paper search used by Research Landscape v0.1.

Uses the existing `papers` table and existing get_connection(); no migration.
"""
from __future__ import annotations

from psycopg.rows import dict_row
from research_landscape.storage.database import get_connection


def search_saved_papers(query: str = "", limit: int = 100) -> list[dict]:
    """Return small metadata dictionaries; fetch a Paper only after selection.

    Search is case-insensitive and treats `%`/`_` literally, so input isn't
    accidentally interpreted as a SQL LIKE wildcard.
    """
    term = (query or "").strip()
    limit = max(1, min(int(limit), 250))

    sql = """
        SELECT paper_id, title, year, citation_count
        FROM papers
        WHERE (
            %s = ''
            OR title ILIKE %s ESCAPE '\\'
            OR paper_id ILIKE %s ESCAPE '\\'
            OR COALESCE(doi, '') ILIKE %s ESCAPE '\\'
        )
        ORDER BY COALESCE(citation_count, 0) DESC,
                 year DESC NULLS LAST,
                 title ASC
        LIMIT %s
    """
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    with get_connection() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(sql, (term, pattern, pattern, pattern, limit))
            return cursor.fetchall()
