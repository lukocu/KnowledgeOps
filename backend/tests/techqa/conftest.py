from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from app.migrations import MIGRATIONS_DIR, apply_migrations
from app.techqa.chunking import ChunkerConfig
from app.techqa.importer import import_snapshot
from tests.techqa.helpers import build_snapshot


@pytest.fixture
def conn(temp_database: str) -> Iterator[psycopg.Connection]:
    """Pusta baza z zastosowanymi migracjami (autocommit)."""
    with psycopg.connect(temp_database, autocommit=True) as connection:
        apply_migrations(connection, MIGRATIONS_DIR)
        yield connection


@pytest.fixture
def imported_conn(conn: psycopg.Connection, tmp_path: Path) -> psycopg.Connection:
    """Baza z zaimportowaną mini-migawką (domyślny `ChunkerConfig`)."""
    data_dir, manifest = build_snapshot(tmp_path)
    import_snapshot(conn, data_dir, manifest, ChunkerConfig())
    return conn
