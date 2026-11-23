import asyncio
import os
import secrets
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import AsyncConnection, sql
from psycopg.conninfo import make_conninfo

from app.main import app
from app.migrations import MIGRATIONS_DIR, apply_migrations
from app.techqa.chunking import ChunkerConfig
from app.techqa.importer import import_snapshot
from tests.techqa.helpers import build_snapshot

# psycopg async nie działa na ProactorEventLoop (domyślnym na Windows).
LOOP_OPTIONS: dict[str, Any] = {"loop_factory": asyncio.SelectorEventLoop}


@pytest.fixture
def anyio_backend() -> tuple[str, dict[str, Any]]:
    return "asyncio", LOOP_OPTIONS


@pytest.fixture
def temp_database() -> Iterator[str]:
    """Tworzy tymczasową bazę obok bazy z `DATABASE_URL` i zwraca jej URL."""
    base_url = os.environ.get("DATABASE_URL")
    if not base_url:
        pytest.skip("brak DATABASE_URL")
    name = f"kops_test_{secrets.token_hex(6)}"
    url = make_conninfo(base_url, dbname=name)
    with psycopg.connect(base_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield url
    finally:
        with psycopg.connect(base_url, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(name)
                )
            )


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


@pytest.fixture
async def async_imported_conn(
    imported_conn: psycopg.Connection, temp_database: str
) -> AsyncIterator[AsyncConnection]:
    """Połączenie async (autocommit) z bazą po imporcie mini-migawki.

    Testy używające tej fikstury wymagają `@pytest.mark.anyio`.
    """
    async with await AsyncConnection.connect(
        temp_database, autocommit=True
    ) as connection:
        yield connection


@pytest.fixture
def api_client(
    imported_conn: psycopg.Connection,
    temp_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    """Klient API na bazie z mini-migawką.

    `with TestClient` uruchamia lifespan, który tworzy pulę we własnej pętli klienta.
    """
    monkeypatch.setenv("DATABASE_URL", temp_database)
    with TestClient(app, backend_options=LOOP_OPTIONS) as client:
        yield client
