import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import psycopg
import psycopg_pool
from fastapi import Depends, HTTPException, Request, status
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

AsyncPool = AsyncConnectionPool

# Limit oczekiwania na połączenie z puli; dłuższe czekanie to niedostępna baza.
CONNECTION_TIMEOUT_S = 5.0

logger = logging.getLogger(__name__)


def create_pool(database_url: str) -> AsyncPool:
    """Tworzy pulę bez otwierania połączeń; otwarcie następuje w `lifespan`."""
    return AsyncConnectionPool(
        database_url,
        min_size=1,
        max_size=5,
        open=False,
        kwargs={"connect_timeout": 5},
        check=AsyncConnectionPool.check_connection,
    )


def get_pool(request: Request) -> AsyncPool:
    pool: AsyncPool = request.app.state.pool
    return pool


PoolDep = Annotated[AsyncPool, Depends(get_pool)]


@asynccontextmanager
async def http_connection(pool: AsyncPool) -> AsyncIterator[AsyncConnection]:
    """Połączenie z puli dla endpointu; niedostępna baza daje 503."""
    try:
        async with pool.connection(timeout=CONNECTION_TIMEOUT_S) as conn:
            yield conn
    except (psycopg.OperationalError, psycopg_pool.PoolTimeout) as exc:
        logger.warning("Baza niedostępna", exc_info=True)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Baza danych jest niedostępna"
        ) from exc
