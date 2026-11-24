import os
from collections.abc import AsyncIterator

import pytest

from app.db import AsyncPool, create_pool
from app.settings import Settings
from tests.techqa.helpers import CHUNK_SET_ID


@pytest.fixture
def answer_settings(temp_database: str) -> Settings:
    """Ustawienia na tymczasowej bazie z mini-migawką; bez kluczy OpenAI i Langfuse."""
    return Settings(
        database_url=temp_database,
        chunk_set_id=CHUNK_SET_ID,
        answer_k=8,
        openai_api_key=None,
        langfuse_public_key=None,
        langfuse_secret_key=None,
    )


@pytest.fixture
async def pool(
    imported_conn: object, answer_settings: Settings
) -> AsyncIterator[AsyncPool]:
    """Otwarta pula na tymczasowej bazie po imporcie mini-migawki."""
    pool = create_pool(answer_settings.database_url)
    await pool.open(wait=True)
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
async def live_pool() -> AsyncIterator[AsyncPool]:
    """Pula na bazie z `DATABASE_URL` (pełna migawka), nie na `temp_database`."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("brak DATABASE_URL")
    pool = create_pool(url)
    await pool.open(wait=True)
    try:
        yield pool
    finally:
        await pool.close()
