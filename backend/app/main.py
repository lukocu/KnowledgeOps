import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Response, status
from pydantic import BaseModel

from app.api import answers, audits, evidence
from app.auditing.runner import AuditTaskManager
from app.auditing.store import fail_orphaned_audits
from app.db import PoolDep, create_pool
from app.settings import Settings

HEALTH_QUERY_TIMEOUT_S = 2.0
ORPHAN_CLEANUP_TIMEOUT_S = 2.0

logger = logging.getLogger(__name__)


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
    audit_tasks = AuditTaskManager()
    app.state.audit_tasks = audit_tasks
    try:
        async with asyncio.timeout(ORPHAN_CLEANUP_TIMEOUT_S):
            async with pool.connection(timeout=ORPHAN_CLEANUP_TIMEOUT_S) as conn:
                orphaned = await fail_orphaned_audits(conn)
                if orphaned:
                    logger.warning(
                        "Oznaczono %d osieroconych audytów jako failed przy starcie",
                        orphaned,
                    )
    except Exception:
        logger.warning(
            "Nie udało się wyczyścić osieroconych audytów przy starcie",
            exc_info=True,
        )
    try:
        yield
    finally:
        await audit_tasks.shutdown()
        await pool.close()


app = FastAPI(title="KnowledgeOps API", version="0.1.0", lifespan=lifespan)
app.include_router(evidence.router)
app.include_router(answers.router)
app.include_router(audits.router)


@app.get(
    "/api/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse}},
)
async def health(pool: PoolDep, response: Response) -> HealthResponse:
    try:
        # Limit obejmuje pobranie połączenia z puli i samo zapytanie.
        async with asyncio.timeout(HEALTH_QUERY_TIMEOUT_S):
            async with pool.connection(timeout=HEALTH_QUERY_TIMEOUT_S) as conn:
                await conn.execute("SELECT 1")
    except Exception:
        logger.warning("Kontrola stanu bazy nie powiodła się", exc_info=True)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="degraded", database="unavailable")
    return HealthResponse(status="ok", database="ok")
