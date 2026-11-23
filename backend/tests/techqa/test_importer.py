import dataclasses
from pathlib import Path

import psycopg
import pytest

from app.techqa import importer
from app.techqa.chunking import ChunkerConfig
from app.techqa.importer import IMPORT_LOCK_KEY, ImportFailure, import_snapshot
from tests.techqa.helpers import (
    CHUNK_SET_ID,
    OTHER_REVISION,
    SNAPSHOT_ID,
    build_snapshot,
)

pytestmark = pytest.mark.db


def _count(conn: psycopg.Connection, table: str) -> int:
    row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
    assert row is not None
    return int(row[0])


def _assert_empty(conn: psycopg.Connection) -> None:
    for table in ("snapshots", "documents", "chunk_sets", "chunks"):
        assert _count(conn, table) == 0, table


def test_counts_and_deduplication(conn: psycopg.Connection, tmp_path: Path) -> None:
    data_dir, manifest = build_snapshot(tmp_path)
    report = import_snapshot(conn, data_dir, manifest, ChunkerConfig())

    assert report.snapshot_id == SNAPSHOT_ID
    assert report.documents == manifest.expected_documents
    assert report.canonical_documents == manifest.expected_documents - 1
    assert report.duplicate_groups == [("dup_a", ["dup_b"])]
    assert report.comparison == "pierwszy import"
    assert report.train.records == 2
    assert report.train.references == 3
    assert report.train.distinct_documents == 2
    assert set(report.timings) >= {"weryfikacja", "zapis", "hash stanu"}

    assert _count(conn, "documents") == manifest.expected_documents
    mapping: dict[str, str] = dict(
        conn.execute(
            "SELECT doc_id, canonical_doc_id FROM documents"
            " WHERE doc_id IN ('dup_a', 'dup_b')"
        ).fetchall()
    )
    assert mapping == {"dup_a": "dup_a", "dup_b": "dup_a"}
    canonical_not_self = conn.execute(
        "SELECT count(*) FROM documents WHERE canonical_doc_id <> doc_id"
    ).fetchone()
    assert canonical_not_self == (1,)

    chunk_docs = {
        row[0] for row in conn.execute("SELECT DISTINCT doc_id FROM chunks").fetchall()
    }
    assert "dup_b" not in chunk_docs
    assert "dup_a" in chunk_docs
    assert _count(conn, "chunks") == report.chunks > 0
    assert conn.execute(
        "SELECT count(*) FROM chunks WHERE id <> %s || '/' || doc_id || '/' || ordinal",
        (CHUNK_SET_ID,),
    ).fetchone() == (0,)


def test_state_hash_is_idempotent(conn: psycopg.Connection, tmp_path: Path) -> None:
    data_dir, manifest = build_snapshot(tmp_path)
    first = import_snapshot(conn, data_dir, manifest, ChunkerConfig())
    second = import_snapshot(conn, data_dir, manifest, ChunkerConfig())

    assert first.comparison == "pierwszy import"
    assert second.comparison == "identyczny"
    assert first.state_sha256 == second.state_sha256
    assert _count(conn, "snapshots") == 1
    assert _count(conn, "documents") == manifest.expected_documents
    assert _count(conn, "chunk_sets") == 1
    assert _count(conn, "chunks") == first.chunks


def test_changed_config_reports_different_state(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    data_dir, manifest = build_snapshot(tmp_path)
    first = import_snapshot(conn, data_dir, manifest, ChunkerConfig())
    second = import_snapshot(
        conn, data_dir, manifest, ChunkerConfig(max_chars=1000, overlap_chars=100)
    )
    assert second.comparison == "różny"
    assert second.state_sha256 != first.state_sha256


def test_chunk_set_is_finalized(conn: psycopg.Connection, tmp_path: Path) -> None:
    data_dir, manifest = build_snapshot(tmp_path)
    import_snapshot(conn, data_dir, manifest, ChunkerConfig())
    row = conn.execute(
        "SELECT chunk_count, state_sha256, built_at,"
        " (SELECT count(*) FROM chunks WHERE chunk_set_id = chunk_sets.id)"
        " FROM chunk_sets WHERE id = %s",
        (CHUNK_SET_ID,),
    ).fetchone()
    assert row is not None
    chunk_count, state_sha256, built_at, actual = row
    assert chunk_count is not None
    assert state_sha256 is not None
    assert built_at is not None
    assert chunk_count == actual > 0


def test_bad_file_hash_is_rejected(conn: psycopg.Connection, tmp_path: Path) -> None:
    data_dir, manifest = build_snapshot(tmp_path)
    files = {**manifest.files, "train.json": "0" * 64}
    bad = dataclasses.replace(manifest, files=files)
    with pytest.raises(ImportFailure, match="train.json"):
        import_snapshot(conn, data_dir, bad, ChunkerConfig())
    _assert_empty(conn)


def test_bad_revision_is_rejected(conn: psycopg.Connection, tmp_path: Path) -> None:
    data_dir, manifest = build_snapshot(tmp_path)
    bad = dataclasses.replace(manifest, revision="f" * 40)
    with pytest.raises(ImportFailure, match="Rewizja"):
        import_snapshot(conn, data_dir, bad, ChunkerConfig())
    _assert_empty(conn)


def test_wrong_document_count_is_rejected(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    data_dir, manifest = build_snapshot(tmp_path)
    bad = dataclasses.replace(
        manifest, expected_documents=manifest.expected_documents + 1
    )
    with pytest.raises(ImportFailure, match="Liczba dokumentów"):
        import_snapshot(conn, data_dir, bad, ChunkerConfig())
    _assert_empty(conn)


def test_train_reference_to_missing_document_is_rejected(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    data_dir, manifest = build_snapshot(tmp_path, extra_reference="nie_istnieje")
    with pytest.raises(ImportFailure, match="nie_istnieje"):
        import_snapshot(conn, data_dir, manifest, ChunkerConfig())
    _assert_empty(conn)


def test_failure_after_documents_rolls_back_and_keeps_previous_import(
    conn: psycopg.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir, manifest = build_snapshot(tmp_path)
    first = import_snapshot(conn, data_dir, manifest, ChunkerConfig())

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("wstrzyknięty błąd")

    # Zapis zestawu następuje po COPY dokumentów i po usunięciu poprzedniego stanu.
    monkeypatch.setattr(importer, "_insert_chunk_set", fail)
    with pytest.raises(RuntimeError, match="wstrzyknięty błąd"):
        import_snapshot(
            conn, data_dir, manifest, ChunkerConfig(max_chars=1000, overlap_chars=100)
        )

    assert _count(conn, "snapshots") == 1
    assert _count(conn, "documents") == manifest.expected_documents
    assert _count(conn, "chunk_sets") == 1
    assert _count(conn, "chunks") == first.chunks
    row = conn.execute(
        "SELECT chunk_count, state_sha256 FROM chunk_sets WHERE id = %s",
        (CHUNK_SET_ID,),
    ).fetchone()
    assert row == (first.chunks, first.state_sha256)


def test_chunk_offsets_match_document_text_in_sql(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    data_dir, manifest = build_snapshot(tmp_path)
    import_snapshot(conn, data_dir, manifest, ChunkerConfig())
    # substring w SQL jest 1-based: start_offset (0-based) + 1.
    row = conn.execute(
        "SELECT count(*),"
        " count(*) FILTER (WHERE substring(d.text FROM c.start_offset + 1"
        " FOR c.end_offset - c.start_offset) = c.text)"
        " FROM chunks c JOIN documents d"
        " ON d.snapshot_id = c.snapshot_id AND d.doc_id = c.doc_id"
    ).fetchone()
    assert row is not None
    total, matching = row
    assert total > 0
    assert matching == total


def test_import_takes_advisory_lock(
    conn: psycopg.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir, manifest = build_snapshot(tmp_path)
    held: list[int] = []

    def inspect_locks(*args: object, **kwargs: object) -> None:
        row = conn.execute(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'"
            " AND classid = 0 AND objid = %s AND pid = pg_backend_pid()"
            " AND granted",
            (IMPORT_LOCK_KEY,),
        ).fetchone()
        assert row is not None
        held.append(int(row[0]))
        raise RuntimeError("stop po sprawdzeniu blokady")

    monkeypatch.setattr(importer, "_insert_chunk_set", inspect_locks)
    with pytest.raises(RuntimeError, match="stop po sprawdzeniu"):
        import_snapshot(conn, data_dir, manifest, ChunkerConfig())
    assert held == [1]
    # Blokada transakcyjna znika razem z wycofaną transakcją.
    assert conn.execute(
        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND objid = %s",
        (IMPORT_LOCK_KEY,),
    ).fetchone() == (0,)


def test_import_of_other_snapshot_leaves_first_untouched(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    dir_a, manifest_a = build_snapshot(tmp_path / "a")
    dir_b, manifest_b = build_snapshot(tmp_path / "b", revision=OTHER_REVISION)
    report_a = import_snapshot(conn, dir_a, manifest_a, ChunkerConfig())

    def per_snapshot(snapshot_id: str) -> tuple[int, int, int]:
        row = conn.execute(
            "SELECT (SELECT count(*) FROM documents WHERE snapshot_id = %(s)s),"
            " (SELECT count(*) FROM chunk_sets WHERE snapshot_id = %(s)s),"
            " (SELECT count(*) FROM chunks WHERE snapshot_id = %(s)s)",
            {"s": snapshot_id},
        ).fetchone()
        assert row is not None
        return (int(row[0]), int(row[1]), int(row[2]))

    before = per_snapshot(SNAPSHOT_ID)
    assert before == (manifest_a.expected_documents, 1, report_a.chunks)

    report_b = import_snapshot(conn, dir_b, manifest_b, ChunkerConfig())

    assert report_b.snapshot_id == manifest_b.snapshot_id != SNAPSHOT_ID
    assert report_b.comparison == "pierwszy import"
    assert per_snapshot(SNAPSHOT_ID) == before
    assert per_snapshot(manifest_b.snapshot_id) == before
    assert conn.execute(
        "SELECT state_sha256 FROM chunk_sets WHERE id = %s", (CHUNK_SET_ID,)
    ).fetchone() == (report_a.state_sha256,)
    assert _count(conn, "snapshots") == 2


def test_unexpected_zip_entry_is_rejected(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    data_dir, manifest = build_snapshot(tmp_path, extra_entries={"inne/plik.txt": b"x"})
    with pytest.raises(ImportFailure, match="Nieoczekiwany wpis"):
        import_snapshot(conn, data_dir, manifest, ChunkerConfig())
    _assert_empty(conn)


def test_duplicate_zip_entry_is_rejected(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    data_dir, manifest = build_snapshot(
        tmp_path, duplicate_entries=("corpus/code_block.txt",)
    )
    with pytest.raises(ImportFailure, match="Powtórzony wpis"):
        import_snapshot(conn, data_dir, manifest, ChunkerConfig())
    _assert_empty(conn)


def test_invalid_utf8_document_is_rejected(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    data_dir, manifest = build_snapshot(
        tmp_path, extra_entries={"corpus/zly_utf8.txt": b"\xff\xfe\xfa"}
    )
    with pytest.raises(ImportFailure, match="zly_utf8.txt"):
        import_snapshot(conn, data_dir, manifest, ChunkerConfig())
    _assert_empty(conn)


def test_corrupt_zip_is_rejected(conn: psycopg.Connection, tmp_path: Path) -> None:
    data_dir, manifest = build_snapshot(
        tmp_path, corpus_zip_bytes=b"to nie jest archiwum zip"
    )
    with pytest.raises(ImportFailure, match="Uszkodzony plik zip"):
        import_snapshot(conn, data_dir, manifest, ChunkerConfig())
    _assert_empty(conn)


def test_train_context_without_filename_is_rejected(
    conn: psycopg.Connection, tmp_path: Path
) -> None:
    train = [
        {
            "id": "TRAIN_Q042",
            "question": "q",
            "answer": "a",
            "is_impossible": False,
            "contexts": [{"text": "x"}],
        }
    ]
    data_dir, manifest = build_snapshot(tmp_path, train=train)
    with pytest.raises(ImportFailure, match="TRAIN_Q042.*filename"):
        import_snapshot(conn, data_dir, manifest, ChunkerConfig())
    _assert_empty(conn)
