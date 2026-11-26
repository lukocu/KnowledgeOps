from pathlib import Path

import psycopg
import pytest
from psycopg import AsyncConnection

from app.retrieval import resolve_active_chunk_set_ids, search_bm25
from tests.synthetic.helpers import ANCHOR_DOC_ID, SYNTHETIC_DOC_ID, import_both
from tests.techqa.helpers import CHUNK_SET_ID

pytestmark = [pytest.mark.db, pytest.mark.anyio]

SYNTHETIC_CHUNK_SET_ID = "synthetic@v1/sections-v1"
QUERY = "nproc value for WebSphere on Linux"


async def test_overlay_returns_techqa_and_synthetic(
    conn: psycopg.Connection, temp_database: str, tmp_path: Path
) -> None:
    import_both(conn, tmp_path)
    async with await AsyncConnection.connect(temp_database, autocommit=True) as aconn:
        hits = await search_bm25(
            aconn,
            QUERY,
            chunk_set_id=CHUNK_SET_ID,
            extra_chunk_set_ids=[SYNTHETIC_CHUNK_SET_ID],
            k=10,
        )
    by_doc = {h.doc_id: h for h in hits}
    assert {ANCHOR_DOC_ID, SYNTHETIC_DOC_ID} <= set(by_doc)
    synthetic = by_doc[SYNTHETIC_DOC_ID]
    assert synthetic.is_synthetic is True
    assert synthetic.snapshot_id == "synthetic@v1"
    assert synthetic.doc_date == "2019-03"
    assert synthetic.audience == "platform team, application servers"
    anchor = by_doc[ANCHOR_DOC_ID]
    assert anchor.is_synthetic is False
    assert anchor.doc_date is None


async def test_without_overlay_only_techqa(
    conn: psycopg.Connection, temp_database: str, tmp_path: Path
) -> None:
    import_both(conn, tmp_path)
    async with await AsyncConnection.connect(temp_database, autocommit=True) as aconn:
        hits = await search_bm25(aconn, QUERY, chunk_set_id=CHUNK_SET_ID, k=10)
    docs = {h.doc_id for h in hits}
    assert ANCHOR_DOC_ID in docs
    assert SYNTHETIC_DOC_ID not in docs
    assert not any(h.is_synthetic for h in hits)


async def test_resolve_active_chunk_set_ids(
    conn: psycopg.Connection, temp_database: str, tmp_path: Path
) -> None:
    async with await AsyncConnection.connect(temp_database, autocommit=True) as aconn:
        # zestaw syntetyczny nie istnieje: zwracana jest sama baza
        assert await resolve_active_chunk_set_ids(
            aconn,
            CHUNK_SET_ID,
            include_synthetic=True,
            synthetic_chunk_set_id=SYNTHETIC_CHUNK_SET_ID,
        ) == [CHUNK_SET_ID]
        import_both(conn, tmp_path)
        assert await resolve_active_chunk_set_ids(
            aconn,
            CHUNK_SET_ID,
            include_synthetic=True,
            synthetic_chunk_set_id=SYNTHETIC_CHUNK_SET_ID,
        ) == [CHUNK_SET_ID, SYNTHETIC_CHUNK_SET_ID]
        assert await resolve_active_chunk_set_ids(
            aconn,
            CHUNK_SET_ID,
            include_synthetic=False,
            synthetic_chunk_set_id=SYNTHETIC_CHUNK_SET_ID,
        ) == [CHUNK_SET_ID]
