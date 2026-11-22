from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.db import get_pool
from app.main import app


class _OkConnection:
    async def execute(self, query: str) -> None:
        assert query == "SELECT 1"


class _OkPool:
    @asynccontextmanager
    async def connection(self, timeout: float) -> Any:
        yield _OkConnection()


class _DownPool:
    def connection(self, timeout: float) -> Any:
        raise psycopg.OperationalError("connection refused")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/none")
    # Bez `with` lifespan się nie uruchamia, więc baza nie jest potrzebna.
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_ok(client: TestClient) -> None:
    app.dependency_overrides[get_pool] = lambda: _OkPool()
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_database_unavailable(client: TestClient) -> None:
    app.dependency_overrides[get_pool] = lambda: _DownPool()
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}
