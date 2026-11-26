"""Schematy wyjścia modeli i wyniku odpowiedzi.

Kolejność pól ma znaczenie: w `ClaimVerdict` `reasoning` stoi przed `verdict`,
żeby model uzasadnił ocenę, zanim ją poda.
"""

from typing import Literal

from pydantic import BaseModel

Verdict = Literal["supported", "contradicted", "insufficient"]
RejectionReason = Literal["quote_not_found", "unknown_chunk"]
AbstainReason = Literal["no_hits", "no_claims", "none_supported"]
ConflictType = Literal["contradiction", "different_recommendations"]
ScopeRelation = Literal["same_scope", "different_scope", "unknown_scope"]


class DraftClaim(BaseModel):
    """Teza ze szkicu: jeden fragment i dosłowny cytat z niego."""

    text: str
    code: str | None
    chunk_id: str
    quote: str


class DraftOutput(BaseModel):
    claims: list[DraftClaim]


class ClaimVerdict(BaseModel):
    claim_index: int
    reasoning: str
    verdict: Verdict


class VerifyOutput(BaseModel):
    verdicts: list[ClaimVerdict]


class AnswerClaim(BaseModel):
    """Teza pokazana konsultantowi; `citation` to numer cytatu (1..N)."""

    text: str
    code: str | None
    citation: int


class CitationClaim(BaseModel):
    """Teza oparta na cytowanym fragmencie.

    `claim_index` to pozycja tezy na liście `AnsweredResult.claims` (od 0);
    offsety cytatu `[quote_start, quote_end)` są względne do tekstu fragmentu.
    """

    claim_index: int
    quote: str
    quote_start: int
    quote_end: int


class Citation(BaseModel):
    """Jeden numer cytatu na fragment; obejmuje wszystkie pokazane tezy z niego.

    Pola migawki i metadanych mają wartości domyślne, żeby zapisane wcześniej
    odpowiedzi (`answers.result`) nadal się walidowały; brak `snapshot_id` oznacza
    migawkę z rekordu odpowiedzi.
    """

    n: int
    chunk_id: str
    doc_id: str
    title: str
    headings: list[str]
    claims: list[CitationClaim]
    snapshot_id: str | None = None
    is_synthetic: bool = False
    doc_date: str | None = None
    product_version: str | None = None


class CheckedChunk(BaseModel):
    rank: int
    chunk_id: str
    doc_id: str
    title: str
    headings: list[str]
    score: float


class AnsweredResult(BaseModel):
    outcome: Literal["answered"] = "answered"
    claims: list[AnswerClaim]
    citations: list[Citation]
    checked_chunks: list[CheckedChunk]
    omitted_claims: int


class AbstainedResult(BaseModel):
    outcome: Literal["abstained"] = "abstained"
    reason: AbstainReason
    checked_chunks: list[CheckedChunk]
    omitted_claims: int


class ConflictComparisonOutput(BaseModel):
    """Porównanie zalecanych wartości po obu stronach (z modelu)."""

    value_label: str
    side_a_value: str
    side_b_value: str


class ConflictCheckOutput(BaseModel):
    """Ocena `detect_conflict`; `reasoning` stoi przed werdyktem.

    Indeksy to `claim_index` tez ze szkicu (jak w `verify`), tylko tez `supported`.
    """

    reasoning: str
    has_conflict: bool
    scope_relation: ScopeRelation | None
    side_a_claim_indices: list[int]
    side_b_claim_indices: list[int]
    conflicting_doc_ids: list[str]
    summary: str | None
    comparison: ConflictComparisonOutput | None
    refine_hint: str | None


class ConflictSide(BaseModel):
    """Jedna strona konfliktu (A albo B) z dosłownym cytatem i metadanymi."""

    label: Literal["A", "B"]
    snapshot_id: str
    doc_id: str
    chunk_id: str
    title: str
    headings: list[str]
    is_synthetic: bool
    doc_date: str | None
    product_version: str | None
    audience: str | None
    claim_text: str
    code: str | None
    quote: str
    quote_start: int
    quote_end: int


class ConflictComparisonRow(BaseModel):
    kind: Literal["recommendation", "audience", "doc_date", "product_version"]
    label: str | None = None
    side_a: str | None
    side_b: str | None


class ConflictingResult(BaseModel):
    outcome: Literal["conflicting"] = "conflicting"
    conflict_type: ConflictType
    summary: str
    refine_hint: str | None
    comparison_rows: list[ConflictComparisonRow]
    sides: tuple[ConflictSide, ConflictSide]
    extra_conflicting_docs: int = 0
    checked_chunks: list[CheckedChunk]
    omitted_claims: int


AnswerResult = AnsweredResult | AbstainedResult | ConflictingResult
