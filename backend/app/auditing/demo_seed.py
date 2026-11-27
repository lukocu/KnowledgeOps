"""Idempotentny seeder przykładów demo audytów (`import-demo-audits`).

Ładuje autorskie definicje spraw z `demo_audits.json` (bez surowego tekstu TechQA),
rozwiązuje fragmenty dowodów i dosłowne cytaty z lokalnej migawki TechQA w bazie
danych, a następnie atomowo zapisuje rekordy `is_demo = true` bez usuwania
zapisanych decyzji użytkowników z `audit_claim_decisions`.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, ValidationError

from app.answering.nodes import locate_quote
from app.auditing.schemas import (
    CaseContext,
    CheckedDoc,
    ClaimEvidence,
    ClaimVerdict,
    NoteVerdict,
)
from app.techqa.importer import Comparison

DEMO_AUDITS_VERSION = "demo-audits@v1"
DEMO_AUDITS_PATH = Path(__file__).resolve().parent / "demo_audits.json"

# Stały klucz blokady doradczej (osobny od TechQA 7_204_001 i synthetic 7_204_002).
DEMO_AUDITS_LOCK_KEY = 7_204_003
DEMO_UUID_NAMESPACE = uuid.UUID("9c7e2b6a-4c3a-5f8d-9b1e-0a4d6f8e2c1b")
DEMO_SESSION_HASH = "demo"
DEMO_BASE_TIMESTAMP = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
DEMO_DURATION_MS = 12_000
QUOTE_MAX_CHARS = 320


class DemoSeedError(Exception):
    """Nie można załadować lub zaseedować przykładów demo."""


class DemoEvidenceSpec(BaseModel):
    """Wskazanie dokumentu i krótkich fraz kotwicznych do wyboru chunku w TechQA."""

    doc_id: str = Field(min_length=1)
    anchor_terms: list[str] = Field(default_factory=list)


class DemoClaimSpec(BaseModel):
    """Definicja pojedynczej tezy w przykładzie demo."""

    claim_index: int = Field(ge=0)
    claim_label: str = Field(min_length=1)
    claim_text: str = Field(min_length=1)
    source_excerpt: str = Field(min_length=1)
    search_query: str = Field(min_length=1)
    verdict: ClaimVerdict
    rationale: str = Field(min_length=1)
    scope_note: str | None = None
    evidence_specs: list[DemoEvidenceSpec] = Field(default_factory=list)
    checked_doc_ids: list[str] = Field(default_factory=list)


class DemoAuditSpec(BaseModel):
    """Definicja pojedynczej sprawy pilotażowej demo."""

    slug: str = Field(min_length=1)
    case_ref: str = Field(min_length=1)
    case_description: str = Field(min_length=1)
    resolution_note: str = Field(min_length=1)
    note_verdict: NoteVerdict
    case_context: CaseContext
    created_offset_minutes: int = Field(ge=0)
    claims: list[DemoClaimSpec] = Field(min_length=1)


class DemoAuditsFile(BaseModel):
    """Struktura pliku `demo_audits.json`."""

    version: str
    audits: list[DemoAuditSpec] = Field(min_length=1)


@dataclass(frozen=True)
class DemoSeedReport:
    """Wynik uruchomienia seedera przykładów demo."""

    snapshot_id: str
    chunk_set_id: str
    audits_count: int
    claims_count: int
    state_sha256: str
    comparison: Comparison


@dataclass(frozen=True)
class _DocRow:
    doc_id: str
    title: str
    is_synthetic: bool


@dataclass(frozen=True)
class _ChunkRow:
    chunk_id: str
    doc_id: str
    ordinal: int
    headings: list[str]
    start_offset: int
    end_offset: int
    text: str


def demo_audit_id(slug: str) -> str:
    """Wyznacza deterministyczny UUIDv5 dla audytu demo na podstawie `slug`."""
    return str(uuid.uuid5(DEMO_UUID_NAMESPACE, f"audit:{slug}"))


def demo_claim_id(slug: str, claim_index: int) -> str:
    """Wyznacza deterministyczny UUIDv5 dla tezy demo na podstawie `slug:index`."""
    return str(uuid.uuid5(DEMO_UUID_NAMESPACE, f"claim:{slug}:{claim_index}"))


def demo_event_id(slug: str, event_type: str) -> str:
    """Wyznacza deterministyczny UUIDv5 dla początkowego zdarzenia systemowego."""
    return str(uuid.uuid5(DEMO_UUID_NAMESPACE, f"event:{slug}:{event_type}"))


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def load_demo_audits(path: Path = DEMO_AUDITS_PATH) -> list[DemoAuditSpec]:
    """Wczytuje i waliduje definicje spraw demo z pliku JSON."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        parsed = DemoAuditsFile.model_validate(raw)
    except (OSError, ValueError, ValidationError) as exc:
        raise DemoSeedError(f"Nieprawidłowy plik {path}: {exc}") from exc

    if parsed.version != DEMO_AUDITS_VERSION:
        raise DemoSeedError(
            f"Plik {path.name} ma wersję {parsed.version!r},"
            f" oczekiwano {DEMO_AUDITS_VERSION!r}."
        )

    slugs = [audit.slug for audit in parsed.audits]
    if len(set(slugs)) != len(slugs):
        raise DemoSeedError(f"Powtórzone wartości slug w {path.name}.")

    for audit in parsed.audits:
        indices = [claim.claim_index for claim in audit.claims]
        if len(set(indices)) != len(indices):
            raise DemoSeedError(
                f"Powtórzone claim_index w sprawie {audit.slug!r} ({path.name})."
            )

    return parsed.audits


def _select_best_chunk(
    chunks: Sequence[_ChunkRow], anchor_terms: Sequence[str]
) -> _ChunkRow:
    """Wybiera chunk o największej liczbie dopasowanych fraz kotwicznych."""
    if not chunks:
        raise DemoSeedError("Brak fragmentów dla wybranego dokumentu.")
    normalized_terms = [
        term.strip().casefold() for term in anchor_terms if term.strip()
    ]
    if not normalized_terms:
        return chunks[0]

    best_chunk = chunks[0]
    best_score = -1
    for chunk in chunks:
        lowered = chunk.text.casefold()
        score = sum(1 for term in normalized_terms if term in lowered)
        if score > best_score:
            best_score = score
            best_chunk = chunk
    return best_chunk


def _extract_quote_span(
    text: str,
    anchor_terms: Sequence[str],
    *,
    max_chars: int = QUOTE_MAX_CHARS,
) -> tuple[int, int]:
    """Wyznacza span `(start, end)` cytatu wokół pierwszej frazy kotwicznej."""
    if not text or not text.strip():
        return (0, 0)

    lowered = text.casefold()
    first_pos: int | None = None
    for term in anchor_terms:
        needle = term.strip().casefold()
        if not needle:
            continue
        pos = lowered.find(needle)
        if pos != -1 and (first_pos is None or pos < first_pos):
            first_pos = pos

    if len(text) <= max_chars:
        start, end = 0, len(text)
    elif first_pos is None:
        start, end = 0, max_chars
    else:
        half = max_chars // 2
        start = max(0, first_pos - half)
        end = min(len(text), start + max_chars)
        if end - start < max_chars:
            start = max(0, end - max_chars)

        if start > 0:
            ws = text.find(" ", start, min(end, start + 32))
            if ws != -1 and ws + 1 < end:
                start = ws + 1
        if end < len(text):
            ws = text.rfind(" ", max(start, end - 32), end)
            if ws != -1 and ws > start:
                end = ws

    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1

    if start >= end:
        stripped = text.strip()
        idx = text.find(stripped)
        return (idx, min(len(text), idx + max_chars))
    return (start, end)


def _demo_state_hash(conn: psycopg.Connection) -> str:
    """SHA-256 deterministycznego stanu wszystkich rekordów demo w bazie."""
    digest = hashlib.sha256()

    def feed(value: Any) -> None:
        digest.update(_canonical_json(value).encode("utf-8"))
        digest.update(b"\n")

    feed(["version", DEMO_AUDITS_VERSION])
    audit_rows = conn.execute(
        "SELECT id::text, session_hash, is_demo, case_ref, case_description,"
        " resolution_note, status, stage, claims_total, claims_done,"
        " note_verdict, case_context, snapshot_id, chunk_set_ids, config,"
        " duration_ms, created_at, updated_at, completed_at"
        ' FROM audits WHERE is_demo = true ORDER BY id::text COLLATE "C"'
    ).fetchall()
    for row in audit_rows:
        serialized = [
            item.isoformat() if isinstance(item, datetime) else item for item in row
        ]
        feed(["audit", *serialized])

    claim_rows = conn.execute(
        "SELECT c.id::text, c.audit_id::text, c.claim_index, c.claim_label,"
        " c.claim_text, c.source_excerpt, c.source_start, c.source_end,"
        " c.search_query, c.verdict, c.rationale, c.scope_note,"
        " c.evidence, c.checked_docs, c.error"
        " FROM audit_claims AS c"
        " JOIN audits AS a ON a.id = c.audit_id"
        " WHERE a.is_demo = true"
        ' ORDER BY c.audit_id::text COLLATE "C", c.claim_index ASC'
    ).fetchall()
    for row in claim_rows:
        feed(["claim", *row])

    return digest.hexdigest()


def _load_corpus_lookup(
    conn: psycopg.Connection,
    chunk_set_id: str,
    required_doc_ids: set[str],
) -> tuple[str, dict[str, _DocRow], dict[str, list[_ChunkRow]]]:
    """Weryfikuje istnienie migawki oraz pobiera dokumenty i fragmenty pilotażu."""
    cs_row = conn.execute(
        "SELECT snapshot_id FROM chunk_sets WHERE id = %s",
        (chunk_set_id,),
    ).fetchone()
    if cs_row is None:
        raise DemoSeedError(
            f"Brak zestawu fragmentów {chunk_set_id!r} w bazie danych. "
            "Najpierw zaimportuj korpus TechQA poleceniem: "
            "`python -m app.cli import-techqa`."
        )
    snapshot_id = str(cs_row[0])

    doc_ids_sorted = sorted(required_doc_ids)
    docs: dict[str, _DocRow] = {}
    if doc_ids_sorted:
        for row in conn.execute(
            "SELECT doc_id, title, is_synthetic"
            " FROM documents"
            " WHERE snapshot_id = %s AND doc_id = ANY(%s)",
            (snapshot_id, doc_ids_sorted),
        ).fetchall():
            doc_id = str(row[0])
            docs[doc_id] = _DocRow(
                doc_id=doc_id,
                title=str(row[1]),
                is_synthetic=bool(row[2]),
            )

    missing_docs = sorted(required_doc_ids - set(docs))
    if missing_docs:
        raise DemoSeedError(
            f"W migawce {snapshot_id!r} brakuje dokumentów wymaganych przez demo: "
            f"{', '.join(missing_docs)}. "
            "Uruchom `python -m app.cli import-techqa` na pełnej migawce TechQA."
        )

    chunks_by_doc: dict[str, list[_ChunkRow]] = {
        doc_id: [] for doc_id in doc_ids_sorted
    }
    if doc_ids_sorted:
        for row in conn.execute(
            "SELECT id, doc_id, ordinal, headings, start_offset, end_offset, text"
            " FROM chunks"
            " WHERE chunk_set_id = %s AND doc_id = ANY(%s)"
            " ORDER BY doc_id, ordinal ASC",
            (chunk_set_id, doc_ids_sorted),
        ).fetchall():
            chunk = _ChunkRow(
                chunk_id=str(row[0]),
                doc_id=str(row[1]),
                ordinal=int(row[2]),
                headings=list(row[3]),
                start_offset=int(row[4]),
                end_offset=int(row[5]),
                text=str(row[6]),
            )
            chunks_by_doc[chunk.doc_id].append(chunk)

    docs_without_chunks = sorted(
        doc_id for doc_id, chunk_list in chunks_by_doc.items() if not chunk_list
    )
    if docs_without_chunks:
        raise DemoSeedError(
            f"W zestawie fragmentów {chunk_set_id!r} brakuje fragmentów dla: "
            f"{', '.join(docs_without_chunks)}. "
            "Uruchom ponownie `python -m app.cli import-techqa`."
        )

    return snapshot_id, docs, chunks_by_doc


def import_demo_audits(
    conn: psycopg.Connection,
    path: Path = DEMO_AUDITS_PATH,
    *,
    chunk_set_id: str,
) -> DemoSeedReport:
    """Idempotentnie seeduje przykłady demo bez kasowania decyzji sesji."""
    specs = load_demo_audits(path)

    required_doc_ids: set[str] = set()
    for spec in specs:
        for claim in spec.claims:
            for ev_spec in claim.evidence_specs:
                required_doc_ids.add(ev_spec.doc_id)
            for doc_id in claim.checked_doc_ids:
                required_doc_ids.add(doc_id)

    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (DEMO_AUDITS_LOCK_KEY,))

        snapshot_id, docs_by_id, chunks_by_doc = _load_corpus_lookup(
            conn, chunk_set_id, required_doc_ids
        )

        had_previous = (
            conn.execute("SELECT 1 FROM audits WHERE is_demo = true LIMIT 1").fetchone()
            is not None
        )
        previous_hash = _demo_state_hash(conn) if had_previous else None

        current_audit_ids = [demo_audit_id(spec.slug) for spec in specs]
        conn.execute(
            "DELETE FROM audits WHERE is_demo = true AND NOT (id = ANY(%s::uuid[]))",
            (current_audit_ids,),
        )

        total_claims = 0
        for spec in specs:
            audit_id = demo_audit_id(spec.slug)
            created_at = DEMO_BASE_TIMESTAMP - timedelta(
                minutes=spec.created_offset_minutes
            )
            completed_at = created_at + timedelta(milliseconds=DEMO_DURATION_MS)
            claims_sorted = sorted(spec.claims, key=lambda item: item.claim_index)
            claims_total = len(claims_sorted)
            config: dict[str, Any] = {
                "source": DEMO_AUDITS_VERSION,
                "include_synthetic": False,
                "chunk_set_id": chunk_set_id,
            }

            conn.execute(
                "INSERT INTO audits ("
                " id, session_hash, is_demo, case_ref, case_description,"
                " resolution_note, status, stage, claims_total, claims_done,"
                " note_verdict, case_context, snapshot_id, chunk_set_ids,"
                " config, error, trace_id, duration_ms,"
                " created_at, updated_at, completed_at"
                ") VALUES ("
                " %s, %s, true, %s, %s,"
                " %s, 'completed', 'completed', %s, %s,"
                " %s, %s, %s, %s,"
                " %s, NULL, NULL, %s,"
                " %s, %s, %s"
                ")"
                " ON CONFLICT (id) DO UPDATE SET"
                " session_hash = EXCLUDED.session_hash,"
                " is_demo = true,"
                " case_ref = EXCLUDED.case_ref,"
                " case_description = EXCLUDED.case_description,"
                " resolution_note = EXCLUDED.resolution_note,"
                " status = EXCLUDED.status,"
                " stage = EXCLUDED.stage,"
                " claims_total = EXCLUDED.claims_total,"
                " claims_done = EXCLUDED.claims_done,"
                " note_verdict = EXCLUDED.note_verdict,"
                " case_context = EXCLUDED.case_context,"
                " snapshot_id = EXCLUDED.snapshot_id,"
                " chunk_set_ids = EXCLUDED.chunk_set_ids,"
                " config = EXCLUDED.config,"
                " error = NULL,"
                " duration_ms = EXCLUDED.duration_ms,"
                " created_at = EXCLUDED.created_at,"
                " updated_at = EXCLUDED.updated_at,"
                " completed_at = EXCLUDED.completed_at",
                (
                    audit_id,
                    DEMO_SESSION_HASH,
                    spec.case_ref,
                    spec.case_description,
                    spec.resolution_note,
                    claims_total,
                    claims_total,
                    spec.note_verdict,
                    Jsonb(spec.case_context.model_dump()),
                    snapshot_id,
                    [chunk_set_id],
                    Jsonb(config),
                    DEMO_DURATION_MS,
                    created_at,
                    completed_at,
                    completed_at,
                ),
            )

            current_claim_ids = [
                demo_claim_id(spec.slug, claim.claim_index) for claim in claims_sorted
            ]
            conn.execute(
                "DELETE FROM audit_claims"
                " WHERE audit_id = %s AND NOT (id = ANY(%s::uuid[]))",
                (audit_id, current_claim_ids),
            )

            for claim in claims_sorted:
                claim_id = demo_claim_id(spec.slug, claim.claim_index)
                span = locate_quote(spec.resolution_note, claim.source_excerpt)
                if span is not None:
                    source_start: int | None = span[0]
                    source_end: int | None = span[1]
                    matched_excerpt = spec.resolution_note[source_start:source_end]
                else:
                    source_start = None
                    source_end = None
                    matched_excerpt = claim.source_excerpt

                evidence_items: list[dict[str, Any]] = []
                matched_chunks_by_doc: dict[str, _ChunkRow] = {}
                for ev_spec in claim.evidence_specs:
                    doc = docs_by_id[ev_spec.doc_id]
                    chunk = _select_best_chunk(
                        chunks_by_doc[ev_spec.doc_id], ev_spec.anchor_terms
                    )
                    matched_chunks_by_doc.setdefault(ev_spec.doc_id, chunk)
                    q_start, q_end = _extract_quote_span(
                        chunk.text, ev_spec.anchor_terms
                    )
                    ev = ClaimEvidence(
                        chunk_id=chunk.chunk_id,
                        document_id=doc.doc_id,
                        document_title=doc.title,
                        source_doc_id=doc.doc_id,
                        chunk_set_id=chunk_set_id,
                        snapshot_id=snapshot_id,
                        is_synthetic=doc.is_synthetic,
                        quote=chunk.text[q_start:q_end],
                        quote_start=q_start,
                        quote_end=q_end,
                        supports_claim=(claim.verdict == "supported"),
                    )
                    evidence_items.append(ev.model_dump())

                checked_items: list[dict[str, Any]] = []
                seen_checked: set[str] = set()
                for doc_id in claim.checked_doc_ids:
                    if doc_id in seen_checked:
                        continue
                    seen_checked.add(doc_id)
                    doc = docs_by_id[doc_id]
                    checked_chunk = matched_chunks_by_doc.get(
                        doc_id, chunks_by_doc[doc_id][0]
                    )
                    checked = CheckedDoc(
                        document_id=doc.doc_id,
                        document_title=doc.title,
                        source_doc_id=doc.doc_id,
                        chunk_id=checked_chunk.chunk_id,
                        chunk_set_id=chunk_set_id,
                        snapshot_id=snapshot_id,
                        is_synthetic=doc.is_synthetic,
                        score=1.0,
                    )
                    checked_items.append(checked.model_dump())

                conn.execute(
                    "INSERT INTO audit_claims ("
                    " id, audit_id, claim_index, claim_label, claim_text,"
                    " source_excerpt, source_start, source_end, search_query,"
                    " verdict, rationale, scope_note, evidence, checked_docs, error"
                    ") VALUES ("
                    " %s, %s, %s, %s, %s,"
                    " %s, %s, %s, %s,"
                    " %s, %s, %s, %s, %s, NULL"
                    ")"
                    " ON CONFLICT (id) DO UPDATE SET"
                    " claim_index = EXCLUDED.claim_index,"
                    " claim_label = EXCLUDED.claim_label,"
                    " claim_text = EXCLUDED.claim_text,"
                    " source_excerpt = EXCLUDED.source_excerpt,"
                    " source_start = EXCLUDED.source_start,"
                    " source_end = EXCLUDED.source_end,"
                    " search_query = EXCLUDED.search_query,"
                    " verdict = EXCLUDED.verdict,"
                    " rationale = EXCLUDED.rationale,"
                    " scope_note = EXCLUDED.scope_note,"
                    " evidence = EXCLUDED.evidence,"
                    " checked_docs = EXCLUDED.checked_docs,"
                    " error = NULL",
                    (
                        claim_id,
                        audit_id,
                        claim.claim_index,
                        claim.claim_label,
                        claim.claim_text,
                        matched_excerpt,
                        source_start,
                        source_end,
                        claim.search_query,
                        claim.verdict,
                        claim.rationale,
                        claim.scope_note,
                        Jsonb(evidence_items),
                        Jsonb(checked_items),
                    ),
                )
                total_claims += 1

            initial_events: list[tuple[str, dict[str, Any], datetime]] = [
                ("audit_created", {"case_ref": spec.case_ref}, created_at),
                (
                    "evaluation_completed",
                    {
                        "note_verdict": spec.note_verdict,
                        "claims_total": claims_total,
                    },
                    completed_at,
                ),
            ]
            for event_type, payload, event_ts in initial_events:
                conn.execute(
                    "INSERT INTO audit_events ("
                    " id, audit_id, claim_id, session_hash, event_type,"
                    " actor_type, role_label, payload, created_at"
                    ")"
                    " SELECT %s, %s, NULL, NULL, %s, 'system', NULL, %s, %s"
                    " WHERE NOT EXISTS ("
                    "  SELECT 1 FROM audit_events"
                    "  WHERE audit_id = %s AND event_type = %s"
                    " )",
                    (
                        demo_event_id(spec.slug, event_type),
                        audit_id,
                        event_type,
                        Jsonb(payload),
                        event_ts,
                        audit_id,
                        event_type,
                    ),
                )

        state_sha256 = _demo_state_hash(conn)

    comparison: Comparison
    if not had_previous or previous_hash is None:
        comparison = "pierwszy import"
    elif previous_hash == state_sha256:
        comparison = "identyczny"
    else:
        comparison = "różny"

    return DemoSeedReport(
        snapshot_id=snapshot_id,
        chunk_set_id=chunk_set_id,
        audits_count=len(specs),
        claims_count=total_claims,
        state_sha256=state_sha256,
        comparison=comparison,
    )
