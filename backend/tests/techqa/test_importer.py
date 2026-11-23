import dataclasses
import hashlib
import json
import os
import zipfile
from pathlib import Path

import psycopg
import pytest

from app.migrations import MIGRATIONS_DIR, apply_migrations
from app.techqa import importer
from app.techqa.chunking import ChunkerConfig
from app.techqa.importer import ImportFailure, Manifest, import_snapshot
from tests.techqa.helpers import FIXTURES_DIR, fixture_paths

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="brak DATABASE_URL"),
]

REVISION = "0123456789abcdef0123456789abcdef01234567"
DUPLICATED_FIXTURE = "apar_template"
SNAPSHOT_ID = f"techqa@{REVISION}"
CHUNK_SET_ID = f"{SNAPSHOT_ID}/sections-v1"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_snapshot(
    root: Path, *, extra_reference: str | None = None
) -> tuple[Path, Manifest]:
    """Mini-migawka: fikstury fazy 2, a jedna z nich jako dwie identyczne kopie."""
    data_dir = root / "techqa"
    data_dir.mkdir()
    entries: dict[str, bytes] = {}
    for path in fixture_paths():
        if path.stem == DUPLICATED_FIXTURE:
            continue
        entries[path.stem] = path.read_bytes()
    duplicated = (FIXTURES_DIR / f"{DUPLICATED_FIXTURE}.txt").read_bytes()
    entries["dup_b"] = duplicated
    entries["dup_a"] = duplicated

    with zipfile.ZipFile(data_dir / "corpus.zip", "w") as archive:
        archive.writestr("corpus/", b"")
        for name, data in entries.items():
            archive.writestr(f"corpus/{name}.txt", data)

    references = ["code_block", "dup_a", "code_block"]
    if extra_reference:
        references.append(extra_reference)
    train = [
        {
            "id": "TRAIN_Q000",
            "question": "q",
            "answer": "a",
            "is_impossible": False,
            "contexts": [
                {"filename": f"{name}.txt", "text": "x"} for name in references
            ],
        },
        {"id": "TRAIN_Q001", "question": "q", "answer": "", "is_impossible": True},
    ]
    (data_dir / "train.json").write_text(json.dumps(train), encoding="utf-8")
    (data_dir / "README.md").write_text("# mini\n", encoding="utf-8")
    (data_dir / "revision.txt").write_text(REVISION + "\r\n", encoding="utf-8")

    manifest = Manifest(
        source="test/mini",
        revision=REVISION,
        files={
            name: _sha((data_dir / name).read_bytes())
            for name in ("README.md", "train.json", "corpus.zip")
        },
        expected_documents=len(entries),
    )
    return data_dir, manifest


@pytest.fixture
def conn(temp_database: str):  # type: ignore[no-untyped-def]
    with psycopg.connect(temp_database, autocommit=True) as connection:
        apply_migrations(connection, MIGRATIONS_DIR)
        yield connection


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
