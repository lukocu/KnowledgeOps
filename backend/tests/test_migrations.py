import os
import shutil
from pathlib import Path

import psycopg
import pytest

from app.migrations import MIGRATIONS_DIR, MigrationError, apply_migrations

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="brak DATABASE_URL"),
]


def test_second_run_applies_nothing(temp_database: str) -> None:
    with psycopg.connect(temp_database, autocommit=True) as conn:
        assert apply_migrations(conn, MIGRATIONS_DIR) == [
            "0001_techqa_schema",
            "0002_answers",
        ]
        assert apply_migrations(conn, MIGRATIONS_DIR) == []


def test_changed_applied_file_is_rejected(temp_database: str, tmp_path: Path) -> None:
    directory = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS_DIR, directory)
    with psycopg.connect(temp_database, autocommit=True) as conn:
        apply_migrations(conn, directory)
        migration = directory / "0001_techqa_schema.sql"
        migration.write_bytes(migration.read_bytes() + b"\n-- zmiana\n")
        with pytest.raises(MigrationError, match="0001_techqa_schema"):
            apply_migrations(conn, directory)


def test_recorded_version_without_file_is_rejected(
    temp_database: str, tmp_path: Path
) -> None:
    directory = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS_DIR, directory)
    with psycopg.connect(temp_database, autocommit=True) as conn:
        apply_migrations(conn, directory)
        (directory / "0001_techqa_schema.sql").unlink()
        with pytest.raises(MigrationError, match="0001_techqa_schema"):
            apply_migrations(conn, directory)


def test_schema_has_tables_and_indexes(temp_database: str) -> None:
    with psycopg.connect(temp_database, autocommit=True) as conn:
        apply_migrations(conn, MIGRATIONS_DIR)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ).fetchall()
        }
        indexes = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT c.relname, am.amname FROM pg_index i"
                " JOIN pg_class c ON c.oid = i.indexrelid"
                " JOIN pg_am am ON am.oid = c.relam"
                " WHERE i.indrelid = 'chunks'::regclass"
            ).fetchall()
        }
    assert {
        "schema_migrations",
        "snapshots",
        "documents",
        "chunk_sets",
        "chunks",
    } <= tables
    assert "chunks_search_idx" in indexes
    assert "gin" in indexes.values()


def test_tokenizer_stems_and_drops_stopwords(temp_database: str) -> None:
    with psycopg.connect(temp_database, autocommit=True) as conn:
        apply_migrations(conn, MIGRATIONS_DIR)
        row = conn.execute(
            "SELECT 'Running the servers'::pdb.simple("
            "'stemmer=english', 'stopwords_language=english')::text[]"
        ).fetchone()
    assert row is not None
    assert row[0] == ["run", "server"]
