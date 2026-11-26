"""Testy generatora raportu Markdown i eksportu surowego JSON (Faza 3)."""

from pathlib import Path

from app.answering.model import JudgeModelInfo
from app.answering.schemas import (
    AbstainedResult,
    AnswerClaim,
    AnsweredResult,
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
from app.evals.report import (
    JudgeAgreementSummary,
    render_markdown_report,
    write_raw_run,
)
from app.evals.runner import EvalRunArtifact, EvalRunConfig
from app.retrieval import ChunkSetReproInfo


def _sample_artifact(
    *,
    use_langfuse: bool = True,
    judge_fallback: bool = False,
) -> EvalRunArtifact:
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
        limit=10,
        concurrency=2,
        use_langfuse=use_langfuse,
        dataset_name="knowledgeops/abstention-eval",
        run_name="abstention-dev-20261126T120000Z",
        repro_info=repro,
        chat_model="gpt-5-mini",
        chat_reasoning_effort="low",
        k=8,
        answer_prompt_versions={"draft": "aaaaaaaaaaaa", "verify": "bbbbbbbbbbbb"},
        judge_model_info=JudgeModelInfo(
            model="gpt-5-mini" if judge_fallback else "gpt-5",
            reasoning_effort="low",
            is_fallback_to_chat_model=judge_fallback,
        ),
        judge_prompt_versions={
            "citation_support": "cccccccccccc",
            "reference_agreement": "dddddddddddd",
        },
        config_sha256="3" * 64,
    )
    dataset = DatasetMetadata(
        schema_version=1,
        snapshot_id="techqa@abc1234",
        train_json_sha256="4" * 64,
        split_seed=20261125,
        dev_ratio=0.3,
        excluded_conflict_ids=[],
        total_labeled=5,
        ambiguous_count=1,
        active_count=4,
    )

    answered_ok = AnsweredResult(
        claims=[AnswerClaim(text="Restart the service.", code=None, citation=1)],
        citations=[
            Citation(
                n=1,
                chunk_id="c1",
                doc_id="d1",
                title="Doc 1",
                headings=["Fix"],
                claims=[
                    CitationClaim(
                        claim_index=0,
                        quote="Restart the service.",
                        quote_start=0,
                        quote_end=20,
                    )
                ],
            )
        ],
        checked_chunks=[],
        omitted_claims=0,
    )
    abstained = AbstainedResult(reason="no_claims", checked_chunks=[], omitted_claims=0)

    items = [
        EvalItemExecution(
            question_id="Q_ANS_OK",
            split="dev",
            verified_label="answerable_in_corpus",
            outcome="answered",
            latency_ms=1200.0,
            answer=answered_ok,
            citation_invariants=CitationInvariantCheck(passed=True),
            citation_judge=CitationJudgeResult(
                verdicts=[
                    CitationJudgeVerdict(
                        claim_index=0, reasoning="Matches quote.", verdict="supported"
                    )
                ]
            ),
            reference_judge=ReferenceJudgeResult(
                output=ReferenceAgreementOutput(reasoning="Same fix.", verdict="full")
            ),
        ),
        EvalItemExecution(
            question_id="Q_FALSE_REFUSAL",
            split="dev",
            verified_label="answerable_in_corpus",
            outcome="abstained",
            latency_ms=900.0,
            answer=abstained,
            abstention_reason="no_claims",
        ),
        EvalItemExecution(
            question_id="Q_MISSED_ABSTAIN",
            split="dev",
            verified_label="verified_unanswerable",
            outcome="answered",
            latency_ms=1500.0,
            answer=answered_ok,
            citation_invariants=CitationInvariantCheck(passed=True),
            citation_judge=CitationJudgeResult(
                verdicts=[
                    CitationJudgeVerdict(
                        claim_index=0, reasoning="Weak.", verdict="unsupported"
                    )
                ]
            ),
        ),
        EvalItemExecution(
            question_id="Q_TIMEOUT",
            split="dev",
            verified_label="verified_unanswerable",
            outcome="failed",
            latency_ms=25000.0,
            error="TimeoutError: przekroczono answer_deadline_s (25s)",
        ),
    ]

    return EvalRunArtifact(
        config=config,
        dataset=dataset,
        summary=aggregate_run(items),
        items=items,
        item_questions={
            "Q_ANS_OK": "How to fix service crash?",
            "Q_FALSE_REFUSAL": "How to configure TLS?",
            "Q_MISSED_ABSTAIN": "What is the price of license?",
            "Q_TIMEOUT": "Slow question?",
        },
        langfuse_run_id="exp-123" if use_langfuse else None,
        langfuse_run_url="https://cloud.langfuse.com/runs/exp-123"
        if use_langfuse
        else None,
        started_at="2026-11-26T12:00:00+00:00",
        finished_at="2026-11-26T12:01:00+00:00",
    )


def test_write_raw_run_round_trip(tmp_path: Path) -> None:
    artifact = _sample_artifact()
    target = tmp_path / "nested" / f"{artifact.config.run_name}.json"

    write_raw_run(target, artifact)

    assert target.is_file()
    restored = EvalRunArtifact.model_validate_json(target.read_text(encoding="utf-8"))
    assert restored == artifact


def test_render_markdown_report_contains_all_required_sections_and_langfuse() -> None:
    artifact = _sample_artifact(use_langfuse=True, judge_fallback=False)

    md = render_markdown_report(artifact)

    for heading in (
        "## Metadane i odtwarzalność",
        "## Podsumowanie Sprawdzianu 2a (Abstencja i fałszywe odmowy)",
        "## Podsumowanie Sprawdzianu 1b (Cytaty, zgodność z referencją i opóźnienie)",
        "## Rozbicie przyczyn abstencji",
        "## Przykłady błędów",
        "## Walidacja ręczna sędziego",
        "## Ograniczenia",
    ):
        assert heading in md

    assert "exp-123" in md
    assert "https://cloud.langfuse.com/runs/exp-123" in md
    assert "Tryb `--no-langfuse`" not in md
    assert "Fallback `EVAL_JUDGE_MODEL`" not in md
    assert "Q_MISSED_ABSTAIN" in md
    assert "Q_FALSE_REFUSAL" in md
    assert "Q_TIMEOUT" in md
    assert "do uzupełnienia w Fazie 4" in md


def test_render_markdown_report_warns_on_no_langfuse_and_judge_fallback() -> None:
    artifact = _sample_artifact(use_langfuse=False, judge_fallback=True)

    md = render_markdown_report(artifact)

    assert "Tryb `--no-langfuse`" in md
    assert "Fallback `EVAL_JUDGE_MODEL`" in md
    assert "wyłączony (`--no-langfuse`)" in md


def test_render_markdown_report_renders_manual_judge_agreement() -> None:
    artifact = _sample_artifact()
    agreement = JudgeAgreementSummary(
        n_sampled=20,
        n_reviewed=20,
        citation_agreement_rate=0.9,
        citation_cohens_kappa=0.81,
        reference_agreement_rate=0.85,
        reference_cohens_kappa=0.74,
        notes="Przegląd jednoosobowy na splicie dev.",
    )

    md = render_markdown_report(artifact, agreement=agreement)

    assert "do uzupełnienia w Fazie 4" not in md
    assert "90.0%" in md
    assert "0.810" in md
    assert "Przegląd jednoosobowy na splicie dev." in md
