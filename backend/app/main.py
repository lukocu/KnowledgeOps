from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Response, status
from pydantic import BaseModel

from app.db import PoolDep, create_pool
from app.settings import Settings

HEALTH_QUERY_TIMEOUT_S = 2.0


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    pool = create_pool(settings.database_url)
    # wait=False: aplikacja startuje nawet gdy baza jest niedostępna.
    await pool.open(wait=False)
    app.state.pool = pool
    try:
        yield
    finally:
        await pool.close()


app = FastAPI(title="KnowledgeOps API", version="0.1.0", lifespan=lifespan)


@app.get(
    "/api/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse}},
)
async def health(pool: PoolDep, response: Response) -> HealthResponse:
    try:
        async with pool.connection(timeout=HEALTH_QUERY_TIMEOUT_S) as conn:
            await conn.execute("SELECT 1")
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="degraded", database="unavailable")
    return HealthResponse(status="ok", database="ok")
