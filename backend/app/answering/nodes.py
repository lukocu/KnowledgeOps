"""Węzły grafu odpowiedzi i czyste funkcje reguły odpowiedzi.

Każdy węzeł zgłasza zdarzenia etapu (`started`, `done`) przez `get_stream_writer()`.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.config import get_stream_writer
from pydantic import BaseModel

from app.answering.prompts import load_prompt
from app.answering.schemas import (
    AbstainedResult,
    AbstainReason,
    AnswerClaim,
    AnsweredResult,
    AnswerResult,
    CheckedChunk,
    Citation,
    CitationClaim,
    ClaimVerdict,
    ConflictCheckOutput,
    ConflictComparisonRow,
    ConflictingResult,
    ConflictSide,
    ConflictType,
    DraftClaim,
    DraftOutput,
    RejectionReason,
    ScopeRelation,
    VerifyOutput,
)
from app.db import CONNECTION_TIMEOUT_S, AsyncPool
from app.retrieval import RetrievedChunk, resolve_active_chunk_set_ids, search_bm25
from app.settings import Settings

Stage = Literal[
    "retrieve",
    "draft",
    "quote_check",
    "verify",
    "detect_conflict",
    "compose",
    "abstain",
]


@dataclass(frozen=True)
class RejectedClaim:
    draft_index: int
    claim: DraftClaim
    reason: RejectionReason


@dataclass(frozen=True)
class QuotedClaim:
    """Teza, której cytat przeszedł `quote_check`; offsety względem tekstu fragmentu."""

    draft_index: int
    claim: DraftClaim
    quote_start: int
    quote_end: int


class AnswerState(TypedDict, total=False):
    question: str
    chunk_set_id: str
    include_synthetic: bool
    chunk_set_ids: list[str]
    k: int
    retrieved: list[RetrievedChunk]
    retrieved_chunk_ids: list[str]
    draft_claims: list[DraftClaim]
    rejected: list[RejectedClaim]
    quoted: list[QuotedClaim]
    verdicts: list[ClaimVerdict]
    conflict_check: ConflictCheckOutput
    outcome: Literal["answered", "abstained", "conflicting"]
    answer: AnswerResult


# --- quote_check -------------------------------------------------------------


def normalize_whitespace(text: str) -> tuple[str, list[int]]:
    """Zwija ciągi białych znaków do jednej spacji i obcina brzegi.

    Zwraca tekst znormalizowany i mapę: pozycja w znormalizowanym -> pozycja
    w oryginale, żeby offsety cytatu wskazywały oryginalny tekst fragmentu.
    """
    chars: list[str] = []
    positions: list[int] = []
    pending_space: int | None = None
    for index, char in enumerate(text):
        if char.isspace():
            if chars and pending_space is None:
                pending_space = index
            continue
        if pending_space is not None:
            chars.append(" ")
            positions.append(pending_space)
            pending_space = None
        chars.append(char)
        positions.append(index)
    return "".join(chars), positions


def locate_quote(chunk_text: str, quote: str) -> tuple[int, int] | None:
    """Offsety `[start, end)` cytatu w oryginalnym tekście albo `None`.

    Porównanie jest dosłowne z dokładnością do białych znaków.
    """
    normalized_quote = " ".join(quote.split())
    if not normalized_quote:
        return None
    normalized_text, positions = normalize_whitespace(chunk_text)
    found = normalized_text.find(normalized_quote)
    if found < 0:
        return None
    last = found + len(normalized_quote) - 1
    return positions[found], positions[last] + 1


def quote_check(
    claims: list[DraftClaim], retrieved: list[RetrievedChunk]
) -> tuple[list[QuotedClaim], list[RejectedClaim]]:
    """Odrzuca tezy z nieznanym `chunk_id` i z cytatem spoza wskazanego fragmentu."""
    by_id = {chunk.chunk_id: chunk for chunk in retrieved}
    quoted: list[QuotedClaim] = []
    rejected: list[RejectedClaim] = []
    for index, claim in enumerate(claims):
        chunk = by_id.get(claim.chunk_id)
        if chunk is None:
            rejected.append(RejectedClaim(index, claim, "unknown_chunk"))
            continue
        span = locate_quote(chunk.text, claim.quote)
        if span is None:
            rejected.append(RejectedClaim(index, claim, "quote_not_found"))
            continue
        quoted.append(QuotedClaim(index, claim, span[0], span[1]))
    return quoted, rejected


# --- składanie wyniku --------------------------------------------------------


def supported_claims(
    quoted: list[QuotedClaim], verdicts: list[ClaimVerdict]
) -> list[QuotedClaim]:
    """Tezy ocenione jako `supported`, w kolejności szkicu.

    Teza bez werdyktu jest traktowana jak niepoparta; przy powtórzonym
    `claim_index` liczy się pierwszy werdykt.
    """
    verdict_by_index: dict[int, str] = {}
    for verdict in verdicts:
        verdict_by_index.setdefault(verdict.claim_index, verdict.verdict)
    return [q for q in quoted if verdict_by_index.get(q.draft_index) == "supported"]


def checked_chunks(retrieved: list[RetrievedChunk]) -> list[CheckedChunk]:
    return [
        CheckedChunk(
            rank=chunk.rank,
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            title=chunk.title,
            headings=chunk.headings,
            score=chunk.score,
        )
        for chunk in retrieved
    ]


def compose_answer(
    supported: list[QuotedClaim],
    retrieved: list[RetrievedChunk],
    total_claims: int,
) -> AnsweredResult:
    """Odpowiedź z tez `supported` (kolejność szkicu), niepustej listy.

    Numer cytatu przypada na fragment w kolejności pierwszego użycia (1..N bez
    dziur). Każda pominięta teza (odrzucona, `contradicted`, `insufficient`,
    bez werdyktu) zwiększa `omitted_claims`.
    """
    chunks = {chunk.chunk_id: chunk for chunk in retrieved}
    numbers: dict[str, int] = {}
    citations: list[Citation] = []
    claims: list[AnswerClaim] = []
    for position, item in enumerate(supported):
        chunk = chunks[item.claim.chunk_id]
        number = numbers.get(chunk.chunk_id)
        if number is None:
            number = len(numbers) + 1
            numbers[chunk.chunk_id] = number
            citations.append(
                Citation(
                    n=number,
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    title=chunk.title,
                    headings=chunk.headings,
                    claims=[],
                    snapshot_id=chunk.snapshot_id or None,
                    is_synthetic=chunk.is_synthetic,
                    doc_date=chunk.doc_date,
                    product_version=chunk.product_version,
                )
            )
        claims.append(
            AnswerClaim(text=item.claim.text, code=item.claim.code, citation=number)
        )
        citations[number - 1].claims.append(
            CitationClaim(
                claim_index=position,
                quote=chunk.text[item.quote_start : item.quote_end],
                quote_start=item.quote_start,
                quote_end=item.quote_end,
            )
        )
    return AnsweredResult(
        claims=claims,
        citations=citations,
        checked_chunks=checked_chunks(retrieved),
        omitted_claims=total_claims - len(supported),
    )


# --- wykrywanie i składanie konfliktu ----------------------------------------

DEFAULT_CONFLICT_SUMMARY = (
    "Retrieved documents provide conflicting recommendations for this question."
)


def _norm_scope_attr(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split()).casefold()
    return normalized or None


def resolve_conflict_type(
    scope_relation: ScopeRelation | None,
    side_a_doc: RetrievedChunk,
    side_b_doc: RetrievedChunk,
) -> ConflictType:
    """Deterministyczny strażnik zakresu (US-03).

    Zwraca `"contradiction"` wyłącznie gdy `scope_relation == "same_scope"` ORAZ
    jawne metadane zakresu (`product_version`, `audience`) obu dokumentów są
    zgodne (nie różnią się i nie zestawiają konkretnej wartości z nieustaloną).
    """
    if scope_relation != "same_scope":
        return "different_recommendations"
    if _norm_scope_attr(side_a_doc.product_version) != _norm_scope_attr(
        side_b_doc.product_version
    ):
        return "different_recommendations"
    if _norm_scope_attr(side_a_doc.audience) != _norm_scope_attr(side_b_doc.audience):
        return "different_recommendations"
    return "contradiction"


@dataclass(frozen=True)
class ResolvedConflict:
    """Zwalidowana para stron A i B uporządkowana wg rankingu wyszukiwania."""

    side_a: QuotedClaim
    side_b: QuotedClaim
    extra_conflicting_docs: int
    swapped: bool


def select_conflict_sides(
    conflict_check: ConflictCheckOutput,
    supported: list[QuotedClaim],
    retrieved: list[RetrievedChunk],
) -> ResolvedConflict | None:
    """Waliduje wyjście `detect_conflict` i wybiera deterministycznie parę A vs B.

    Zwraca `None` (bezpieczny fallback do `compose`), gdy nie ma konfliktu,
    indeksy są spoza zbioru wspartych tez albo nie wyznaczają co najmniej dwóch
    różnych dokumentów (`doc_id`).
    """
    if not conflict_check.has_conflict:
        return None

    supported_by_index = {item.draft_index: item for item in supported}
    chunks_by_id = {chunk.chunk_id: chunk for chunk in retrieved}
    supported_doc_ids = {
        chunks_by_id[item.claim.chunk_id].doc_id
        for item in supported
        if item.claim.chunk_id in chunks_by_id
    }

    def _valid_claims(indices: list[int]) -> list[QuotedClaim]:
        seen: set[int] = set()
        result: list[QuotedClaim] = []
        for idx in indices:
            if idx in seen:
                continue
            item = supported_by_index.get(idx)
            if item is None or item.claim.chunk_id not in chunks_by_id:
                continue
            seen.add(idx)
            result.append(item)
        return result

    valid_a = _valid_claims(conflict_check.side_a_claim_indices)
    valid_b = _valid_claims(conflict_check.side_b_claim_indices)
    if not valid_a or not valid_b:
        return None

    def _rank_key(item: QuotedClaim) -> tuple[int, int]:
        return (chunks_by_id[item.claim.chunk_id].rank, item.draft_index)

    ordered_a = sorted(valid_a, key=_rank_key)
    ordered_b = sorted(valid_b, key=_rank_key)

    best_a = ordered_a[0]
    doc_a = chunks_by_id[best_a.claim.chunk_id].doc_id
    best_b = next(
        (
            item
            for item in ordered_b
            if chunks_by_id[item.claim.chunk_id].doc_id != doc_a
        ),
        None,
    )
    if best_b is None:
        best_b = ordered_b[0]
        doc_b = chunks_by_id[best_b.claim.chunk_id].doc_id
        best_a_alt = next(
            (
                item
                for item in ordered_a
                if chunks_by_id[item.claim.chunk_id].doc_id != doc_b
            ),
            None,
        )
        if best_a_alt is None:
            return None
        best_a = best_a_alt

    swapped = _rank_key(best_b) < _rank_key(best_a)
    side_a, side_b = (best_b, best_a) if swapped else (best_a, best_b)

    conflicting_docs = {
        chunks_by_id[side_a.claim.chunk_id].doc_id,
        chunks_by_id[side_b.claim.chunk_id].doc_id,
    }
    for item in (*ordered_a, *ordered_b):
        conflicting_docs.add(chunks_by_id[item.claim.chunk_id].doc_id)
    for doc_id in conflict_check.conflicting_doc_ids:
        if doc_id in supported_doc_ids:
            conflicting_docs.add(doc_id)

    extra_conflicting_docs = max(0, len(conflicting_docs) - 2)
    return ResolvedConflict(
        side_a=side_a,
        side_b=side_b,
        extra_conflicting_docs=extra_conflicting_docs,
        swapped=swapped,
    )


def _build_conflict_side(
    label: Literal["A", "B"],
    item: QuotedClaim,
    chunk: RetrievedChunk,
) -> ConflictSide:
    return ConflictSide(
        label=label,
        snapshot_id=chunk.snapshot_id,
        doc_id=chunk.doc_id,
        chunk_id=chunk.chunk_id,
        title=chunk.title,
        headings=chunk.headings,
        is_synthetic=chunk.is_synthetic,
        doc_date=chunk.doc_date,
        product_version=chunk.product_version,
        audience=chunk.audience,
        claim_text=item.claim.text,
        code=item.claim.code,
        quote=chunk.text[item.quote_start : item.quote_end],
        quote_start=item.quote_start,
        quote_end=item.quote_end,
    )


def compose_conflict_result(
    conflict_check: ConflictCheckOutput,
    supported: list[QuotedClaim],
    retrieved: list[RetrievedChunk],
    total_claims: int,
) -> ConflictingResult:
    """Składa `ConflictingResult` (para A vs B, metadane, tabela porównania)."""
    resolved = select_conflict_sides(conflict_check, supported, retrieved)
    if resolved is None:
        raise ValueError("nieprawidłowy stan konfliktu dla compose_conflict_result")

    chunks = {chunk.chunk_id: chunk for chunk in retrieved}
    chunk_a = chunks[resolved.side_a.claim.chunk_id]
    chunk_b = chunks[resolved.side_b.claim.chunk_id]

    side_a = _build_conflict_side("A", resolved.side_a, chunk_a)
    side_b = _build_conflict_side("B", resolved.side_b, chunk_b)
    conflict_type = resolve_conflict_type(
        conflict_check.scope_relation, chunk_a, chunk_b
    )

    if conflict_check.comparison is not None:
        comp = conflict_check.comparison
        raw_a = comp.side_b_value if resolved.swapped else comp.side_a_value
        raw_b = comp.side_a_value if resolved.swapped else comp.side_b_value
        rec_a = raw_a.strip() or resolved.side_a.claim.text
        rec_b = raw_b.strip() or resolved.side_b.claim.text
        rec_label: str | None = comp.value_label.strip() or None
    else:
        rec_a = resolved.side_a.claim.text
        rec_b = resolved.side_b.claim.text
        rec_label = None

    comparison_rows = [
        ConflictComparisonRow(
            kind="recommendation", label=rec_label, side_a=rec_a, side_b=rec_b
        ),
        ConflictComparisonRow(
            kind="audience", side_a=chunk_a.audience, side_b=chunk_b.audience
        ),
        ConflictComparisonRow(
            kind="doc_date", side_a=chunk_a.doc_date, side_b=chunk_b.doc_date
        ),
        ConflictComparisonRow(
            kind="product_version",
            side_a=chunk_a.product_version,
            side_b=chunk_b.product_version,
        ),
    ]

    summary = (
        conflict_check.summary.strip()
        if conflict_check.summary and conflict_check.summary.strip()
        else DEFAULT_CONFLICT_SUMMARY
    )
    refine_hint = (
        conflict_check.refine_hint.strip()
        if conflict_check.refine_hint and conflict_check.refine_hint.strip()
        else None
    )

    return ConflictingResult(
        conflict_type=conflict_type,
        summary=summary,
        refine_hint=refine_hint,
        comparison_rows=comparison_rows,
        sides=(side_a, side_b),
        extra_conflicting_docs=resolved.extra_conflicting_docs,
        checked_chunks=checked_chunks(retrieved),
        omitted_claims=total_claims - len(supported),
    )


# --- komunikaty do modeli ----------------------------------------------------


def draft_message(question: str, retrieved: list[RetrievedChunk]) -> str:
    passages = "\n\n".join(
        f"[{chunk.rank}] chunk_id: {chunk.chunk_id}\n"
        f"Document: {chunk.title}\n"
        f"Section: {' > '.join(chunk.headings) if chunk.headings else '(none)'}\n"
        f"Text:\n{chunk.text}"
        for chunk in retrieved
    )
    return f"Question:\n{question}\n\nPassages:\n\n{passages}"


def verify_message(quoted: list[QuotedClaim], retrieved: list[RetrievedChunk]) -> str:
    """Tezy z ich fragmentami; bez pytania, żeby weryfikator oceniał wsparcie."""
    chunks = {chunk.chunk_id: chunk for chunk in retrieved}
    blocks = []
    for item in quoted:
        code = f"\nCode: {item.claim.code}" if item.claim.code else ""
        blocks.append(
            f"claim_index: {item.draft_index}\n"
            f"Claim: {item.claim.text}{code}\n"
            f"Passage:\n{chunks[item.claim.chunk_id].text}"
        )
    return "Claims to check:\n\n" + "\n\n---\n\n".join(blocks)


def detect_conflict_message(
    question: str, supported: list[QuotedClaim], retrieved: list[RetrievedChunk]
) -> str:
    """Wsparte tezy z co najmniej dwóch dokumentów wraz z metadanymi i fragmentami."""
    chunks = {chunk.chunk_id: chunk for chunk in retrieved}
    blocks = []
    for item in supported:
        chunk = chunks[item.claim.chunk_id]
        code = f"\nCode: {item.claim.code}" if item.claim.code else ""
        quote = chunk.text[item.quote_start : item.quote_end]
        blocks.append(
            f"claim_index: {item.draft_index}\n"
            f"doc_id: {chunk.doc_id}\n"
            f"chunk_id: {chunk.chunk_id}\n"
            f"Document: {chunk.title}\n"
            f"Section: {' > '.join(chunk.headings) if chunk.headings else '(none)'}\n"
            f"Metadata: is_synthetic={chunk.is_synthetic}, "
            f"doc_date={chunk.doc_date or 'unknown'}, "
            f"product_version={chunk.product_version or 'unknown'}, "
            f"audience={chunk.audience or 'unknown'}\n"
            f"Claim: {item.claim.text}{code}\n"
            f"Quote: {quote}\n"
            f"Passage:\n{chunk.text}"
        )
    return f"Question:\n{question}\n\nSupported claims:\n\n" + "\n\n---\n\n".join(
        blocks
    )


# --- węzły -------------------------------------------------------------------


def emit(stage: Stage, status: Literal["started", "done"], **data: Any) -> None:
    get_stream_writer()({"stage": stage, "status": status, "data": data})


class AnswerNodes:
    """Węzły grafu z wstrzykniętym modelem, pulą i ustawieniami."""

    def __init__(
        self, *, chat_model: BaseChatModel, pool: AsyncPool, settings: Settings
    ) -> None:
        self._chat_model = chat_model
        self._pool = pool
        self._settings = settings

    async def _call_model[T: BaseModel](
        self, schema: type[T], system: str, human: str
    ) -> T:
        """Jedno wywołanie modelu ze strict structured output i limitem czasu."""
        runnable = self._chat_model.with_structured_output(schema, strict=True)
        async with asyncio.timeout(self._settings.chat_timeout_s):
            raw = await runnable.ainvoke(
                [SystemMessage(content=system), HumanMessage(content=human)]
            )
        return schema.model_validate(raw)

    async def retrieve(self, state: AnswerState) -> AnswerState:
        emit("retrieve", "started")
        include_synthetic = state.get(
            "include_synthetic", self._settings.include_synthetic
        )
        async with self._pool.connection(timeout=CONNECTION_TIMEOUT_S) as conn:
            chunk_set_ids = await resolve_active_chunk_set_ids(
                conn,
                state["chunk_set_id"],
                include_synthetic=include_synthetic,
                synthetic_chunk_set_id=self._settings.effective_synthetic_chunk_set_id(),
            )
            extra = chunk_set_ids[1:]
            if extra:
                retrieved = await search_bm25(
                    conn,
                    state["question"],
                    chunk_set_id=state["chunk_set_id"],
                    extra_chunk_set_ids=extra,
                    k=state["k"],
                )
            else:
                retrieved = await search_bm25(
                    conn,
                    state["question"],
                    chunk_set_id=state["chunk_set_id"],
                    k=state["k"],
                )
        emit("retrieve", "done", checked=len(retrieved))
        return {
            "retrieved": retrieved,
            "retrieved_chunk_ids": [chunk.chunk_id for chunk in retrieved],
            "chunk_set_ids": chunk_set_ids,
        }

    async def draft(self, state: AnswerState) -> AnswerState:
        emit("draft", "started")
        output = await self._call_model(
            DraftOutput,
            load_prompt("draft"),
            draft_message(state["question"], state["retrieved"]),
        )
        emit("draft", "done", claims=len(output.claims))
        return {"draft_claims": output.claims}

    async def quote_check(self, state: AnswerState) -> AnswerState:
        emit("quote_check", "started")
        quoted, rejected = quote_check(state["draft_claims"], state["retrieved"])
        emit("quote_check", "done", accepted=len(quoted), rejected=len(rejected))
        return {"quoted": quoted, "rejected": rejected}

    async def verify(self, state: AnswerState) -> AnswerState:
        emit("verify", "started")
        output = await self._call_model(
            VerifyOutput,
            load_prompt("verify"),
            verify_message(state["quoted"], state["retrieved"]),
        )
        supported = len(supported_claims(state["quoted"], output.verdicts))
        omitted = len(state["draft_claims"]) - supported
        emit("verify", "done", supported=supported, omitted=omitted)
        return {"verdicts": output.verdicts}

    async def detect_conflict(self, state: AnswerState) -> AnswerState:
        emit("detect_conflict", "started")
        supported = supported_claims(state["quoted"], state["verdicts"])
        output = await self._call_model(
            ConflictCheckOutput,
            load_prompt("detect_conflict"),
            detect_conflict_message(state["question"], supported, state["retrieved"]),
        )
        emit("detect_conflict", "done", has_conflict=output.has_conflict)
        return {"conflict_check": output}

    async def compose(self, state: AnswerState) -> AnswerState:
        emit("compose", "started")
        supported = supported_claims(state["quoted"], state["verdicts"])
        result = compose_answer(
            supported, state["retrieved"], len(state["draft_claims"])
        )
        emit("compose", "done")
        return {"outcome": "answered", "answer": result}

    async def compose_conflict(self, state: AnswerState) -> AnswerState:
        emit("compose", "started")
        supported = supported_claims(state["quoted"], state["verdicts"])
        result = compose_conflict_result(
            state["conflict_check"],
            supported,
            state["retrieved"],
            len(state["draft_claims"]),
        )
        emit("compose", "done")
        return {"outcome": "conflicting", "answer": result}

    async def abstain(self, state: AnswerState) -> AnswerState:
        emit("abstain", "started")
        retrieved = state.get("retrieved", [])
        drafted = state.get("draft_claims", [])
        reason: AbstainReason
        if not retrieved:
            reason = "no_hits"
        elif not drafted:
            reason = "no_claims"
        else:
            reason = "none_supported"
        emit("abstain", "done", reason=reason)
        return {
            "outcome": "abstained",
            "answer": AbstainedResult(
                reason=reason,
                checked_chunks=checked_chunks(retrieved),
                omitted_claims=len(drafted),
            ),
        }
