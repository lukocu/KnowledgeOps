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
                " WHERE status IN ('queued', 'running')",
                (reason,),
            )
            return cur.rowcount


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
    return StoredAudit.model_validate({**audit_row, "claims": claim_rows})
