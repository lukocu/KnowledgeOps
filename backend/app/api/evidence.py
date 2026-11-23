"""Endpointy dowodu i migawki: opis korpusu, okno dowodu i cały dokument."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import psycopg
import psycopg_pool
from fastapi import APIRouter, HTTPException, Query, status
from psycopg import AsyncConnection

from app.db import PoolDep
from app.retrieval import (
    CorpusInfo,
    DocumentText,
    EvidenceWindow,
    get_corpus_info,
    get_document,
    get_evidence_window,
)
from app.settings import Settings

CONNECTION_TIMEOUT_S = 5.0
MAX_CONTEXT_CHUNKS = 5

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["evidence"])


@asynccontextmanager
async def _connection(pool: PoolDep) -> AsyncIterator[AsyncConnection]:
    """Połączenie z puli; niedostępna baza daje 503."""
    try:
        async with pool.connection(timeout=CONNECTION_TIMEOUT_S) as conn:
            yield conn
    except (psycopg.OperationalError, psycopg_pool.PoolTimeout) as exc:
        logger.warning("Baza niedostępna", exc_info=True)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Baza danych jest niedostępna"
        ) from exc


@router.get(
    "/corpus",
    response_model=CorpusInfo,
    responses={404: {"description": "Zestaw fragmentów nie został zaimportowany"}},
)
async def corpus(pool: PoolDep) -> CorpusInfo:
    chunk_set_id = Settings().effective_chunk_set_id()
    async with _connection(pool) as conn:
        try:
            return await get_corpus_info(conn, chunk_set_id)
        except LookupError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get(
    "/evidence",
    response_model=EvidenceWindow,
    responses={404: {"description": "Nieznany fragment"}},
)
async def evidence(
    pool: PoolDep,
    chunk_id: str,
    before: Annotated[int, Query(ge=0, le=MAX_CONTEXT_CHUNKS)] = 1,
    after: Annotated[int, Query(ge=0, le=MAX_CONTEXT_CHUNKS)] = 1,
) -> EvidenceWindow:
    async with _connection(pool) as conn:
        window = await get_evidence_window(conn, chunk_id, before=before, after=after)
    if window is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nieznany fragment")
    return window


@router.get(
    "/documents",
    response_model=DocumentText,
    responses={404: {"description": "Nieznany dokument"}},
)
async def document(pool: PoolDep, snapshot_id: str, doc_id: str) -> DocumentText:
    chunk_set_id = Settings().effective_chunk_set_id()
    async with _connection(pool) as conn:
        result = await get_document(
            conn, snapshot_id, doc_id, chunk_set_id=chunk_set_id
        )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nieznany dokument")
    return result
