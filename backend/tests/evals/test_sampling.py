"""Testy stratyfikowanego próbkowania i eksportu arkusza do audytu ręcznego (Faza 4)."""

import json
from pathlib import Path

from app.answering.model import JudgeModelInfo
from app.answering.schemas import (
    AbstainedResult,
    AnswerClaim,
    AnsweredResult,
    CheckedChunk,
    Citation,
    CitationClaim,
)
from app.evals.dataset import DatasetMetadata
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
)
from app.evals.runner import EvalRunArtifact, EvalRunConfig
from app.evals.sampling import export_manual_audit, sample_for_manual_audit
from app.retrieval import ChunkSetReproInfo


def _make_answered_item(
    qid: str,
    *,
    omitted_claims: int = 0,
    verified_label: str = "answerable_in_corpus",
    citation_reasoning: str = "SECRET_CITATION_JUDGE_REASONING",
    reference_reasoning: str = "SECRET_REFERENCE_JUDGE_REASONING",
) -> EvalItemExecution:
    chunk_text = (
        "Before restarting the cluster node, run `systemctl restart knowledgeops`"
        " and verify port 8000 responds."
    )
    quote = "run `systemctl restart knowledgeops`"
    start = chunk_text.index(quote)
    end = start + len(quote)

    answer = AnsweredResult(
        claims=[
            AnswerClaim(
                text="Uruchom ponownie usługę poleceniem systemctl.",
                code="systemctl restart knowledgeops",
                citation=1,
            )
        ],
        citations=[
            Citation(
                n=1,
                chunk_id=f"chunk_{qid}",
                doc_id=f"doc_{qid}",
                title=f"Restart Guide {qid}",
                headings=["Operations", "Restart"],
                claims=[
                    CitationClaim(
                        claim_index=0,
                        quote=quote,
                        quote_start=start,
                        quote_end=end,
                    )
                ],
            )
        ],
        checked_chunks=[
            CheckedChunk(
                rank=1,
                chunk_id=f"chunk_{qid}",
                doc_id=f"doc_{qid}",
                title=f"Restart Guide {qid}",
                headings=["Operations", "Restart"],
                score=3.2,
            )
        ],
        omitted_claims=omitted_claims,
    )
    label = (
        "answerable_in_corpus"
        if verified_label == "answerable_in_corpus"
        else "verified_unanswerable"
    )
    ref_judge = (
        ReferenceJudgeResult(
            output=ReferenceAgreementOutput(
                reasoning=reference_reasoning, verdict="full"
            )
        )
        if label == "answerable_in_corpus"
        else None
    )
    return EvalItemExecution(
        question_id=qid,
        split="dev",
        verified_label=label,
        outcome="answered",
        latency_ms=1100.0,
        answer=answer,
        citation_invariants=CitationInvariantCheck(passed=True),
        citation_judge=CitationJudgeResult(
            verdicts=[
                CitationJudgeVerdict(
                    claim_index=0,
                    reasoning=citation_reasoning,
                    verdict="supported",
                )
            ]
        ),
        reference_judge=ref_judge,
        cited_chunk_texts={f"chunk_{qid}": chunk_text},
    )


def _make_abstained_item(qid: str) -> EvalItemExecution:
    return EvalItemExecution(
        question_id=qid,
        split="dev",
        verified_label="verified_unanswerable",
        outcome="abstained",
        latency_ms=500.0,
        answer=AbstainedResult(reason="no_claims", checked_chunks=[], omitted_claims=0),
        abstention_reason="no_claims",
    )


def _make_failed_item(qid: str) -> EvalItemExecution:
    return EvalItemExecution(
        question_id=qid,
        split="dev",
        verified_label="verified_unanswerable",
        outcome="failed",
        latency_ms=25000.0,
        error="TimeoutError: deadline",
    )


def _build_artifact(items: list[EvalItemExecution]) -> EvalRunArtifact:
    repro = ChunkSetReproInfo(
        snapshot_id="techqa@abc1234",
        revision="abc1234567890",
        chunk_set_id="techqa@abc1234/sections-v1",
        variant="sections-v1",
        config_sha256="1" * 64,
        state_sha256="2" * 64,
    )
    config = EvalRunConfig(
        split="dev",
        limit=None,
        concurrency=2,
        use_langfuse=False,
        dataset_name="knowledgeops/abstention-eval",
        run_name="abstention-dev-20261126T120000Z",
        repro_info=repro,
        chat_model="gpt-5-mini",
        chat_reasoning_effort="low",
        k=8,
        answer_prompt_versions={"draft": "aaaaaaaaaaaa"},
        judge_model_info=JudgeModelInfo(
            model="gpt-5", reasoning_effort="low", is_fallback_to_chat_model=False
        ),
        judge_prompt_versions={"citation_support": "bbbbbbbbbbbb"},
        config_sha256="3" * 64,
    )
    dataset = DatasetMetadata(
        schema_version=1,
        snapshot_id="techqa@abc1234",
        train_json_sha256="4" * 64,
        split_seed=20261125,
        dev_ratio=0.3,
        excluded_conflict_ids=[],
        total_labeled=len(items),
        ambiguous_count=0,
        active_count=len(items),
    )
    return EvalRunArtifact(
        config=config,
        dataset=dataset,
        summary=aggregate_run(items),
        items=items,
        item_questions={
            item.question_id: f"Question text for {item.question_id}?" for item in items
        },
        item_reference_answers={
            item.question_id: f"Reference answer for {item.question_id}."
            for item in items
            if item.verified_label == "answerable_in_corpus"
        },
        started_at="2026-11-26T12:00:00+00:00",
        finished_at="2026-11-26T12:01:00+00:00",
    )


def test_sampling_is_deterministic_and_order_independent() -> None:
    items = [
        *[_make_answered_item(f"OM_{i:02d}", omitted_claims=2) for i in range(8)],
        *[_make_abstained_item(f"AB_{i:02d}") for i in range(8)],
        *[_make_answered_item(f"REG_{i:02d}", omitted_claims=0) for i in range(25)],
    ]
    run_forward = _build_artifact(items)
    run_reversed = _build_artifact(list(reversed(items)))

    sample_a = sample_for_manual_audit(run_forward, seed=20261125)
    sample_b = sample_for_manual_audit(run_reversed, seed=20261125)
    sample_other_seed = sample_for_manual_audit(run_forward, seed=999)

    ids_a = [entry.question_id for entry in sample_a]
    ids_b = [entry.question_id for entry in sample_b]
    ids_other = [entry.question_id for entry in sample_other_seed]

    assert ids_a == ids_b
    assert ids_a != ids_other


def test_sampling_small_run_below_min_samples_takes_all_non_failed() -> None:
    items = [
        _make_answered_item("A1", omitted_claims=1),
        _make_answered_item("A2", omitted_claims=0),
        _make_answered_item("A3", omitted_claims=0),
        _make_abstained_item("B1"),
        _make_abstained_item("B2"),
        _make_failed_item("F1"),
        _make_failed_item("F2"),
    ]
    run = _build_artifact(items)

    entries = sample_for_manual_audit(run, min_samples=20)

    assert len(entries) == 5
    selected_ids = {entry.question_id for entry in entries}
    assert selected_ids == {"A1", "A2", "A3", "B1", "B2"}
    assert "F1" not in selected_ids
    assert "F2" not in selected_ids


def test_sampling_scales_with_answer_fraction_above_min_samples() -> None:
    # 100 answered (10 omitted + 90 regular) + 10 abstained => ceil(0.25 * 100) = 25
    items = [
        *[_make_answered_item(f"OM_{i:02d}", omitted_claims=1) for i in range(10)],
        *[_make_abstained_item(f"AB_{i:02d}") for i in range(10)],
        *[_make_answered_item(f"REG_{i:02d}", omitted_claims=0) for i in range(90)],
    ]
    run = _build_artifact(items)

    entries = sample_for_manual_audit(run, min_samples=20, answer_fraction=0.25)

    assert len(entries) == 25
    by_stratum = {
        "answered_omitted_claims": sum(
            1 for e in entries if e.stratum == "answered_omitted_claims"
        ),
        "abstained": sum(1 for e in entries if e.stratum == "abstained"),
        "answered_regular": sum(1 for e in entries if e.stratum == "answered_regular"),
    }
    assert by_stratum == {
        "answered_omitted_claims": 5,
        "abstained": 5,
        "answered_regular": 15,
    }


def test_sampling_tops_up_budget_when_regular_answered_is_exhausted() -> None:
    items = [
        *[_make_answered_item(f"OM_{i:02d}", omitted_claims=3) for i in range(8)],
        *[_make_abstained_item(f"AB_{i:02d}") for i in range(8)],
    ]
    run = _build_artifact(items)

    entries = sample_for_manual_audit(run, min_samples=20)

    assert len(entries) == 16
    assert sum(1 for e in entries if e.outcome == "answered") == 8
    assert sum(1 for e in entries if e.outcome == "abstained") == 8


def test_export_manual_audit_hides_judge_verdicts_and_includes_full_context(
    tmp_path: Path,
) -> None:
    items = [
        _make_answered_item(
            "Q_ANS_1",
            omitted_claims=1,
            citation_reasoning="SECRET_CITATION_JUDGE_REASONING_XYZ",
            reference_reasoning="SECRET_REFERENCE_JUDGE_REASONING_ABC",
        ),
        _make_abstained_item("Q_ABST_1"),
    ]
    run = _build_artifact(items)
    entries = sample_for_manual_audit(run)

    json_path, md_path = export_manual_audit(entries, tmp_path, run.config.run_name)

    assert json_path == tmp_path / f"{run.config.run_name}-manual-audit.json"
    assert md_path == tmp_path / f"{run.config.run_name}-manual-audit.md"
    assert json_path.is_file()
    assert md_path.is_file()

    json_text = json_path.read_text(encoding="utf-8")
    md_text = md_path.read_text(encoding="utf-8")

    # Brak wycieku werdyktów i uzasadnień sędziego LLM (ochrona przed zakotwiczeniem).
    for forbidden in (
        "SECRET_CITATION_JUDGE_REASONING_XYZ",
        "SECRET_REFERENCE_JUDGE_REASONING_ABC",
        "citation_judge",
        "reference_judge",
    ):
        assert forbidden not in json_text
        assert forbidden not in md_text

    # Sprawdzenie struktury JSON: osobne pola dla answered i abstained.
    payload = json.loads(json_text)
    assert payload["schema_version"] == 1
    assert payload["run_name"] == run.config.run_name
    by_id = {entry["question_id"]: entry for entry in payload["entries"]}

    ans_record = by_id["Q_ANS_1"]
    assert ans_record["outcome"] == "answered"
    assert ans_record["human_citation_supported"] is None
    assert ans_record["human_reference_verdict"] is None
    assert ans_record["human_note"] == ""
    assert "human_abstain_justified" not in ans_record

    abst_record = by_id["Q_ABST_1"]
    assert abst_record["outcome"] == "abstained"
    assert abst_record["human_abstain_justified"] is None
    assert abst_record["human_note"] == ""
    assert "human_citation_supported" not in abst_record
    assert "human_reference_verdict" not in abst_record

    # Sprawdzenie pełnego kontekstu w Markdownie.
    assert "Question text for Q_ANS_1?" in md_text
    assert "Uruchom ponownie usługę poleceniem systemctl." in md_text
    assert "run `systemctl restart knowledgeops`" in md_text
    assert "Before restarting the cluster node" in md_text
    assert "Reference answer for Q_ANS_1." in md_text
    assert "Q_ABST_1" in md_text
    assert "`no_claims`" in md_text
