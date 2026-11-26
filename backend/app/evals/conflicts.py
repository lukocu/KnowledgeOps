"""Sprawdzian 2b: ewaluacja wykrywania sprzecznych źródeł, Langfuse i raport."""

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from langchain_core.callbacks import BaseCallbackHandler, UsageMetadataCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langfuse import Evaluation, Langfuse
from langfuse.api.commons.errors import NotFoundError
from langfuse.experiment import ExperimentItemResult
from pydantic import BaseModel, ConfigDict, model_validator

from app.answering.graph import AnswerGraph, build_answer_graph, initial_state
from app.answering.model import make_chat_model
from app.answering.nodes import AnswerState
from app.answering.prompts import prompt_versions as answer_prompt_versions
from app.answering.schemas import (
    AbstainedResult,
    AnsweredResult,
    AnswerResult,
    ConflictingResult,
    ConflictType,
)
from app.db import CONNECTION_TIMEOUT_S, AsyncPool
from app.evals.metrics import (
    LATENCY_BUDGET_MS,
    CitationInvariantCheck,
    ExecutionOutcome,
    ItemScore,
    TokenUsage,
    _percentile,
    check_citation_invariants,
)
from app.evals.runner import _extract_token_usage, ensure_langfuse_ready
from app.observability import flush_traces, make_trace_handler, run_config
from app.retrieval import ChunkSetReproInfo, get_chunk_set_repro_info
from app.settings import Settings

DEFAULT_CONFLICTS_DATASET_PATH = Path("evals/conflicts-dataset.json")
DEFAULT_CONFLICTS_LANGFUSE_DATASET_NAME = "knowledgeops/conflicts-eval"

ExpectedConflictOutcome = Literal["conflicting", "answered"]
ConflictClass = Literal[
    "contradiction", "different_recommendations", "answered", "abstained"
]
CONFLICT_CLASSES: tuple[ConflictClass, ...] = (
    "contradiction",
    "different_recommendations",
    "answered",
    "abstained",
)


# --- modele zbioru -----------------------------------------------------------


class ConflictEvalItem(BaseModel):
    """Pojedynczy przypadek Sprawdzianu 2b z `conflicts-dataset.json`."""

    model_config = ConfigDict(frozen=True)

    id: str
    question: str
    expected_outcome: ExpectedConflictOutcome
    expected_conflict_type: ConflictType | None = None
    anchor_techqa_doc_id: str
    synthetic_doc_id: str | None = None
    secondary_synthetic_doc_id: str | None = None
    scope_note: str

    @model_validator(mode="after")
    def _validate_consistency(self) -> ConflictEvalItem:
        if not self.id.strip():
            raise ValueError("pole id nie może być puste")
        if not self.question.strip():
            raise ValueError(f"{self.id}: pole question nie może być puste")
        if not self.anchor_techqa_doc_id.strip():
            raise ValueError(f"{self.id}: pole anchor_techqa_doc_id nie może być puste")
        if self.expected_outcome == "conflicting":
            if self.expected_conflict_type is None:
                raise ValueError(
                    f"{self.id}: expected_outcome='conflicting' wymaga"
                    " expected_conflict_type"
                )
            if not self.synthetic_doc_id:
                raise ValueError(
                    f"{self.id}: expected_outcome='conflicting' wymaga synthetic_doc_id"
                )
        else:
            if self.expected_conflict_type is not None:
                raise ValueError(
                    f"{self.id}: expected_outcome='answered' wymaga"
                    " expected_conflict_type=null"
                )
        return self


class ConflictDatasetMetadata(BaseModel):
    """Metadane zamrożonego zbioru `conflicts-dataset.json`."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    snapshot_id: str
    synthetic_snapshot_id: str
    dataset_sha256: str
    n_total: int
    n_contradiction: int
    n_different_recommendations: int
    n_answered: int


class LoadedConflictDataset(BaseModel):
    """Załadowany i zwalidowany zbiór Sprawdzianu 2b."""

    model_config = ConfigDict(frozen=True)

    metadata: ConflictDatasetMetadata
    items: list[ConflictEvalItem]


def load_conflicts_dataset(path: Path) -> LoadedConflictDataset:
    """Wczytuje i waliduje `conflicts-dataset.json`."""
    raw_text = path.read_text(encoding="utf-8")
    payload = json.loads(raw_text)
    if payload.get("schema_version") != 1:
        raise ValueError(
            f"Nieobsługiwana schema_version w {path}: {payload.get('schema_version')!r}"
        )
    items = [ConflictEvalItem.model_validate(item) for item in payload["items"]]
    ids = [item.id for item in items]
    if len(set(ids)) != len(ids):
        raise ValueError(f"Powtórzone identyfikatory w {path}")

    n_contradiction = sum(
        1 for item in items if item.expected_conflict_type == "contradiction"
    )
    n_diff = sum(
        1
        for item in items
        if item.expected_conflict_type == "different_recommendations"
    )
    n_answered = sum(1 for item in items if item.expected_outcome == "answered")
    dataset_sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    metadata = ConflictDatasetMetadata(
        schema_version=1,
        snapshot_id=str(payload["snapshot_id"]),
        synthetic_snapshot_id=str(payload["synthetic_snapshot_id"]),
        dataset_sha256=dataset_sha,
        n_total=len(items),
        n_contradiction=n_contradiction,
        n_different_recommendations=n_diff,
        n_answered=n_answered,
    )
    return LoadedConflictDataset(metadata=metadata, items=items)


# --- metryki deterministyczne ------------------------------------------------


def expected_conflict_class(item: ConflictEvalItem) -> ConflictClass:
    if item.expected_outcome == "conflicting":
        assert item.expected_conflict_type is not None
        return item.expected_conflict_type
    return "answered"


def is_different_version_item(item: ConflictEvalItem) -> bool:
    """Czy przypadek dotyczy konfliktu między różnymi wersjami produktu."""
    return (
        item.expected_conflict_type == "different_recommendations"
        and "different_version" in item.scope_note.casefold()
    )


def check_conflict_citation_invariants(
    result: ConflictingResult,
    chunk_texts: Mapping[str, str],
) -> CitationInvariantCheck:
    """Weryfikuje dosłowność cytatów i offsety `[quote_start, quote_end)` dla A i B."""
    violations: list[str] = []
    if len(result.sides) != 2:
        violations.append(
            f"oczekiwano dokładnie 2 stron konfliktu, otrzymano {len(result.sides)}"
        )
        return CitationInvariantCheck(passed=False, violations=violations)

    side_a, side_b = result.sides
    if (side_a.label, side_b.label) != ("A", "B"):
        violations.append(
            f"nieprawidłowe etykiety stron: {(side_a.label, side_b.label)!r}"
        )
    if side_a.doc_id == side_b.doc_id:
        violations.append(f"obie strony wskazują ten sam doc_id={side_a.doc_id!r}")

    for side in (side_a, side_b):
        if not side.claim_text.strip():
            violations.append(f"strona {side.label}: pusta treść tezy")
        if not side.quote.strip():
            violations.append(f"strona {side.label}: pusty cytat")
        chunk_text = chunk_texts.get(side.chunk_id)
        if chunk_text is None:
            violations.append(
                f"strona {side.label}: brak tekstu fragmentu dla"
                f" chunk_id={side.chunk_id!r}"
            )
            continue
        if not (0 <= side.quote_start < side.quote_end <= len(chunk_text)):
            violations.append(
                f"strona {side.label}: nieprawidłowe offsety"
                f" [{side.quote_start}, {side.quote_end}) dla długości"
                f" {len(chunk_text)}"
            )
            continue
        if chunk_text[side.quote_start : side.quote_end] != side.quote:
            violations.append(
                f"strona {side.label}: wycinek [{side.quote_start}:{side.quote_end}]"
                f" dla chunk_id={side.chunk_id!r} nie zgadza się dosłownie z quote"
            )

    return CitationInvariantCheck(passed=not violations, violations=violations)


class ConflictItemExecution(BaseModel):
    """Wynik wykonania pojedynczego przypadku Sprawdzianu 2b."""

    model_config = ConfigDict(frozen=True)

    id: str
    expected_outcome: ExpectedConflictOutcome
    expected_conflict_type: ConflictType | None = None
    expected_class: ConflictClass
    anchor_techqa_doc_id: str
    synthetic_doc_id: str | None = None
    secondary_synthetic_doc_id: str | None = None
    scope_note: str
    outcome: ExecutionOutcome
    predicted_conflict_type: ConflictType | None = None
    predicted_class: ConflictClass | None = None
    latency_ms: float
    answer: AnswerResult | None = None
    error: str | None = None
    both_sides_cited: bool | None = None
    citation_invariants: CitationInvariantCheck | None = None
    usage: TokenUsage | None = None


class ConflictRunSummary(BaseModel):
    """Zagregowane metryki Sprawdzianu 2b."""

    model_config = ConfigDict(frozen=True)

    n_total: int
    n_evaluated: int
    n_failed: int
    confusion_matrix: dict[str, dict[str, int]]
    overall_state_accuracy: float | None
    n_conflict_expected_eval: int
    scope_distinction_accuracy: float | None
    n_different_version_eval: int
    different_version_misclassified_as_contradiction: int
    n_control_answered_eval: int
    false_conflict_rate: float | None
    both_sides_cited_rate: float | None
    citation_invariants_pass_rate: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    within_latency_budget_rate: float | None
    total_usage: TokenUsage


def score_conflict_item(
    item: ConflictEvalItem, execution: ConflictItemExecution
) -> list[ItemScore]:
    """Oblicza deterministyczne oceny per-item (zgodne z Langfuse)."""
    if execution.outcome == "failed":
        return [ItemScore(name="execution_ok", value=0.0, comment=execution.error)]

    exp_cls = expected_conflict_class(item)
    scores: list[ItemScore] = [
        ItemScore(name="execution_ok", value=1.0),
        ItemScore(
            name="state_correct",
            value=1.0 if execution.predicted_class == exp_cls else 0.0,
            comment=(
                f"expected={exp_cls}, predicted={execution.predicted_class or 'none'}"
            ),
        ),
    ]

    if item.expected_outcome == "conflicting":
        scores.append(
            ItemScore(
                name="scope_distinction_correct",
                value=1.0 if execution.predicted_class == exp_cls else 0.0,
            )
        )
    if is_different_version_item(item):
        misclassified = execution.predicted_class == "contradiction"
        scores.append(
            ItemScore(
                name="different_version_misclassified_as_contradiction",
                value=1.0 if misclassified else 0.0,
            )
        )
    if item.expected_outcome == "answered":
        scores.append(
            ItemScore(
                name="false_conflict",
                value=1.0 if execution.outcome == "conflicting" else 0.0,
            )
        )
    if execution.both_sides_cited is not None:
        scores.append(
            ItemScore(
                name="both_sides_cited",
                value=1.0 if execution.both_sides_cited else 0.0,
            )
        )
    if execution.citation_invariants is not None:
        comment = (
            None
            if execution.citation_invariants.passed
            else "; ".join(execution.citation_invariants.violations)
        )
        scores.append(
            ItemScore(
                name="citation_invariants_ok",
                value=1.0 if execution.citation_invariants.passed else 0.0,
                comment=comment,
            )
        )

    scores.append(ItemScore(name="latency_ms", value=float(execution.latency_ms)))
    scores.append(
        ItemScore(
            name="within_latency_budget",
            value=1.0 if execution.latency_ms < LATENCY_BUDGET_MS else 0.0,
        )
    )
    return scores


def aggregate_conflict_run(
    results: Sequence[ConflictItemExecution],
) -> ConflictRunSummary:
    """Agreguje metryki Sprawdzianu 2b z wykluczeniem `failed` z mianowników."""
    n_total = len(results)
    evaluated = [r for r in results if r.outcome != "failed"]
    n_evaluated = len(evaluated)
    n_failed = n_total - n_evaluated

    matrix: dict[str, dict[str, int]] = {
        exp: {pred: 0 for pred in CONFLICT_CLASSES} for exp in CONFLICT_CLASSES
    }
    correct_state = 0
    for r in evaluated:
        if r.predicted_class is not None:
            matrix[r.expected_class][r.predicted_class] += 1
            if r.predicted_class == r.expected_class:
                correct_state += 1

    overall_state_accuracy = correct_state / n_evaluated if n_evaluated > 0 else None

    conflict_expected = [r for r in evaluated if r.expected_outcome == "conflicting"]
    n_conflict_expected_eval = len(conflict_expected)
    scope_distinction_accuracy = (
        sum(1 for r in conflict_expected if r.predicted_class == r.expected_class)
        / n_conflict_expected_eval
        if n_conflict_expected_eval > 0
        else None
    )

    diff_version_items = [
        r
        for r in evaluated
        if r.expected_conflict_type == "different_recommendations"
        and "different_version" in r.scope_note.casefold()
    ]
    n_different_version_eval = len(diff_version_items)
    diff_version_misclassified = sum(
        1 for r in diff_version_items if r.predicted_class == "contradiction"
    )

    control_answered = [r for r in evaluated if r.expected_outcome == "answered"]
    n_control_answered_eval = len(control_answered)
    false_conflict_rate = (
        sum(1 for r in control_answered if r.outcome == "conflicting")
        / n_control_answered_eval
        if n_control_answered_eval > 0
        else None
    )

    conflicting_outcomes = [r for r in evaluated if r.outcome == "conflicting"]
    both_sides_cited_rate = (
        sum(1 for r in conflicting_outcomes if r.both_sides_cited is True)
        / len(conflicting_outcomes)
        if conflicting_outcomes
        else None
    )

    with_invariants = [r for r in evaluated if r.citation_invariants is not None]
    citation_invariants_pass_rate = (
        sum(
            1
            for r in with_invariants
            if r.citation_invariants is not None and r.citation_invariants.passed
        )
        / len(with_invariants)
        if with_invariants
        else None
    )

    latencies = [float(r.latency_ms) for r in evaluated]
    latency_p50_ms = _percentile(latencies, 50.0)
    latency_p95_ms = _percentile(latencies, 95.0)
    within_latency_budget_rate = (
        sum(1 for lat in latencies if lat < LATENCY_BUDGET_MS) / len(latencies)
        if latencies
        else None
    )

    total_usage = TokenUsage(
        input_tokens=sum(r.usage.input_tokens for r in results if r.usage is not None),
        output_tokens=sum(
            r.usage.output_tokens for r in results if r.usage is not None
        ),
        total_tokens=sum(r.usage.total_tokens for r in results if r.usage is not None),
    )

    return ConflictRunSummary(
        n_total=n_total,
        n_evaluated=n_evaluated,
        n_failed=n_failed,
        confusion_matrix=matrix,
        overall_state_accuracy=overall_state_accuracy,
        n_conflict_expected_eval=n_conflict_expected_eval,
        scope_distinction_accuracy=scope_distinction_accuracy,
        n_different_version_eval=n_different_version_eval,
        different_version_misclassified_as_contradiction=diff_version_misclassified,
        n_control_answered_eval=n_control_answered_eval,
        false_conflict_rate=false_conflict_rate,
        both_sides_cited_rate=both_sides_cited_rate,
        citation_invariants_pass_rate=citation_invariants_pass_rate,
        latency_p50_ms=latency_p50_ms,
        latency_p95_ms=latency_p95_ms,
        within_latency_budget_rate=within_latency_budget_rate,
        total_usage=total_usage,
    )


# --- konfiguracja, potwierdzenie kosztu i wykonanie --------------------------


class ConflictEvalRunConfig(BaseModel):
    """Odtwarzalna konfiguracja przebiegu Sprawdzianu 2b."""

    model_config = ConfigDict(frozen=True)

    limit: int | None = None
    concurrency: int = 2
    use_langfuse: bool = True
    dataset_name: str = DEFAULT_CONFLICTS_LANGFUSE_DATASET_NAME
    run_name: str
    repro_info: ChunkSetReproInfo
    synthetic_repro_info: ChunkSetReproInfo
    chat_model: str
    chat_reasoning_effort: str
    k: int
    answer_prompt_versions: dict[str, str]
    config_sha256: str


class ConflictEvalRunArtifact(BaseModel):
    """Kompletny, serializowalny zapis przebiegu Sprawdzianu 2b."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    config: ConflictEvalRunConfig
    dataset: ConflictDatasetMetadata
    summary: ConflictRunSummary
    items: list[ConflictItemExecution]
    langfuse_run_id: str | None = None
    langfuse_run_url: str | None = None
    started_at: str
    finished_at: str


def compute_conflicts_config_sha256(
    *,
    limit: int | None,
    concurrency: int,
    use_langfuse: bool,
    dataset_name: str,
    dataset_sha256: str,
    repro_info: ChunkSetReproInfo,
    synthetic_repro_info: ChunkSetReproInfo,
    chat_model: str,
    chat_reasoning_effort: str,
    k: int,
    answer_prompts: dict[str, str],
) -> str:
    payload = {
        "limit": limit,
        "concurrency": concurrency,
        "use_langfuse": use_langfuse,
        "dataset_name": dataset_name,
        "dataset_sha256": dataset_sha256,
        "repro_info": repro_info.model_dump(mode="json"),
        "synthetic_repro_info": synthetic_repro_info.model_dump(mode="json"),
        "chat_model": chat_model,
        "chat_reasoning_effort": chat_reasoning_effort,
        "k": k,
        "answer_prompt_versions": answer_prompts,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def default_conflicts_run_name(*, now: datetime | None = None) -> str:
    current = now if now is not None else datetime.now(UTC)
    return f"conflicts-{current.strftime('%Y%m%dT%H%M%SZ')}"


def estimate_conflict_llm_calls(items: Sequence[ConflictEvalItem]) -> tuple[int, int]:
    """Szacuje przedział `(min_calls, max_calls)` wywołań LLM (1..3 na pytanie)."""
    n_total = len(items)
    return n_total, 3 * n_total


def format_conflicts_cost_confirmation(
    *,
    items: Sequence[ConflictEvalItem],
    chat_model: str,
    chat_reasoning_effort: str,
    use_langfuse: bool,
    dataset_name: str,
) -> str:
    min_calls, max_calls = estimate_conflict_llm_calls(items)
    n_contra = sum(
        1 for item in items if item.expected_conflict_type == "contradiction"
    )
    n_diff = sum(
        1
        for item in items
        if item.expected_conflict_type == "different_recommendations"
    )
    n_ans = sum(1 for item in items if item.expected_outcome == "answered")
    langfuse_line = (
        f"Langfuse Cloud (dataset: {dataset_name})"
        if use_langfuse
        else "LOKALNY (--no-langfuse, bez zapisu w Langfuse Cloud)"
    )
    return "\n".join(
        [
            "=== Podsumowanie przebiegu ewaluacji konfliktów (Sprawdzian 2b) ===",
            (
                f"Przypadki: {len(items)}"
                f" (contradiction={n_contra},"
                f" different_recommendations={n_diff},"
                f" answered={n_ans})"
            ),
            (
                f"Model odpowiedzi: {chat_model}"
                f" (reasoning_effort={chat_reasoning_effort})"
            ),
            (
                f"Szacowana liczba wywołań LLM: {min_calls}–{max_calls}"
                " (draft + verify + opcjonalnie detect_conflict)"
            ),
            f"Tryb rejestrowania: {langfuse_line}",
        ]
    )


def confirm_conflicts_eval_run(
    *,
    items: Sequence[ConflictEvalItem],
    chat_model: str,
    chat_reasoning_effort: str,
    use_langfuse: bool,
    dataset_name: str,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> bool:
    print_fn(
        format_conflicts_cost_confirmation(
            items=items,
            chat_model=chat_model,
            chat_reasoning_effort=chat_reasoning_effort,
            use_langfuse=use_langfuse,
            dataset_name=dataset_name,
        )
    )
    reply = input_fn("Kontynuować przebieg ewaluacji? [t/N]: ").strip().lower()
    return reply in {"t", "tak", "y", "yes"}


async def execute_conflict_item(
    item: ConflictEvalItem,
    *,
    graph: AnswerGraph,
    settings: Settings,
    chunk_set_id: str,
    use_langfuse: bool,
) -> ConflictItemExecution:
    """Wykonuje graf odpowiedzi z nakładką `synthetic@v1` i liczy inwarianty."""
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

    exp_cls = expected_conflict_class(item)
    base_fields: dict[str, Any] = {
        "id": item.id,
        "expected_outcome": item.expected_outcome,
        "expected_conflict_type": item.expected_conflict_type,
        "expected_class": exp_cls,
        "anchor_techqa_doc_id": item.anchor_techqa_doc_id,
        "synthetic_doc_id": item.synthetic_doc_id,
        "secondary_synthetic_doc_id": item.secondary_synthetic_doc_id,
        "scope_note": item.scope_note,
    }

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
                        include_synthetic=True,
                    ),
                    run_cfg,
                ),
            )
    except TimeoutError:
        latency_ms = (time.monotonic() - started) * 1000.0
        return ConflictItemExecution(
            **base_fields,
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
        return ConflictItemExecution(
            **base_fields,
            outcome="failed",
            latency_ms=latency_ms,
            error=f"{type(exc).__name__}: {exc}",
            usage=_extract_token_usage(usage_handler),
        )

    latency_ms = (time.monotonic() - started) * 1000.0
    result = final_state.get("answer")
    if result is None:
        return ConflictItemExecution(
            **base_fields,
            outcome="failed",
            latency_ms=latency_ms,
            error="brak wyniku answer w stanie końcowym grafu",
            usage=_extract_token_usage(usage_handler),
        )

    chunk_texts = {
        chunk.chunk_id: chunk.text for chunk in final_state.get("retrieved", [])
    }

    if isinstance(result, ConflictingResult):
        invariants = check_conflict_citation_invariants(result, chunk_texts)
        return ConflictItemExecution(
            **base_fields,
            outcome="conflicting",
            predicted_conflict_type=result.conflict_type,
            predicted_class=result.conflict_type,
            latency_ms=latency_ms,
            answer=result,
            both_sides_cited=invariants.passed,
            citation_invariants=invariants,
            usage=_extract_token_usage(usage_handler),
        )

    if isinstance(result, AnsweredResult):
        invariants = check_citation_invariants(result, chunk_texts)
        return ConflictItemExecution(
            **base_fields,
            outcome="answered",
            predicted_conflict_type=None,
            predicted_class="answered",
            latency_ms=latency_ms,
            answer=result,
            both_sides_cited=None,
            citation_invariants=invariants,
            usage=_extract_token_usage(usage_handler),
        )

    assert isinstance(result, AbstainedResult)
    return ConflictItemExecution(
        **base_fields,
        outcome="abstained",
        predicted_conflict_type=None,
        predicted_class="abstained",
        latency_ms=latency_ms,
        answer=result,
        both_sides_cited=None,
        citation_invariants=None,
        usage=_extract_token_usage(usage_handler),
    )


# --- integracja Langfuse 5.2.0 -----------------------------------------------


@dataclass(frozen=True)
class ConflictsLangfuseOutput:
    executions: list[ConflictItemExecution]
    langfuse_run_id: str | None
    langfuse_run_url: str | None


def conflict_dataset_item_id(item: ConflictEvalItem) -> str:
    return f"conflicts_{item.id}"


def build_conflict_run_evaluations(summary: ConflictRunSummary) -> list[Evaluation]:
    evaluations: list[Evaluation] = []
    if summary.overall_state_accuracy is not None:
        evaluations.append(
            Evaluation(
                name="overall_state_accuracy",
                value=summary.overall_state_accuracy,
                comment=f"n_evaluated={summary.n_evaluated}",
            )
        )
    if summary.scope_distinction_accuracy is not None:
        evaluations.append(
            Evaluation(
                name="scope_distinction_accuracy",
                value=summary.scope_distinction_accuracy,
                comment=f"n_conflict={summary.n_conflict_expected_eval}",
            )
        )
    evaluations.append(
        Evaluation(
            name="different_version_misclassified_as_contradiction",
            value=float(summary.different_version_misclassified_as_contradiction),
            comment=f"n_different_version={summary.n_different_version_eval}",
        )
    )
    if summary.false_conflict_rate is not None:
        evaluations.append(
            Evaluation(
                name="false_conflict_rate",
                value=summary.false_conflict_rate,
                comment=f"n_control={summary.n_control_answered_eval}",
            )
        )
    if summary.both_sides_cited_rate is not None:
        evaluations.append(
            Evaluation(
                name="both_sides_cited_rate",
                value=summary.both_sides_cited_rate,
            )
        )
    if summary.citation_invariants_pass_rate is not None:
        evaluations.append(
            Evaluation(
                name="citation_invariants_pass_rate",
                value=summary.citation_invariants_pass_rate,
            )
        )
    if summary.latency_p95_ms is not None:
        evaluations.append(
            Evaluation(
                name="latency_p95_ms",
                value=summary.latency_p95_ms,
            )
        )
    evaluations.append(Evaluation(name="failed_count", value=float(summary.n_failed)))
    return evaluations


def _is_not_found(exc: Exception) -> bool:
    return isinstance(exc, NotFoundError) or getattr(exc, "status_code", None) == 404


def ensure_and_sync_conflicts_dataset(
    client: Langfuse,
    *,
    dataset_name: str,
    description: str,
    items: Sequence[ConflictEvalItem],
    dataset_metadata: dict[str, Any] | None = None,
) -> list[Any]:
    try:
        client.get_dataset(dataset_name)
    except Exception as exc:
        if not _is_not_found(exc):
            raise
        client.create_dataset(
            name=dataset_name,
            description=description,
            metadata=dataset_metadata,
        )

    for item in items:
        client.create_dataset_item(
            dataset_name=dataset_name,
            id=conflict_dataset_item_id(item),
            input={
                "id": item.id,
                "question": item.question,
            },
            expected_output={
                "expected_outcome": item.expected_outcome,
                "expected_conflict_type": item.expected_conflict_type,
                "expected_class": expected_conflict_class(item),
            },
            metadata={
                "id": item.id,
                "anchor_techqa_doc_id": item.anchor_techqa_doc_id,
                "synthetic_doc_id": item.synthetic_doc_id,
                "secondary_synthetic_doc_id": item.secondary_synthetic_doc_id,
                "scope_note": item.scope_note,
            },
        )

    dataset = client.get_dataset(dataset_name)
    by_id = {ds_item.id: ds_item for ds_item in dataset.items}
    selected_ids = [conflict_dataset_item_id(item) for item in items]
    missing_ids = [item_id for item_id in selected_ids if item_id not in by_id]
    if missing_ids:
        raise RuntimeError(
            f"Po synchronizacji datasetu {dataset_name!r} brakuje "
            f"{len(missing_ids)}/{len(selected_ids)} elementów: "
            f"{', '.join(missing_ids[:5])}"
        )
    return [by_id[item_id] for item_id in selected_ids]


async def run_conflicts_langfuse_experiment(
    *,
    client: Langfuse,
    dataset_name: str,
    run_name: str,
    description: str,
    items: Sequence[ConflictEvalItem],
    execute_fn: Callable[[ConflictEvalItem], Awaitable[ConflictItemExecution]],
    concurrency: int,
    metadata: dict[str, Any],
    dataset_metadata: dict[str, Any] | None = None,
) -> ConflictsLangfuseOutput:
    selected_items = await asyncio.to_thread(
        ensure_and_sync_conflicts_dataset,
        client,
        dataset_name=dataset_name,
        description=description,
        items=items,
        dataset_metadata=dataset_metadata,
    )

    items_by_ds_id = {conflict_dataset_item_id(item): item for item in items}
    items_by_id = {item.id: item for item in items}
    executions_by_id: dict[str, ConflictItemExecution] = {}

    async def _task(*, item: Any, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        ds_id = getattr(item, "id", None)
        eval_item = items_by_ds_id.get(ds_id) if isinstance(ds_id, str) else None
        if eval_item is None:
            raw_input = getattr(item, "input", None)
            if isinstance(raw_input, dict):
                item_id = raw_input.get("id")
                if isinstance(item_id, str):
                    eval_item = items_by_id.get(item_id)
        if eval_item is None:
            raise KeyError(f"Nieznany element datasetu Langfuse: {ds_id!r}")

        execution = await execute_fn(eval_item)
        executions_by_id[eval_item.id] = execution
        return execution.model_dump(mode="json")

    def _item_evaluator(
        *,
        input: Any,
        output: Any,
        expected_output: Any,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> list[Evaluation]:
        del expected_output, kwargs
        item_id: str | None = None
        if isinstance(input, dict) and isinstance(input.get("id"), str):
            item_id = input["id"]
        elif isinstance(metadata, dict) and isinstance(metadata.get("id"), str):
            item_id = metadata["id"]
        if item_id is None or item_id not in items_by_id:
            return []

        eval_item = items_by_id[item_id]
        execution = executions_by_id.get(item_id)
        if execution is None:
            execution = ConflictItemExecution.model_validate(output)
            executions_by_id[item_id] = execution

        return [
            Evaluation(name=score.name, value=score.value, comment=score.comment)
            for score in score_conflict_item(eval_item, execution)
        ]

    def _collect_ordered() -> list[ConflictItemExecution]:
        ordered: list[ConflictItemExecution] = []
        for item in items:
            execution = executions_by_id.get(item.id)
            if execution is None:
                execution = ConflictItemExecution(
                    id=item.id,
                    expected_outcome=item.expected_outcome,
                    expected_conflict_type=item.expected_conflict_type,
                    expected_class=expected_conflict_class(item),
                    anchor_techqa_doc_id=item.anchor_techqa_doc_id,
                    synthetic_doc_id=item.synthetic_doc_id,
                    secondary_synthetic_doc_id=item.secondary_synthetic_doc_id,
                    scope_note=item.scope_note,
                    outcome="failed",
                    latency_ms=0.0,
                    error=(
                        "Brak wyniku wykonania elementu z eksperymentu Langfuse "
                        f"({conflict_dataset_item_id(item)})."
                    ),
                )
            ordered.append(execution)
        return ordered

    def _run_evaluator(
        *,
        item_results: list[ExperimentItemResult],
        **kwargs: Any,
    ) -> list[Evaluation]:
        del kwargs
        if not executions_by_id and item_results:
            ordered = [
                ConflictItemExecution.model_validate(res.output)
                for res in item_results
                if res.output is not None
            ]
        else:
            ordered = _collect_ordered()
        summary = aggregate_conflict_run(ordered)
        return build_conflict_run_evaluations(summary)

    result = await client._run_experiment_async(
        name=dataset_name,
        run_name=run_name,
        description=description,
        data=selected_items,
        task=_task,
        evaluators=[_item_evaluator],
        composite_evaluator=None,
        run_evaluators=[_run_evaluator],
        max_concurrency=concurrency,
        metadata=metadata,
    )
    await asyncio.to_thread(flush_traces)

    return ConflictsLangfuseOutput(
        executions=_collect_ordered(),
        langfuse_run_id=result.experiment_id,
        langfuse_run_url=result.experiment_url,
    )


# --- główny runner -----------------------------------------------------------


def _conflicts_experiment_metadata(
    config: ConflictEvalRunConfig, dataset: ConflictDatasetMetadata
) -> dict[str, Any]:
    return {
        "limit": config.limit,
        "concurrency": config.concurrency,
        "snapshot_id": config.repro_info.snapshot_id,
        "chunk_set_id": config.repro_info.chunk_set_id,
        "chunk_set_state_sha256": config.repro_info.state_sha256,
        "synthetic_snapshot_id": config.synthetic_repro_info.snapshot_id,
        "synthetic_chunk_set_id": config.synthetic_repro_info.chunk_set_id,
        "synthetic_state_sha256": config.synthetic_repro_info.state_sha256,
        "dataset_sha256": dataset.dataset_sha256,
        "chat_model": config.chat_model,
        "chat_reasoning_effort": config.chat_reasoning_effort,
        "k": config.k,
        "answer_prompt_versions": config.answer_prompt_versions,
        "config_sha256": config.config_sha256,
    }


async def run_conflicts_eval(
    *,
    dataset: LoadedConflictDataset,
    settings: Settings,
    pool: AsyncPool,
    limit: int | None = None,
    concurrency: int = 2,
    use_langfuse: bool = True,
    dataset_name: str = DEFAULT_CONFLICTS_LANGFUSE_DATASET_NAME,
    run_name: str | None = None,
    chat_model: BaseChatModel | None = None,
    langfuse_client: Langfuse | None = None,
    repro_info: ChunkSetReproInfo | None = None,
    synthetic_repro_info: ChunkSetReproInfo | None = None,
) -> ConflictEvalRunArtifact:
    """Uruchamia Sprawdzian 2b (Langfuse Cloud lub lokalnie)."""
    if concurrency < 1:
        raise ValueError("concurrency musi być >= 1")
    if limit is not None and limit < 1:
        raise ValueError("limit musi być >= 1")

    active_langfuse = ensure_langfuse_ready(
        settings, use_langfuse=use_langfuse, langfuse_client=langfuse_client
    )

    items = list(dataset.items[:limit]) if limit is not None else list(dataset.items)
    chunk_set_id = settings.effective_chunk_set_id()
    synthetic_chunk_set_id = settings.effective_synthetic_chunk_set_id()

    if repro_info is None or synthetic_repro_info is None:
        async with pool.connection(timeout=CONNECTION_TIMEOUT_S) as conn:
            active_repro = (
                repro_info
                if repro_info is not None
                else await get_chunk_set_repro_info(conn, chunk_set_id)
            )
            active_syn_repro = (
                synthetic_repro_info
                if synthetic_repro_info is not None
                else await get_chunk_set_repro_info(conn, synthetic_chunk_set_id)
            )
    else:
        active_repro = repro_info
        active_syn_repro = synthetic_repro_info

    active_chat_model = (
        chat_model if chat_model is not None else make_chat_model(settings)
    )
    ans_prompts = answer_prompt_versions()
    effective_run_name = run_name or default_conflicts_run_name()
    cfg_hash = compute_conflicts_config_sha256(
        limit=limit,
        concurrency=concurrency,
        use_langfuse=use_langfuse,
        dataset_name=dataset_name,
        dataset_sha256=dataset.metadata.dataset_sha256,
        repro_info=active_repro,
        synthetic_repro_info=active_syn_repro,
        chat_model=settings.chat_model,
        chat_reasoning_effort=settings.chat_reasoning_effort,
        k=settings.answer_k,
        answer_prompts=ans_prompts,
    )
    config = ConflictEvalRunConfig(
        limit=limit,
        concurrency=concurrency,
        use_langfuse=use_langfuse,
        dataset_name=dataset_name,
        run_name=effective_run_name,
        repro_info=active_repro,
        synthetic_repro_info=active_syn_repro,
        chat_model=settings.chat_model,
        chat_reasoning_effort=settings.chat_reasoning_effort,
        k=settings.answer_k,
        answer_prompt_versions=ans_prompts,
        config_sha256=cfg_hash,
    )

    graph = build_answer_graph(
        chat_model=active_chat_model, pool=pool, settings=settings
    )

    async def _exec(item: ConflictEvalItem) -> ConflictItemExecution:
        return await execute_conflict_item(
            item,
            graph=graph,
            settings=settings,
            chunk_set_id=chunk_set_id,
            use_langfuse=use_langfuse,
        )

    started_at = datetime.now(UTC).isoformat()
    langfuse_run_id: str | None = None
    langfuse_run_url: str | None = None

    if use_langfuse and active_langfuse is not None:
        lf_output = await run_conflicts_langfuse_experiment(
            client=active_langfuse,
            dataset_name=dataset_name,
            run_name=effective_run_name,
            description="KnowledgeOps S-07 conflicting sources eval (Sprawdzian 2b)",
            items=items,
            execute_fn=_exec,
            concurrency=concurrency,
            metadata=_conflicts_experiment_metadata(config, dataset.metadata),
            dataset_metadata={
                "snapshot_id": dataset.metadata.snapshot_id,
                "synthetic_snapshot_id": dataset.metadata.synthetic_snapshot_id,
                "dataset_sha256": dataset.metadata.dataset_sha256,
            },
        )
        executions = lf_output.executions
        langfuse_run_id = lf_output.langfuse_run_id
        langfuse_run_url = lf_output.langfuse_run_url
    else:
        semaphore = asyncio.Semaphore(concurrency)

        async def _bounded(item: ConflictEvalItem) -> ConflictItemExecution:
            async with semaphore:
                return await _exec(item)

        executions = list(await asyncio.gather(*(_bounded(item) for item in items)))

    finished_at = datetime.now(UTC).isoformat()
    summary = aggregate_conflict_run(executions)

    return ConflictEvalRunArtifact(
        config=config,
        dataset=dataset.metadata,
        summary=summary,
        items=executions,
        langfuse_run_id=langfuse_run_id,
        langfuse_run_url=langfuse_run_url,
        started_at=started_at,
        finished_at=finished_at,
    )


# --- zapis JSON i raport Markdown --------------------------------------------


def write_conflicts_raw_run(path: Path, run: ConflictEvalRunArtifact) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(run.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _fmt_pct(value: float | None) -> str:
    return f"{value * 100:.1f}%" if value is not None else "n/d"


def _fmt_ms(value: float | None) -> str:
    return f"{value:.0f} ms" if value is not None else "n/d"


def _fmt_prompts(mapping: dict[str, str]) -> str:
    if not mapping:
        return "brak"
    return ", ".join(f"`{k}={v}`" for k, v in sorted(mapping.items()))


def render_conflicts_markdown_report(run: ConflictEvalRunArtifact) -> str:
    """Generuje raport Markdown Sprawdzianu 2b bez surowych tekstów TechQA."""
    cfg = run.config
    ds = run.dataset
    s = run.summary

    lines: list[str] = [
        "# Raport Sprawdzianu 2b: Wykrywanie sprzecznych źródeł (S-07)",
        "",
    ]

    if not cfg.use_langfuse:
        lines.extend(
            [
                "> [!WARNING]",
                "> **Tryb `--no-langfuse`**: Przebieg uruchomiono lokalnie bez zapisu"
                " eksperymentu i śladów w Langfuse Cloud.",
                "",
            ]
        )

    langfuse_status = (
        f"`{run.langfuse_run_id}` ({run.langfuse_run_url or 'brak URL'})"
        if cfg.use_langfuse and run.langfuse_run_id
        else "wyłączony (`--no-langfuse`)"
    )

    lines.extend(
        [
            "## Metadane i odtwarzalność",
            "",
            "| Parametr | Wartość |",
            "| --- | --- |",
            f"| Nazwa przebiegu | `{cfg.run_name}` |",
            f"| Czas przebiegu (UTC) | `{run.started_at}` -> `{run.finished_at}` |",
            (f"| Limit / współbieżność | `{cfg.limit}` / `{cfg.concurrency}` |"),
            (
                "| Migawka TechQA / zestaw fragmentów |"
                f" `{cfg.repro_info.snapshot_id}` / `{cfg.repro_info.chunk_set_id}` |"
            ),
            (
                "| Hash stanu TechQA (`state_sha256`) |"
                f" `{cfg.repro_info.state_sha256 or 'brak'}` |"
            ),
            (
                "| Migawka syntetyczna / zestaw fragmentów |"
                f" `{cfg.synthetic_repro_info.snapshot_id}` /"
                f" `{cfg.synthetic_repro_info.chunk_set_id}` |"
            ),
            (
                "| Hash stanu syntetycznego (`state_sha256`) |"
                f" `{cfg.synthetic_repro_info.state_sha256 or 'brak'}` |"
            ),
            (
                "| Zbiór przypadków (`dataset_sha256`) |"
                f" `{ds.dataset_sha256}` (`n={ds.n_total}`:"
                f" `contradiction={ds.n_contradiction}`,"
                f" `different_recommendations={ds.n_different_recommendations}`,"
                f" `answered={ds.n_answered}`) |"
            ),
            (
                "| Model odpowiedzi |"
                f" `{cfg.chat_model}` (reasoning: `{cfg.chat_reasoning_effort}`,"
                f" `k={cfg.k}`) |"
            ),
            (
                "| Wersje promptów odpowiedzi |"
                f" {_fmt_prompts(cfg.answer_prompt_versions)} |"
            ),
            (
                "| Hash konfiguracji przebiegu (`config_sha256`) |"
                f" `{cfg.config_sha256}` |"
            ),
            f"| Langfuse Cloud (`experiment_id` / URL) | {langfuse_status} |",
            "",
            "## Podsumowanie metryk (Sprawdzian 2b)",
            "",
            "| Metryka | Wartość | Próba / uwaga |",
            "| --- | --- | --- |",
            (
                "| Trafność stanu (`overall_state_accuracy`) |"
                f" **{_fmt_pct(s.overall_state_accuracy)}** |"
                f" `n={s.n_evaluated}` (`n_failed={s.n_failed}`) |"
            ),
            (
                "| Rozróżnienie zakresu (`scope_distinction_accuracy`) |"
                f" **{_fmt_pct(s.scope_distinction_accuracy)}** |"
                f" `n={s.n_conflict_expected_eval}` (pary konfliktowe) |"
            ),
            (
                "| Różne wersje błędnie jako `contradiction`"
                " (`different_version_misclassified_as_contradiction`) |"
                f" **`{s.different_version_misclassified_as_contradiction}`** |"
                f" cel: `0` (`n={s.n_different_version_eval}`) |"
            ),
            (
                "| Odsetek fałszywych konfliktów (`false_conflict_rate`) |"
                f" **{_fmt_pct(s.false_conflict_rate)}** |"
                f" `n={s.n_control_answered_eval}` (grupa kontrolna `answered`) |"
            ),
            (
                "| Cytaty po obu stronach A i B (`both_sides_cited_rate`) |"
                f" **{_fmt_pct(s.both_sides_cited_rate)}** |"
                " wyniki `conflicting` |"
            ),
            (
                "| Inwarianty cytatów (`citation_invariants_pass_rate`) |"
                f" **{_fmt_pct(s.citation_invariants_pass_rate)}** |"
                " dosłowny wycinek `[quote_start, quote_end)` (A, B i `answered`) |"
            ),
            (
                "| Opóźnienie grafu `p50` / `p95` |"
                f" {_fmt_ms(s.latency_p50_ms)} / {_fmt_ms(s.latency_p95_ms)} |"
                f" w budżecie `< {int(LATENCY_BUDGET_MS)} ms`:"
                f" {_fmt_pct(s.within_latency_budget_rate)} |"
            ),
            (
                "| Zużycie tokenów (łącznie) |"
                f" `total={s.total_usage.total_tokens}` |"
                f" `input={s.total_usage.input_tokens}`,"
                f" `output={s.total_usage.output_tokens}` |"
            ),
            "",
            "## Macierz pomyłek (4 klasy)",
            "",
            "| Oczekiwane \\ Przewidziane | "
            + " | ".join(f"`{cls}`" for cls in CONFLICT_CLASSES)
            + " |",
            "| --- | " + " | ".join("---" for _ in CONFLICT_CLASSES) + " |",
        ]
    )

    for exp_cls in CONFLICT_CLASSES:
        row_counts = s.confusion_matrix.get(exp_cls, {})
        cells = " | ".join(
            f"`{row_counts.get(pred_cls, 0)}`" for pred_cls in CONFLICT_CLASSES
        )
        lines.append(f"| `{exp_cls}` | {cells} |")

    lines.extend(
        [
            "",
            "## Przegląd przypadków (bez surowych tekstów TechQA)",
            "",
            (
                "| ID | Oczekiwane | Przewidziane | Strony / dokumenty |"
                " Inwarianty | Czas |"
            ),
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )

    for item in run.items:
        pred = item.predicted_class or f"failed ({item.error or 'błąd'})"
        if isinstance(item.answer, ConflictingResult):
            s0, s1 = item.answer.sides
            docs_str = f"`{s0.doc_id}` vs `{s1.doc_id}`"
        elif isinstance(item.answer, AnsweredResult):
            cited = ", ".join(f"`{c.doc_id}`" for c in item.answer.citations[:3])
            docs_str = cited or "brak"
        else:
            docs_str = "brak"
        inv_str = (
            "PASS"
            if item.citation_invariants and item.citation_invariants.passed
            else ("FAIL" if item.citation_invariants is not None else "n/d")
        )
        lines.append(
            f"| `{item.id}` | `{item.expected_class}` | `{pred}` |"
            f" {docs_str} | `{inv_str}` | {_fmt_ms(item.latency_ms)} |"
        )

    mismatches = [
        item
        for item in run.items
        if item.outcome == "failed" or item.predicted_class != item.expected_class
    ]
    lines.extend(["", "## Błędy i rozbieżności", ""])
    if not mismatches:
        lines.append("- Brak błędów klasyfikacji ani błędów wykonania.")
    else:
        for item in mismatches:
            if item.outcome == "failed":
                err_msg = item.error or "nieznany błąd"
                lines.append(f"- `{item.id}`: `failed` — {err_msg}")
            else:
                lines.append(
                    f"- `{item.id}`: oczekiwano `{item.expected_class}`,"
                    f" otrzymano `{item.predicted_class}` (`{item.scope_note}`)"
                )

    lines.extend(
        [
            "",
            "## Ograniczenia danych syntetycznych",
            "",
            "- Zestaw Sprawdzianu 2b (`n=24`) opiera się na autorskiej nakładce"
            " syntetycznej `synthetic@v1` zakotwiczonej tematycznie w prawdziwych"
            " dokumentach TechQA — nie pochodzi z rzeczywistych sprzeczności"
            " odkrytych w produkcji.",
            "- Wszystkie 8 przypadków `contradiction` zestawia pary dokumentów"
            " syntetycznych o jawnych, identycznych metadanych (`product_version`,"
            " `audience`), ponieważ dokumenty TechQA nie mają strukturalnych pól"
            " wersji ani odbiorcy (`NULL`), a deterministyczny strażnik"
            " `resolve_conflict_type()` celowo degraduje pary z nieustaloną lub"
            " rozbieżną wersją do `different_recommendations`.",
            "- Próba liczy 24 przypadki (po 8 na klasę) i używa pojedynczego"
            f" mechanizmu wyszukiwania BM25 (`k={cfg.k}`), więc przedział ufności"
            " pojedynczych wskaźników jest szeroki; wynik służy jako bramka"
            " regresyjna mechanizmu `detect_conflict` i strażnika zakresu.",
            "",
        ]
    )
    return "\n".join(lines)
