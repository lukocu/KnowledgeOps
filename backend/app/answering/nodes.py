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
    DraftClaim,
    DraftOutput,
    RejectionReason,
    VerifyOutput,
)
from app.db import CONNECTION_TIMEOUT_S, AsyncPool
from app.retrieval import RetrievedChunk, search_bm25
from app.settings import Settings

Stage = Literal["retrieve", "draft", "quote_check", "verify", "compose", "abstain"]


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
    k: int
    retrieved: list[RetrievedChunk]
    retrieved_chunk_ids: list[str]
    draft_claims: list[DraftClaim]
    rejected: list[RejectedClaim]
    quoted: list[QuotedClaim]
    verdicts: list[ClaimVerdict]
    outcome: Literal["answered", "abstained"]
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
        async with self._pool.connection(timeout=CONNECTION_TIMEOUT_S) as conn:
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

    async def compose(self, state: AnswerState) -> AnswerState:
        emit("compose", "started")
        supported = supported_claims(state["quoted"], state["verdicts"])
        result = compose_answer(
            supported, state["retrieved"], len(state["draft_claims"])
        )
        emit("compose", "done")
        return {"outcome": "answered", "answer": result}

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
