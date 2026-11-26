"""Testy jednostkowe metryk deterministycznych i agregacji przebiegu S-03."""

import pytest

from app.answering.schemas import (
    AbstainedResult,
    AnswerClaim,
    AnsweredResult,
    CheckedChunk,
    Citation,
    CitationClaim,
)
from app.evals.dataset import EvalItem, VerifiedLabel
from app.evals.judge import (
    CitationJudgeResult,
    CitationJudgeVerdict,
    ReferenceAgreementOutput,
    ReferenceJudgeResult,
)
from app.evals.metrics import (
    CitationInvariantCheck,
    EvalItemExecution,
    aggregate_run,
    check_citation_invariants,
    classify_abstention_reason,
    score_item,
)

CHUNK_TEXT_1 = "Run db2start to start the DB2 database manager instance."
CHUNK_TEXT_2 = "Check db2diag.log for SQL1032N error details."


def make_eval_item(
    question_id: str = "q1",
    *,
    verified_label: VerifiedLabel = "answerable_in_corpus",
    original_is_impossible: bool = False,
) -> EvalItem:
    return EvalItem(
        question_id=question_id,
        split="dev",
        original_is_impossible=original_is_impossible,
        canonical_doc_id="doc1",
        verified_label=verified_label,
        question="How do I start DB2?",
        answer="Run db2start." if verified_label == "answerable_in_corpus" else "",
        doc_ids=["doc1"],
    )


def make_valid_answered_result() -> AnsweredResult:
    q1 = "Run db2start to start the DB2 database manager instance."
    q2 = "Check db2diag.log"
    return AnsweredResult(
        claims=[
            AnswerClaim(text="Start DB2 with db2start.", code="db2start", citation=1),
            AnswerClaim(text="Inspect db2diag.log.", code=None, citation=2),
        ],
        citations=[
            Citation(
                n=1,
                chunk_id="c1",
                doc_id="doc1",
                title="DB2 Start",
                headings=["Start"],
                claims=[
                    CitationClaim(
                        claim_index=0,
                        quote=q1,
                        quote_start=0,
                        quote_end=len(q1),
                    )
                ],
            ),
            Citation(
                n=2,
                chunk_id="c2",
                doc_id="doc2",
                title="DB2 Logs",
                headings=["Logs"],
                claims=[
                    CitationClaim(
                        claim_index=1,
                        quote=q2,
                        quote_start=0,
                        quote_end=len(q2),
                    )
                ],
            ),
        ],
        checked_chunks=[
            CheckedChunk(
                rank=1,
                chunk_id="c1",
                doc_id="doc1",
                title="DB2 Start",
                headings=["Start"],
                score=1.5,
            )
        ],
        omitted_claims=0,
    )


# --- check_citation_invariants -----------------------------------------------


def test_citation_invariants_pass_for_valid_answer() -> None:
    result = make_valid_answered_result()
    check = check_citation_invariants(result, {"c1": CHUNK_TEXT_1, "c2": CHUNK_TEXT_2})
    assert check.passed is True
    assert check.violations == []


def test_citation_invariants_fail_on_empty_citations_and_out_of_range_number() -> None:
    result = AnsweredResult(
        claims=[AnswerClaim(text="Claim", code=None, citation=1)],
        citations=[],
        checked_chunks=[],
        omitted_claims=0,
    )
    check = check_citation_invariants(result, {})
    assert check.passed is False
    assert any("żadnego cytatu" in v for v in check.violations)
    assert any("nieprawidłowy numer cytatu" in v for v in check.violations)


def test_citation_invariants_fail_on_offset_mismatch_and_missing_chunk() -> None:
    result = make_valid_answered_result()
    # Popsuj dosłowny wycinek w c1 i pomiń c2 w chunk_texts.
    result.citations[0].claims[0].quote = "Run db2stop"
    check = check_citation_invariants(result, {"c1": CHUNK_TEXT_1})
    assert check.passed is False
    assert any("nie zgadza się dosłownie" in v for v in check.violations)
    assert any("brak tekstu fragmentu" in v for v in check.violations)


def test_citation_invariants_fail_on_invalid_bounds_and_numbering_gap() -> None:
    result = AnsweredResult(
        claims=[AnswerClaim(text="Claim", code=None, citation=2)],
        citations=[
            Citation(
                n=2,
                chunk_id="c1",
                doc_id="doc1",
                title="T",
                headings=[],
                claims=[
                    CitationClaim(
                        claim_index=0,
                        quote="Run",
                        quote_start=5,
                        quote_end=3,
                    )
                ],
            )
        ],
        checked_chunks=[],
        omitted_claims=0,
    )
    check = check_citation_invariants(result, {"c1": CHUNK_TEXT_1})
    assert check.passed is False
    assert any("nieprawidłowa numeracja cytatów" in v for v in check.violations)
    assert any("nieprawidłowy zakres offsetów" in v for v in check.violations)


# --- classify_abstention_reason ----------------------------------------------


def test_classify_abstention_reason_distinguishes_quote_check_and_verify() -> None:
    no_hits = AbstainedResult(reason="no_hits", checked_chunks=[], omitted_claims=0)
    no_claims = AbstainedResult(reason="no_claims", checked_chunks=[], omitted_claims=0)
    none_sup = AbstainedResult(
        reason="none_supported", checked_chunks=[], omitted_claims=2
    )

    assert classify_abstention_reason(no_hits) == "no_hits"
    assert classify_abstention_reason(no_claims) == "no_claims"
    assert (
        classify_abstention_reason(none_sup, quoted_count=0)
        == "quote_check_rejected_all"
    )
    assert classify_abstention_reason(none_sup, quoted_count=2) == "verify_rejected_all"
    assert classify_abstention_reason(none_sup) == "none_supported"


# --- score_item --------------------------------------------------------------


def test_score_item_failed_returns_only_execution_ok_zero() -> None:
    item = make_eval_item(verified_label="verified_unanswerable")
    run_item = EvalItemExecution(
        question_id="q1",
        split="dev",
        verified_label="verified_unanswerable",
        outcome="failed",
        latency_ms=1500.0,
        error="TimeoutError: deadline exceeded",
    )
    scores = score_item(item, run_item)
    assert len(scores) == 1
    assert scores[0].name == "execution_ok"
    assert scores[0].value == 0.0
    assert scores[0].comment == "TimeoutError: deadline exceeded"


def test_score_item_unanswerable_abstained_and_answered() -> None:
    item = make_eval_item(
        verified_label="verified_unanswerable", original_is_impossible=True
    )
    abstained_exec = EvalItemExecution(
        question_id="q1",
        split="dev",
        verified_label="verified_unanswerable",
        outcome="abstained",
        latency_ms=1200.0,
        abstention_reason="no_hits",
    )
    abstained_map = {s.name: s for s in score_item(item, abstained_exec)}
    assert abstained_map["execution_ok"].value == 1.0
    assert abstained_map["abstention_accuracy"].value == 1.0
    assert abstained_map["latency_ms"].value == 1200.0
    assert abstained_map["within_latency_budget"].value == 1.0
    assert "false_refusal" not in abstained_map
    assert "reference_agreement" not in abstained_map

    answered_exec = EvalItemExecution(
        question_id="q1",
        split="dev",
        verified_label="verified_unanswerable",
        outcome="answered",
        latency_ms=11_500.0,
        answer=make_valid_answered_result(),
        citation_invariants=CitationInvariantCheck(passed=True),
        citation_judge=CitationJudgeResult(
            verdicts=[
                CitationJudgeVerdict(
                    claim_index=0, reasoning="ok", verdict="supported"
                ),
                CitationJudgeVerdict(
                    claim_index=1, reasoning="off topic", verdict="unsupported"
                ),
            ]
        ),
        reference_judge=ReferenceJudgeResult(
            output=ReferenceAgreementOutput(reasoning="ignored", verdict="full")
        ),
    )
    answered_map = {s.name: s for s in score_item(item, answered_exec)}
    assert answered_map["abstention_accuracy"].value == 0.0
    assert answered_map["citation_invariants_ok"].value == 1.0
    assert answered_map["citation_support_rate"].value == pytest.approx(0.5)
    assert answered_map["within_latency_budget"].value == 0.0
    assert "reference_agreement" not in answered_map


def test_score_item_answerable_reference_and_judge_errors() -> None:
    item = make_eval_item(verified_label="answerable_in_corpus")
    run_item = EvalItemExecution(
        question_id="q1",
        split="dev",
        verified_label="answerable_in_corpus",
        outcome="answered",
        latency_ms=2500.0,
        answer=make_valid_answered_result(),
        citation_invariants=CitationInvariantCheck(passed=True),
        citation_judge=CitationJudgeResult(judge_error="timeout"),
        reference_judge=ReferenceJudgeResult(
            output=ReferenceAgreementOutput(
                reasoning="Covers command but misses log step.", verdict="partial"
            )
        ),
    )
    score_map = {s.name: s for s in score_item(item, run_item)}
    assert score_map["false_refusal"].value == 0.0
    assert "citation_support_rate" not in score_map
    assert score_map["reference_agreement"].value == pytest.approx(0.5)
    assert score_map["reference_agreement"].comment == (
        "partial: Covers command but misses log step."
    )


# --- aggregate_run -----------------------------------------------------------


def test_aggregate_run_empty_results() -> None:
    summary = aggregate_run([])
    assert summary.n_total == 0
    assert summary.n_evaluated == 0
    assert summary.n_failed == 0
    assert summary.abstention_accuracy is None
    assert summary.false_refusal_rate is None
    assert summary.citation_invariants_pass_rate is None
    assert summary.citation_support_claim_rate is None
    assert summary.citation_support_answer_rate is None
    assert summary.reference_agreement_mean is None
    assert summary.reference_agreement_counts == {
        "full": 0,
        "partial": 0,
        "incorrect": 0,
    }
    assert summary.latency_p50_ms is None
    assert summary.latency_p95_ms is None
    assert summary.within_latency_budget_rate is None
    assert summary.abstention_reasons == {
        "no_hits": 0,
        "no_claims": 0,
        "quote_check_rejected_all": 0,
        "verify_rejected_all": 0,
    }
    assert summary.n_judge_failed == 0


def test_aggregate_run_excludes_failed_from_denominators() -> None:
    results = [
        EvalItemExecution(
            question_id="u1",
            split="dev",
            verified_label="verified_unanswerable",
            outcome="abstained",
            latency_ms=1000.0,
            abstention_reason="no_hits",
        ),
        EvalItemExecution(
            question_id="u2",
            split="dev",
            verified_label="verified_unanswerable",
            outcome="failed",
            latency_ms=25_000.0,
            error="deadline exceeded",
        ),
        EvalItemExecution(
            question_id="a1",
            split="dev",
            verified_label="answerable_in_corpus",
            outcome="answered",
            latency_ms=3000.0,
            answer=make_valid_answered_result(),
            citation_invariants=CitationInvariantCheck(passed=True),
        ),
        EvalItemExecution(
            question_id="a2",
            split="dev",
            verified_label="answerable_in_corpus",
            outcome="failed",
            latency_ms=25_000.0,
            error="api error",
        ),
    ]
    summary = aggregate_run(results)
    assert summary.n_total == 4
    assert summary.n_evaluated == 2
    assert summary.n_failed == 2
    assert summary.n_unanswerable_eval == 1
    assert summary.abstention_accuracy == pytest.approx(1.0)
    assert summary.n_answerable_eval == 1
    assert summary.false_refusal_rate == pytest.approx(0.0)
    assert summary.latency_p50_ms == pytest.approx(2000.0)
    assert summary.within_latency_budget_rate == pytest.approx(1.0)


def test_aggregate_run_all_abstained_and_reason_breakdown() -> None:
    results = [
        EvalItemExecution(
            question_id="u1",
            split="test",
            verified_label="verified_unanswerable",
            outcome="abstained",
            latency_ms=500.0,
            abstention_reason="no_hits",
        ),
        EvalItemExecution(
            question_id="u2",
            split="test",
            verified_label="verified_unanswerable",
            outcome="abstained",
            latency_ms=1500.0,
            abstention_reason="no_claims",
        ),
        EvalItemExecution(
            question_id="a1",
            split="test",
            verified_label="answerable_in_corpus",
            outcome="abstained",
            latency_ms=2500.0,
            abstention_reason="quote_check_rejected_all",
        ),
        EvalItemExecution(
            question_id="a2",
            split="test",
            verified_label="answerable_in_corpus",
            outcome="abstained",
            latency_ms=3500.0,
            abstention_reason="verify_rejected_all",
        ),
    ]
    summary = aggregate_run(results)
    assert summary.abstention_accuracy == pytest.approx(1.0)
    assert summary.false_refusal_rate == pytest.approx(1.0)
    assert summary.citation_invariants_pass_rate is None
    assert summary.citation_support_claim_rate is None
    assert summary.citation_support_answer_rate is None
    assert summary.reference_agreement_mean is None
    assert summary.abstention_reasons == {
        "no_hits": 1,
        "no_claims": 1,
        "quote_check_rejected_all": 1,
        "verify_rejected_all": 1,
    }


def test_aggregate_run_zero_abstentions_partial_support_and_judge_errors() -> None:
    ans = make_valid_answered_result()
    results = [
        # Answerable 1: 2/2 supported, full agreement
        EvalItemExecution(
            question_id="a1",
            split="test",
            verified_label="answerable_in_corpus",
            outcome="answered",
            latency_ms=1000.0,
            answer=ans,
            citation_invariants=CitationInvariantCheck(passed=True),
            citation_judge=CitationJudgeResult(
                verdicts=[
                    CitationJudgeVerdict(
                        claim_index=0, reasoning="r0", verdict="supported"
                    ),
                    CitationJudgeVerdict(
                        claim_index=1, reasoning="r1", verdict="supported"
                    ),
                ]
            ),
            reference_judge=ReferenceJudgeResult(
                output=ReferenceAgreementOutput(reasoning="complete", verdict="full")
            ),
        ),
        # Answerable 2: 1/2 supported, partial agreement, invariant failed
        EvalItemExecution(
            question_id="a2",
            split="test",
            verified_label="answerable_in_corpus",
            outcome="answered",
            latency_ms=2000.0,
            answer=ans,
            citation_invariants=CitationInvariantCheck(
                passed=False, violations=["mismatch"]
            ),
            citation_judge=CitationJudgeResult(
                verdicts=[
                    CitationJudgeVerdict(
                        claim_index=0, reasoning="r0", verdict="supported"
                    ),
                    CitationJudgeVerdict(
                        claim_index=1, reasoning="r1", verdict="unsupported"
                    ),
                ]
            ),
            reference_judge=ReferenceJudgeResult(
                output=ReferenceAgreementOutput(reasoning="partial", verdict="partial")
            ),
        ),
        # Answerable 3: both judges failed -> counted in n_judge_failed, not in means
        EvalItemExecution(
            question_id="a3",
            split="test",
            verified_label="answerable_in_corpus",
            outcome="answered",
            latency_ms=4000.0,
            answer=ans,
            citation_invariants=CitationInvariantCheck(passed=True),
            citation_judge=CitationJudgeResult(judge_error="timeout"),
            reference_judge=ReferenceJudgeResult(judge_error="timeout"),
        ),
        # Unanswerable 1: answered (hallucinated) -> abstention_accuracy = 0.0
        EvalItemExecution(
            question_id="u1",
            split="test",
            verified_label="verified_unanswerable",
            outcome="answered",
            latency_ms=12_000.0,
            answer=ans,
            citation_invariants=CitationInvariantCheck(passed=True),
        ),
    ]
    summary = aggregate_run(results)
    assert summary.abstention_accuracy == pytest.approx(0.0)
    assert summary.false_refusal_rate == pytest.approx(0.0)
    assert summary.citation_invariants_pass_rate == pytest.approx(3 / 4)
    # 3 supported out of 4 judged claims; 1 fully supported out of 2 judged answers
    assert summary.citation_support_claim_rate == pytest.approx(0.75)
    assert summary.citation_support_answer_rate == pytest.approx(0.5)
    assert summary.reference_agreement_counts == {
        "full": 1,
        "partial": 1,
        "incorrect": 0,
    }
    assert summary.reference_agreement_mean == pytest.approx(0.75)
    assert summary.n_judge_failed == 2
    assert summary.latency_p50_ms == pytest.approx(3000.0)
    assert summary.latency_p95_ms == pytest.approx(10_800.0)
    assert summary.within_latency_budget_rate == pytest.approx(3 / 4)
