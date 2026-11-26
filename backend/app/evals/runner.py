"""Asynchroniczny runner ewaluacji abstynencji i jakości odpowiedzi (S-06)."""

import asyncio
import hashlib
import json
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Literal, cast

from langchain_core.callbacks import BaseCallbackHandler, UsageMetadataCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langfuse import Langfuse
from pydantic import BaseModel, ConfigDict, Field

from app.answering.graph import AnswerGraph, build_answer_graph, initial_state
from app.answering.model import JudgeModelInfo, make_chat_model, make_judge_model
from app.answering.nodes import AnswerState
from app.answering.prompts import prompt_versions as answer_prompt_versions
from app.answering.schemas import AbstainedResult, AnsweredResult, ConflictingResult
from app.db import CONNECTION_TIMEOUT_S, AsyncPool
from app.evals.dataset import DatasetMetadata, EvalItem, LoadedDataset
from app.evals.judge import EvalJudge
from app.evals.langfuse_eval import run_langfuse_experiment
from app.evals.metrics import (
    EvalItemExecution,
    RunSummary,
    TokenUsage,
    aggregate_run,
    check_citation_invariants,
    classify_abstention_reason,
)
from app.evals.prompts import prompt_versions as eval_prompt_versions
from app.observability import get_langfuse_client, make_trace_handler, run_config
from app.retrieval import ChunkSetReproInfo, get_chunk_set_repro_info
from app.settings import Settings

DEFAULT_LANGFUSE_DATASET_NAME = "knowledgeops/abstention-eval"
EvalSplit = Literal["dev", "test", "all"]


class LangfuseNotConfiguredError(RuntimeError):
    """Brak kluczy Langfuse przy uruchomieniu bez flagi `--no-langfuse`."""


class EvalRunConfig(BaseModel):
    """Pełna, odtwarzalna konfiguracja pojedynczego przebiegu ewaluacji."""

    model_config = ConfigDict(frozen=True)

    split: EvalSplit
    limit: int | None = None
    concurrency: int = 2
    use_langfuse: bool = True
    dataset_name: str = DEFAULT_LANGFUSE_DATASET_NAME
    run_name: str
    repro_info: ChunkSetReproInfo
    chat_model: str
    chat_reasoning_effort: str
    k: int
    answer_prompt_versions: dict[str, str]
    judge_model_info: JudgeModelInfo
    judge_prompt_versions: dict[str, str]
    config_sha256: str


class EvalRunArtifact(BaseModel):
    """Kompletny, serializowalny zapis przebiegu ewaluacji (`data/evals/<run>.json`)."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    config: EvalRunConfig
    dataset: DatasetMetadata
    summary: RunSummary
    items: list[EvalItemExecution]
    item_questions: dict[str, str] = Field(default_factory=dict)
    item_reference_answers: dict[str, str] = Field(default_factory=dict)
    langfuse_run_id: str | None = None
    langfuse_run_url: str | None = None
    started_at: str
    finished_at: str


def compute_config_sha256(
    *,
    split: EvalSplit,
    limit: int | None,
    concurrency: int,
    use_langfuse: bool,
    dataset_name: str,
    repro_info: ChunkSetReproInfo,
    chat_model: str,
    chat_reasoning_effort: str,
    k: int,
    answer_prompts: dict[str, str],
    judge_model_info: JudgeModelInfo,
    judge_prompts: dict[str, str],
) -> str:
    """Oblicza kanoniczny SHA-256 całej konfiguracji przebiegu ewaluacji."""
    payload = {
        "split": split,
        "limit": limit,
        "concurrency": concurrency,
        "use_langfuse": use_langfuse,
        "dataset_name": dataset_name,
        "repro_info": repro_info.model_dump(mode="json"),
        "chat_model": chat_model,
        "chat_reasoning_effort": chat_reasoning_effort,
        "k": k,
        "answer_prompt_versions": answer_prompts,
        "judge_model_info": asdict(judge_model_info),
        "judge_prompt_versions": judge_prompts,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def default_run_name(split: EvalSplit, *, now: datetime | None = None) -> str:
    """Deterministyczny wzorzec nazwy przebiegu: `abstention-<split>-<UTC>`."""
    current = now if now is not None else datetime.now(UTC)
    return f"abstention-{split}-{current.strftime('%Y%m%dT%H%M%SZ')}"


def estimate_llm_calls(items: Sequence[EvalItem]) -> tuple[int, int]:
    """Szacuje przedział `(min_calls, max_calls)` wywołań LLM dla listy pytań.

    Minimum: 1 wywołanie `draft` na pytanie (gdy brak trafień BM25 może być 0,
    ale konserwatywnie raportujemy co najmniej 1 przy założeniu trafień).
    Maksimum: `draft` + `verify` + opcjonalny `detect_conflict` + `judge_citations`
    na każde pytanie oraz `judge_reference` dla każdego pytania `answerable_in_corpus`.
    """
    n_total = len(items)
    n_answerable = sum(
        1 for item in items if item.verified_label == "answerable_in_corpus"
    )
    return n_total, (4 * n_total) + n_answerable


def format_cost_confirmation(
    *,
    items: Sequence[EvalItem],
    split: EvalSplit,
    chat_model: str,
    chat_reasoning_effort: str,
    judge_model_info: JudgeModelInfo,
    use_langfuse: bool,
    dataset_name: str,
) -> str:
    """Buduje podsumowanie kosztu przed uruchomieniem przebiegu ewaluacji."""
    min_calls, max_calls = estimate_llm_calls(items)
    n_unanswerable = sum(
        1 for item in items if item.verified_label == "verified_unanswerable"
    )
    n_answerable = sum(
        1 for item in items if item.verified_label == "answerable_in_corpus"
    )
    judge_suffix = (
        " [FALLBACK na CHAT_MODEL]"
        if judge_model_info.is_fallback_to_chat_model
        else ""
    )
    langfuse_line = (
        f"Langfuse Cloud (dataset: {dataset_name})"
        if use_langfuse
        else "LOKALNY (--no-langfuse, bez zapisu w Langfuse Cloud)"
    )
    lines = [
        "=== Podsumowanie przebiegu ewaluacji (S-06) ===",
        (
            f"Pytania ({split}): {len(items)}"
            f" (verified_unanswerable={n_unanswerable},"
            f" answerable_in_corpus={n_answerable})"
        ),
        f"Model odpowiedzi: {chat_model} (reasoning_effort={chat_reasoning_effort})",
        (
            f"Model sędziego: {judge_model_info.model}"
            f" (reasoning_effort={judge_model_info.reasoning_effort}){judge_suffix}"
        ),
        (
            f"Szacowana liczba wywołań LLM: {min_calls}–{max_calls}"
            " (maks. w najgorszym razie)"
        ),
        f"Tryb rejestrowania: {langfuse_line}",
    ]
    return "\n".join(lines)


def confirm_eval_run(
    *,
    items: Sequence[EvalItem],
    split: EvalSplit,
    chat_model: str,
    chat_reasoning_effort: str,
    judge_model_info: JudgeModelInfo,
    use_langfuse: bool,
    dataset_name: str,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> bool:
    """Wyświetla bramkę potwierdzenia kosztu i pyta operatora o zgodę."""
    print_fn(
        format_cost_confirmation(
            items=items,
            split=split,
            chat_model=chat_model,
            chat_reasoning_effort=chat_reasoning_effort,
            judge_model_info=judge_model_info,
            use_langfuse=use_langfuse,
            dataset_name=dataset_name,
        )
    )
    reply = input_fn("Kontynuować przebieg ewaluacji? [t/N]: ").strip().lower()
    return reply in {"t", "tak", "y", "yes"}


def ensure_langfuse_ready(
    settings: Settings,
    *,
    use_langfuse: bool,
    langfuse_client: Langfuse | None = None,
) -> Langfuse | None:
    """Waliduje konfigurację Langfuse (fail-fast przed pierwszym wywołaniem LLM)."""
    if not use_langfuse:
        return None
    client = (
        langfuse_client
        if langfuse_client is not None
        else get_langfuse_client(settings)
    )
    if client is None:
        raise LangfuseNotConfiguredError(
            "Brak kluczy LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY. "
            "Ustaw zmienne środowiskowe Langfuse albo uruchom ponownie z flagą "
            "--no-langfuse."
        )
    return client


def extract_token_usage(handler: UsageMetadataCallbackHandler) -> TokenUsage | None:
    """Sumuje `usage_metadata` zebrane ze wszystkich wywołań LLM dla jednego pytania."""
    if not handler.usage_metadata:
        return None
    input_tokens = sum(
        int(meta.get("input_tokens", 0)) for meta in handler.usage_metadata.values()
    )
    output_tokens = sum(
        int(meta.get("output_tokens", 0)) for meta in handler.usage_metadata.values()
    )
    total_tokens = sum(
        int(meta.get("total_tokens", 0)) for meta in handler.usage_metadata.values()
    )
    if input_tokens == 0 and output_tokens == 0 and total_tokens == 0:
        return None
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


_extract_token_usage = extract_token_usage


async def execute_item(
    item: EvalItem,
    *,
    graph: AnswerGraph,
    judge: EvalJudge,
    settings: Settings,
    chunk_set_id: str,
    use_langfuse: bool,
) -> EvalItemExecution:
    """Wykonuje graf S-02 dla jednego pytania, mierzy `latency_ms` i uruchamia sędziego.

    Pomiar `latency_ms` obejmuje wyłącznie wykonanie grafu odpowiedzi (od `retrieve`
    do `compose`/`abstain`), bez czasu wywołań sędziego LLM.
    """
    handler = make_trace_handler(settings) if use_langfuse else None
    usage_handler = UsageMetadataCallbackHandler()
    run_cfg = run_config(
        settings,
        chunk_set_id=chunk_set_id,
        k=settings.answer_k,
        handler=handler,
    )
    raw_callbacks = run_cfg.get("callbacks")
    callbacks: list[BaseCallbackHandler] = (
        list(raw_callbacks) if isinstance(raw_callbacks, list) else []
    )
    callbacks.append(usage_handler)
    run_cfg["callbacks"] = callbacks

    started = time.monotonic()
    try:
        async with asyncio.timeout(settings.answer_deadline_s):
            final_state = cast(
                AnswerState,
                await graph.ainvoke(
                    initial_state(
                        item.question,
                        settings,
                        chunk_set_id=chunk_set_id,
                        include_synthetic=False,
                    ),
                    run_cfg,
                ),
            )
    except TimeoutError:
        latency_ms = (time.monotonic() - started) * 1000.0
        return EvalItemExecution(
            question_id=item.question_id,
            split=item.split,
            verified_label=item.verified_label,
            outcome="failed",
            latency_ms=latency_ms,
            error=(
                f"TimeoutError: przekroczono answer_deadline_s"
                f" ({settings.answer_deadline_s:g}s)"
            ),
            usage=_extract_token_usage(usage_handler),
        )
    except Exception as exc:
        latency_ms = (time.monotonic() - started) * 1000.0
        return EvalItemExecution(
            question_id=item.question_id,
            split=item.split,
            verified_label=item.verified_label,
            outcome="failed",
            latency_ms=latency_ms,
            error=f"{type(exc).__name__}: {exc}",
            usage=_extract_token_usage(usage_handler),
        )

    latency_ms = (time.monotonic() - started) * 1000.0
    result = final_state.get("answer")
    if result is None:
        return EvalItemExecution(
            question_id=item.question_id,
            split=item.split,
            verified_label=item.verified_label,
            outcome="failed",
            latency_ms=latency_ms,
            error="brak wyniku answer w stanie końcowym grafu",
            usage=_extract_token_usage(usage_handler),
        )

    if isinstance(result, AbstainedResult):
        quoted_count = len(final_state["quoted"]) if "quoted" in final_state else None
        cause = classify_abstention_reason(result, quoted_count=quoted_count)
        return EvalItemExecution(
            question_id=item.question_id,
            split=item.split,
            verified_label=item.verified_label,
            outcome="abstained",
            latency_ms=latency_ms,
            answer=result,
            abstention_reason=cause,
            usage=_extract_token_usage(usage_handler),
        )

    if isinstance(result, ConflictingResult):
        return EvalItemExecution(
            question_id=item.question_id,
            split=item.split,
            verified_label=item.verified_label,
            outcome="conflicting",
            latency_ms=latency_ms,
            answer=result,
            usage=_extract_token_usage(usage_handler),
        )

    assert isinstance(result, AnsweredResult)
    chunk_texts = {
        chunk.chunk_id: chunk.text for chunk in final_state.get("retrieved", [])
    }
    invariants = check_citation_invariants(result, chunk_texts)
    citation_judge = await judge.judge_citations(
        result.claims,
        result.citations,
        chunk_texts,
        callbacks=[usage_handler],
    )
    reference_judge = None
    if item.verified_label == "answerable_in_corpus" and item.answer.strip():
        reference_judge = await judge.judge_reference(
            item.question,
            item.answer,
            result.claims,
            callbacks=[usage_handler],
        )

    cited_chunk_texts = {
        citation.chunk_id: chunk_texts[citation.chunk_id]
        for citation in result.citations
        if citation.chunk_id in chunk_texts
    }
    return EvalItemExecution(
        question_id=item.question_id,
        split=item.split,
        verified_label=item.verified_label,
        outcome="answered",
        latency_ms=latency_ms,
        answer=result,
        citation_invariants=invariants,
        citation_judge=citation_judge,
        reference_judge=reference_judge,
        cited_chunk_texts=cited_chunk_texts,
        usage=_extract_token_usage(usage_handler),
    )


def _experiment_metadata(
    config: EvalRunConfig, dataset: DatasetMetadata
) -> dict[str, Any]:
    return {
        "split": config.split,
        "limit": config.limit,
        "concurrency": config.concurrency,
        "snapshot_id": config.repro_info.snapshot_id,
        "revision": config.repro_info.revision,
        "chunk_set_id": config.repro_info.chunk_set_id,
        "variant": config.repro_info.variant,
        "chunker_config_sha256": config.repro_info.config_sha256,
        "chunk_set_state_sha256": config.repro_info.state_sha256,
        "train_json_sha256": dataset.train_json_sha256,
        "split_seed": dataset.split_seed,
        "chat_model": config.chat_model,
        "chat_reasoning_effort": config.chat_reasoning_effort,
        "k": config.k,
        "answer_prompt_versions": config.answer_prompt_versions,
        "judge_model": config.judge_model_info.model,
        "judge_reasoning_effort": config.judge_model_info.reasoning_effort,
        "judge_is_fallback_to_chat_model": (
            config.judge_model_info.is_fallback_to_chat_model
        ),
        "judge_prompt_versions": config.judge_prompt_versions,
        "config_sha256": config.config_sha256,
    }


async def run_abstention_eval(
    *,
    dataset: LoadedDataset,
    settings: Settings,
    pool: AsyncPool,
    split: EvalSplit = "all",
    limit: int | None = None,
    concurrency: int = 2,
    use_langfuse: bool = True,
    dataset_name: str = DEFAULT_LANGFUSE_DATASET_NAME,
    run_name: str | None = None,
    chat_model: BaseChatModel | None = None,
    judge_model: BaseChatModel | None = None,
    judge_model_info: JudgeModelInfo | None = None,
    langfuse_client: Langfuse | None = None,
    repro_info: ChunkSetReproInfo | None = None,
) -> EvalRunArtifact:
    """Uruchamia pełny przebieg ewaluacji S-06 (Langfuse Cloud lub lokalnie)."""
    if concurrency < 1:
        raise ValueError("concurrency musi być >= 1")
    if limit is not None and limit < 1:
        raise ValueError("limit musi być >= 1")

    # Fail-fast przed utworzeniem modeli i pierwszym wywołaniem LLM.
    active_langfuse = ensure_langfuse_ready(
        settings, use_langfuse=use_langfuse, langfuse_client=langfuse_client
    )

    items = list(dataset.items[:limit]) if limit is not None else list(dataset.items)
    chunk_set_id = settings.effective_chunk_set_id()

    if repro_info is None:
        async with pool.connection(timeout=CONNECTION_TIMEOUT_S) as conn:
            active_repro = await get_chunk_set_repro_info(conn, chunk_set_id)
    else:
        active_repro = repro_info

    active_chat_model = (
        chat_model if chat_model is not None else make_chat_model(settings)
    )
    if judge_model is not None and judge_model_info is not None:
        active_judge_model = judge_model
        active_judge_info = judge_model_info
    elif judge_model is not None:
        active_judge_model = judge_model
        is_fallback = not settings.eval_judge_model
        active_judge_info = JudgeModelInfo(
            model=settings.eval_judge_model or settings.chat_model,
            reasoning_effort=(
                settings.eval_judge_reasoning_effort or settings.chat_reasoning_effort
            ),
            is_fallback_to_chat_model=is_fallback,
        )
    else:
        active_judge_model, active_judge_info = make_judge_model(settings)

    ans_prompts = answer_prompt_versions()
    ev_prompts = eval_prompt_versions()
    effective_run_name = run_name or default_run_name(split)
    cfg_hash = compute_config_sha256(
        split=split,
        limit=limit,
        concurrency=concurrency,
        use_langfuse=use_langfuse,
        dataset_name=dataset_name,
        repro_info=active_repro,
        chat_model=settings.chat_model,
        chat_reasoning_effort=settings.chat_reasoning_effort,
        k=settings.answer_k,
        answer_prompts=ans_prompts,
        judge_model_info=active_judge_info,
        judge_prompts=ev_prompts,
    )
    config = EvalRunConfig(
        split=split,
        limit=limit,
        concurrency=concurrency,
        use_langfuse=use_langfuse,
        dataset_name=dataset_name,
        run_name=effective_run_name,
        repro_info=active_repro,
        chat_model=settings.chat_model,
        chat_reasoning_effort=settings.chat_reasoning_effort,
        k=settings.answer_k,
        answer_prompt_versions=ans_prompts,
        judge_model_info=active_judge_info,
        judge_prompt_versions=ev_prompts,
        config_sha256=cfg_hash,
    )

    graph = build_answer_graph(
        chat_model=active_chat_model, pool=pool, settings=settings
    )
    judge = EvalJudge(model=active_judge_model, timeout_s=settings.eval_judge_timeout_s)

    async def _exec(item: EvalItem) -> EvalItemExecution:
        return await execute_item(
            item,
            graph=graph,
            judge=judge,
            settings=settings,
            chunk_set_id=chunk_set_id,
            use_langfuse=use_langfuse,
        )

    started_at = datetime.now(UTC).isoformat()
    langfuse_run_id: str | None = None
    langfuse_run_url: str | None = None

    if use_langfuse and active_langfuse is not None:
        lf_output = await run_langfuse_experiment(
            client=active_langfuse,
            dataset_name=dataset_name,
            run_name=effective_run_name,
            description=f"KnowledgeOps S-06 abstention & citation eval ({split})",
            items=items,
            execute_fn=_exec,
            concurrency=concurrency,
            metadata=_experiment_metadata(config, dataset.metadata),
            dataset_metadata={
                "snapshot_id": dataset.metadata.snapshot_id,
                "train_json_sha256": dataset.metadata.train_json_sha256,
                "split_seed": dataset.metadata.split_seed,
            },
        )
        executions = lf_output.executions
        langfuse_run_id = lf_output.langfuse_run_id
        langfuse_run_url = lf_output.langfuse_run_url
    else:
        semaphore = asyncio.Semaphore(concurrency)

        async def _bounded(item: EvalItem) -> EvalItemExecution:
            async with semaphore:
                return await _exec(item)

        executions = list(await asyncio.gather(*(_bounded(item) for item in items)))

    finished_at = datetime.now(UTC).isoformat()
    summary = aggregate_run(executions)

    return EvalRunArtifact(
        config=config,
        dataset=dataset.metadata,
        summary=summary,
        items=executions,
        item_questions={item.question_id: item.question for item in items},
        item_reference_answers={
            item.question_id: item.answer for item in items if item.answer.strip()
        },
        langfuse_run_id=langfuse_run_id,
        langfuse_run_url=langfuse_run_url,
        started_at=started_at,
        finished_at=finished_at,
    )
