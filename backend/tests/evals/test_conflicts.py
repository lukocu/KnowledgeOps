"""Testy Sprawdzianu 2b: walidacja zbioru, metryki deterministyczne i Langfuse."""

import asyncio
import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from langfuse import Evaluation, Langfuse
from langfuse.api.commons.errors import NotFoundError
from langfuse.experiment import ExperimentItemResult, ExperimentResult

from app.answering.graph import build_answer_graph
from app.answering.schemas import (
    ClaimVerdict,
    ConflictCheckOutput,
    ConflictComparisonOutput,
    ConflictComparisonRow,
    ConflictingResult,
    ConflictSide,
    DraftClaim,
    DraftOutput,
    VerifyOutput,
)
from app.db import AsyncPool
from app.evals.conflicts import (
    CONFLICT_CLASSES,
    DEFAULT_CONFLICTS_LANGFUSE_DATASET_NAME,
    ConflictEvalItem,
    ConflictItemExecution,
    aggregate_conflict_run,
    check_conflict_citation_invariants,
    conflict_dataset_item_id,
    execute_conflict_item,
    load_conflicts_dataset,
    render_conflicts_markdown_report,
    run_conflicts_eval,
    score_conflict_item,
)
from app.evals.langfuse_eval import RUN_EXPERIMENT_ASYNC_KWARGS
from app.evals.metrics import CitationInvariantCheck, TokenUsage
from app.retrieval import ChunkSetReproInfo, RetrievedChunk
from app.settings import Settings
from app.synthetic.importer import DOCUMENTS_PATH, load_synthetic_documents
from tests.answering.fakes import Script, ScriptedChatModel

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = BACKEND_ROOT / "evals" / "conflicts-dataset.json"

TECHQA_RAW_MARKERS = (
    "TECHNOTE (TROUBLESHOOTING)",
    "TECHNOTE (FAQ)",
    "PROBLEM(ABSTRACT)",
    "RESOLVING THE PROBLEM",
    "SUBSCRIBE TO THIS APAR",
    "THIS DOCUMENT APPLIES ONLY TO THE FOLLOWING LANGUAGE VERSION(S)",
)


# --- 1. Walidacja zbioru conflicts-dataset.json i czystość gita --------------


def test_conflicts_dataset_is_balanced_and_valid() -> None:
    loaded = load_conflicts_dataset(DATASET_PATH)
    assert loaded.metadata.schema_version == 1
    assert loaded.metadata.n_total == 24
    assert loaded.metadata.n_contradiction == 8
    assert loaded.metadata.n_different_recommendations == 8
    assert loaded.metadata.n_answered == 8
    assert len(loaded.items) == 24

    ids = [item.id for item in loaded.items]
    assert len(set(ids)) == 24

    anchors = [item.anchor_techqa_doc_id for item in loaded.items]
    assert len(set(anchors)) == 24

    synthetic_docs = {doc.doc_id for doc in load_synthetic_documents(DOCUMENTS_PATH)}
    assert "SYN-KB-0007" in synthetic_docs

    for item in loaded.items:
        if item.synthetic_doc_id is not None:
            assert item.synthetic_doc_id in synthetic_docs
        if item.secondary_synthetic_doc_id is not None:
            assert item.secondary_synthetic_doc_id in synthetic_docs

    nproc_items = [
        item for item in loaded.items if item.synthetic_doc_id == "SYN-KB-0007"
    ]
    assert len(nproc_items) == 1
    assert nproc_items[0].anchor_techqa_doc_id == "swg21648497"
    assert nproc_items[0].expected_conflict_type == "different_recommendations"


def test_git_tracked_conflict_files_contain_no_raw_techqa_text() -> None:
    for path in (DATASET_PATH, DOCUMENTS_PATH):
        raw = path.read_text(encoding="utf-8")
        for marker in TECHQA_RAW_MARKERS:
            assert marker not in raw, (
                f"Wykryto surowy znacznik TechQA {marker!r} w {path.name}"
            )

    train_json = BACKEND_ROOT.parent / "data" / "raw" / "techqa" / "train.json"
    if train_json.exists():
        train_records = json.loads(train_json.read_text(encoding="utf-8"))
        techqa_questions = {
            " ".join(str(rec.get("QUESTION_TEXT", "")).split()).casefold()
            for rec in train_records
            if rec.get("QUESTION_TEXT")
        }
        loaded = load_conflicts_dataset(DATASET_PATH)
        for item in loaded.items:
            norm_q = " ".join(item.question.split()).casefold()
            assert norm_q not in techqa_questions, (
                f"{item.id} zawiera dosłowne pytanie z TechQA train.json"
            )


# --- 2. Metryki deterministyczne i inwarianty cytatów A/B --------------------


def _make_conflict_side(
    label: str, doc_id: str, chunk_id: str, quote: str, start: int, end: int
) -> ConflictSide:
    return ConflictSide(
        label="A" if label == "A" else "B",
        snapshot_id="synthetic@v1",
        doc_id=doc_id,
        chunk_id=chunk_id,
        title=f"Doc {doc_id}",
        headings=[],
        is_synthetic=True,
        doc_date="2020-01",
        product_version="v1",
        audience="admins",
        claim_text=f"Claim for {doc_id}",
        code=None,
        quote=quote,
        quote_start=start,
        quote_end=end,
    )


def test_check_conflict_citation_invariants_valid_and_invalid() -> None:
    chunks = {
        "c1": "Set parameter foo to 100 on Linux.",
        "c2": "Set parameter foo to 200 on Linux.",
    }
    valid = ConflictingResult(
        conflict_type="contradiction",
        summary="Docs disagree on foo.",
        refine_hint=None,
        comparison_rows=[
            ConflictComparisonRow(kind="recommendation", side_a="100", side_b="200")
        ],
        sides=(
            _make_conflict_side("A", "DOC-1", "c1", "foo to 100", 14, 24),
            _make_conflict_side("B", "DOC-2", "c2", "foo to 200", 14, 24),
        ),
        checked_chunks=[],
        omitted_claims=0,
    )
    ok = check_conflict_citation_invariants(valid, chunks)
    assert ok.passed is True
    assert ok.violations == []

    bad_slice = ConflictingResult(
        conflict_type="contradiction",
        summary="Docs disagree on foo.",
        refine_hint=None,
        comparison_rows=[],
        sides=(
            _make_conflict_side("A", "DOC-1", "c1", "WRONG QUOTE", 14, 24),
            _make_conflict_side("B", "DOC-1", "c2", "foo to 200", 14, 24),
        ),
        checked_chunks=[],
        omitted_claims=0,
    )
    bad = check_conflict_citation_invariants(bad_slice, chunks)
    assert bad.passed is False
    assert any("ten sam doc_id" in v for v in bad.violations)
    assert any("nie zgadza się dosłownie" in v for v in bad.violations)


def test_aggregate_conflict_run_confusion_matrix_and_metrics() -> None:
    def _exec(
        *,
        item_id: str,
        exp_outcome: str,
        exp_type: str | None,
        scope_note: str,
        outcome: str,
        pred_type: str | None,
        latency_ms: float,
        inv_ok: bool | None = True,
        both_cited: bool | None = None,
        tokens: int = 100,
    ) -> ConflictItemExecution:
        exp_cls = exp_type if exp_outcome == "conflicting" else "answered"
        assert exp_cls in CONFLICT_CLASSES
        pred_cls: Any = None
        if outcome == "conflicting":
            pred_cls = pred_type
        elif outcome in ("answered", "abstained"):
            pred_cls = outcome
        return ConflictItemExecution(
            id=item_id,
            expected_outcome="conflicting"
            if exp_outcome == "conflicting"
            else "answered",
            expected_conflict_type=cast(Any, exp_type),
            expected_class=cast(Any, exp_cls),
            anchor_techqa_doc_id="swg20000001",
            synthetic_doc_id="SYN-1" if exp_outcome == "conflicting" else None,
            scope_note=scope_note,
            outcome=cast(Any, outcome),
            predicted_conflict_type=cast(Any, pred_type),
            predicted_class=pred_cls,
            latency_ms=latency_ms,
            both_sides_cited=both_cited,
            citation_invariants=(
                CitationInvariantCheck(
                    passed=inv_ok, violations=[] if inv_ok else ["err"]
                )
                if inv_ok is not None
                else None
            ),
            usage=TokenUsage(
                input_tokens=tokens - 20, output_tokens=20, total_tokens=tokens
            ),
        )

    runs = [
        _exec(
            item_id="C1",
            exp_outcome="conflicting",
            exp_type="contradiction",
            scope_note="same_scope",
            outcome="conflicting",
            pred_type="contradiction",
            latency_ms=1000.0,
            both_cited=True,
        ),
        _exec(
            item_id="D1",
            exp_outcome="conflicting",
            exp_type="different_recommendations",
            scope_note="different_version: v1 vs v2",
            outcome="conflicting",
            pred_type="contradiction",  # misclassified different_version!
            latency_ms=2000.0,
            both_cited=True,
        ),
        _exec(
            item_id="D2",
            exp_outcome="conflicting",
            exp_type="different_recommendations",
            scope_note="different_version: v2 vs v3",
            outcome="conflicting",
            pred_type="different_recommendations",
            latency_ms=3000.0,
            both_cited=True,
        ),
        _exec(
            item_id="A1",
            exp_outcome="answered",
            exp_type=None,
            scope_note="control_no_conflict",
            outcome="answered",
            pred_type=None,
            latency_ms=1500.0,
        ),
        _exec(
            item_id="A2",
            exp_outcome="answered",
            exp_type=None,
            scope_note="control_no_conflict",
            outcome="conflicting",  # false conflict!
            pred_type="different_recommendations",
            latency_ms=12_000.0,  # over 10s budget
            both_cited=False,
            inv_ok=False,
        ),
        _exec(
            item_id="F1",
            exp_outcome="answered",
            exp_type=None,
            scope_note="control_no_conflict",
            outcome="failed",
            pred_type=None,
            latency_ms=25_000.0,
            inv_ok=None,
        ),
    ]

    summary = aggregate_conflict_run(runs)
    assert summary.n_total == 6
    assert summary.n_evaluated == 5
    assert summary.n_failed == 1
    assert summary.confusion_matrix["contradiction"]["contradiction"] == 1
    assert summary.confusion_matrix["different_recommendations"]["contradiction"] == 1
    assert (
        summary.confusion_matrix["different_recommendations"][
            "different_recommendations"
        ]
        == 1
    )
    assert summary.confusion_matrix["answered"]["answered"] == 1
    assert summary.confusion_matrix["answered"]["different_recommendations"] == 1
    assert summary.overall_state_accuracy == pytest.approx(3 / 5)
    assert summary.scope_distinction_accuracy == pytest.approx(2 / 3)
    assert summary.n_different_version_eval == 2
    assert summary.different_version_misclassified_as_contradiction == 1
    assert summary.false_conflict_rate == pytest.approx(1 / 2)
    assert summary.both_sides_cited_rate == pytest.approx(3 / 4)
    assert summary.citation_invariants_pass_rate == pytest.approx(4 / 5)
    assert summary.within_latency_budget_rate == pytest.approx(4 / 5)
    assert summary.total_usage.total_tokens == 600


def test_score_conflict_item_emits_expected_scores() -> None:
    item = ConflictEvalItem(
        id="DIFF-1",
        question="Q?",
        expected_outcome="conflicting",
        expected_conflict_type="different_recommendations",
        anchor_techqa_doc_id="swg1",
        synthetic_doc_id="SYN-1",
        scope_note="different_version: v1 vs v2",
    )
    execution = ConflictItemExecution(
        id="DIFF-1",
        expected_outcome="conflicting",
        expected_conflict_type="different_recommendations",
        expected_class="different_recommendations",
        anchor_techqa_doc_id="swg1",
        synthetic_doc_id="SYN-1",
        scope_note="different_version: v1 vs v2",
        outcome="conflicting",
        predicted_conflict_type="different_recommendations",
        predicted_class="different_recommendations",
        latency_ms=1200.0,
        both_sides_cited=True,
        citation_invariants=CitationInvariantCheck(passed=True),
    )
    scores = {s.name: s.value for s in score_conflict_item(item, execution)}
    assert scores["execution_ok"] == 1.0
    assert scores["state_correct"] == 1.0
    assert scores["scope_distinction_correct"] == 1.0
    assert scores["different_version_misclassified_as_contradiction"] == 0.0
    assert scores["both_sides_cited"] == 1.0
    assert scores["citation_invariants_ok"] == 1.0
    assert scores["within_latency_budget"] == 1.0

    misclassified = execution.model_copy(
        update={
            "predicted_conflict_type": "contradiction",
            "predicted_class": "contradiction",
        }
    )
    bad_scores = {s.name: s.value for s in score_conflict_item(item, misclassified)}
    assert bad_scores["state_correct"] == 0.0
    assert bad_scores["scope_distinction_correct"] == 0.0
    assert bad_scores["different_version_misclassified_as_contradiction"] == 1.0


# --- 3. Obsługa błędów/timeoutów i kontrakt Langfuse 5.2.0 -------------------


class _AsyncContextStub:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *args: object) -> None:
        return None


class _DummyPool:
    def connection(self, **kwargs: Any) -> _AsyncContextStub:
        del kwargs
        return _AsyncContextStub()


class _SlowModel(BaseChatModel):
    delay_s: float = 0.2

    @property
    def _llm_type(self) -> str:
        return "slow-fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise AssertionError("tylko with_structured_output")

    def with_structured_output(
        self, schema: Any, *, strict: bool | None = None, **kwargs: Any
    ) -> Runnable[LanguageModelInput, Any]:
        del schema, strict, kwargs
        delay = self.delay_s

        def sync_fn(messages: LanguageModelInput) -> Any:
            del messages
            raise AssertionError("oczekiwano ainvoke")

        async def async_fn(messages: LanguageModelInput) -> Any:
            del messages
            await asyncio.sleep(delay)
            return DraftOutput(claims=[])

        return RunnableLambda(sync_fn, afunc=async_fn)


@pytest.mark.anyio
async def test_execute_conflict_item_handles_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_resolve(*args: Any, **kwargs: Any) -> list[str]:
        del args, kwargs
        return ["techqa@rev/sections-v1", "synthetic@v1/sections-v1"]

    async def fake_search(*args: Any, **kwargs: Any) -> list[RetrievedChunk]:
        del args, kwargs
        return [
            RetrievedChunk(
                rank=1,
                score=10.0,
                chunk_id="c1",
                doc_id="swg1",
                title="T",
                headings=[],
                text="Some passage text.",
                snapshot_id="techqa@rev",
            )
        ]

    monkeypatch.setattr(
        "app.answering.nodes.resolve_active_chunk_set_ids", fake_resolve
    )
    monkeypatch.setattr("app.answering.nodes.search_bm25", fake_search)

    settings = Settings(
        database_url="postgresql://u:p@127.0.0.1:5433/db",
        answer_deadline_s=0.05,
        chat_timeout_s=1.0,
    )
    graph = build_answer_graph(
        chat_model=_SlowModel(delay_s=0.3),
        pool=cast(AsyncPool, _DummyPool()),
        settings=settings,
    )
    item = ConflictEvalItem(
        id="T1",
        question="Q?",
        expected_outcome="answered",
        expected_conflict_type=None,
        anchor_techqa_doc_id="swg1",
        synthetic_doc_id=None,
        scope_note="control_no_conflict",
    )
    res = await execute_conflict_item(
        item,
        graph=graph,
        settings=settings,
        chunk_set_id="techqa@rev/sections-v1",
        use_langfuse=False,
    )
    assert res.outcome == "failed"
    assert res.error is not None and "TimeoutError" in res.error


@dataclass
class _FakeDatasetItem:
    id: str
    input: Any
    expected_output: Any
    metadata: dict[str, Any] | None


@dataclass
class _FakeDataset:
    name: str
    items: list[_FakeDatasetItem]


class _FakeLangfuseClient:
    def __init__(self) -> None:
        self.datasets: dict[str, dict[str, _FakeDatasetItem]] = {}
        self.experiment_calls: list[dict[str, Any]] = []
        self.item_evaluations: list[list[Evaluation]] = []
        self.run_evaluations: list[Evaluation] = []

    def get_dataset(self, name: str, **kwargs: Any) -> _FakeDataset:
        del kwargs
        if name not in self.datasets:
            raise NotFoundError(body={"message": "not found"})
        return _FakeDataset(name=name, items=list(self.datasets[name].values()))

    def create_dataset(
        self, *, name: str, description: str | None = None, metadata: Any = None
    ) -> None:
        del description, metadata
        self.datasets.setdefault(name, {})

    def create_dataset_item(
        self,
        *,
        dataset_name: str,
        id: str | None = None,
        input: Any = None,
        expected_output: Any = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> _FakeDatasetItem:
        del kwargs
        assert id is not None
        item = _FakeDatasetItem(
            id=id, input=input, expected_output=expected_output, metadata=metadata
        )
        self.datasets.setdefault(dataset_name, {})[id] = item
        return item

    async def _run_experiment_async(
        self,
        *,
        name: str,
        run_name: str,
        description: str | None,
        data: list[Any],
        task: Any,
        evaluators: list[Any],
        composite_evaluator: Any,
        run_evaluators: list[Any],
        max_concurrency: int,
        metadata: dict[str, Any] | None = None,
    ) -> ExperimentResult:
        self.experiment_calls.append(
            {
                "name": name,
                "run_name": run_name,
                "description": description,
                "data_len": len(data),
                "max_concurrency": max_concurrency,
                "metadata": metadata,
            }
        )
        item_results: list[ExperimentItemResult] = []
        for ds_item in data:
            output = await task(item=ds_item)
            evals: list[Evaluation] = []
            for ev in evaluators:
                evals.extend(
                    ev(
                        input=ds_item.input,
                        output=output,
                        expected_output=ds_item.expected_output,
                        metadata=ds_item.metadata,
                    )
                )
            self.item_evaluations.append(evals)
            item_results.append(
                ExperimentItemResult(
                    item=ds_item,
                    output=output,
                    evaluations=evals,
                    trace_id="trace-1",
                    dataset_run_id="run-1",
                )
            )
        for run_ev in run_evaluators:
            self.run_evaluations.extend(run_ev(item_results=item_results))
        return ExperimentResult(
            name=name,
            run_name=run_name,
            description=description,
            experiment_id="run-1",
            dataset_run_id="run-1",
            dataset_run_url="https://cloud.langfuse.com/project/p/datasets/d/runs/run-1",
            item_results=item_results,
            run_evaluations=self.run_evaluations,
        )


def test_langfuse_run_experiment_async_signature_contract() -> None:
    sig = inspect.signature(Langfuse._run_experiment_async)
    for kwarg in RUN_EXPERIMENT_ASYNC_KWARGS:
        assert kwarg in sig.parameters


@pytest.mark.anyio
async def test_run_conflicts_eval_with_fake_langfuse_and_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunk_a = RetrievedChunk(
        rank=1,
        score=12.0,
        chunk_id="syn/SYN-1/0",
        doc_id="SYN-1",
        title="Doc A",
        headings=[],
        text="Set nproc to 1024 on Linux.",
        snapshot_id="synthetic@v1",
        is_synthetic=True,
        doc_date="2020-01",
        product_version="v1",
        audience="admins",
    )
    chunk_b = RetrievedChunk(
        rank=2,
        score=11.0,
        chunk_id="syn/SYN-2/0",
        doc_id="SYN-2",
        title="Doc B",
        headings=[],
        text="Set nproc to 131072 on Linux.",
        snapshot_id="synthetic@v1",
        is_synthetic=True,
        doc_date="2020-01",
        product_version="v1",
        audience="admins",
    )

    async def fake_resolve(*args: Any, **kwargs: Any) -> list[str]:
        del args, kwargs
        return ["techqa@rev/sections-v1", "synthetic@v1/sections-v1"]

    async def fake_search(*args: Any, **kwargs: Any) -> list[RetrievedChunk]:
        del args, kwargs
        return [chunk_a, chunk_b]

    monkeypatch.setattr(
        "app.answering.nodes.resolve_active_chunk_set_ids", fake_resolve
    )
    monkeypatch.setattr("app.answering.nodes.search_bm25", fake_search)
    monkeypatch.setattr("app.evals.conflicts.flush_traces", lambda: None)

    model = ScriptedChatModel(
        script=Script(
            drafts=[
                DraftOutput(
                    claims=[
                        DraftClaim(
                            text="Set nproc to 1024.",
                            code=None,
                            chunk_id="syn/SYN-1/0",
                            quote="Set nproc to 1024 on Linux.",
                        ),
                        DraftClaim(
                            text="Set nproc to 131072.",
                            code=None,
                            chunk_id="syn/SYN-2/0",
                            quote="Set nproc to 131072 on Linux.",
                        ),
                    ]
                )
            ],
            verifies=[
                VerifyOutput(
                    verdicts=[
                        ClaimVerdict(
                            claim_index=0, verdict="supported", reasoning="ok"
                        ),
                        ClaimVerdict(
                            claim_index=1, verdict="supported", reasoning="ok"
                        ),
                    ]
                )
            ],
            conflicts=[
                ConflictCheckOutput(
                    reasoning="Same product version and audience with opposite values.",
                    has_conflict=True,
                    scope_relation="same_scope",
                    side_a_claim_indices=[0],
                    side_b_claim_indices=[1],
                    conflicting_doc_ids=["SYN-1", "SYN-2"],
                    summary="Documents disagree on nproc value.",
                    refine_hint=None,
                    comparison=ConflictComparisonOutput(
                        value_label="nproc",
                        side_a_value="1024",
                        side_b_value="131072",
                    ),
                )
            ],
        )
    )

    loaded = load_conflicts_dataset(DATASET_PATH)
    fake_lf = _FakeLangfuseClient()
    repro = ChunkSetReproInfo(
        snapshot_id="techqa@rev",
        revision="rev",
        chunk_set_id="techqa@rev/sections-v1",
        variant="sections-v1",
        config_sha256="cfg1",
        state_sha256="state-techqa",
    )
    syn_repro = ChunkSetReproInfo(
        snapshot_id="synthetic@v1",
        revision="v1",
        chunk_set_id="synthetic@v1/sections-v1",
        variant="sections-v1",
        config_sha256="cfg1",
        state_sha256="state-syn",
    )
    settings = Settings(database_url="postgresql://u:p@127.0.0.1:5433/db")

    artifact = await run_conflicts_eval(
        dataset=loaded,
        settings=settings,
        pool=cast(AsyncPool, _DummyPool()),
        limit=1,
        concurrency=1,
        use_langfuse=True,
        chat_model=model,
        langfuse_client=cast(Langfuse, fake_lf),
        repro_info=repro,
        synthetic_repro_info=syn_repro,
    )

    assert artifact.summary.n_evaluated == 1
    assert artifact.summary.n_failed == 0
    assert artifact.summary.overall_state_accuracy == 1.0
    assert artifact.summary.citation_invariants_pass_rate == 1.0
    assert artifact.langfuse_run_id == "run-1"
    assert len(fake_lf.experiment_calls) == 1
    assert (
        fake_lf.experiment_calls[0]["name"] == DEFAULT_CONFLICTS_LANGFUSE_DATASET_NAME
    )
    assert (
        conflict_dataset_item_id(loaded.items[0])
        in fake_lf.datasets[DEFAULT_CONFLICTS_LANGFUSE_DATASET_NAME]
    )
    assert any(ev.name == "overall_state_accuracy" for ev in fake_lf.run_evaluations)

    md = render_conflicts_markdown_report(artifact)
    assert artifact.config.config_sha256 in md
    assert "state-techqa" in md
    assert "state-syn" in md
    assert "Macierz pomyłek (4 klasy)" in md
    assert "Ograniczenia danych syntetycznych" in md
    for marker in TECHQA_RAW_MARKERS:
        assert marker not in md
