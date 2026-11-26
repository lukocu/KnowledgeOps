"""Metryki deterministyczne per-item i agregacja przebiegu ewaluacji S-06."""

import math
from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.answering.schemas import AbstainedResult, AnsweredResult, AnswerResult
from app.evals.dataset import EvalItem, Split, VerifiedLabel
from app.evals.judge import (
    REFERENCE_AGREEMENT_SCORES,
    CitationJudgeResult,
    CitationVerdict,
    ReferenceJudgeResult,
    ReferenceVerdict,
)

ExecutionOutcome = Literal["answered", "abstained", "failed"]
AbstentionCause = Literal[
    "no_hits",
    "no_claims",
    "quote_check_rejected_all",
    "verify_rejected_all",
    "none_supported",
]

CANONICAL_ABSTENTION_CAUSES: tuple[str, ...] = (
    "no_hits",
    "no_claims",
    "quote_check_rejected_all",
    "verify_rejected_all",
)
LATENCY_BUDGET_MS = 10_000.0


class CitationInvariantCheck(BaseModel):
    """Wynik deterministycznej weryfikacji inwariantów cytatów odpowiedzi."""

    model_config = ConfigDict(frozen=True)

    passed: bool
    violations: list[str] = Field(default_factory=list)


class ItemScore(BaseModel):
    """Pojedyncza ocena per-item zgodna z `langfuse.experiment.Evaluation`."""

    model_config = ConfigDict(frozen=True)

    name: str
    value: float
    comment: str | None = None


class EvalItemExecution(BaseModel):
    """Wynik wykonania pojedynczego elementu zbioru w przebiegu ewaluacji."""

    model_config = ConfigDict(frozen=True)

    question_id: str
    split: Split
    verified_label: VerifiedLabel
    outcome: ExecutionOutcome
    latency_ms: float
    answer: AnswerResult | None = None
    abstention_reason: AbstentionCause | None = None
    error: str | None = None
    citation_invariants: CitationInvariantCheck | None = None
    citation_judge: CitationJudgeResult | None = None
    reference_judge: ReferenceJudgeResult | None = None
    cited_chunk_texts: dict[str, str] = Field(default_factory=dict)


class RunSummary(BaseModel):
    """Zagregowane metryki całego przebiegu ewaluacji."""

    model_config = ConfigDict(frozen=True)

    n_total: int
    n_evaluated: int
    n_failed: int
    n_answered: int
    n_abstained: int
    n_unanswerable_eval: int
    abstention_accuracy: float | None
    n_answerable_eval: int
    false_refusal_rate: float | None
    citation_invariants_pass_rate: float | None
    citation_support_claim_rate: float | None
    citation_support_answer_rate: float | None
    reference_agreement_counts: dict[ReferenceVerdict, int]
    reference_agreement_mean: float | None
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    within_latency_budget_rate: float | None
    abstention_reasons: dict[str, int]
    n_judge_failed: int


def classify_abstention_reason(
    result: AbstainedResult,
    *,
    quoted_count: int | None = None,
) -> AbstentionCause:
    """Uszczegóławia przyczynę abstencji z grafu S-02 na potrzeby raportu S-06."""
    if result.reason == "no_hits":
        return "no_hits"
    if result.reason == "no_claims":
        return "no_claims"
    if quoted_count == 0:
        return "quote_check_rejected_all"
    if quoted_count is not None and quoted_count > 0:
        return "verify_rejected_all"
    return "none_supported"


def check_citation_invariants(
    result: AnsweredResult,
    chunk_texts: Mapping[str, str],
) -> CitationInvariantCheck:
    """Sprawdza inwarianty cytatów zgodnie z kontraktem `compose_answer`."""
    violations: list[str] = []

    if not result.claims:
        violations.append("odpowiedź nie zawiera żadnej tezy")
    if not result.citations:
        violations.append("odpowiedź nie zawiera żadnego cytatu")

    expected_numbers = list(range(1, len(result.citations) + 1))
    actual_numbers = [citation.n for citation in result.citations]
    if actual_numbers != expected_numbers:
        violations.append(
            f"nieprawidłowa numeracja cytatów: {actual_numbers} != {expected_numbers}"
        )

    valid_numbers = set(actual_numbers)
    for idx, claim in enumerate(result.claims):
        if (
            claim.citation < 1
            or claim.citation > len(result.citations)
            or claim.citation not in valid_numbers
        ):
            violations.append(
                f"teza {idx} wskazuje nieprawidłowy numer cytatu {claim.citation}"
            )

    covered_claims: set[int] = set()
    for citation in result.citations:
        if not citation.claims:
            violations.append(f"cytat [{citation.n}] nie zawiera żadnego CitationClaim")

        chunk_text = chunk_texts.get(citation.chunk_id)
        if chunk_text is None:
            violations.append(
                f"brak tekstu fragmentu dla chunk_id={citation.chunk_id!r}"
            )

        for cc in citation.claims:
            if not (0 <= cc.claim_index < len(result.claims)):
                violations.append(
                    f"cytat [{citation.n}] ma nieprawidłowy"
                    f" claim_index={cc.claim_index}"
                )
            else:
                covered_claims.add(cc.claim_index)
                if result.claims[cc.claim_index].citation != citation.n:
                    violations.append(
                        f"teza {cc.claim_index} ma numer cytatu"
                        f" {result.claims[cc.claim_index].citation},"
                        f" ale widnieje w cytacie [{citation.n}]"
                    )

            if chunk_text is None:
                continue

            if not (0 <= cc.quote_start < cc.quote_end <= len(chunk_text)):
                violations.append(
                    f"nieprawidłowy zakres offsetów [{cc.quote_start}, {cc.quote_end})"
                    f" dla chunk_id={citation.chunk_id!r} (długość {len(chunk_text)})"
                )
                continue

            sliced = chunk_text[cc.quote_start : cc.quote_end]
            if sliced != cc.quote:
                violations.append(
                    f"wycinek [{cc.quote_start}:{cc.quote_end}] dla"
                    f" chunk_id={citation.chunk_id!r} nie zgadza się dosłownie z quote"
                )

    for idx in range(len(result.claims)):
        if idx not in covered_claims:
            violations.append(f"teza {idx} nie ma przypisanego CitationClaim")

    return CitationInvariantCheck(passed=not violations, violations=violations)


def _evaluate_citation_support(run_item: EvalItemExecution) -> tuple[int, int] | None:
    """Zwraca `(supported_claims, total_claims)` lub `None`, gdy brak ważnej oceny."""
    if run_item.outcome != "answered":
        return None
    judge = run_item.citation_judge
    if judge is None or judge.judge_error is not None:
        return None

    verdict_by_index: dict[int, CitationVerdict] = {}
    for verdict in judge.verdicts:
        verdict_by_index.setdefault(verdict.claim_index, verdict.verdict)

    if isinstance(run_item.answer, AnsweredResult):
        total = len(run_item.answer.claims)
        if total == 0:
            return None
        supported = sum(
            1 for idx in range(total) if verdict_by_index.get(idx) == "supported"
        )
        return supported, total

    total = len(judge.verdicts)
    if total == 0:
        return None
    supported = sum(1 for verdict in judge.verdicts if verdict.verdict == "supported")
    return supported, total


def score_item(item: EvalItem, run_item: EvalItemExecution) -> list[ItemScore]:
    """Oblicza oceny per-item dla pojedynczego wykonania (zgodne z Langfuse)."""
    if run_item.outcome == "failed":
        return [ItemScore(name="execution_ok", value=0.0, comment=run_item.error)]

    scores: list[ItemScore] = [ItemScore(name="execution_ok", value=1.0)]

    if item.verified_label == "verified_unanswerable":
        scores.append(
            ItemScore(
                name="abstention_accuracy",
                value=1.0 if run_item.outcome == "abstained" else 0.0,
            )
        )
    elif item.verified_label == "answerable_in_corpus":
        scores.append(
            ItemScore(
                name="false_refusal",
                value=1.0 if run_item.outcome == "abstained" else 0.0,
            )
        )

    if run_item.outcome == "answered":
        if run_item.citation_invariants is not None:
            comment = (
                None
                if run_item.citation_invariants.passed
                else "; ".join(run_item.citation_invariants.violations)
            )
            scores.append(
                ItemScore(
                    name="citation_invariants_ok",
                    value=1.0 if run_item.citation_invariants.passed else 0.0,
                    comment=comment,
                )
            )

        support = _evaluate_citation_support(run_item)
        if support is not None:
            supported_count, total_claims = support
            scores.append(
                ItemScore(
                    name="citation_support_rate",
                    value=supported_count / total_claims,
                    comment=f"{supported_count}/{total_claims} supported",
                )
            )

        if (
            item.verified_label == "answerable_in_corpus"
            and run_item.reference_judge is not None
            and run_item.reference_judge.judge_error is None
            and run_item.reference_judge.output is not None
        ):
            ref_output = run_item.reference_judge.output
            scores.append(
                ItemScore(
                    name="reference_agreement",
                    value=REFERENCE_AGREEMENT_SCORES[ref_output.verdict],
                    comment=f"{ref_output.verdict}: {ref_output.reasoning}",
                )
            )

    scores.append(ItemScore(name="latency_ms", value=float(run_item.latency_ms)))
    scores.append(
        ItemScore(
            name="within_latency_budget",
            value=1.0 if run_item.latency_ms < LATENCY_BUDGET_MS else 0.0,
        )
    )
    return scores


def _percentile(values: Sequence[float], pct: float) -> float | None:
    """Percentyl z interpolacją liniową (0..100); dla pustej listy zwraca `None`."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(ordered[low])
    weight = rank - low
    return ordered[low] + weight * (ordered[high] - ordered[low])


def _resolve_abstention_cause(run_item: EvalItemExecution) -> str | None:
    if run_item.abstention_reason is not None:
        return run_item.abstention_reason
    if isinstance(run_item.answer, AbstainedResult):
        return run_item.answer.reason
    return None


def aggregate_run(results: Sequence[EvalItemExecution]) -> RunSummary:
    """Agreguje metryki całego przebiegu z wykluczeniem `failed` z mianowników."""
    n_total = len(results)
    evaluated = [item for item in results if item.outcome != "failed"]
    n_evaluated = len(evaluated)
    n_failed = n_total - n_evaluated
    n_answered = sum(1 for item in evaluated if item.outcome == "answered")
    n_abstained = sum(1 for item in evaluated if item.outcome == "abstained")

    unanswerable = [
        item for item in evaluated if item.verified_label == "verified_unanswerable"
    ]
    n_unanswerable_eval = len(unanswerable)
    abstention_accuracy = (
        sum(1 for item in unanswerable if item.outcome == "abstained")
        / n_unanswerable_eval
        if n_unanswerable_eval > 0
        else None
    )

    answerable = [
        item for item in evaluated if item.verified_label == "answerable_in_corpus"
    ]
    n_answerable_eval = len(answerable)
    false_refusal_rate = (
        sum(1 for item in answerable if item.outcome == "abstained") / n_answerable_eval
        if n_answerable_eval > 0
        else None
    )

    answered_with_invariants = [
        item
        for item in evaluated
        if item.outcome == "answered" and item.citation_invariants is not None
    ]
    citation_invariants_pass_rate = (
        sum(
            1
            for item in answered_with_invariants
            if item.citation_invariants is not None and item.citation_invariants.passed
        )
        / len(answered_with_invariants)
        if answered_with_invariants
        else None
    )

    total_supported_claims = 0
    total_judged_claims = 0
    judged_answers = 0
    fully_supported_answers = 0
    for item in evaluated:
        support = _evaluate_citation_support(item)
        if support is None:
            continue
        supported_count, claim_count = support
        total_supported_claims += supported_count
        total_judged_claims += claim_count
        judged_answers += 1
        if supported_count == claim_count:
            fully_supported_answers += 1

    citation_support_claim_rate = (
        total_supported_claims / total_judged_claims
        if total_judged_claims > 0
        else None
    )
    citation_support_answer_rate = (
        fully_supported_answers / judged_answers if judged_answers > 0 else None
    )

    reference_counts: dict[ReferenceVerdict, int] = {
        "full": 0,
        "partial": 0,
        "incorrect": 0,
    }
    reference_scores: list[float] = []
    for item in evaluated:
        if (
            item.outcome == "answered"
            and item.verified_label == "answerable_in_corpus"
            and item.reference_judge is not None
            and item.reference_judge.judge_error is None
            and item.reference_judge.output is not None
        ):
            verdict = item.reference_judge.output.verdict
            reference_counts[verdict] += 1
            reference_scores.append(REFERENCE_AGREEMENT_SCORES[verdict])

    reference_agreement_mean = (
        sum(reference_scores) / len(reference_scores) if reference_scores else None
    )

    latencies = [float(item.latency_ms) for item in evaluated]
    latency_p50_ms = _percentile(latencies, 50.0)
    latency_p95_ms = _percentile(latencies, 95.0)
    within_latency_budget_rate = (
        sum(1 for latency in latencies if latency < LATENCY_BUDGET_MS) / len(latencies)
        if latencies
        else None
    )

    abstention_reasons: dict[str, int] = {
        cause: 0 for cause in CANONICAL_ABSTENTION_CAUSES
    }
    for item in evaluated:
        if item.outcome != "abstained":
            continue
        cause = _resolve_abstention_cause(item)
        if cause is None:
            continue
        abstention_reasons[cause] = abstention_reasons.get(cause, 0) + 1

    n_judge_failed = 0
    for item in evaluated:
        if item.citation_judge is not None and item.citation_judge.judge_error:
            n_judge_failed += 1
        if item.reference_judge is not None and item.reference_judge.judge_error:
            n_judge_failed += 1

    return RunSummary(
        n_total=n_total,
        n_evaluated=n_evaluated,
        n_failed=n_failed,
        n_answered=n_answered,
        n_abstained=n_abstained,
        n_unanswerable_eval=n_unanswerable_eval,
        abstention_accuracy=abstention_accuracy,
        n_answerable_eval=n_answerable_eval,
        false_refusal_rate=false_refusal_rate,
        citation_invariants_pass_rate=citation_invariants_pass_rate,
        citation_support_claim_rate=citation_support_claim_rate,
        citation_support_answer_rate=citation_support_answer_rate,
        reference_agreement_counts=reference_counts,
        reference_agreement_mean=reference_agreement_mean,
        latency_p50_ms=latency_p50_ms,
        latency_p95_ms=latency_p95_ms,
        within_latency_budget_rate=within_latency_budget_rate,
        abstention_reasons=abstention_reasons,
        n_judge_failed=n_judge_failed,
    )
