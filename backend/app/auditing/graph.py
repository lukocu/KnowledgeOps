"""4-etapowy graf audytu LangGraph: extract -> retrieve -> verify -> aggregate."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from app.auditing.prompts import load_prompt
from app.auditing.rules import (
    PreparedClaim,
    aggregate_note_verdict,
    build_checked_docs,
    build_closest_evidence,
    normalize_extracted_claims,
    resolve_claim_verdict,
)
from app.auditing.schemas import (
    AuditStage,
    CaseContext,
    ClaimVerdictOutput,
    ExtractOutput,
    NoteVerdict,
)
from app.auditing.store import NewAuditClaim
from app.db import CONNECTION_TIMEOUT_S, AsyncPool
from app.retrieval import RetrievedChunk, resolve_active_chunk_set_ids, search_bm25
from app.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditProgressUpdate:
    """Raport postępu wysyłany z węzłów grafu do warstwy uruchomieniowej."""

    stage: AuditStage
    claims_total: int | None = None
    claims_done: int | None = None
    case_context: dict[str, Any] | None = None


ProgressCallback = Callable[[AuditProgressUpdate], Awaitable[None]]
RetrieveFn = Callable[
    [str, str, bool, int],
    Awaitable[tuple[list[str], list[RetrievedChunk]]],
]


class AuditState(TypedDict, total=False):
    case_description: str
    resolution_note: str
    chunk_set_id: str
    include_synthetic: bool
    k: int
    case_context: CaseContext
    prepared_claims: list[PreparedClaim]
    chunk_set_ids: list[str]
    candidates_by_claim: dict[int, list[RetrievedChunk]]
    claims: list[NewAuditClaim]
    note_verdict: NoteVerdict


AuditGraph = CompiledStateGraph[AuditState, Any, AuditState, AuditState]


def initial_audit_state(
    *,
    case_description: str,
    resolution_note: str,
    settings: Settings,
    chunk_set_id: str | None = None,
    include_synthetic: bool | None = None,
    k: int | None = None,
) -> AuditState:
    """Stan wejściowy grafu audytu z dziedziczeniem ustawień audytu."""
    return {
        "case_description": case_description,
        "resolution_note": resolution_note,
        "chunk_set_id": chunk_set_id or settings.effective_chunk_set_id(),
        "include_synthetic": (
            settings.include_synthetic
            if include_synthetic is None
            else include_synthetic
        ),
        "k": settings.audit_k if k is None else k,
    }


def make_pool_retriever(pool: AsyncPool, settings: Settings) -> RetrieveFn:
    """Tworzy funkcję wyszukiwania BM25 z krótką transakcją per zapytanie."""
    cached_ids: dict[tuple[str, bool], list[str]] = {}
    cache_lock = asyncio.Lock()

    async def _retrieve(
        query: str,
        chunk_set_id: str,
        include_synthetic: bool,
        k: int,
    ) -> tuple[list[str], list[RetrievedChunk]]:
        cache_key = (chunk_set_id, include_synthetic)
        chunk_set_ids = cached_ids.get(cache_key)
        if chunk_set_ids is None:
            async with cache_lock:
                chunk_set_ids = cached_ids.get(cache_key)
                if chunk_set_ids is None:
                    async with pool.connection(timeout=CONNECTION_TIMEOUT_S) as conn:
                        chunk_set_ids = await resolve_active_chunk_set_ids(
                            conn,
                            chunk_set_id,
                            include_synthetic=include_synthetic,
                            synthetic_chunk_set_id=settings.effective_synthetic_chunk_set_id(),
                        )
                    cached_ids[cache_key] = chunk_set_ids

        extra = chunk_set_ids[1:]
        async with pool.connection(timeout=CONNECTION_TIMEOUT_S) as conn:
            if extra:
                hits = await search_bm25(
                    conn,
                    query,
                    chunk_set_id=chunk_set_id,
                    extra_chunk_set_ids=extra,
                    k=k,
                )
            else:
                hits = await search_bm25(
                    conn,
                    query,
                    chunk_set_id=chunk_set_id,
                    k=k,
                )
        return chunk_set_ids, hits

    return _retrieve


def extract_message(case_description: str, resolution_note: str) -> str:
    """Buduje wiadomość wejściową dla etapu `extract`."""
    return (
        f"Case description:\n{case_description}\n\n"
        f"Resolution note (unverified — extract claims from this text):\n"
        f"{resolution_note}"
    )


def verify_claim_message(
    claim: PreparedClaim,
    case_context: CaseContext,
    candidates: Sequence[RetrievedChunk],
) -> str:
    """Buduje wiadomość wejściową dla etapu `verify` jednej tezy."""
    constraints_text = (
        ", ".join(case_context.constraints) if case_context.constraints else "none"
    )
    context_lines = [
        f"Problem: {case_context.problem or 'unknown'}",
        f"Environment: {case_context.environment or 'unknown'}",
        f"Solution: {case_context.solution or 'unknown'}",
        f"Constraints: {constraints_text}",
    ]
    passages = "\n\n---\n\n".join(
        f"[{chunk.rank}] chunk_id: {chunk.chunk_id}\n"
        f"doc_id: {chunk.doc_id}\n"
        f"Document: {chunk.title}\n"
        f"Section: {' > '.join(chunk.headings) if chunk.headings else '(none)'}\n"
        f"Metadata: is_synthetic={chunk.is_synthetic}, "
        f"doc_date={chunk.doc_date or 'unknown'}, "
        f"product_version={chunk.product_version or 'unknown'}, "
        f"audience={chunk.audience or 'unknown'}\n"
        f"Text:\n{chunk.text}"
        for chunk in candidates
    )
    return (
        "Case context:\n"
        + "\n".join(context_lines)
        + "\n\nClaim to verify:\n"
        + f"Label: {claim.claim_label}\n"
        + f"Claim: {claim.claim_text}\n"
        + f"Source excerpt: {claim.source_excerpt}\n\n"
        + f"Candidate passages:\n\n{passages}"
    )


class AuditNodes:
    """Węzły grafu audytu z wstrzykniętym modelem, retrieverem i callbackiem postępu."""

    def __init__(
        self,
        *,
        chat_model: BaseChatModel,
        retrieve_fn: RetrieveFn,
        settings: Settings,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self._chat_model = chat_model
        self._retrieve_fn = retrieve_fn
        self._settings = settings
        self._on_progress = on_progress

    async def _report(self, update: AuditProgressUpdate) -> None:
        if self._on_progress is not None:
            await self._on_progress(update)

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

    async def extract(self, state: AuditState) -> AuditState:
        await self._report(AuditProgressUpdate(stage="extracting"))
        output = await self._call_model(
            ExtractOutput,
            load_prompt("extract"),
            extract_message(state["case_description"], state["resolution_note"]),
        )
        prepared = normalize_extracted_claims(
            output.claims,
            state["resolution_note"],
            max_claims=self._settings.audit_max_claims,
        )
        return {
            "case_context": output.case_context,
            "prepared_claims": prepared,
        }

    async def retrieve(self, state: AuditState) -> AuditState:
        prepared = state["prepared_claims"]
        total = len(prepared)
        chunk_set_id = state["chunk_set_id"]
        include_synthetic = state.get(
            "include_synthetic", self._settings.include_synthetic
        )
        k = state.get("k", self._settings.audit_k)

        await self._report(
            AuditProgressUpdate(
                stage="retrieving",
                claims_total=total,
                claims_done=0,
                case_context=state["case_context"].model_dump(),
            )
        )
        if not prepared:
            return {
                "candidates_by_claim": {},
                "chunk_set_ids": [chunk_set_id],
            }

        semaphore = asyncio.Semaphore(max(1, self._settings.audit_claim_concurrency))
        progress_lock = asyncio.Lock()
        done_count = 0

        async def _retrieve_one(
            claim: PreparedClaim,
        ) -> tuple[int, list[str], list[RetrievedChunk]]:
            nonlocal done_count
            async with semaphore:
                active_ids, hits = await self._retrieve_fn(
                    claim.search_query,
                    chunk_set_id,
                    include_synthetic,
                    k,
                )
            async with progress_lock:
                done_count += 1
                await self._report(
                    AuditProgressUpdate(
                        stage="retrieving",
                        claims_total=total,
                        claims_done=done_count,
                    )
                )
            return claim.claim_index, active_ids, hits

        results = await asyncio.gather(*(_retrieve_one(claim) for claim in prepared))
        candidates_by_claim: dict[int, list[RetrievedChunk]] = {}
        resolved_chunk_set_ids: list[str] = []
        for claim_index, active_ids, hits in results:
            candidates_by_claim[claim_index] = hits
            if not resolved_chunk_set_ids and active_ids:
                resolved_chunk_set_ids = list(active_ids)

        return {
            "candidates_by_claim": candidates_by_claim,
            "chunk_set_ids": resolved_chunk_set_ids or [chunk_set_id],
        }

    async def verify(self, state: AuditState) -> AuditState:
        prepared = state["prepared_claims"]
        total = len(prepared)
        candidates_by_claim = state["candidates_by_claim"]
        case_context = state["case_context"]

        await self._report(
            AuditProgressUpdate(
                stage="verifying",
                claims_total=total,
                claims_done=0,
            )
        )
        if not prepared:
            return {"claims": []}

        semaphore = asyncio.Semaphore(max(1, self._settings.audit_claim_concurrency))
        progress_lock = asyncio.Lock()
        done_count = 0
        system_prompt = load_prompt("verify_claim")

        async def _verify_one(claim: PreparedClaim) -> NewAuditClaim:
            nonlocal done_count
            candidates = candidates_by_claim.get(claim.claim_index, [])
            checked_docs = [doc.model_dump() for doc in build_checked_docs(candidates)]

            if not candidates:
                result = NewAuditClaim(
                    claim_index=claim.claim_index,
                    claim_label=claim.claim_label,
                    claim_text=claim.claim_text,
                    source_excerpt=claim.source_excerpt,
                    source_start=claim.source_start,
                    source_end=claim.source_end,
                    search_query=claim.search_query,
                    verdict="insufficient",
                    rationale=(
                        "No candidate documentation passages were found for this claim."
                    ),
                    scope_note=None,
                    evidence=[],
                    checked_docs=[],
                    error=None,
                )
            else:
                try:
                    async with semaphore:
                        raw = await self._call_model(
                            ClaimVerdictOutput,
                            system_prompt,
                            verify_claim_message(claim, case_context, candidates),
                        )
                except TimeoutError:
                    closest = build_closest_evidence(candidates)
                    result = NewAuditClaim(
                        claim_index=claim.claim_index,
                        claim_label=claim.claim_label,
                        claim_text=claim.claim_text,
                        source_excerpt=claim.source_excerpt,
                        source_start=claim.source_start,
                        source_end=claim.source_end,
                        search_query=claim.search_query,
                        verdict="insufficient",
                        rationale=(
                            "Verification timed out before the model"
                            " returned a verdict."
                        ),
                        scope_note=None,
                        evidence=[closest.model_dump()] if closest is not None else [],
                        checked_docs=checked_docs,
                        error="Przekroczono limit czasu weryfikacji tezy.",
                    )
                except Exception:
                    logger.warning(
                        "Błąd weryfikacji tezy %s", claim.claim_index, exc_info=True
                    )
                    closest = build_closest_evidence(candidates)
                    result = NewAuditClaim(
                        claim_index=claim.claim_index,
                        claim_label=claim.claim_label,
                        claim_text=claim.claim_text,
                        source_excerpt=claim.source_excerpt,
                        source_start=claim.source_start,
                        source_end=claim.source_end,
                        search_query=claim.search_query,
                        verdict="insufficient",
                        rationale="Verification failed due to a model error.",
                        scope_note=None,
                        evidence=[closest.model_dump()] if closest is not None else [],
                        checked_docs=checked_docs,
                        error="Nie udało się zweryfikować tezy z powodu błędu modelu.",
                    )
                else:
                    resolved = resolve_claim_verdict(raw, candidates)
                    result = NewAuditClaim(
                        claim_index=claim.claim_index,
                        claim_label=claim.claim_label,
                        claim_text=claim.claim_text,
                        source_excerpt=claim.source_excerpt,
                        source_start=claim.source_start,
                        source_end=claim.source_end,
                        search_query=claim.search_query,
                        verdict=resolved.verdict,
                        rationale=resolved.rationale,
                        scope_note=resolved.scope_note,
                        evidence=[ev.model_dump() for ev in resolved.evidence],
                        checked_docs=checked_docs,
                        error=None,
                    )

            async with progress_lock:
                done_count += 1
                await self._report(
                    AuditProgressUpdate(
                        stage="verifying",
                        claims_total=total,
                        claims_done=done_count,
                    )
                )
            return result

        verified = list(
            await asyncio.gather(*(_verify_one(claim) for claim in prepared))
        )
        verified.sort(key=lambda item: item.claim_index)
        return {"claims": verified}

    async def aggregate(self, state: AuditState) -> AuditState:
        claims = state["claims"]
        await self._report(
            AuditProgressUpdate(
                stage="aggregating",
                claims_total=len(claims),
                claims_done=len(claims),
            )
        )
        verdict = aggregate_note_verdict([claim.verdict for claim in claims])
        return {"note_verdict": verdict}


def build_audit_graph(
    *,
    chat_model: BaseChatModel,
    settings: Settings,
    pool: AsyncPool | None = None,
    retrieve_fn: RetrieveFn | None = None,
    on_progress: ProgressCallback | None = None,
) -> AuditGraph:
    """Kompiluje 4-etapowy graf audytu (extract -> retrieve -> verify -> aggregate)."""
    resolved_retrieve = retrieve_fn
    if resolved_retrieve is None:
        if pool is None:
            raise ValueError(
                "build_audit_graph wymaga parametru `pool` lub `retrieve_fn`"
            )
        resolved_retrieve = make_pool_retriever(pool, settings)

    nodes = AuditNodes(
        chat_model=chat_model,
        retrieve_fn=resolved_retrieve,
        settings=settings,
        on_progress=on_progress,
    )
    builder = StateGraph(AuditState)
    builder.add_node("extract", nodes.extract)
    builder.add_node("retrieve", nodes.retrieve)
    builder.add_node("verify", nodes.verify)
    builder.add_node("aggregate", nodes.aggregate)

    builder.add_edge(START, "extract")
    builder.add_edge("extract", "retrieve")
    builder.add_edge("retrieve", "verify")
    builder.add_edge("verify", "aggregate")
    builder.add_edge("aggregate", END)
    return builder.compile()
