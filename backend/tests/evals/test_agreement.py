"""Testy obliczania zgodności sędzia–człowiek (Cohen's kappa) i CLI (Faza 4)."""

import json
from pathlib import Path

import pytest

from app import cli
from app.answering.model import JudgeModelInfo
from app.answering.schemas import (
    AbstainedResult,
    AnswerClaim,
    AnsweredResult,
    Citation,
    CitationClaim,
)
from app.evals.agreement import (
    NO_VARIANCE_KAPPA_NOTE,
    compute_cohens_kappa,
    evaluate_judge_agreement,
)
from app.evals.dataset import DatasetMetadata
from app.evals.judge import (
    CitationJudgeResult,
    CitationJudgeVerdict,
    CitationVerdict,
    ReferenceAgreementOutput,
    ReferenceJudgeResult,
    ReferenceVerdict,
)
from app.evals.metrics import (
    CitationInvariantCheck,
    EvalItemExecution,
    aggregate_run,
)
from app.evals.report import render_markdown_report, write_raw_run
from app.evals.runner import EvalRunArtifact, EvalRunConfig
from app.evals.sampling import export_manual_audit, sample_for_manual_audit
from app.retrieval import ChunkSetReproInfo


def _make_answered(
    qid: str,
    *,
    citation_verdict: CitationVerdict,
    reference_verdict: ReferenceVerdict | None,
) -> EvalItemExecution:
    label = (
        "answerable_in_corpus"
        if reference_verdict is not None
        else "verified_unanswerable"
    )
    answer = AnsweredResult(
        claims=[AnswerClaim(text="Claim text.", code=None, citation=1)],
        citations=[
            Citation(
                n=1,
                chunk_id=f"c_{qid}",
                doc_id=f"d_{qid}",
                title="Doc",
                headings=["Sec"],
                claims=[
                    CitationClaim(
                        claim_index=0,
                        quote="Claim quote.",
                        quote_start=0,
                        quote_end=12,
                    )
                ],
            )
        ],
        checked_chunks=[],
        omitted_claims=0,
    )
    ref_judge = (
        ReferenceJudgeResult(
            output=ReferenceAgreementOutput(
                reasoning="Judge reasoning.", verdict=reference_verdict
            )
        )
        if reference_verdict is not None
        else None
    )
    return EvalItemExecution(
        question_id=qid,
        split="dev",
        verified_label=label,
        outcome="answered",
        latency_ms=1000.0,
        answer=answer,
        citation_invariants=CitationInvariantCheck(passed=True),
        citation_judge=CitationJudgeResult(
            verdicts=[
                CitationJudgeVerdict(
                    claim_index=0,
                    reasoning="Judge quote reasoning.",
                    verdict=citation_verdict,
                )
            ]
        ),
        reference_judge=ref_judge,
        cited_chunk_texts={f"c_{qid}": "Claim quote. Extra context."},
    )


def _make_abstained(qid: str) -> EvalItemExecution:
    return EvalItemExecution(
        question_id=qid,
        split="dev",
        verified_label="verified_unanswerable",
        outcome="abstained",
        latency_ms=400.0,
        answer=AbstainedResult(reason="no_hits", checked_chunks=[], omitted_claims=0),
        abstention_reason="no_hits",
    )


def _make_artifact(items: list[EvalItemExecution]) -> EvalRunArtifact:
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
        run_name="abstention-dev-20261126T130000Z",
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
        item_questions={item.question_id: f"Q {item.question_id}?" for item in items},
        item_reference_answers={
            item.question_id: f"Ref {item.question_id}"
            for item in items
            if item.verified_label == "answerable_in_corpus"
        },
        started_at="2026-11-26T13:00:00+00:00",
        finished_at="2026-11-26T13:01:00+00:00",
    )


def test_cohens_kappa_perfect_agreement() -> None:
    pairs = [
        ("supported", "supported"),
        ("supported", "supported"),
        ("unsupported", "unsupported"),
    ]
    assert compute_cohens_kappa(pairs) == pytest.approx(1.0)


def test_cohens_kappa_chance_agreement() -> None:
    pairs = [
        ("supported", "supported"),
        ("supported", "unsupported"),
        ("unsupported", "supported"),
        ("unsupported", "unsupported"),
    ]
    assert compute_cohens_kappa(pairs) == pytest.approx(0.0)


def test_cohens_kappa_complete_disagreement() -> None:
    pairs = [
        ("supported", "unsupported"),
        ("unsupported", "supported"),
    ]
    assert compute_cohens_kappa(pairs) == pytest.approx(-1.0)


def test_cohens_kappa_partial_agreement_exact_value() -> None:
    # 4 pairs: (full, full) x2, (partial, partial) x1, (partial, incorrect) x1
    # p_o = 3/4 = 0.75
    # marginals A: full=2/4, partial=2/4, incorrect=0
    # marginals B: full=2/4, partial=1/4, incorrect=1/4
    # p_e = (2/4)*(2/4) + (2/4)*(1/4) + 0 = 0.25 + 0.125 = 0.375
    # kappa = (0.75 - 0.375) / (1 - 0.375) = 0.375 / 0.625 = 0.6
    pairs = [
        ("full", "full"),
        ("full", "full"),
        ("partial", "partial"),
        ("partial", "incorrect"),
    ]
    assert compute_cohens_kappa(pairs) == pytest.approx(0.6)


def test_cohens_kappa_no_variance_and_empty_return_none() -> None:
    assert compute_cohens_kappa([]) is None
    assert (
        compute_cohens_kappa([("supported", "supported"), ("supported", "supported")])
        is None
    )


def test_evaluate_judge_agreement_metrics_confusion_and_abstained(
    tmp_path: Path,
) -> None:
    items = [
        _make_answered("Q1", citation_verdict="supported", reference_verdict="full"),
        _make_answered("Q2", citation_verdict="supported", reference_verdict="partial"),
        _make_answered(
            "Q3", citation_verdict="unsupported", reference_verdict="incorrect"
        ),
        # verified_unanswerable answered: ma citation_judge, ale brak reference_judge
        _make_answered("Q4", citation_verdict="unsupported", reference_verdict=None),
        _make_abstained("A1"),
        _make_abstained("A2"),
    ]
    artifact = _make_artifact(items)
    run_path = tmp_path / f"{artifact.config.run_name}.json"
    write_raw_run(run_path, artifact)

    entries = sample_for_manual_audit(artifact)
    audit_json, _ = export_manual_audit(entries, tmp_path, artifact.config.run_name)

    payload = json.loads(audit_json.read_text(encoding="utf-8"))
    human_overrides = {
        "Q1": {"human_citation_supported": True, "human_reference_verdict": "full"},
        "Q2": {
            "human_citation_supported": False,
            "human_reference_verdict": "partial",
        },
        "Q3": {
            "human_citation_supported": False,
            "human_reference_verdict": "incorrect",
        },
        # Brak human_reference_verdict dla Q4 jest poprawny (brak reference_judge).
        "Q4": {"human_citation_supported": False, "human_reference_verdict": None},
        "A1": {"human_abstain_justified": True},
        "A2": {"human_abstain_justified": False},
    }
    for rec in payload["entries"]:
        rec.update(human_overrides[rec["question_id"]])
    audit_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    summary = evaluate_judge_agreement(run_path, audit_json)

    assert summary.n_sampled == 6
    assert summary.n_reviewed == 6
    assert summary.n_citation_pairs == 4
    # 3 z 4 zgodne (Q1, Q3, Q4); p_o = 0.75
    # judge: 2 sup, 2 unsup; human: 1 sup, 3 unsup => p_e = 0.5*0.25 + 0.5*0.75 = 0.5
    # kappa = (0.75 - 0.5) / 0.5 = 0.5
    assert summary.citation_agreement_rate == pytest.approx(0.75)
    assert summary.citation_cohens_kappa == pytest.approx(0.5)
    assert summary.citation_kappa_note is None
    assert summary.citation_confusion_matrix == {
        "supported": {"supported": 1, "unsupported": 1},
        "unsupported": {"supported": 0, "unsupported": 2},
    }

    assert summary.n_reference_pairs == 3
    assert summary.reference_agreement_rate == pytest.approx(1.0)
    assert summary.reference_cohens_kappa == pytest.approx(1.0)
    assert summary.reference_confusion_matrix == {
        "full": {"full": 1, "partial": 0, "incorrect": 0},
        "partial": {"full": 0, "partial": 1, "incorrect": 0},
        "incorrect": {"full": 0, "partial": 0, "incorrect": 1},
    }

    assert summary.n_abstained_sampled == 2
    assert summary.n_abstained_reviewed == 2
    assert summary.abstained_justified_count == 1
    assert summary.abstained_unjustified_count == 1


def test_evaluate_judge_agreement_handles_no_variance_and_renders_report(
    tmp_path: Path,
) -> None:
    items = [
        _make_answered("Q1", citation_verdict="supported", reference_verdict="full"),
        _make_answered("Q2", citation_verdict="supported", reference_verdict="full"),
        _make_abstained("A1"),
    ]
    artifact = _make_artifact(items)
    run_path = tmp_path / f"{artifact.config.run_name}.json"
    write_raw_run(run_path, artifact)

    entries = sample_for_manual_audit(artifact)
    audit_json, _ = export_manual_audit(entries, tmp_path, artifact.config.run_name)

    payload = json.loads(audit_json.read_text(encoding="utf-8"))
    for rec in payload["entries"]:
        if rec["outcome"] == "answered":
            rec["human_citation_supported"] = True
            rec["human_reference_verdict"] = "full"
        else:
            rec["human_abstain_justified"] = True
    audit_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    summary = evaluate_judge_agreement(run_path, audit_json)

    assert summary.citation_agreement_rate == pytest.approx(1.0)
    assert summary.citation_cohens_kappa is None
    assert summary.citation_kappa_note == NO_VARIANCE_KAPPA_NOTE
    assert summary.reference_agreement_rate == pytest.approx(1.0)
    assert summary.reference_cohens_kappa is None
    assert summary.reference_kappa_note == NO_VARIANCE_KAPPA_NOTE

    md = render_markdown_report(artifact, agreement=summary)
    assert "do uzupełnienia w Fazie 4" not in md
    assert NO_VARIANCE_KAPPA_NOTE in md
    assert "Macierz pomyłek — wsparcie cytatów" in md
    assert "Macierz pomyłek — zgodność z odpowiedzią referencyjną" in md
    assert "Przegląd jakościowy warstwy `abstained`" in md


def test_evaluate_judge_agreement_validates_missing_answered_ratings(
    tmp_path: Path,
) -> None:
    items = [
        _make_answered("Q1", citation_verdict="supported", reference_verdict="full"),
        _make_abstained("A1"),
    ]
    artifact = _make_artifact(items)
    run_path = tmp_path / f"{artifact.config.run_name}.json"
    write_raw_run(run_path, artifact)

    entries = sample_for_manual_audit(artifact)
    audit_json, _ = export_manual_audit(entries, tmp_path, artifact.config.run_name)

    # Nieuzupełniony arkusz -> błąd walidacji dla Q1.
    with pytest.raises(ValueError, match="human_citation_supported"):
        evaluate_judge_agreement(run_path, audit_json)

    # Uzupełnione tylko cytaty, brak reference -> błąd walidacji dla reference.
    payload = json.loads(audit_json.read_text(encoding="utf-8"))
    for rec in payload["entries"]:
        if rec["question_id"] == "Q1":
            rec["human_citation_supported"] = True
    audit_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="human_reference_verdict"):
        evaluate_judge_agreement(run_path, audit_json)

    # Uzupełnione oba pola na Q1, a A1 pozostawione null -> przechodzi bez błędu.
    for rec in payload["entries"]:
        if rec["question_id"] == "Q1":
            rec["human_reference_verdict"] = "full"
    audit_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    summary = evaluate_judge_agreement(run_path, audit_json)
    assert summary.n_citation_pairs == 1
    assert summary.n_reference_pairs == 1
    assert summary.n_abstained_sampled == 1
    assert summary.n_abstained_reviewed == 0


def test_cli_eval_judge_agreement_help_and_report_update(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["eval-judge-agreement", "--help"])
    assert exc_info.value.code == 0

    items = [
        _make_answered("Q1", citation_verdict="supported", reference_verdict="full"),
        _make_answered(
            "Q2", citation_verdict="unsupported", reference_verdict="incorrect"
        ),
    ]
    artifact = _make_artifact(items)
    run_path = tmp_path / f"{artifact.config.run_name}.json"
    write_raw_run(run_path, artifact)

    entries = sample_for_manual_audit(artifact)
    audit_json, _ = export_manual_audit(entries, tmp_path, artifact.config.run_name)

    payload = json.loads(audit_json.read_text(encoding="utf-8"))
    for rec in payload["entries"]:
        if rec["question_id"] == "Q1":
            rec["human_citation_supported"] = True
            rec["human_reference_verdict"] = "full"
        else:
            rec["human_citation_supported"] = False
            rec["human_reference_verdict"] = "incorrect"
    audit_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    report_out = tmp_path / "updated-report.md"
    exit_code = cli.main(
        [
            "eval-judge-agreement",
            "--run",
            str(run_path),
            "--audit",
            str(audit_json),
            "--report-out",
            str(report_out),
        ]
    )

    assert exit_code == 0
    assert report_out.is_file()
    md = report_out.read_text(encoding="utf-8")
    assert "100.0%" in md
    assert "1.000" in md
    assert "Macierz pomyłek — wsparcie cytatów" in md
