"""Endpointy audytu notatek ze spraw: zlecenie, odczyt postępu/wyniku i decyzje."""

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
    AuditEventActor,
    AuditEventType,
    AuditNotCompletedError,
    AuditNotFoundError,
    AuditSourceFilter,
    AuditStatus,
    DecisionCategory,
    DecisionStatus,
    RoleLabel,
    StoredAudit,
    StoredAuditEvent,
    StoredAuditListItem,
    StoredAuditListResult,
    StoredClaimDecision,
    compute_decision_status,
    create_audit,
    get_audit_for_session,
    list_audits_for_session,
    upsert_claim_decision,
)
from app.db import PoolDep, http_connection
from app.retrieval import get_corpus_info, resolve_active_chunk_set_ids
from app.session import OptionalSessionDep, SessionDep
from app.settings import SettingsDep

logger = logging.getLogger(__name__)

MAX_CASE_REF_LENGTH = 120
MAX_CASE_TEXT_LENGTH = 4000
MAX_JUSTIFICATION_LENGTH = 2000

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


class SaveClaimDecisionRequest(BaseModel):
    """Wejście zapisu lub edycji decyzji redaktora dla pojedynczej tezy."""

    decision: DecisionCategory
    justification: str = Field(min_length=1, max_length=MAX_JUSTIFICATION_LENGTH)
    role_label: RoleLabel = "editor"

    @field_validator("justification")
    @classmethod
    def _reject_blank_justification(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError(
                "Uzasadnienie nie może składać się wyłącznie z białych znaków."
            )
        return stripped


class ClaimDecisionResponse(BaseModel):
    """Bieżąca decyzja redaktora zapisana dla pojedynczej tezy audytu."""

    decision: DecisionCategory
    justification: str
    role_label: RoleLabel
    created_at: datetime
    updated_at: datetime


class AuditHistoryEventResponse(BaseModel):
    """Niemutowalne zdarzenie w historii cyklu życia audytu."""

    event_id: str
    event_type: AuditEventType
    actor_type: AuditEventActor
    role_label: RoleLabel | None = None
    claim_id: str | None = None
    claim_index: int | None = None
    decision: DecisionCategory | None = None
    note_verdict: NoteVerdict | None = None
    claims_total: int | None = None
    created_at: datetime


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
    decision: ClaimDecisionResponse | None = None


class AuditDetailResponse(BaseModel):
    """Pełny stan audytu (w kolejce, w toku, zakończony lub błędny)."""

    audit_id: str
    is_demo: bool
    case_ref: str | None
    case_description: str
    resolution_note: str
    status: AuditStatus
    stage: AuditStage
    decision_status: DecisionStatus
    decisions_count: int
    claims_total: int
    claims_done: int
    note_verdict: NoteVerdict | None
    case_context: CaseContext | None
    claims: list[AuditClaimResponse]
    history: list[AuditHistoryEventResponse]
    snapshot_id: str
    chunk_set_ids: list[str]
    include_synthetic: bool
    config: dict[str, Any]
    error: str | None
    duration_ms: int | None
    created_at: datetime
    completed_at: datetime | None


class AuditListItemResponse(BaseModel):
    """Wiersz listy analiz w odpowiedzi `GET /api/audits`."""

    audit_id: str
    is_demo: bool
    case_ref: str | None
    problem_summary: str
    status: AuditStatus
    stage: AuditStage
    note_verdict: NoteVerdict | None
    claims_total: int
    claims_done: int
    claims_supported: int
    claims_contradicted: int
    claims_insufficient: int
    decisions_count: int
    decision_status: DecisionStatus
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime


class AuditListSummaryResponse(BaseModel):
    """Podsumowanie pełnego zbioru analiz widocznego dla sesji (przed filtrami)."""

    demo_count: int
    session_count: int
    pending_count: int
    in_progress_count: int
    saved_count: int
    next_pending_audit_id: str | None = None
    next_pending_case_ref: str | None = None


class AuditListResponse(BaseModel):
    """Odpowiedź `GET /api/audits`: przefiltrowane wiersze i pełne podsumowanie."""

    items: list[AuditListItemResponse]
    summary: AuditListSummaryResponse


def _to_list_item_response(item: StoredAuditListItem) -> AuditListItemResponse:
    return AuditListItemResponse(
        audit_id=item.id,
        is_demo=item.is_demo,
        case_ref=item.case_ref,
        problem_summary=item.problem_summary,
        status=item.status,
        stage=item.stage,
        note_verdict=item.note_verdict,
        claims_total=item.claims_total,
        claims_done=item.claims_done,
        claims_supported=item.claims_supported,
        claims_contradicted=item.claims_contradicted,
        claims_insufficient=item.claims_insufficient,
        decisions_count=item.decisions_count,
        decision_status=item.decision_status,
        created_at=item.created_at,
        updated_at=item.updated_at,
        last_activity_at=item.last_activity_at,
    )


def _to_list_response(result: StoredAuditListResult) -> AuditListResponse:
    return AuditListResponse(
        items=[_to_list_item_response(item) for item in result.items],
        summary=AuditListSummaryResponse(
            demo_count=result.demo_count,
            session_count=result.session_count,
            pending_count=result.pending_count,
            in_progress_count=result.in_progress_count,
            saved_count=result.saved_count,
            next_pending_audit_id=result.next_pending_audit_id,
            next_pending_case_ref=result.next_pending_case_ref,
        ),
    )


def _to_claim_decision_response(
    decision: StoredClaimDecision | None,
) -> ClaimDecisionResponse | None:
    if decision is None:
        return None
    return ClaimDecisionResponse(
        decision=decision.decision,
        justification=decision.justification,
        role_label=decision.role_label,
        created_at=decision.created_at,
        updated_at=decision.updated_at,
    )


def _to_history_event_response(
    event: StoredAuditEvent,
) -> AuditHistoryEventResponse:
    raw_claim_index = (
        event.claim_index
        if event.claim_index is not None
        else event.payload.get("claim_index")
    )
    return AuditHistoryEventResponse.model_validate(
        {
            "event_id": event.id,
            "event_type": event.event_type,
            "actor_type": event.actor_type,
            "role_label": event.role_label,
            "claim_id": event.claim_id,
            "claim_index": raw_claim_index,
            "decision": event.payload.get("decision"),
            "note_verdict": event.payload.get("note_verdict"),
            "claims_total": event.payload.get("claims_total"),
            "created_at": event.created_at,
        }
    )


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
            decision=_to_claim_decision_response(claim.decision),
        )
        for claim in stored.claims
    ]
    decisions_count = sum(1 for claim in stored.claims if claim.decision is not None)
    decision_status = compute_decision_status(
        stored.status, stored.claims_total, decisions_count
    )
    history = [_to_history_event_response(event) for event in stored.history]
    return AuditDetailResponse(
        audit_id=stored.id,
        is_demo=stored.is_demo,
        case_ref=stored.case_ref,
        case_description=stored.case_description,
        resolution_note=stored.resolution_note,
        status=stored.status,
        stage=stored.stage,
        decision_status=decision_status,
        decisions_count=decisions_count,
        claims_total=stored.claims_total,
        claims_done=stored.claims_done,
        note_verdict=stored.note_verdict,
        case_context=case_context,
        claims=claims,
        history=history,
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
    "/audits",
    response_model=AuditListResponse,
)
async def list_audits_endpoint(
    pool: PoolDep,
    session_hash: OptionalSessionDep,
    q: str | None = None,
    decision_status: DecisionStatus | None = None,
    note_verdict: NoteVerdict | None = None,
    source: AuditSourceFilter = "all",
) -> AuditListResponse:
    async with http_connection(pool) as conn:
        result = await list_audits_for_session(
            conn,
            session_hash,
            q=q,
            decision_status=decision_status,
            note_verdict=note_verdict,
            source=source,
        )
    return _to_list_response(result)


@router.get(
    "/audits/{audit_id}",
    response_model=AuditDetailResponse,
    responses={404: {"description": "Brak analizy w tej sesji"}},
)
async def get_audit_endpoint(
    audit_id: str,
    pool: PoolDep,
    session_hash: OptionalSessionDep,
) -> AuditDetailResponse:
    async with http_connection(pool) as conn:
        stored = await get_audit_for_session(conn, audit_id, session_hash)
    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono analizy")
    return _to_detail_response(stored)


@router.put(
    "/audits/{audit_id}/claims/{claim_id}/decision",
    response_model=AuditDetailResponse,
    responses={
        404: {"description": "Brak analizy lub tezy w tej sesji"},
        409: {"description": "Analiza nie jest zakończona"},
    },
)
async def save_claim_decision_endpoint(
    audit_id: str,
    claim_id: str,
    body: SaveClaimDecisionRequest,
    pool: PoolDep,
    session_hash: SessionDep,
) -> AuditDetailResponse:
    async with http_connection(pool) as conn:
        try:
            await upsert_claim_decision(
                conn,
                audit_id=audit_id,
                claim_id=claim_id,
                session_hash=session_hash,
                decision=body.decision,
                justification=body.justification,
                role_label=body.role_label,
            )
        except AuditNotFoundError as exc:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Nie znaleziono analizy lub tezy"
            ) from exc
        except AuditNotCompletedError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Decyzję można zapisać wyłącznie dla zakończonej analizy.",
            ) from exc
        stored = await get_audit_for_session(conn, audit_id, session_hash)
    if stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono analizy")
    return _to_detail_response(stored)
