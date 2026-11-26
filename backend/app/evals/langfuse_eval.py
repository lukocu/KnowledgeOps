"""Integracja runnera ewaluacji S-06 z Langfuse 5.2.0 (`_run_experiment_async`)."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from langfuse import Evaluation, Langfuse
from langfuse.api.commons.errors import NotFoundError
from langfuse.experiment import ExperimentItemResult

from app.evals.dataset import EvalItem
from app.evals.metrics import (
    EvalItemExecution,
    RunSummary,
    aggregate_run,
    score_item,
)
from app.observability import flush_traces

RUN_EXPERIMENT_ASYNC_KWARGS: tuple[str, ...] = (
    "name",
    "run_name",
    "description",
    "data",
    "task",
    "evaluators",
    "composite_evaluator",
    "run_evaluators",
    "max_concurrency",
    "metadata",
)


@dataclass(frozen=True)
class LangfuseExperimentOutput:
    """Wynik eksperymentu Langfuse: wykonania w kolejności wejścia i ID runu."""

    executions: list[EvalItemExecution]
    langfuse_run_id: str | None
    langfuse_run_url: str | None


def dataset_item_id(item: EvalItem) -> str:
    """Deterministyczny identyfikator elementu datasetu w Langfuse."""
    return f"abstention_{item.split}_{item.question_id}"


def build_run_evaluations(summary: RunSummary) -> list[Evaluation]:
    """Buduje oceny poziomu eksperymentu (`run_evaluators`) dla Langfuse."""
    evaluations: list[Evaluation] = []
    if summary.abstention_accuracy is not None:
        evaluations.append(
            Evaluation(
                name="abstention_accuracy",
                value=summary.abstention_accuracy,
                comment=f"n_unanswerable={summary.n_unanswerable_eval}",
            )
        )
    if summary.false_refusal_rate is not None:
        evaluations.append(
            Evaluation(
                name="false_refusal_rate",
                value=summary.false_refusal_rate,
                comment=f"n_answerable={summary.n_answerable_eval}",
            )
        )
    if summary.citation_invariants_pass_rate is not None:
        evaluations.append(
            Evaluation(
                name="citation_invariants_pass_rate",
                value=summary.citation_invariants_pass_rate,
            )
        )
    if summary.citation_support_claim_rate is not None:
        evaluations.append(
            Evaluation(
                name="citation_support_claim_rate",
                value=summary.citation_support_claim_rate,
            )
        )
    if summary.reference_agreement_mean is not None:
        evaluations.append(
            Evaluation(
                name="reference_agreement_avg",
                value=summary.reference_agreement_mean,
            )
        )
    if summary.latency_p95_ms is not None:
        evaluations.append(
            Evaluation(
                name="latency_p95_ms",
                value=summary.latency_p95_ms,
            )
        )
    evaluations.append(
        Evaluation(
            name="failed_count",
            value=summary.n_failed,
        )
    )
    return evaluations


def _is_not_found(exc: Exception) -> bool:
    return isinstance(exc, NotFoundError) or getattr(exc, "status_code", None) == 404


def ensure_and_sync_dataset(
    client: Langfuse,
    *,
    dataset_name: str,
    description: str,
    items: Sequence[EvalItem],
    dataset_metadata: dict[str, Any] | None = None,
) -> list[Any]:
    """Idempotentnie tworzy/synchronizuje dataset i zwraca elementy aktywnego splitu."""
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
            id=dataset_item_id(item),
            input={
                "question_id": item.question_id,
                "question": item.question,
                "split": item.split,
            },
            expected_output={
                "verified_label": item.verified_label,
                "reference_answer": item.answer,
                "doc_ids": list(item.doc_ids),
            },
            metadata={
                "question_id": item.question_id,
                "split": item.split,
                "original_is_impossible": item.original_is_impossible,
                "canonical_doc_id": item.canonical_doc_id,
                "verified_label": item.verified_label,
            },
        )

    dataset = client.get_dataset(dataset_name)
    by_id = {ds_item.id: ds_item for ds_item in dataset.items}
    selected_ids = [dataset_item_id(item) for item in items]
    missing_ids = [item_id for item_id in selected_ids if item_id not in by_id]
    if missing_ids:
        raise RuntimeError(
            f"Po synchronizacji datasetu {dataset_name!r} brakuje "
            f"{len(missing_ids)}/{len(selected_ids)} elementów: "
            f"{', '.join(missing_ids[:5])}"
        )
    return [by_id[item_id] for item_id in selected_ids]


async def run_langfuse_experiment(
    *,
    client: Langfuse,
    dataset_name: str,
    run_name: str,
    description: str,
    items: Sequence[EvalItem],
    execute_fn: Callable[[EvalItem], Awaitable[EvalItemExecution]],
    concurrency: int,
    metadata: dict[str, Any],
    dataset_metadata: dict[str, Any] | None = None,
) -> LangfuseExperimentOutput:
    """Uruchamia eksperyment w Langfuse 5.2.0 na bieżącej pętli zdarzeń."""
    selected_items = await asyncio.to_thread(
        ensure_and_sync_dataset,
        client,
        dataset_name=dataset_name,
        description=description,
        items=items,
        dataset_metadata=dataset_metadata,
    )

    items_by_ds_id = {dataset_item_id(item): item for item in items}
    items_by_question_id = {item.question_id: item for item in items}
    executions_by_question_id: dict[str, EvalItemExecution] = {}

    async def _task(*, item: Any, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        ds_id = getattr(item, "id", None)
        eval_item = items_by_ds_id.get(ds_id) if isinstance(ds_id, str) else None
        if eval_item is None:
            raw_input = getattr(item, "input", None)
            if isinstance(raw_input, dict):
                qid = raw_input.get("question_id")
                if isinstance(qid, str):
                    eval_item = items_by_question_id.get(qid)
        if eval_item is None:
            raise KeyError(f"Nieznany element datasetu Langfuse: {ds_id!r}")

        execution = await execute_fn(eval_item)
        executions_by_question_id[eval_item.question_id] = execution
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
        qid: str | None = None
        if isinstance(input, dict) and isinstance(input.get("question_id"), str):
            qid = input["question_id"]
        elif isinstance(metadata, dict) and isinstance(
            metadata.get("question_id"), str
        ):
            qid = metadata["question_id"]
        if qid is None or qid not in items_by_question_id:
            return []

        eval_item = items_by_question_id[qid]
        execution = executions_by_question_id.get(qid)
        if execution is None:
            execution = EvalItemExecution.model_validate(output)
            executions_by_question_id[qid] = execution

        return [
            Evaluation(name=score.name, value=score.value, comment=score.comment)
            for score in score_item(eval_item, execution)
        ]

    def _collect_ordered_executions() -> list[EvalItemExecution]:
        ordered: list[EvalItemExecution] = []
        for item in items:
            execution = executions_by_question_id.get(item.question_id)
            if execution is None:
                execution = EvalItemExecution(
                    question_id=item.question_id,
                    split=item.split,
                    verified_label=item.verified_label,
                    outcome="failed",
                    latency_ms=0.0,
                    error=(
                        "Brak wyniku wykonania elementu z eksperymentu Langfuse "
                        f"({dataset_item_id(item)})."
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
        if not executions_by_question_id and item_results:
            ordered = [
                EvalItemExecution.model_validate(res.output)
                for res in item_results
                if res.output is not None
            ]
        else:
            ordered = _collect_ordered_executions()
        summary = aggregate_run(ordered)
        return build_run_evaluations(summary)

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

    ordered_executions = _collect_ordered_executions()
    return LangfuseExperimentOutput(
        executions=ordered_executions,
        langfuse_run_id=result.experiment_id,
        langfuse_run_url=result.experiment_url,
    )
