"""Testy runnera ewaluacji, kontraktu Langfuse 5.2.0 i trybu DB (Faza 3)."""

import asyncio
import inspect
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

import psycopg
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
from psycopg import AsyncConnection

from app.answering.model import JudgeModelInfo
from app.answering.schemas import (
    ClaimVerdict,
    DraftClaim,
    DraftOutput,
    VerifyOutput,
)
from app.db import AsyncPool, create_pool
from app.evals.dataset import DatasetMetadata, EvalItem, LoadedDataset
from app.evals.judge import (
    CitationJudgeOutput,
    CitationJudgeVerdict,
    ReferenceAgreementOutput,
)
from app.evals.langfuse_eval import RUN_EXPERIMENT_ASYNC_KWARGS, dataset_item_id
from app.evals.runner import (
    LangfuseNotConfiguredError,
    run_abstention_eval,
)
from app.retrieval import ChunkSetReproInfo, RetrievedChunk, get_chunk_set_repro_info
from app.settings import Settings
from tests.answering.fakes import Script, ScriptedChatModel
from tests.evals.fakes import DelayedResponse, FakeJudgeChatModel
from tests.techqa.helpers import CHUNK_SET_ID, REVISION, SNAPSHOT_ID


class _UnusedPool:
    """Atrapa puli dla testów jednostkowych, gdy `search_bm25` jest zamockowany."""

    def connection(self, **kwargs: Any) -> Any:
        del kwargs
        raise AssertionError("nie oczekiwano połączenia z bazą")


class _AsyncContextStub:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, *args: object) -> None:
        return None


class _DummyPool:
    """Pula atrapa zwracająca puste połączenie (używana z monkeypatch `search_bm25`)."""

    def connection(self, **kwargs: Any) -> _AsyncContextStub:
        del kwargs
        return _AsyncContextStub()


class _SlowDraftChatModel(BaseChatModel):
    """Model czatu, który zawiesza się na `delay_s` przy `draft` (test deadline)."""

    delay_s: float = 0.2
    calls: int = 0

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
        model = self

        def sync_fn(messages: LanguageModelInput) -> Any:
            del messages
            raise AssertionError("oczekiwano ainvoke")

        async def async_fn(messages: LanguageModelInput) -> Any:
            del messages
            model.calls += 1
            await asyncio.sleep(model.delay_s)
            return DraftOutput(claims=[])

        return RunnableLambda(sync_fn, afunc=async_fn)


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
    """Lekka atrapa klienta Langfuse 5.2.0 zgodna z wywołaniami `langfuse_eval.py`."""

    def __init__(
        self, *, pre_existing_items: list[_FakeDatasetItem] | None = None
    ) -> None:
        self.datasets: dict[str, dict[str, _FakeDatasetItem]] = {}
        if pre_existing_items is not None:
            self.datasets["knowledgeops/abstention-eval"] = {
                item.id: item for item in pre_existing_items
            }
        self.created_datasets: list[str] = []
        self.synced_item_ids: list[str] = []
        self.experiment_calls: list[dict[str, Any]] = []
        self.item_evaluations: list[list[Evaluation]] = []
        self.run_evaluations: list[Evaluation] = []
        self.flushed = False

    def get_dataset(self, name: str, **kwargs: Any) -> _FakeDataset:
        del kwargs
        if name not in self.datasets:
            raise NotFoundError(body={"message": "not found"})
        return _FakeDataset(name=name, items=list(self.datasets[name].values()))

    def create_dataset(
        self, *, name: str, description: str | None = None, metadata: Any = None
    ) -> None:
        del description, metadata
        self.created_datasets.append(name)
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
        self.synced_item_ids.append(id)
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
                "data_ids": [item.id for item in data],
                "composite_evaluator": composite_evaluator,
                "max_concurrency": max_concurrency,
                "metadata": metadata,
            }
        )
        item_results: list[ExperimentItemResult] = []
        for ds_item in data:
            output = await task(item=ds_item)
            evals: list[Evaluation] = []
            for evaluator in evaluators:
                ev = evaluator(
                    input=ds_item.input,
                    output=output,
                    expected_output=ds_item.expected_output,
                    metadata=ds_item.metadata,
                )
                if inspect.isawaitable(ev):
                    ev = await ev
                if isinstance(ev, list):
                    evals.extend(ev)
                else:
                    evals.append(ev)
            self.item_evaluations.append(evals)
            item_results.append(
                ExperimentItemResult(
                    item=cast(Any, ds_item),
                    output=output,
                    evaluations=evals,
                    trace_id=f"trace-{ds_item.id}",
                    experiment_id="exp-test-42",
                )
            )

        run_evals: list[Evaluation] = []
        for run_ev in run_evaluators:
            res = run_ev(item_results=item_results)
            if inspect.isawaitable(res):
                res = await res
            if isinstance(res, list):
                run_evals.extend(res)
            else:
                run_evals.append(res)
        self.run_evaluations = run_evals

        return ExperimentResult(
            name=name,
            run_name=run_name,
            description=description,
            item_results=item_results,
            run_evaluations=run_evals,
            experiment_id="exp-test-42",
            experiment_url="https://cloud.langfuse.com/experiments/exp-test-42",
        )


def _make_settings(
    monkeypatch: pytest.MonkeyPatch, *, deadline_s: float = 5.0
) -> Settings:
    for var in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    return Settings(
        database_url="postgresql://x/y",
        chunk_set_id="techqa@rev/sections-v1",
        chat_model="gpt-5-mini",
        chat_timeout_s=5.0,
        answer_deadline_s=deadline_s,
    )


def _sample_repro() -> ChunkSetReproInfo:
    return ChunkSetReproInfo(
        snapshot_id="techqa@rev",
        revision="rev1234567",
        chunk_set_id="techqa@rev/sections-v1",
        variant="sections-v1",
        config_sha256="a" * 64,
        state_sha256="b" * 64,
    )


def _sample_dataset(items: Sequence[EvalItem]) -> LoadedDataset:
    return LoadedDataset(
        metadata=DatasetMetadata(
            schema_version=1,
            snapshot_id="techqa@rev",
            train_json_sha256="c" * 64,
            split_seed=20261125,
            dev_ratio=0.3,
            excluded_conflict_ids=[],
            total_labeled=len(items),
            ambiguous_count=0,
            active_count=len(items),
        ),
        items=list(items),
    )


def _sample_items() -> list[EvalItem]:
    return [
        EvalItem(
            question_id="Q1",
            split="dev",
            original_is_impossible=False,
            canonical_doc_id="doc_1",
            verified_label="answerable_in_corpus",
            question="How to restart service?",
            answer="Run systemctl restart.",
            doc_ids=["doc_1"],
        ),
        EvalItem(
            question_id="Q2",
            split="dev",
            original_is_impossible=True,
            canonical_doc_id=None,
            verified_label="verified_unanswerable",
            question="What is the enterprise pricing?",
            answer="",
            doc_ids=[],
        ),
    ]


def test_langfuse_run_experiment_async_signature_contract() -> None:
    """Kontrakt sygnatury: argumenty z `langfuse_eval.py` istnieją w SDK 5.2.0."""
    sig = inspect.signature(Langfuse._run_experiment_async)
    for kwarg in RUN_EXPERIMENT_ASYNC_KWARGS:
        assert kwarg in sig.parameters, f"brak parametru {kwarg!r} w Langfuse SDK"


@pytest.mark.anyio
async def test_missing_langfuse_keys_fails_fast_before_any_llm_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _make_settings(monkeypatch)
    chat_script = Script()
    chat_model = ScriptedChatModel(script=chat_script)
    judge_model = FakeJudgeChatModel()

    with pytest.raises(LangfuseNotConfiguredError, match="--no-langfuse"):
        await run_abstention_eval(
            dataset=_sample_dataset(_sample_items()),
            settings=settings,
            pool=cast(AsyncPool, _UnusedPool()),
            split="dev",
            use_langfuse=True,
            chat_model=chat_model,
            judge_model=judge_model,
            repro_info=_sample_repro(),
        )

    assert chat_script.calls == []
    assert judge_model.calls == []


@pytest.mark.anyio
async def test_timeout_marks_item_failed_and_excludes_from_denominators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _make_settings(monkeypatch, deadline_s=0.05)

    async def _fake_search(
        conn: Any, query: str, *, chunk_set_id: str, k: int
    ) -> list[RetrievedChunk]:
        del conn, query, chunk_set_id, k
        return [
            RetrievedChunk(
                rank=1,
                score=1.0,
                chunk_id="c1",
                doc_id="doc_1",
                title="Doc 1",
                headings=[],
                text="Run systemctl restart to recover.",
            )
        ]

    monkeypatch.setattr("app.answering.nodes.search_bm25", _fake_search)

    slow_model = _SlowDraftChatModel(delay_s=0.25)
    judge_model = FakeJudgeChatModel()

    artifact = await run_abstention_eval(
        dataset=_sample_dataset(_sample_items()[:1]),
        settings=settings,
        pool=cast(AsyncPool, _DummyPool()),
        split="dev",
        use_langfuse=False,
        chat_model=slow_model,
        judge_model=judge_model,
        repro_info=_sample_repro(),
    )

    assert len(artifact.items) == 1
    item = artifact.items[0]
    assert item.outcome == "failed"
    assert item.error is not None and "TimeoutError" in item.error
    assert artifact.summary.n_total == 1
    assert artifact.summary.n_failed == 1
    assert artifact.summary.n_evaluated == 0
    assert artifact.summary.false_refusal_rate is None
    assert artifact.summary.latency_p50_ms is None
    assert artifact.summary.latency_p95_ms is None
    assert judge_model.calls == []


@pytest.mark.anyio
async def test_local_and_langfuse_modes_produce_identical_metrics_and_filter_split(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _make_settings(monkeypatch)
    chunk_text = "Run systemctl restart to recover the service."

    async def _fake_search(
        conn: Any, query: str, *, chunk_set_id: str, k: int
    ) -> list[RetrievedChunk]:
        del conn, chunk_set_id, k
        if "restart" in query.lower():
            return [
                RetrievedChunk(
                    rank=1,
                    score=2.5,
                    chunk_id="c1",
                    doc_id="doc_1",
                    title="Doc 1",
                    headings=["Ops"],
                    text=chunk_text,
                )
            ]
        return []

    monkeypatch.setattr("app.answering.nodes.search_bm25", _fake_search)
    flushed_calls: list[bool] = []
    monkeypatch.setattr(
        "app.evals.langfuse_eval.flush_traces", lambda: flushed_calls.append(True)
    )
    monkeypatch.setattr("app.evals.runner.make_trace_handler", lambda _s: None)

    def _make_models() -> tuple[ScriptedChatModel, FakeJudgeChatModel]:
        script = Script(
            drafts=[
                DraftOutput(
                    claims=[
                        DraftClaim(
                            text="Restart with systemctl.",
                            code=None,
                            chunk_id="c1",
                            quote="Run systemctl restart",
                        )
                    ]
                )
            ],
            verifies=[
                VerifyOutput(
                    verdicts=[
                        ClaimVerdict(
                            claim_index=0,
                            reasoning="Directly stated.",
                            verdict="supported",
                        )
                    ]
                )
            ],
        )
        judge = FakeJudgeChatModel(
            responses=[
                DelayedResponse(
                    delay_s=0.0,
                    value=CitationJudgeOutput(
                        verdicts=[
                            CitationJudgeVerdict(
                                claim_index=0,
                                reasoning="Supported by quote.",
                                verdict="supported",
                            )
                        ]
                    ),
                ),
                ReferenceAgreementOutput(
                    reasoning="Matches reference.", verdict="full"
                ),
            ]
        )
        return ScriptedChatModel(script=script), judge

    items = _sample_items()
    judge_info = JudgeModelInfo(
        model="gpt-5-judge", reasoning_effort="low", is_fallback_to_chat_model=False
    )

    chat_local, judge_local = _make_models()
    local_artifact = await run_abstention_eval(
        dataset=_sample_dataset(items),
        settings=settings,
        pool=cast(AsyncPool, _DummyPool()),
        split="dev",
        concurrency=1,
        use_langfuse=False,
        chat_model=chat_local,
        judge_model=judge_local,
        judge_model_info=judge_info,
        repro_info=_sample_repro(),
    )

    assert local_artifact.langfuse_run_id is None
    assert local_artifact.langfuse_run_url is None

    # Pre-existing item z innego splitu ("test") nie może trafić do `data` eksperymentu.
    fake_lf = _FakeLangfuseClient(
        pre_existing_items=[
            _FakeDatasetItem(
                id="abstention_test_Q999",
                input={
                    "question_id": "Q999",
                    "question": "Other split",
                    "split": "test",
                },
                expected_output={},
                metadata={"split": "test"},
            )
        ]
    )
    chat_lf, judge_lf = _make_models()
    lf_artifact = await run_abstention_eval(
        dataset=_sample_dataset(items),
        settings=settings,
        pool=cast(AsyncPool, _DummyPool()),
        split="dev",
        concurrency=1,
        use_langfuse=True,
        chat_model=chat_lf,
        judge_model=judge_lf,
        judge_model_info=judge_info,
        langfuse_client=cast(Langfuse, fake_lf),
        repro_info=_sample_repro(),
    )

    assert lf_artifact.langfuse_run_id == "exp-test-42"
    assert (
        lf_artifact.langfuse_run_url
        == "https://cloud.langfuse.com/experiments/exp-test-42"
    )
    assert flushed_calls == [True]
    assert len(fake_lf.experiment_calls) == 1
    assert fake_lf.experiment_calls[0]["data_ids"] == [
        dataset_item_id(items[0]),
        dataset_item_id(items[1]),
    ]
    assert "abstention_test_Q999" not in fake_lf.experiment_calls[0]["data_ids"]

    # Porównanie metryk jakości (bez zmiennych latency_p50_ms / latency_p95_ms).
    for field_name in (
        "n_total",
        "n_evaluated",
        "n_failed",
        "n_answered",
        "n_abstained",
        "n_unanswerable_eval",
        "abstention_accuracy",
        "n_answerable_eval",
        "false_refusal_rate",
        "citation_invariants_pass_rate",
        "citation_support_claim_rate",
        "citation_support_answer_rate",
        "reference_agreement_counts",
        "reference_agreement_mean",
        "abstention_reasons",
        "n_judge_failed",
    ):
        assert getattr(lf_artifact.summary, field_name) == getattr(
            local_artifact.summary, field_name
        ), f"rozbieżność dla {field_name}"

    assert lf_artifact.summary.abstention_accuracy == 1.0
    assert lf_artifact.summary.false_refusal_rate == 0.0
    assert lf_artifact.summary.citation_invariants_pass_rate == 1.0
    assert lf_artifact.summary.citation_support_claim_rate == 1.0
    assert lf_artifact.summary.reference_agreement_mean == 1.0

    run_eval_names = {ev.name for ev in fake_lf.run_evaluations}
    assert {
        "abstention_accuracy",
        "false_refusal_rate",
        "citation_invariants_pass_rate",
        "citation_support_claim_rate",
        "reference_agreement_avg",
        "latency_p95_ms",
        "failed_count",
    }.issubset(run_eval_names)


@pytest.mark.db
@pytest.mark.anyio
async def test_get_chunk_set_repro_info_reads_hashes_from_db(
    async_imported_conn: AsyncConnection,
) -> None:
    repro = await get_chunk_set_repro_info(async_imported_conn, CHUNK_SET_ID)

    assert repro.snapshot_id == SNAPSHOT_ID
    assert repro.revision == REVISION
    assert repro.chunk_set_id == CHUNK_SET_ID
    assert repro.variant == "sections-v1"
    assert len(repro.config_sha256) == 64
    assert repro.state_sha256 is not None and len(repro.state_sha256) == 64

    with pytest.raises(LookupError):
        await get_chunk_set_repro_info(async_imported_conn, "nieznany/zestaw")


@pytest.mark.db
@pytest.mark.anyio
async def test_runner_executes_against_mini_snapshot_on_selector_loop(
    imported_conn: psycopg.Connection,
    temp_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = imported_conn.execute(
        "SELECT id, doc_id, text FROM chunks"
        " WHERE chunk_set_id = %s ORDER BY id LIMIT 1",
        (CHUNK_SET_ID,),
    ).fetchone()
    assert row is not None
    chunk_id, doc_id, chunk_text = row
    words = [
        cleaned
        for token in chunk_text.split()
        if len(cleaned := token.strip(".,:;()[]\"'")) >= 5
    ]
    assert words
    query_term = " ".join(words[:3])
    quote = chunk_text[: min(40, len(chunk_text))].strip()

    for var in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    settings = Settings(
        database_url=temp_database,
        chunk_set_id=CHUNK_SET_ID,
        chat_model="gpt-5-mini",
        answer_k=20,
        answer_deadline_s=10.0,
    )

    items = [
        EvalItem(
            question_id="DB_Q_ANS",
            split="dev",
            original_is_impossible=False,
            canonical_doc_id=doc_id,
            verified_label="answerable_in_corpus",
            question=query_term,
            answer=quote,
            doc_ids=[doc_id],
        ),
        EvalItem(
            question_id="DB_Q_UNANS",
            split="dev",
            original_is_impossible=True,
            canonical_doc_id=None,
            verified_label="verified_unanswerable",
            question="zzzzzz_nonexistent_token_99999",
            answer="",
            doc_ids=[],
        ),
    ]
    dataset = LoadedDataset(
        metadata=DatasetMetadata(
            schema_version=1,
            snapshot_id=SNAPSHOT_ID,
            train_json_sha256="d" * 64,
            split_seed=20261125,
            dev_ratio=0.3,
            excluded_conflict_ids=[],
            total_labeled=2,
            ambiguous_count=0,
            active_count=2,
        ),
        items=items,
    )

    script = Script(
        drafts=[
            DraftOutput(
                claims=[
                    DraftClaim(
                        text="Zacytowana informacja z dokumentu.",
                        code=None,
                        chunk_id=chunk_id,
                        quote=quote,
                    )
                ]
            )
        ],
        verifies=[
            VerifyOutput(
                verdicts=[
                    ClaimVerdict(
                        claim_index=0,
                        reasoning="Fragment potwierdza tezę.",
                        verdict="supported",
                    )
                ]
            )
        ],
    )
    chat_model = ScriptedChatModel(script=script)
    judge_model = FakeJudgeChatModel(
        responses=[
            CitationJudgeOutput(
                verdicts=[
                    CitationJudgeVerdict(
                        claim_index=0,
                        reasoning="Cytat wspiera tezę.",
                        verdict="supported",
                    )
                ]
            ),
            ReferenceAgreementOutput(reasoning="Zgodne.", verdict="full"),
        ]
    )

    pool = create_pool(temp_database)
    async with pool:
        artifact = await run_abstention_eval(
            dataset=dataset,
            settings=settings,
            pool=pool,
            split="dev",
            concurrency=1,
            use_langfuse=False,
            chat_model=chat_model,
            judge_model=judge_model,
        )

    assert artifact.config.repro_info.snapshot_id == SNAPSHOT_ID
    assert artifact.config.repro_info.state_sha256 is not None
    assert artifact.summary.n_total == 2
    assert artifact.summary.n_evaluated == 2
    assert artifact.summary.n_failed == 0
    assert artifact.summary.abstention_accuracy == 1.0
    assert artifact.summary.false_refusal_rate == 0.0
    assert artifact.summary.citation_invariants_pass_rate == 1.0
    assert artifact.summary.citation_support_claim_rate == 1.0
    assert artifact.summary.reference_agreement_mean == 1.0
    assert artifact.items[1].abstention_reason == "no_hits"
