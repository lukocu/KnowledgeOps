"""Deterministyczne reguły domenowe audytu notatek ze spraw.

Wszystkie funkcje w tym module są czyste (bez I/O i bez wywołań modeli):
- normalizacja wyodrębnionych tez i walidacja spanów w notatce,
- walidacja cytatów z bazy wiedzy i strażnik zakresu dla sprzeczności,
- dobór najbliższego sprawdzonego fragmentu i listy sprawdzonych dokumentów,
- agregacja 4-stanowej oceny całej notatki (`NoteVerdict`).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.answering.nodes import locate_quote
from app.auditing.schemas import (
    CheckedDoc,
    ClaimEvidence,
    ClaimVerdict,
    ClaimVerdictOutput,
    ExtractedClaim,
    NoteVerdict,
)
from app.retrieval import RetrievedChunk

DegradedReason = Literal[
    "missing_evidence",
    "unknown_chunk",
    "quote_not_found",
    "different_scope",
]

CLOSEST_QUOTE_MAX_CHARS = 360


@dataclass(frozen=True)
class PreparedClaim:
    """Teza po przycięciu limitu i dopasowaniu fragmentu źródłowego do notatki."""

    claim_index: int
    claim_label: str
    claim_text: str
    source_excerpt: str
    source_start: int | None
    source_end: int | None
    search_query: str


@dataclass(frozen=True)
class ResolvedClaimEvidence:
    """Zwalidowany werdykt tezy po sprawdzeniu cytatu i strażniku zakresu."""

    verdict: ClaimVerdict
    rationale: str
    scope_note: str | None
    evidence: list[ClaimEvidence]
    degraded_reason: DegradedReason | None = None


def chunk_set_id_from_chunk_id(chunk_id: str) -> str:
    """Wyciąga `chunk_set_id` z identyfikatora fragmentu `<chunk_set_id>/<doc>/<n>`."""
    if "/" in chunk_id:
        return chunk_id.split("/", 1)[0]
    return ""


def _make_evidence(
    chunk: RetrievedChunk,
    *,
    quote_start: int,
    quote_end: int,
    supports_claim: bool,
) -> ClaimEvidence:
    return ClaimEvidence(
        chunk_id=chunk.chunk_id,
        document_id=chunk.doc_id,
        document_title=chunk.title,
        source_doc_id=chunk.doc_id,
        chunk_set_id=chunk_set_id_from_chunk_id(chunk.chunk_id),
        snapshot_id=chunk.snapshot_id or None,
        is_synthetic=chunk.is_synthetic,
        quote=chunk.text[quote_start:quote_end],
        quote_start=quote_start,
        quote_end=quote_end,
        supports_claim=supports_claim,
    )


def build_checked_docs(candidates: Sequence[RetrievedChunk]) -> list[CheckedDoc]:
    """Zwraca unikalne dokumenty sprawdzone dla tezy w kolejności rankingu."""
    seen: set[tuple[str, str]] = set()
    docs: list[CheckedDoc] = []
    for chunk in candidates:
        key = (chunk.snapshot_id, chunk.doc_id)
        if key in seen:
            continue
        seen.add(key)
        docs.append(
            CheckedDoc(
                document_id=chunk.doc_id,
                document_title=chunk.title,
                source_doc_id=chunk.doc_id,
                chunk_id=chunk.chunk_id,
                chunk_set_id=chunk_set_id_from_chunk_id(chunk.chunk_id),
                snapshot_id=chunk.snapshot_id or None,
                is_synthetic=chunk.is_synthetic,
                score=chunk.score,
            )
        )
    return docs


def build_closest_evidence(
    candidates: Sequence[RetrievedChunk],
    *,
    max_chars: int = CLOSEST_QUOTE_MAX_CHARS,
) -> ClaimEvidence | None:
    """Buduje najbliższy fragment (`supports_claim=False`) z top-1 kandydata."""
    if not candidates:
        return None
    best = candidates[0]
    if not best.text.strip():
        return None
    excerpt = best.text[:max_chars].strip()
    span = locate_quote(best.text, excerpt)
    if span is None:
        start, end = 0, min(len(best.text), max_chars)
    else:
        start, end = span
    return _make_evidence(
        best,
        quote_start=start,
        quote_end=end,
        supports_claim=False,
    )


def normalize_extracted_claims(
    claims: Sequence[ExtractedClaim],
    resolution_note: str,
    *,
    max_claims: int,
) -> list[PreparedClaim]:
    """Ucina listę tez do `max_claims` i dopasowuje `source_excerpt` do notatki."""
    limit = max(0, max_claims)
    prepared: list[PreparedClaim] = []
    for raw in claims[:limit]:
        source_excerpt = raw.source_excerpt.strip()
        claim_text = raw.claim_text.strip() or source_excerpt
        if not claim_text:
            continue
        if not source_excerpt:
            source_excerpt = claim_text
        claim_label = raw.claim_label.strip() or source_excerpt[:80]
        search_query = raw.search_query.strip() or claim_text

        span = locate_quote(resolution_note, source_excerpt)
        if span is not None:
            source_start, source_end = span
            matched_excerpt = resolution_note[source_start:source_end]
        else:
            source_start, source_end = None, None
            matched_excerpt = source_excerpt

        prepared.append(
            PreparedClaim(
                claim_index=len(prepared),
                claim_label=claim_label,
                claim_text=claim_text,
                source_excerpt=matched_excerpt,
                source_start=source_start,
                source_end=source_end,
                search_query=search_query,
            )
        )
    return prepared


def resolve_claim_verdict(
    raw: ClaimVerdictOutput,
    candidates: Sequence[RetrievedChunk],
) -> ResolvedClaimEvidence:
    """Waliduje cytat i zakres pojedynczej tezy; degraduje niezweryfikowane werdykty."""
    rationale = raw.reasoning.strip()
    scope_note = (
        raw.scope_note.strip() if raw.scope_note and raw.scope_note.strip() else None
    )
    by_id = {chunk.chunk_id: chunk for chunk in candidates}

    verified_chunk: RetrievedChunk | None = None
    verified_span: tuple[int, int] | None = None
    evidence_error: DegradedReason | None = None

    chunk_id = raw.evidence_chunk_id.strip() if raw.evidence_chunk_id else ""
    quote = raw.evidence_quote.strip() if raw.evidence_quote else ""
    if not chunk_id or not quote:
        evidence_error = "missing_evidence"
    elif chunk_id not in by_id:
        evidence_error = "unknown_chunk"
    else:
        candidate = by_id[chunk_id]
        span = locate_quote(candidate.text, quote)
        if span is None:
            evidence_error = "quote_not_found"
        else:
            verified_chunk = candidate
            verified_span = span

    # Strażnik zakresu: sprzeczność dopuszczalna wyłącznie przy tym samym zakresie.
    if raw.verdict == "contradicted" and raw.scope_relation != "same_scope":
        evidence: list[ClaimEvidence] = []
        if verified_chunk is not None and verified_span is not None:
            evidence.append(
                _make_evidence(
                    verified_chunk,
                    quote_start=verified_span[0],
                    quote_end=verified_span[1],
                    supports_claim=False,
                )
            )
        else:
            closest = build_closest_evidence(candidates)
            if closest is not None:
                evidence.append(closest)
        return ResolvedClaimEvidence(
            verdict="insufficient",
            rationale=rationale,
            scope_note=scope_note,
            evidence=evidence,
            degraded_reason="different_scope",
        )

    if raw.verdict in ("supported", "contradicted"):
        if verified_chunk is not None and verified_span is not None:
            return ResolvedClaimEvidence(
                verdict=raw.verdict,
                rationale=rationale,
                scope_note=scope_note,
                evidence=[
                    _make_evidence(
                        verified_chunk,
                        quote_start=verified_span[0],
                        quote_end=verified_span[1],
                        supports_claim=(raw.verdict == "supported"),
                    )
                ],
                degraded_reason=None,
            )
        closest = build_closest_evidence(candidates)
        return ResolvedClaimEvidence(
            verdict="insufficient",
            rationale=rationale,
            scope_note=scope_note,
            evidence=[closest] if closest is not None else [],
            degraded_reason=evidence_error,
        )

    # Werdykt `insufficient`: dołączamy zweryfikowany fragment (jeśli model wskazał)
    # lub najbliższy sprawdzony fragment z `retrieve`, zawsze z `supports_claim=False`.
    insufficient_evidence: list[ClaimEvidence] = []
    if verified_chunk is not None and verified_span is not None:
        insufficient_evidence.append(
            _make_evidence(
                verified_chunk,
                quote_start=verified_span[0],
                quote_end=verified_span[1],
                supports_claim=False,
            )
        )
    else:
        closest = build_closest_evidence(candidates)
        if closest is not None:
            insufficient_evidence.append(closest)

    return ResolvedClaimEvidence(
        verdict="insufficient",
        rationale=rationale,
        scope_note=scope_note,
        evidence=insufficient_evidence,
        degraded_reason=None,
    )


def aggregate_note_verdict(verdicts: Sequence[ClaimVerdict]) -> NoteVerdict:
    """Deterministyczna agregacja werdyktów tez do 4-stanowej oceny notatki."""
    if not verdicts:
        return "insufficient"
    if any(verdict == "contradicted" for verdict in verdicts):
        return "contradiction"
    if all(verdict == "supported" for verdict in verdicts):
        return "full"
    if any(verdict == "supported" for verdict in verdicts):
        return "partial"
    return "insufficient"
