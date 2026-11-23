"""Wyszukiwanie kontrolne we fragmentach: BM25 (pg_search) i tsvector, zwykły SQL."""

from dataclasses import dataclass
from typing import Literal

import psycopg

SNIPPET_CHARS = 200

Method = Literal["bm25", "fts"]

# Kanoniczny warunek i kolejność BM25; współdzielone z `app.retrieval` (wariant async).
BM25_WHERE = "chunk_set_id = %(chunk_set_id)s AND text ||| %(query)s"
BM25_ORDER_BY = 'pdb.score(id) DESC, id COLLATE "C"'

_BM25_SQL = f"""
SELECT id, doc_id, headings, left(text, %(snippet)s), pdb.score(id)::float8
FROM chunks
WHERE {BM25_WHERE}
ORDER BY {BM25_ORDER_BY}
LIMIT %(k)s
"""

_FTS_SQL = """
SELECT id, doc_id, headings, left(text, %(snippet)s), ts_rank_cd(tsv, q)::float8
FROM chunks, websearch_to_tsquery('english', %(query)s) AS q
WHERE chunk_set_id = %(chunk_set_id)s AND tsv @@ q
ORDER BY ts_rank_cd(tsv, q) DESC, id COLLATE "C"
LIMIT %(k)s
"""


@dataclass(frozen=True)
class SearchHit:
    rank: int
    score: float
    chunk_id: str
    doc_id: str
    headings: list[str]
    snippet: str


def search_chunks(
    conn: psycopg.Connection,
    query: str,
    *,
    method: Method,
    chunk_set_id: str,
    k: int = 10,
) -> list[SearchHit]:
    """Zwraca k najlepszych fragmentów zestawu; remisy rozstrzyga `id`."""
    if k < 1:
        raise ValueError("k musi być dodatnie")
    statement = _BM25_SQL if method == "bm25" else _FTS_SQL
    params = {
        "query": query,
        "chunk_set_id": chunk_set_id,
        "k": k,
        "snippet": SNIPPET_CHARS,
    }
    rows = conn.execute(statement, params).fetchall()
    return [
        SearchHit(
            rank=position,
            score=float(score),
            chunk_id=chunk_id,
            doc_id=doc_id,
            headings=list(headings),
            snippet=snippet,
        )
        for position, (chunk_id, doc_id, headings, snippet, score) in enumerate(
            rows, start=1
        )
    ]
