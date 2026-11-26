from pathlib import Path

import psycopg
import pytest

from app.synthetic.importer import (
    DOCUMENTS_PATH,
    SYNTHETIC_SNAPSHOT_ID,
    import_synthetic_snapshot,
    synthetic_chunk_set_id,
)
from app.techqa.chunking import ChunkerConfig
from app.techqa.importer import import_snapshot
from tests.synthetic.helpers import SYNTHETIC_DOC_ID
from tests.techqa.helpers import CHUNK_SET_ID, build_snapshot

pytestmark = pytest.mark.db


def test_chunk_set_id() -> None:
    assert synthetic_chunk_set_id(ChunkerConfig()) == "synthetic@v1/sections-v1"


def test_import_is_idempotent(conn: psycopg.Connection) -> None:
    first = import_synthetic_snapshot(conn, DOCUMENTS_PATH, ChunkerConfig())
    second = import_synthetic_snapshot(conn, DOCUMENTS_PATH, ChunkerConfig())

    assert first.snapshot_id == SYNTHETIC_SNAPSHOT_ID
    assert first.chunk_set_id == "synthetic@v1/sections-v1"
    assert first.comparison == "pierwszy import"
    assert second.comparison == "identyczny"
    assert first.state_sha256 == second.state_sha256
    assert first.documents >= 1
    assert first.chunks >= 1
    assert conn.execute("SELECT count(*) FROM snapshots").fetchone() == (1,)
    assert conn.execute("SELECT count(*) FROM documents").fetchone() == (
        first.documents,
    )
    assert conn.execute("SELECT count(*) FROM chunks").fetchone() == (first.chunks,)


def test_documents_are_marked_synthetic_with_metadata(
    conn: psycopg.Connection,
) -> None:
    import_synthetic_snapshot(conn, DOCUMENTS_PATH, ChunkerConfig())
    row = conn.execute(
        "SELECT is_synthetic, doc_date, product_version, audience, text"
        " FROM documents WHERE snapshot_id = %s AND doc_id = %s",
        (SYNTHETIC_SNAPSHOT_ID, SYNTHETIC_DOC_ID),
    ).fetchone()
    assert row is not None
    is_synthetic, doc_date, product_version, audience, text = row
    assert is_synthetic is True
    assert doc_date == "2019-03"
    assert product_version is None
    assert audience == "platform team, application servers"
    assert "1024" in text
    # offsety fragmentów odpowiadają tekstowi dokumentu (jak w TechQA)
    mismatched = conn.execute(
        "SELECT count(*) FROM chunks c JOIN documents d"
        " ON d.snapshot_id = c.snapshot_id AND d.doc_id = c.doc_id"
        " WHERE substring(d.text FROM c.start_offset + 1"
        " FOR c.end_offset - c.start_offset) <> c.text"
    ).fetchone()
    assert mismatched == (0,)


def test_techqa_state_hash_unaffected_and_untouched(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    data_dir, manifest = build_snapshot(tmp_path)
    clean = import_snapshot(conn, data_dir, manifest, ChunkerConfig())
    syn = import_synthetic_snapshot(conn, DOCUMENTS_PATH, ChunkerConfig())
    import_synthetic_snapshot(conn, DOCUMENTS_PATH, ChunkerConfig())

    assert conn.execute(
        "SELECT state_sha256 FROM chunk_sets WHERE id = %s", (CHUNK_SET_ID,)
    ).fetchone() == (clean.state_sha256,)
    again = import_snapshot(conn, data_dir, manifest, ChunkerConfig())
    assert again.comparison == "identyczny"
    assert again.state_sha256 == clean.state_sha256
    # reimport TechQA nie kasuje migawki syntetycznej
    assert conn.execute(
        "SELECT count(*) FROM documents WHERE snapshot_id = %s",
        (SYNTHETIC_SNAPSHOT_ID,),
    ).fetchone() == (syn.documents,)


def test_answers_accept_conflicting_outcome(conn: psycopg.Connection) -> None:
    conn.execute(
        "INSERT INTO answers (id, session_hash, question, outcome, snapshot_id,"
        " chunk_set_id, config) VALUES (gen_random_uuid(), 'h', 'q', 'conflicting',"
        " 's', 'c', '{}'::jsonb)"
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute(
            "INSERT INTO answers (id, session_hash, question, outcome, snapshot_id,"
            " chunk_set_id, config) VALUES (gen_random_uuid(), 'h', 'q', 'bogus',"
            " 's', 'c', '{}'::jsonb)"
        )
