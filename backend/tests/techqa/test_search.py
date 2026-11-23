import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from app.migrations import MIGRATIONS_DIR, apply_migrations
from app.techqa.chunking import ChunkerConfig
from app.techqa.importer import import_snapshot
from app.techqa.search import Method, search_chunks
from tests.techqa.test_importer import CHUNK_SET_ID, build_snapshot

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="brak DATABASE_URL"),
]

OTHER_CHUNK_SET_ID = f"{CHUNK_SET_ID}-other"
METHODS: list[Method] = ["bm25", "fts"]


@pytest.fixture
def conn(temp_database: str, tmp_path: Path) -> Iterator[psycopg.Connection]:
    with psycopg.connect(temp_database, autocommit=True) as connection:
        apply_migrations(connection, MIGRATIONS_DIR)
        data_dir, manifest = build_snapshot(tmp_path)
        import_snapshot(connection, data_dir, manifest, ChunkerConfig())
        yield connection


@pytest.mark.parametrize("method", METHODS)
def test_inflected_query_finds_document(
    conn: psycopg.Connection, method: Method
) -> None:
    hits = search_chunks(conn, "restarting", method=method, chunk_set_id=CHUNK_SET_ID)
    assert "multiline_title" in {hit.doc_id for hit in hits}
    assert [hit.rank for hit in hits] == list(range(1, len(hits) + 1))
    assert all(len(hit.snippet) <= 200 for hit in hits)


@pytest.mark.parametrize("method", METHODS)
def test_scores_descending_and_k_respected(
    conn: psycopg.Connection, method: Method
) -> None:
    hits = search_chunks(
        conn, "restart server", method=method, chunk_set_id=CHUNK_SET_ID, k=3
    )
    assert 0 < len(hits) <= 3
    scores = [hit.score for hit in hits]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize("method", METHODS)
def test_other_chunk_set_is_not_returned(
    conn: psycopg.Connection, method: Method
) -> None:
    conn.execute(
        "INSERT INTO chunk_sets (id, snapshot_id, variant, config, config_sha256)"
        " SELECT %s, snapshot_id, 'other', '{}', 'x' FROM chunk_sets WHERE id = %s",
        (OTHER_CHUNK_SET_ID, CHUNK_SET_ID),
    )
    conn.execute(
        "INSERT INTO chunks (id, chunk_set_id, snapshot_id, doc_id, ordinal, headings,"
        " start_offset, end_offset, text, text_sha256)"
        " SELECT id || '-other', %s, snapshot_id, doc_id, ordinal, headings,"
        " start_offset, end_offset, text, text_sha256"
        " FROM chunks WHERE chunk_set_id = %s",
        (OTHER_CHUNK_SET_ID, CHUNK_SET_ID),
    )
    main_hits = search_chunks(
        conn, "restart", method=method, chunk_set_id=CHUNK_SET_ID, k=50
    )
    other_hits = search_chunks(
        conn, "restart", method=method, chunk_set_id=OTHER_CHUNK_SET_ID, k=50
    )
    assert main_hits
    assert len(other_hits) == len(main_hits)
    assert not any(hit.chunk_id.endswith("-other") for hit in main_hits)
    assert all(hit.chunk_id.endswith("-other") for hit in other_hits)
