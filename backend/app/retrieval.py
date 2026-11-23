"""Asynchroniczny dostęp do fragmentów i dowodu (API, graf): BM25, okna i dokumenty."""

from dataclasses import dataclass

from psycopg import AsyncConnection
from pydantic import BaseModel

from app.techqa.search import BM25_ORDER_BY, BM25_WHERE

# Najlepsze k fragmentów wybiera ten sam warunek i kolejność co `search_chunks`;
# dołączenie dokumentu (tytuł) następuje dopiero po ograniczeniu do k.
_BM25_SQL = f"""
WITH top AS (
    SELECT id, snapshot_id, doc_id, headings, text, pdb.score(id)::float8 AS score
    FROM chunks
    WHERE {BM25_WHERE}
    ORDER BY {BM25_ORDER_BY}
    LIMIT %(k)s
)
SELECT top.id, top.doc_id, d.title, top.headings, top.text, top.score
FROM top
JOIN documents d ON d.snapshot_id = top.snapshot_id AND d.doc_id = top.doc_id
ORDER BY top.score DESC, top.id COLLATE "C"
"""

_CHUNK_SQL = """
SELECT c.snapshot_id, c.chunk_set_id, c.doc_id, c.ordinal, c.headings,
       c.start_offset, c.end_offset, d.title
FROM chunks c
JOIN documents d ON d.snapshot_id = c.snapshot_id AND d.doc_id = c.doc_id
WHERE c.id = %(chunk_id)s
"""

# Fragmenty o numerach w zakresie [ordinal - before, ordinal + after] tego samego
# dokumentu i zestawu; brakujące na krawędziach dokumentu są po prostu pomijane.
_WINDOW_SQL = """
SELECT min(ordinal), max(ordinal), min(start_offset), max(end_offset)
FROM chunks
WHERE chunk_set_id = %(chunk_set_id)s AND doc_id = %(doc_id)s
  AND ordinal BETWEEN %(low)s AND %(high)s
"""

_DOC_BOUNDS_SQL = """
SELECT min(ordinal), max(ordinal)
FROM chunks
WHERE chunk_set_id = %(chunk_set_id)s AND doc_id = %(doc_id)s
"""

_SUBSTRING_SQL = """
SELECT substr(text, %(start)s + 1, %(length)s) FROM documents
WHERE snapshot_id = %(snapshot_id)s AND doc_id = %(doc_id)s
"""

_DOCUMENT_SQL = """
SELECT title, text FROM documents
WHERE snapshot_id = %(snapshot_id)s AND doc_id = %(doc_id)s
"""

_DOCUMENT_CHUNKS_SQL = """
SELECT id, ordinal, start_offset, end_offset
FROM chunks
WHERE snapshot_id = %(snapshot_id)s AND doc_id = %(doc_id)s
  AND (%(chunk_set_id)s::text IS NULL OR chunk_set_id = %(chunk_set_id)s)
ORDER BY ordinal
"""

_CORPUS_SQL = """
SELECT s.id, s.revision, s.source, cs.id, cs.variant,
       (SELECT count(*) FROM documents d WHERE d.snapshot_id = s.id),
       (SELECT count(*) FROM chunks c WHERE c.chunk_set_id = cs.id)
FROM chunk_sets cs
JOIN snapshots s ON s.id = cs.snapshot_id
WHERE cs.id = %(chunk_set_id)s
"""


@dataclass(frozen=True)
class RetrievedChunk:
    rank: int
    score: float
    chunk_id: str
    doc_id: str
    title: str
    headings: list[str]
    text: str


class EvidenceWindow(BaseModel):
    """Okno dowodu; offsety zaznaczenia są względne do `window_text`."""

    chunk_id: str
    snapshot_id: str
    doc_id: str
    title: str
    headings: list[str]
    window_text: str
    highlight_start: int
    highlight_end: int
    window_ordinal_from: int
    window_ordinal_to: int
    has_more_before: bool
    has_more_after: bool


class ChunkSpan(BaseModel):
    chunk_id: str
    ordinal: int
    start_offset: int
    end_offset: int


class DocumentText(BaseModel):
    snapshot_id: str
    doc_id: str
    title: str
    text: str
    chunks: list[ChunkSpan]


class CorpusInfo(BaseModel):
    snapshot_id: str
    revision: str
    revision_short: str
    source: str
    chunk_set_id: str
    variant: str
    document_count: int
    chunk_count: int


async def search_bm25(
    conn: AsyncConnection, query: str, *, chunk_set_id: str, k: int
) -> list[RetrievedChunk]:
    """Zwraca k najlepszych fragmentów (BM25) z pełnym tekstem i tytułem dokumentu."""
    if k < 1:
        raise ValueError("k musi być dodatnie")
    cursor = await conn.execute(
        _BM25_SQL, {"query": query, "chunk_set_id": chunk_set_id, "k": k}
    )
    rows = await cursor.fetchall()
    return [
        RetrievedChunk(
            rank=position,
            score=float(score),
            chunk_id=chunk_id,
            doc_id=doc_id,
            title=title,
            headings=list(headings),
            text=text,
        )
        for position, (chunk_id, doc_id, title, headings, text, score) in enumerate(
            rows, start=1
        )
    ]


async def get_evidence_window(
    conn: AsyncConnection, chunk_id: str, *, before: int, after: int
) -> EvidenceWindow | None:
    """Okno dowodu: fragment z `before`/`after` sąsiadami jako wycinek dokumentu.

    Fragmenty zachodzą na siebie, więc okno to wycinek `documents.text`, a nie
    sklejenie tekstów fragmentów.
    """
    if before < 0 or after < 0:
        raise ValueError("before i after nie mogą być ujemne")
    cursor = await conn.execute(_CHUNK_SQL, {"chunk_id": chunk_id})
    row = await cursor.fetchone()
    if row is None:
        return None
    snapshot_id, chunk_set_id, doc_id, ordinal, headings, start, end, title = row

    scope = {"chunk_set_id": chunk_set_id, "doc_id": doc_id}
    cursor = await conn.execute(
        _WINDOW_SQL, {**scope, "low": ordinal - before, "high": ordinal + after}
    )
    window = await cursor.fetchone()
    assert window is not None  # co najmniej sam fragment
    ordinal_from, ordinal_to, window_start, window_end = window

    cursor = await conn.execute(_DOC_BOUNDS_SQL, scope)
    bounds = await cursor.fetchone()
    assert bounds is not None
    first_ordinal, last_ordinal = bounds

    cursor = await conn.execute(
        _SUBSTRING_SQL,
        {
            "snapshot_id": snapshot_id,
            "doc_id": doc_id,
            "start": window_start,
            "length": window_end - window_start,
        },
    )
    text_row = await cursor.fetchone()
    assert text_row is not None
    return EvidenceWindow(
        chunk_id=chunk_id,
        snapshot_id=snapshot_id,
        doc_id=doc_id,
        title=title,
        headings=list(headings),
        window_text=text_row[0],
        highlight_start=start - window_start,
        highlight_end=end - window_start,
        window_ordinal_from=ordinal_from,
        window_ordinal_to=ordinal_to,
        has_more_before=ordinal_from > first_ordinal,
        has_more_after=ordinal_to < last_ordinal,
    )


async def get_document(
    conn: AsyncConnection,
    snapshot_id: str,
    doc_id: str,
    *,
    chunk_set_id: str | None = None,
) -> DocumentText | None:
    """Cały dokument ze znormalizowanym tekstem i położeniem fragmentów.

    Bez `chunk_set_id` zwraca fragmenty wszystkich zestawów migawki.
    """
    scope = {"snapshot_id": snapshot_id, "doc_id": doc_id}
    cursor = await conn.execute(_DOCUMENT_SQL, scope)
    row = await cursor.fetchone()
    if row is None:
        return None
    title, text = row
    cursor = await conn.execute(
        _DOCUMENT_CHUNKS_SQL, {**scope, "chunk_set_id": chunk_set_id}
    )
    chunks = [
        ChunkSpan(chunk_id=cid, ordinal=ordinal, start_offset=start, end_offset=end)
        for cid, ordinal, start, end in await cursor.fetchall()
    ]
    return DocumentText(
        snapshot_id=snapshot_id, doc_id=doc_id, title=title, text=text, chunks=chunks
    )


async def get_corpus_info(conn: AsyncConnection, chunk_set_id: str) -> CorpusInfo:
    """Opis migawki i zestawu fragmentów; `LookupError`, gdy zestawu nie ma."""
    cursor = await conn.execute(_CORPUS_SQL, {"chunk_set_id": chunk_set_id})
    row = await cursor.fetchone()
    if row is None:
        raise LookupError(f"nieznany zestaw fragmentów: {chunk_set_id}")
    snapshot_id, revision, source, set_id, variant, documents, chunks = row
    return CorpusInfo(
        snapshot_id=snapshot_id,
        revision=revision,
        revision_short=revision[:7],
        source=source,
        chunk_set_id=set_id,
        variant=variant,
        document_count=documents,
        chunk_count=chunks,
    )
