"""Endpointy dowodu i migawki: opis korpusu, okno dowodu i cały dokument."""

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.db import PoolDep, http_connection
from app.retrieval import (
    CorpusInfo,
    DocumentText,
    EvidenceWindow,
    get_corpus_info,
    get_document,
    get_evidence_window,
)
from app.settings import SettingsDep
from app.synthetic.importer import SYNTHETIC_SNAPSHOT_ID

MAX_CONTEXT_CHUNKS = 5

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["evidence"])

ContextChunks = Annotated[int | None, Query(ge=0, le=MAX_CONTEXT_CHUNKS)]


@router.get(
    "/corpus",
    response_model=CorpusInfo,
    responses={404: {"description": "Zestaw fragmentów nie został zaimportowany"}},
)
async def corpus(pool: PoolDep, settings: SettingsDep) -> CorpusInfo:
    chunk_set_id = settings.effective_chunk_set_id()
    async with http_connection(pool) as conn:
        try:
            return await get_corpus_info(conn, chunk_set_id)
        except LookupError as exc:
            logger.warning("Brak zestawu fragmentów: %s", exc)
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Zestaw fragmentów nie został zaimportowany"
            ) from exc


@router.get(
    "/evidence",
    response_model=EvidenceWindow,
    responses={404: {"description": "Nieznany fragment"}},
)
async def evidence(
    pool: PoolDep,
    settings: SettingsDep,
    chunk_id: str,
    before: ContextChunks = None,
    after: ContextChunks = None,
) -> EvidenceWindow:
    """Okno dowodu; bez `before`/`after` sąsiedztwo z `EVIDENCE_CONTEXT_CHUNKS`."""
    default = min(settings.evidence_context_chunks, MAX_CONTEXT_CHUNKS)
    async with http_connection(pool) as conn:
        window = await get_evidence_window(
            conn,
            chunk_id,
            before=default if before is None else before,
            after=default if after is None else after,
        )
    if window is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nieznany fragment")
    return window


@router.get(
    "/documents",
    response_model=DocumentText,
    responses={404: {"description": "Nieznany dokument"}},
)
async def document(
    pool: PoolDep, settings: SettingsDep, snapshot_id: str, doc_id: str
) -> DocumentText:
    base_chunk_set_id = settings.effective_chunk_set_id()
    chunk_set_id: str | None
    if snapshot_id == SYNTHETIC_SNAPSHOT_ID:
        chunk_set_id = settings.effective_synthetic_chunk_set_id()
    elif snapshot_id == base_chunk_set_id.rsplit("/", 1)[0]:
        chunk_set_id = base_chunk_set_id
    else:
        chunk_set_id = None  # inna migawka: fragmenty wszystkich jej zestawów
    async with http_connection(pool) as conn:
        result = await get_document(
            conn, snapshot_id, doc_id, chunk_set_id=chunk_set_id
        )
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nieznany dokument")
    return result
