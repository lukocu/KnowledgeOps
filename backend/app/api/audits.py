"""Endpointy audytu notatek ze spraw: zlecenie analizy i odczyt postępu/wyniku."""

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.answering.model import ModelNotConfiguredError
from app.api.answers import ChatModelFactoryDep
from app.auditing.prompts import prompt_versions
from app.auditing.runner import AuditTaskManagerDep
from app.auditing.schemas import (
    AuditStage,
    CaseContext,
    CheckedDoc,
    ClaimEvidence,
    ClaimVerdict,
    NoteVerdict,
)
from app.auditing.store import (
    AuditStatus,
    StoredAudit,
    create_audit,
    get_audit_for_session,
)
from app.db import PoolDep, http_connection
from app.retrieval import get_corpus_info, resolve_active_chunk_set_ids
from app.session import AuditSessionDep, SessionDep
from app.settings import SettingsDep

logger = logging.getLogger(__name__)

MAX_CASE_REF_LENGTH = 120
MAX_CASE_TEXT_LENGTH = 4000

router = APIRouter(prefix="/api", tags=["audits"])


class CreateAuditRequest(BaseModel):
    """Wejście zlecenia audytu notatki ze sprawy."""

    case_ref: str | None = Field(default=None, max_length=MAX_CASE_REF_LENGTH)
    case_description: str = Field(min_length=1, max_length=MAX_CASE_TEXT_LENGTH)
    resolution_note: str = Field(min_length=1, max_length=MAX_CASE_TEXT_LENGTH)

    @field_validator("case_ref")
    @classmethod
    def _normalize_case_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("case_description", "resolution_note")
    @classmethod
    def _reject_blank_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Pole nie może składać się wyłącznie z białych znaków.")
        return stripped


class CreateAuditResponse(BaseModel):
    """Odpowiedź po przyjęciu audytu do kolejki (`202 Accepted`)."""

    audit_id: str
    status: AuditStatus
    stage: AuditStage


class AuditClaimResponse(BaseModel):
    """Pojedyncza zweryfikowana teza w odpowiedzi `GET /api/audits/{audit_id}`."""

    claim_id: str
    claim_index: int
    claim_label: str
    claim_text: str
    source_excerpt: str
    source_start: int | None
    source_end: int | None
    verdict: ClaimVerdict
    rationale: str
    scope_note: str | None
    evidence: list[ClaimEvidence]
    checked_docs: list[CheckedDoc]
    error: str | None


class AuditDetailResponse(BaseModel):
    """Pełny stan audytu (w kolejce, w toku, zakończony lub błędny)."""

    audit_id: str
    case_ref: str | None
    case_description: str
    resolution_note: str
    status: AuditStatus
    stage: AuditStage
    claims_total: int
    claims_done: int
    note_verdict: NoteVerdict | None
    case_context: CaseContext | None
    claims: list[AuditClaimResponse]
    snapshot_id: str
    chunk_set_ids: list[str]
    include_synthetic: bool
    config: dict[str, Any]
    error: str | None
    duration_ms: int | None
    created_at: datetime
    completed_at: datetime | None


def _to_detail_response(stored: StoredAudit) -> AuditDetailResponse:
    include_synthetic = bool(
        stored.config.get("include_synthetic", len(stored.chunk_set_ids) > 1)
    )
    case_context = (
        CaseContext.model_validate(stored.case_context)
        if stored.case_context is not None
        else None
    )
    claims = [
        AuditClaimResponse(
            claim_id=claim.id,
            claim_index=claim.claim_index,
            claim_label=claim.claim_label,
            claim_text=claim.claim_text,
            source_excerpt=claim.source_excerpt,
            source_start=claim.source_start,
            source_end=claim.source_end,
            verdict=claim.verdict,
            rationale=claim.rationale,
            scope_note=claim.scope_note,
            evidence=[ClaimEvidence.model_validate(item) for item in claim.evidence],
            checked_docs=[
                CheckedDoc.model_validate(item) for item in claim.checked_docs
            ],
            error=claim.error,
        )
        for claim in stored.claims
    ]
    return AuditDetailResponse(
        audit_id=stored.id,
        case_ref=stored.case_ref,
        case_description=stored.case_description,
        resolution_note=stored.resolution_note,
        status=stored.status,
        stage=stored.stage,
        claims_total=stored.claims_total,
        claims_done=stored.claims_done,
        note_verdict=stored.note_verdict,
        case_context=case_context,
        claims=claims,
        snapshot_id=stored.snapshot_id,
        chunk_set_ids=stored.chunk_set_ids,
        include_synthetic=include_synthetic,
        config=stored.config,
        error=stored.error,
        duration_ms=stored.duration_ms,
        created_at=stored.created_at,
        completed_at=stored.completed_at,
    )


@router.post(
    "/audits",
    response_model=CreateAuditResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        503: {
            "description": (
                "Brak konfiguracji modelu, niedostępna baza danych lub brak migawki."
            )
        }
    },
)
async def create_audit_endpoint(
    body: CreateAuditRequest,
    pool: PoolDep,
    session_hash: SessionDep,
    settings: SettingsDep,
    chat_model_factory: ChatModelFactoryDep,
    audit_tasks: AuditTaskManagerDep,
) -> CreateAuditResponse:
    try:
        chat_model = chat_model_factory(settings)
    except ModelNotConfiguredError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Brak klucza modelu (OPENAI_API_KEY) w konfiguracji.",
        ) from exc

    chunk_set_id = settings.effective_chunk_set_id()
    include_synthetic = settings.include_synthetic
    synthetic_chunk_set_id = settings.effective_synthetic_chunk_set_id()

    async with http_connection(pool) as conn:
        try:
            corpus = await get_corpus_info(conn, chunk_set_id)
        except LookupError as exc:
            logger.warning("Brak zestawu fragmentów: %s", exc)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Zestaw fragmentów nie został zaimportowany.",
            ) from exc

        chunk_set_ids = await resolve_active_chunk_set_ids(
            conn,
            chunk_set_id,
            include_synthetic=include_synthetic,
            synthetic_chunk_set_id=synthetic_chunk_set_id,
        )
        config: dict[str, Any] = {
            "chat_model": settings.chat_model,
            "chat_reasoning_effort": settings.chat_reasoning_effort,
            "k": settings.audit_k,
            "chunk_set_id": chunk_set_id,
            "chunk_set_ids": chunk_set_ids,
            "include_synthetic": include_synthetic,
            "audit_max_claims": settings.audit_max_claims,
            "audit_claim_concurrency": settings.audit_claim_concurrency,
            "prompt_versions": prompt_versions(),
        }
        audit_id = await create_audit(
            conn,
            session_hash=session_hash,
            case_ref=body.case_ref,
            case_description=body.case_description,
            resolution_note=body.resolution_note,
            snapshot_id=corpus.snapshot_id,
            chunk_set_ids=chunk_set_ids,
            config=config,
        )

    audit_tasks.schedule(
        audit_id,
        pool=pool,
        settings=settings,
        chat_model=chat_model,
        case_description=body.case_description,
        resolution_note=body.resolution_note,
        chunk_set_id=chunk_set_id,
        include_synthetic=include_synthetic,
        k=settings.audit_k,
    )
    return CreateAuditResponse(audit_id=audit_id, status="queued", stage="queued")


@router.get(
    "/audits/{audit_id}",
    response_model=AuditDetailResponse,
    responses={404: {"description": "Brak analizy w tej sesji"}},
)
async def get_audit_endpoint(
    audit_id: str,
    pool: PoolDep,
    session_hash: AuditSessionDep,
) -> AuditDetailResponse:
    async with http_connection(pool) as conn:
        stored = await get_audit_for_session(conn, audit_id, session_hash)
    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono analizy")
    return _to_detail_response(stored)
