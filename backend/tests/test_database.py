import os

import psycopg
import pytest

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="brak DATABASE_URL"),
]


def test_required_extensions_installed() -> None:
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        rows = conn.execute("SELECT extname FROM pg_extension").fetchall()
    names = {row[0] for row in rows}
    assert {"pg_search", "vector"} <= names
