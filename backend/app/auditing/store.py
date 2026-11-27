"""Repozytorium SQL dla audytów notatek ze spraw i ich zweryfikowanych tez."""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

AuditStatus = Literal["queued", "running", "completed", "failed"]
AuditStage = Literal[
    "queued",
    "extracting",
    "retrieving",
    "verifying",
    "aggregating",
    "completed",
    "failed",
]
NoteVerdict = Literal["full", "partial", "contradiction", "insufficient"]
ClaimVerdict = Literal["supported", "contradicted", "insufficient"]
DecisionCategory = Literal[
    "agree_with_system",
    "request_source_or_verify",
    "consider_doc_update",
    "system_verdict_wrong",
]
RoleLabel = Literal["editor", "consultant"]
AuditEventType = Literal[
    "audit_created",
    "evaluation_completed",
    "evaluation_failed",
    "decision_saved",
    "decision_updated",
]
AuditEventActor = Literal["system", "human"]
DecisionStatus = Literal["pending", "in_progress", "saved", "not_applicable"]


class AuditNotFoundError(LookupError):
    """Audyt lub teza nie istnieje albo nie należy do bieżącej sesji."""


class AuditNotCompletedError(RuntimeError):
    """Audyt nie jest zakończony i nie można zapisać dla niego decyzji."""


class StoredClaimDecision(BaseModel):
    """Bieżąca decyzja redaktora zapisana dla pojedynczej tezy audytu."""

    id: str
    audit_id: str
    claim_id: str
    decision: DecisionCategory
    justification: str
    role_label: RoleLabel
    created_at: datetime
    updated_at: datetime


class StoredAuditEvent(BaseModel):
    """Niemutowalne zdarzenie w historii cyklu życia audytu."""

    id: str
    audit_id: str
    claim_id: str | None = None
    claim_index: int | None = None
    event_type: AuditEventType
    actor_type: AuditEventActor
    role_label: RoleLabel | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class NewAuditClaim(BaseModel):
    """Dane zweryfikowanej tezy do zapisu przy zakończeniu audytu."""

    claim_index: int
    claim_label: str
    claim_text: str
    source_excerpt: str
    source_start: int | None = None
    source_end: int | None = None
    search_query: str
    verdict: ClaimVerdict
    rationale: str
    scope_note: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    checked_docs: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    id: str | None = None


class StoredAuditClaim(BaseModel):
    """Zapisana w bazie teza audytu."""

    id: str
    audit_id: str
    claim_index: int
    claim_label: str
    claim_text: str
    source_excerpt: str
    source_start: int | None = None
    source_end: int | None = None
    search_query: str
    verdict: ClaimVerdict
    rationale: str
    scope_note: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    checked_docs: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
    decision: StoredClaimDecision | None = None


class StoredAudit(BaseModel):
    """Pełny rekord audytu odczytany z bazy razem z uporządkowanymi tezami."""

    id: str
    session_hash: str
    is_demo: bool
    case_ref: str | None
    case_description: str
    resolution_note: str
    status: AuditStatus
    stage: AuditStage
    claims_total: int
    claims_done: int
    note_verdict: NoteVerdict | None
    case_context: dict[str, Any] | None
    snapshot_id: str
    chunk_set_ids: list[str]
    config: dict[str, Any]
    error: str | None
    trace_id: str | None
    duration_ms: int | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    claims: list[StoredAuditClaim] = Field(default_factory=list)
    history: list[StoredAuditEvent] = Field(default_factory=list)


async def _insert_audit_event(
    conn: AsyncConnection,
    *,
    audit_id: str,
    event_type: AuditEventType,
    actor_type: AuditEventActor,
    claim_id: str | None = None,
    session_hash: str | None = None,
    role_label: RoleLabel | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Dopisuje niemutowalne zdarzenie do `audit_events` w bieżącej transakcji."""
    await conn.execute(
        "INSERT INTO audit_events ("
        " id, audit_id, claim_id, session_hash, event_type,"
        " actor_type, role_label, payload"
        ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (
            str(uuid.uuid4()),
            audit_id,
            claim_id,
            session_hash,
            event_type,
            actor_type,
            role_label,
            Jsonb(payload if payload is not None else {}),
        ),
    )


async def create_audit(
    conn: AsyncConnection,
    *,
    session_hash: str,
    case_description: str,
    resolution_note: str,
    snapshot_id: str,
    chunk_set_ids: Sequence[str],
    config: dict[str, Any],
    case_ref: str | None = None,
    is_demo: bool = False,
    audit_id: str | None = None,
) -> str:
    """Tworzy nowy wiersz audytu w stanie `queued` i zwraca jego identyfikator."""
    resolved_id = audit_id or str(uuid.uuid4())
    async with conn.transaction():
        await conn.execute(
            "INSERT INTO audits ("
            " id, session_hash, is_demo, case_ref, case_description,"
            " resolution_note, status, stage, snapshot_id, chunk_set_ids, config"
            ") VALUES (%s, %s, %s, %s, %s, %s, 'queued', 'queued', %s, %s, %s)",
            (
                resolved_id,
                session_hash,
                is_demo,
                case_ref,
                case_description,
                resolution_note,
                snapshot_id,
                list(chunk_set_ids),
                Jsonb(config),
            ),
        )
        await _insert_audit_event(
            conn,
            audit_id=resolved_id,
            event_type="audit_created",
            actor_type="system",
            payload={"case_ref": case_ref},
        )
    return resolved_id


async def update_audit_progress(
    conn: AsyncConnection,
    audit_id: str,
    *,
    stage: AuditStage,
    status: AuditStatus = "running",
    claims_total: int | None = None,
    claims_done: int | None = None,
    case_context: dict[str, Any] | None = None,
) -> None:
    """Aktualizuje etap, status i liczniki postępu trwającego audytu."""
    async with conn.transaction():
        await conn.execute(
            "UPDATE audits"
            " SET status = %s,"
            "     stage = %s,"
            "     claims_total = COALESCE(%s, claims_total),"
            "     claims_done = COALESCE(%s, claims_done),"
            "     case_context = COALESCE(%s, case_context),"
            "     updated_at = now()"
            " WHERE id = %s",
            (
                status,
                stage,
                claims_total,
                claims_done,
                Jsonb(case_context) if case_context is not None else None,
                audit_id,
            ),
        )


async def complete_audit(
    conn: AsyncConnection,
    audit_id: str,
    *,
    claims: Sequence[NewAuditClaim],
    note_verdict: NoteVerdict,
    case_context: dict[str, Any] | None = None,
    trace_id: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """Atomowo zapisuje tezy audytu i oznacza audyt jako `completed`.

    Tezy są zapisywane przed zmianą `audits.status` na `completed` w tej samej
    transakcji, więc klient odpytujący nigdy nie zobaczy `completed` bez tez.
    """
    total = len(claims)
    async with conn.transaction():
        for claim in claims:
            claim_id = claim.id or str(uuid.uuid4())
            await conn.execute(
                "INSERT INTO audit_claims ("
                " id, audit_id, claim_index, claim_label, claim_text,"
                " source_excerpt, source_start, source_end, search_query,"
                " verdict, rationale, scope_note, evidence, checked_docs, error"
                ") VALUES ("
                " %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s"
                ")",
                (
                    claim_id,
                    audit_id,
                    claim.claim_index,
                    claim.claim_label,
                    claim.claim_text,
                    claim.source_excerpt,
                    claim.source_start,
                    claim.source_end,
                    claim.search_query,
                    claim.verdict,
                    claim.rationale,
                    claim.scope_note,
                    Jsonb(claim.evidence),
                    Jsonb(claim.checked_docs),
                    claim.error,
                ),
            )
        await conn.execute(
            "UPDATE audits"
            " SET status = 'completed',"
            "     stage = 'completed',"
            "     note_verdict = %s,"
            "     case_context = COALESCE(%s, case_context),"
            "     claims_total = %s,"
            "     claims_done = %s,"
            "     error = NULL,"
            "     trace_id = COALESCE(%s, trace_id),"
            "     duration_ms = COALESCE(%s, duration_ms),"
            "     updated_at = now(),"
            "     completed_at = now()"
            " WHERE id = %s",
            (
                note_verdict,
                Jsonb(case_context) if case_context is not None else None,
                total,
                total,
                trace_id,
                duration_ms,
                audit_id,
            ),
        )
        await _insert_audit_event(
            conn,
            audit_id=audit_id,
            event_type="evaluation_completed",
            actor_type="system",
            payload={"note_verdict": note_verdict, "claims_total": total},
        )


async def fail_audit(
    conn: AsyncConnection,
    audit_id: str,
    *,
    error: str,
    trace_id: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """Oznacza audyt jako zakończony błędem."""
    async with conn.transaction():
        await conn.execute(
            "UPDATE audits"
            " SET status = 'failed',"
            "     stage = 'failed',"
            "     error = %s,"
            "     trace_id = COALESCE(%s, trace_id),"
            "     duration_ms = COALESCE(%s, duration_ms),"
            "     updated_at = now()"
            " WHERE id = %s",
            (error, trace_id, duration_ms, audit_id),
        )
        await _insert_audit_event(
            conn,
            audit_id=audit_id,
            event_type="evaluation_failed",
            actor_type="system",
            payload={},
        )


async def fail_orphaned_audits(
    conn: AsyncConnection,
    reason: str = "Analiza została przerwana przez restart serwera.",
) -> int:
    """Oznacza osierocone audyty (`queued`/`running`) jako `failed`."""
    async with conn.transaction():
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE audits"
                " SET status = 'failed',"
                "     stage = 'failed',"
                "     error = %s,"
                "     updated_at = now()"
                " WHERE status IN ('queued', 'running')"
                " RETURNING id::text",
                (reason,),
            )
            rows = await cur.fetchall()
        for row in rows:
            await _insert_audit_event(
                conn,
                audit_id=str(row[0]),
                event_type="evaluation_failed",
                actor_type="system",
                payload={"orphaned": True},
            )
        return len(rows)


async def upsert_claim_decision(
    conn: AsyncConnection,
    *,
    audit_id: str,
    claim_id: str,
    session_hash: str,
    decision: DecisionCategory,
    justification: str,
    role_label: RoleLabel,
) -> Literal["saved", "updated"]:
    """Zapisuje lub aktualizuje decyzję redaktora dla tezy i dopisuje zdarzenie."""
    try:
        uuid.UUID(audit_id)
        uuid.UUID(claim_id)
    except ValueError as exc:
        raise AuditNotFoundError(
            "Nieprawidłowy identyfikator audytu lub tezy."
        ) from exc

    async with conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT status"
                " FROM audits"
                " WHERE id = %s AND (is_demo = true OR session_hash = %s)",
                (audit_id, session_hash),
            )
            audit_row = await cur.fetchone()
            if audit_row is None:
                raise AuditNotFoundError(f"Nie znaleziono audytu {audit_id}.")
            if audit_row["status"] != "completed":
                raise AuditNotCompletedError(
                    f"Audyt {audit_id} ma status '{audit_row['status']}', "
                    "decyzje można zapisywać tylko dla zakończonych audytów."
                )
            await cur.execute(
                "SELECT claim_index FROM audit_claims WHERE id = %s AND audit_id = %s",
                (claim_id, audit_id),
            )
            claim_row = await cur.fetchone()
            if claim_row is None:
                raise AuditNotFoundError(
                    f"Nie znaleziono tezy {claim_id} w audycie {audit_id}."
                )
            claim_index = int(claim_row["claim_index"])
            await cur.execute(
                "INSERT INTO audit_claim_decisions ("
                " id, audit_id, claim_id, session_hash,"
                " decision, justification, role_label"
                ") VALUES (%s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (claim_id, session_hash) DO UPDATE"
                " SET decision = EXCLUDED.decision,"
                "     justification = EXCLUDED.justification,"
                "     role_label = EXCLUDED.role_label,"
                "     updated_at = now()"
                " RETURNING (xmax = 0) AS inserted",
                (
                    str(uuid.uuid4()),
                    audit_id,
                    claim_id,
                    session_hash,
                    decision,
                    justification,
                    role_label,
                ),
            )
            upsert_row = await cur.fetchone()
            inserted = bool(upsert_row["inserted"]) if upsert_row is not None else False
        event_type: AuditEventType = (
            "decision_saved" if inserted else "decision_updated"
        )
        await _insert_audit_event(
            conn,
            audit_id=audit_id,
            claim_id=claim_id,
            session_hash=session_hash,
            event_type=event_type,
            actor_type="human",
            role_label=role_label,
            payload={"decision": decision, "claim_index": claim_index},
        )
        return "saved" if inserted else "updated"


async def get_audit_for_session(
    conn: AsyncConnection,
    audit_id: str,
    session_hash: str | None,
) -> StoredAudit | None:
    """Zwraca audyt z uporządkowanymi tezami dla danej sesji albo `None`.

    Rekordy z `is_demo = true` są widoczne niezależnie od `session_hash`;
    pozostałe wymagają zgodności `session_hash`.
    """
    try:
        uuid.UUID(audit_id)
    except ValueError:
        return None
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT id::text AS id, session_hash, is_demo, case_ref,"
            " case_description, resolution_note, status, stage,"
            " claims_total, claims_done, note_verdict, case_context,"
            " snapshot_id, chunk_set_ids, config, error, trace_id,"
            " duration_ms, created_at, updated_at, completed_at"
            " FROM audits"
            " WHERE id = %s AND (is_demo = true OR session_hash = %s)",
            (audit_id, session_hash),
        )
        audit_row = await cur.fetchone()
        if audit_row is None:
            return None
        await cur.execute(
            "SELECT id::text AS id, audit_id::text AS audit_id, claim_index,"
            " claim_label, claim_text, source_excerpt, source_start,"
            " source_end, search_query, verdict, rationale, scope_note,"
            " evidence, checked_docs, error"
            " FROM audit_claims"
            " WHERE audit_id = %s"
            " ORDER BY claim_index",
            (audit_id,),
        )
        claim_rows = await cur.fetchall()
        decisions_by_claim: dict[str, dict[str, Any]] = {}
        if session_hash is not None:
            await cur.execute(
                "SELECT id::text AS id, audit_id::text AS audit_id,"
                " claim_id::text AS claim_id, decision, justification,"
                " role_label, created_at, updated_at"
                " FROM audit_claim_decisions"
                " WHERE audit_id = %s AND session_hash = %s",
                (audit_id, session_hash),
            )
            decision_rows = await cur.fetchall()
            decisions_by_claim = {str(row["claim_id"]): row for row in decision_rows}
        await cur.execute(
            "SELECT e.id::text AS id, e.audit_id::text AS audit_id,"
            " e.claim_id::text AS claim_id, c.claim_index AS claim_index,"
            " e.event_type, e.actor_type, e.role_label, e.payload, e.created_at"
            " FROM audit_events AS e"
            " LEFT JOIN audit_claims AS c ON c.id = e.claim_id"
            " WHERE e.audit_id = %s"
            "   AND (e.actor_type = 'system' OR e.session_hash = %s)"
            " ORDER BY e.created_at ASC, e.seq ASC",
            (audit_id, session_hash),
        )
        event_rows = await cur.fetchall()
    enriched_claims = [
        {**claim_row, "decision": decisions_by_claim.get(str(claim_row["id"]))}
        for claim_row in claim_rows
    ]
    return StoredAudit.model_validate(
        {**audit_row, "claims": enriched_claims, "history": event_rows}
    )
