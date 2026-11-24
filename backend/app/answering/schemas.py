"""Schematy wyjścia modeli i wyniku odpowiedzi.

Kolejność pól ma znaczenie: w `ClaimVerdict` `reasoning` stoi przed `verdict`,
żeby model uzasadnił ocenę, zanim ją poda.
"""

from typing import Literal

from pydantic import BaseModel

Verdict = Literal["supported", "contradicted", "insufficient"]
RejectionReason = Literal["quote_not_found", "unknown_chunk"]
AbstainReason = Literal["no_hits", "no_claims", "none_supported"]


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
    """Jeden numer cytatu na fragment; obejmuje wszystkie pokazane tezy z niego."""

    n: int
    chunk_id: str
    doc_id: str
    title: str
    headings: list[str]
    claims: list[CitationClaim]


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


AnswerResult = AnsweredResult | AbstainedResult
