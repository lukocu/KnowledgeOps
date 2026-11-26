"""Schematy domenowe audytu notatek ze spraw (wejście/wyjście modeli i dowody).

Kolejność pól w `ClaimVerdictOutput` ma znaczenie: `reasoning` stoi przed
`verdict`, żeby model uzasadnił ocenę, zanim ją wybierze. Modele używane ze
`strict=True` nie pomijają kluczy i deklarują wszystkie pola jawnie.
"""

from typing import Literal

from pydantic import BaseModel

from app.auditing.store import AuditStage, ClaimVerdict, NoteVerdict

__all__ = [
    "AuditStage",
    "CaseContext",
    "CheckedDoc",
    "ClaimEvidence",
    "ClaimVerdict",
    "ClaimVerdictOutput",
    "ExtractOutput",
    "ExtractedClaim",
    "NoteVerdict",
    "ScopeRelation",
]

ScopeRelation = Literal["same_scope", "different_scope", "unclear"]


class CaseContext(BaseModel):
    """Wyodrębniony kontekst sprawy (FR-007) — wszystkie pola jawne."""

    problem: str | None
    environment: str | None
    solution: str | None
    constraints: list[str]
    missing_info: list[str]


class ExtractedClaim(BaseModel):
    """Pojedyncza teza wyodrębniona z notatki rozwiązania."""

    claim_label: str
    claim_text: str
    source_excerpt: str
    search_query: str


class ExtractOutput(BaseModel):
    """Wyjście etapu `extract`: kontekst sprawy i lista tez do weryfikacji."""

    case_context: CaseContext
    claims: list[ExtractedClaim]


class ClaimVerdictOutput(BaseModel):
    """Wyjście etapu `verify` dla jednej tezy (`reasoning` przed `verdict`)."""

    reasoning: str
    verdict: ClaimVerdict
    scope_relation: ScopeRelation
    scope_note: str | None
    evidence_chunk_id: str | None
    evidence_quote: str | None


class ClaimEvidence(BaseModel):
    """Zweryfikowany cytat z bazy wiedzy lub najbliższy sprawdzony fragment."""

    chunk_id: str
    document_id: str
    document_title: str
    source_doc_id: str
    chunk_set_id: str
    snapshot_id: str | None = None
    is_synthetic: bool = False
    quote: str
    quote_start: int
    quote_end: int
    supports_claim: bool


class CheckedDoc(BaseModel):
    """Unikalny dokument bazy wiedzy sprawdzony podczas weryfikacji tezy."""

    document_id: str
    document_title: str
    source_doc_id: str
    chunk_id: str
    chunk_set_id: str
    snapshot_id: str | None = None
    is_synthetic: bool = False
    score: float
