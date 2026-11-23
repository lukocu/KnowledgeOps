import os
import secrets
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo


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
