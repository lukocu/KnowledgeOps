import psycopg
import pytest
from psycopg import AsyncConnection

from app.retrieval import (
    get_corpus_info,
    get_document,
    get_evidence_window,
    search_bm25,
)
from app.techqa.search import search_chunks
from tests.techqa.helpers import CHUNK_SET_ID, REVISION, SNAPSHOT_ID

pytestmark = [pytest.mark.db, pytest.mark.anyio]


def _doc_with_chunks(conn: psycopg.Connection, *, single: bool) -> str:
    """Id dokumentu z jednym fragmentem albo z co najmniej trzema."""
    having = "count(*) = 1" if single else "count(*) >= 3"
    row = conn.execute(
        "SELECT doc_id FROM chunks WHERE chunk_set_id = %s"
        f" GROUP BY doc_id HAVING {having} ORDER BY doc_id LIMIT 1",
        (CHUNK_SET_ID,),
    ).fetchone()
    assert row is not None, "brak dokumentu o oczekiwanej liczbie fragmentów"
    return str(row[0])


def _chunk_id(conn: psycopg.Connection, doc_id: str, ordinal: int) -> str:
    row = conn.execute(
        "SELECT id FROM chunks WHERE chunk_set_id = %s AND doc_id = %s"
        " AND ordinal = %s",
        (CHUNK_SET_ID, doc_id, ordinal),
    ).fetchone()
    assert row is not None
    return str(row[0])


def _last_ordinal(conn: psycopg.Connection, doc_id: str) -> int:
    row = conn.execute(
        "SELECT max(ordinal) FROM chunks WHERE chunk_set_id = %s AND doc_id = %s",
        (CHUNK_SET_ID, doc_id),
    ).fetchone()
    assert row is not None
    return int(row[0])


async def test_bm25_matches_sync_order(
    imported_conn: psycopg.Connection, async_imported_conn: AsyncConnection
) -> None:
    for query in ("restart server", "restarting", "restart"):
        sync_hits = search_chunks(
            imported_conn, query, method="bm25", chunk_set_id=CHUNK_SET_ID, k=20
        )
        async_hits = await search_bm25(
            async_imported_conn, query, chunk_set_id=CHUNK_SET_ID, k=20
        )
        assert sync_hits
        assert [h.chunk_id for h in async_hits] == [h.chunk_id for h in sync_hits]
        assert [h.rank for h in async_hits] == list(range(1, len(async_hits) + 1))
        assert [round(h.score, 4) for h in async_hits] == [
            round(h.score, 4) for h in sync_hits
        ]


async def test_bm25_returns_full_text_and_title(
    imported_conn: psycopg.Connection, async_imported_conn: AsyncConnection
) -> None:
    hits = await search_bm25(
        async_imported_conn, "restart", chunk_set_id=CHUNK_SET_ID, k=5
    )
    assert hits
    for hit in hits:
        row = imported_conn.execute(
            "SELECT c.text, d.title FROM chunks c JOIN documents d"
            " ON d.snapshot_id = c.snapshot_id AND d.doc_id = c.doc_id"
            " WHERE c.id = %s",
            (hit.chunk_id,),
        ).fetchone()
        assert row == (hit.text, hit.title)


async def test_bm25_non_positive_k_is_rejected(
    async_imported_conn: AsyncConnection,
) -> None:
    with pytest.raises(ValueError, match="k"):
        await search_bm25(
            async_imported_conn, "restart", chunk_set_id=CHUNK_SET_ID, k=0
        )


async def test_window_highlight_matches_chunk_text(
    imported_conn: psycopg.Connection, async_imported_conn: AsyncConnection
) -> None:
    doc_id = _doc_with_chunks(imported_conn, single=False)
    chunk_id = _chunk_id(imported_conn, doc_id, 1)
    window = await get_evidence_window(async_imported_conn, chunk_id, before=1, after=1)
    assert window is not None
    row = imported_conn.execute(
        "SELECT text FROM chunks WHERE id = %s", (chunk_id,)
    ).fetchone()
    assert row is not None
    highlighted = window.window_text[window.highlight_start : window.highlight_end]
    assert highlighted == row[0]
    assert (window.window_ordinal_from, window.window_ordinal_to) == (0, 2)
    assert window.snapshot_id == SNAPSHOT_ID
    assert window.doc_id == doc_id


async def test_window_at_document_start_and_end(
    imported_conn: psycopg.Connection, async_imported_conn: AsyncConnection
) -> None:
    doc_id = _doc_with_chunks(imported_conn, single=False)
    last = _last_ordinal(imported_conn, doc_id)

    first = await get_evidence_window(
        async_imported_conn, _chunk_id(imported_conn, doc_id, 0), before=1, after=1
    )
    assert first is not None
    assert first.window_ordinal_from == 0
    assert first.has_more_before is False
    assert first.has_more_after is (last > 1)

    final = await get_evidence_window(
        async_imported_conn, _chunk_id(imported_conn, doc_id, last), before=1, after=1
    )
    assert final is not None
    assert final.window_ordinal_to == last
    assert final.has_more_after is False
    assert final.has_more_before is (last > 1)


async def test_window_without_context_is_the_chunk_itself(
    imported_conn: psycopg.Connection, async_imported_conn: AsyncConnection
) -> None:
    doc_id = _doc_with_chunks(imported_conn, single=False)
    chunk_id = _chunk_id(imported_conn, doc_id, 1)
    window = await get_evidence_window(async_imported_conn, chunk_id, before=0, after=0)
    assert window is not None
    assert window.highlight_start == 0
    assert window.highlight_end == len(window.window_text)
    assert window.has_more_before and window.has_more_after


async def test_window_of_single_chunk_document(
    imported_conn: psycopg.Connection, async_imported_conn: AsyncConnection
) -> None:
    doc_id = _doc_with_chunks(imported_conn, single=True)
    window = await get_evidence_window(
        async_imported_conn, _chunk_id(imported_conn, doc_id, 0), before=3, after=3
    )
    assert window is not None
    assert (window.window_ordinal_from, window.window_ordinal_to) == (0, 0)
    assert window.has_more_before is False
    assert window.has_more_after is False


async def test_window_unknown_chunk_is_none(
    async_imported_conn: AsyncConnection,
) -> None:
    window = await get_evidence_window(async_imported_conn, "brak", before=1, after=1)
    assert window is None


async def test_document_offsets_match_chunk_text(
    imported_conn: psycopg.Connection, async_imported_conn: AsyncConnection
) -> None:
    doc_id = _doc_with_chunks(imported_conn, single=False)
    document = await get_document(
        async_imported_conn, SNAPSHOT_ID, doc_id, chunk_set_id=CHUNK_SET_ID
    )
    assert document is not None
    assert len(document.chunks) >= 3
    assert [c.ordinal for c in document.chunks] == list(range(len(document.chunks)))
    for span in document.chunks:
        row = imported_conn.execute(
            "SELECT text FROM chunks WHERE id = %s", (span.chunk_id,)
        ).fetchone()
        assert row is not None
        assert document.text[span.start_offset : span.end_offset] == row[0]


async def test_document_unknown_is_none(async_imported_conn: AsyncConnection) -> None:
    assert await get_document(async_imported_conn, SNAPSHOT_ID, "brak") is None


async def test_corpus_info(
    imported_conn: psycopg.Connection, async_imported_conn: AsyncConnection
) -> None:
    info = await get_corpus_info(async_imported_conn, CHUNK_SET_ID)
    assert info.snapshot_id == SNAPSHOT_ID
    assert info.revision == REVISION
    assert info.revision_short == REVISION[:7]
    assert info.source == "test/mini"
    assert info.chunk_set_id == CHUNK_SET_ID
    assert info.variant == "sections-v1"
    expected = imported_conn.execute(
        "SELECT (SELECT count(*) FROM documents), (SELECT count(*) FROM chunks)"
    ).fetchone()
    assert expected == (info.document_count, info.chunk_count)


async def test_corpus_info_unknown_chunk_set(
    async_imported_conn: AsyncConnection,
) -> None:
    with pytest.raises(LookupError):
        await get_corpus_info(async_imported_conn, "techqa@x/none")
