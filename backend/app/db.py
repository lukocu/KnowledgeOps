from typing import Annotated

from fastapi import Depends, Request
from psycopg_pool import AsyncConnectionPool

AsyncPool = AsyncConnectionPool


def create_pool(database_url: str) -> AsyncPool:
    """Tworzy pulę bez otwierania połączeń; otwarcie następuje w `lifespan`."""
    return AsyncConnectionPool(database_url, min_size=1, max_size=5, open=False)


def get_pool(request: Request) -> AsyncPool:
    pool: AsyncPool = request.app.state.pool
    return pool


PoolDep = Annotated[AsyncPool, Depends(get_pool)]
