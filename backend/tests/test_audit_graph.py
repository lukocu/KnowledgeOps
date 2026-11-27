"""Testy jednostkowe 4-etapowego grafu audytu z fałszywym modelem i stubem BM25."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable, RunnableLambda

from app.auditing.graph import (
    AuditProgressUpdate,
    build_audit_graph,
    initial_audit_state,
)
from app.auditing.schemas import (
    CaseContext,
    ClaimVerdictOutput,
    ExtractedClaim,
    ExtractOutput,
)
from app.retrieval import RetrievedChunk
from app.settings import Settings

pytestmark = pytest.mark.anyio


@dataclass
class RecordedCall:
    schema: str
    strict: bool | None
    messages: list[BaseMessage]


@dataclass
class AuditScript:
    extract: ExtractOutput
    verifies: list[ClaimVerdictOutput | BaseException] = field(default_factory=list)
    calls: list[RecordedCall] = field(default_factory=list)


class FakeAuditChatModel(BaseChatModel):
    """Fałszywy model czatu zwracający skryptowane wyjścia lub wyjątki."""

    script: AuditScript

    @property
    def _llm_type(self) -> str:
        return "fake-audit-chat"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise AssertionError("graf audytu ma używać wyłącznie with_structured_output")

    def with_structured_output(
        self, schema: Any, *, strict: bool | None = None, **kwargs: Any
    ) -> Runnable[LanguageModelInput, Any]:
        script = self.script

        def respond(messages: LanguageModelInput) -> Any:
            assert isinstance(messages, Sequence)
            script.calls.append(
                RecordedCall(
                    schema=schema.__name__,
                    strict=strict,
                    messages=list(messages),  # type: ignore[arg-type]
                )
            )
            if schema is ExtractOutput:
                return script.extract
            if schema is ClaimVerdictOutput:
                item = script.verifies.pop(0)
                if isinstance(item, BaseException):
                    raise item
                return item
            raise AssertionError(f"nieoczekiwany schemat: {schema}")

        return RunnableLambda(respond)


def _settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "database_url": "postgresql://unused:unused@127.0.0.1:5433/unused",
        "chunk_set_id": "cs-base",
        "synthetic_chunk_set_id": "synthetic@v1",
        "include_synthetic": True,
        "audit_k": 5,
        "audit_claim_concurrency": 2,
        "audit_max_claims": 12,
        "chat_timeout_s": 5,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _context() -> CaseContext:
    return CaseContext(
        problem="Connection pool exhausted under load.",
        environment="WebSphere 9.0 on Linux",
        solution="Increased maxConnections to 50 and restarted JVM.",
        constraints=["Production cluster"],
        missing_info=["Exact fix pack level"],
    )


def _chunk(
    *,
    rank: int = 1,
    chunk_id: str = "cs-base/doc-1/0",
    doc_id: str = "doc-1",
    title: str = "Connection Pool Tuning",
    text: str = "Set maxConnections to 50 and restart the JVM to apply changes.",
    score: float = 5.5,
    is_synthetic: bool = False,
) -> RetrievedChunk:
    return RetrievedChunk(
        rank=rank,
        score=score,
        chunk_id=chunk_id,
        doc_id=doc_id,
        title=title,
        headings=["Tuning"],
        text=text,
        snapshot_id="snap-1",
        is_synthetic=is_synthetic,
    )


async def test_audit_graph_full_happy_path_and_progress_callbacks() -> None:
    note = "Set maxConnections to 50. Restart the JVM to apply changes."
    hit = _chunk()
    script = AuditScript(
        extract=ExtractOutput(
            case_context=_context(),
            claims=[
                ExtractedClaim(
                    claim_label="Increase maxConnections",
                    claim_text="Set maxConnections to 50.",
                    source_excerpt="Set maxConnections to 50.",
                    search_query="maxConnections 50",
                ),
                ExtractedClaim(
                    claim_label="Restart JVM",
                    claim_text="Restart the JVM to apply changes.",
                    source_excerpt="Restart the JVM to apply changes.",
                    search_query="restart JVM apply changes",
                ),
            ],
        ),
        verifies=[
            ClaimVerdictOutput(
                reasoning="Passage explicitly recommends maxConnections 50.",
                verdict="supported",
                scope_relation="same_scope",
                scope_note=None,
                evidence_chunk_id=hit.chunk_id,
                evidence_quote="Set maxConnections to 50",
            ),
            ClaimVerdictOutput(
                reasoning="Passage confirms restarting JVM applies changes.",
                verdict="supported",
                scope_relation="same_scope",
                scope_note=None,
                evidence_chunk_id=hit.chunk_id,
                evidence_quote="restart the JVM to apply changes.",
            ),
        ],
    )

    progress: list[AuditProgressUpdate] = []
    retrieve_calls: list[tuple[str, str, bool, int]] = []

    async def on_progress(update: AuditProgressUpdate) -> None:
        progress.append(update)

    async def stub_retrieve(
        query: str, chunk_set_id: str, include_synthetic: bool, k: int
    ) -> tuple[list[str], list[RetrievedChunk]]:
        retrieve_calls.append((query, chunk_set_id, include_synthetic, k))
        return [chunk_set_id, "synthetic@v1"], [hit]

    settings = _settings()
    graph = build_audit_graph(
        chat_model=FakeAuditChatModel(script=script),
        settings=settings,
        retrieve_fn=stub_retrieve,
        on_progress=on_progress,
    )

    final_state = await graph.ainvoke(
        initial_audit_state(
            case_description="Pool errors in logs",
            resolution_note=note,
            settings=settings,
        )
    )

    assert final_state["note_verdict"] == "full"
    assert final_state["chunk_set_ids"] == ["cs-base", "synthetic@v1"]
    assert len(final_state["claims"]) == 2
    assert [c.verdict for c in final_state["claims"]] == ["supported", "supported"]
    assert final_state["claims"][0].source_start == 0
    assert final_state["claims"][0].source_end == len("Set maxConnections to 50.")
    assert final_state["claims"][0].evidence[0]["supports_claim"] is True
    assert final_state["claims"][0].checked_docs[0]["document_id"] == "doc-1"

    assert [(c.schema, c.strict) for c in script.calls] == [
        ("ExtractOutput", True),
        ("ClaimVerdictOutput", True),
        ("ClaimVerdictOutput", True),
    ]
    assert len(retrieve_calls) == 2
    assert all(call[2] is True and call[3] == 5 for call in retrieve_calls)

    stages = [(p.stage, p.claims_total, p.claims_done) for p in progress]
    assert stages == [
        ("extracting", None, None),
        ("retrieving", 2, 0),
        ("retrieving", 2, 1),
        ("retrieving", 2, 2),
        ("verifying", 2, 0),
        ("verifying", 2, 1),
        ("verifying", 2, 2),
        ("aggregating", 2, 2),
    ]
    assert progress[1].case_context is not None
    assert progress[1].case_context["environment"] == "WebSphere 9.0 on Linux"


async def test_audit_graph_handles_zero_extracted_claims() -> None:
    script = AuditScript(extract=ExtractOutput(case_context=_context(), claims=[]))
    retrieve_called = False

    async def stub_retrieve(
        query: str, chunk_set_id: str, include_synthetic: bool, k: int
    ) -> tuple[list[str], list[RetrievedChunk]]:
        nonlocal retrieve_called
        retrieve_called = True
        return [chunk_set_id], []

    settings = _settings()
    graph = build_audit_graph(
        chat_model=FakeAuditChatModel(script=script),
        settings=settings,
        retrieve_fn=stub_retrieve,
    )

    final_state = await graph.ainvoke(
        initial_audit_state(
            case_description="Thanks, closing ticket.",
            resolution_note="Resolved by user.",
            settings=settings,
        )
    )

    assert final_state["note_verdict"] == "insufficient"
    assert final_state["claims"] == []
    assert retrieve_called is False
    assert [c.schema for c in script.calls] == ["ExtractOutput"]


async def test_audit_graph_isolates_single_claim_llm_error_and_timeout() -> None:
    note = "Step A works. Step B fails. Step C times out."
    hit = _chunk(text="Step A works as documented in section 1.")
    script = AuditScript(
        extract=ExtractOutput(
            case_context=_context(),
            claims=[
                ExtractedClaim(
                    claim_label="Step A",
                    claim_text="Step A works.",
                    source_excerpt="Step A works.",
                    search_query="Step A",
                ),
                ExtractedClaim(
                    claim_label="Step B",
                    claim_text="Step B fails.",
                    source_excerpt="Step B fails.",
                    search_query="Step B",
                ),
                ExtractedClaim(
                    claim_label="Step C",
                    claim_text="Step C times out.",
                    source_excerpt="Step C times out.",
                    search_query="Step C",
                ),
            ],
        ),
        verifies=[
            ClaimVerdictOutput(
                reasoning="Directly supported.",
                verdict="supported",
                scope_relation="same_scope",
                scope_note=None,
                evidence_chunk_id=hit.chunk_id,
                evidence_quote="Step A works as documented",
            ),
            RuntimeError("upstream 502"),
            TimeoutError(),
        ],
    )

    async def stub_retrieve(
        query: str, chunk_set_id: str, include_synthetic: bool, k: int
    ) -> tuple[list[str], list[RetrievedChunk]]:
        return [chunk_set_id], [hit]

    # Konkurencyjność=1 zapewnia deterministyczną kolejność zdejmowania z kolejki.
    settings = _settings(audit_claim_concurrency=1)
    graph = build_audit_graph(
        chat_model=FakeAuditChatModel(script=script),
        settings=settings,
        retrieve_fn=stub_retrieve,
    )

    final_state = await graph.ainvoke(
        initial_audit_state(
            case_description="Case",
            resolution_note=note,
            settings=settings,
        )
    )

    claims = final_state["claims"]
    assert final_state["note_verdict"] == "partial"
    assert [c.verdict for c in claims] == ["supported", "insufficient", "insufficient"]

    assert claims[0].error is None
    assert claims[1].error == "Nie udało się zweryfikować tezy z powodu błędu modelu."
    assert "upstream 502" not in claims[1].error
    assert claims[1].evidence[0]["chunk_id"] == hit.chunk_id
    assert claims[1].evidence[0]["supports_claim"] is False

    assert claims[2].error == "Przekroczono limit czasu weryfikacji tezy."
    assert claims[2].evidence[0]["chunk_id"] == hit.chunk_id
    assert claims[2].evidence[0]["supports_claim"] is False


async def test_audit_graph_degrades_different_scope_contradiction() -> None:
    hit = _chunk(text="Version 8.5 uses maxConnections=20.")
    script = AuditScript(
        extract=ExtractOutput(
            case_context=_context(),
            claims=[
                ExtractedClaim(
                    claim_label="Set maxConnections",
                    claim_text="Set maxConnections to 50 on v9.0.",
                    source_excerpt="maxConnections to 50",
                    search_query="maxConnections",
                )
            ],
        ),
        verifies=[
            ClaimVerdictOutput(
                reasoning="Value differs, but passage is for v8.5.",
                verdict="contradicted",
                scope_relation="different_scope",
                scope_note="Doc is for v8.5, note is for v9.0.",
                evidence_chunk_id=hit.chunk_id,
                evidence_quote="Version 8.5 uses maxConnections=20.",
            )
        ],
    )

    async def stub_retrieve(
        query: str, chunk_set_id: str, include_synthetic: bool, k: int
    ) -> tuple[list[str], list[RetrievedChunk]]:
        return [chunk_set_id], [hit]

    settings = _settings()
    graph = build_audit_graph(
        chat_model=FakeAuditChatModel(script=script),
        settings=settings,
        retrieve_fn=stub_retrieve,
    )

    final_state = await graph.ainvoke(
        initial_audit_state(
            case_description="Case",
            resolution_note="Set maxConnections to 50 on v9.0.",
            settings=settings,
        )
    )

    assert final_state["note_verdict"] == "insufficient"
    assert final_state["claims"][0].verdict == "insufficient"
    assert final_state["claims"][0].scope_note == "Doc is for v8.5, note is for v9.0."


async def test_audit_graph_truncates_max_claims_and_inherits_synthetic() -> None:
    synth_hit = _chunk(
        chunk_id="synthetic@v1/syn-doc/0",
        doc_id="syn-doc",
        title="Synthetic Policy",
        text="Claim 1 is contradicted by the synthetic policy.",
        is_synthetic=True,
    )
    script = AuditScript(
        extract=ExtractOutput(
            case_context=_context(),
            claims=[
                ExtractedClaim(
                    claim_label=f"Claim {i}",
                    claim_text=f"Claim {i} text.",
                    source_excerpt=f"Claim {i} text.",
                    search_query=f"claim {i}",
                )
                for i in range(1, 5)
            ],
        ),
        verifies=[
            ClaimVerdictOutput(
                reasoning="Directly contradicted by synthetic doc.",
                verdict="contradicted",
                scope_relation="same_scope",
                scope_note=None,
                evidence_chunk_id=synth_hit.chunk_id,
                evidence_quote="Claim 1 is contradicted by the synthetic policy.",
            ),
            ClaimVerdictOutput(
                reasoning="Not covered.",
                verdict="insufficient",
                scope_relation="unclear",
                scope_note=None,
                evidence_chunk_id=None,
                evidence_quote=None,
            ),
        ],
    )

    observed_include_synthetic: list[bool] = []

    async def stub_retrieve(
        query: str, chunk_set_id: str, include_synthetic: bool, k: int
    ) -> tuple[list[str], list[RetrievedChunk]]:
        observed_include_synthetic.append(include_synthetic)
        return [chunk_set_id], [synth_hit]

    settings = _settings(
        audit_max_claims=2,
        audit_claim_concurrency=1,
        include_synthetic=False,
    )
    graph = build_audit_graph(
        chat_model=FakeAuditChatModel(script=script),
        settings=settings,
        retrieve_fn=stub_retrieve,
    )

    final_state = await graph.ainvoke(
        initial_audit_state(
            case_description="Case",
            resolution_note="Claim 1 text. Claim 2 text. Claim 3 text. Claim 4 text.",
            settings=settings,
        )
    )

    assert len(final_state["claims"]) == 2
    assert observed_include_synthetic == [False, False]
    assert final_state["note_verdict"] == "contradiction"
    assert final_state["claims"][0].evidence[0]["is_synthetic"] is True
    assert final_state["claims"][0].checked_docs[0]["is_synthetic"] is True


async def test_audit_graph_skips_verify_llm_when_no_retrieval_hits() -> None:
    script = AuditScript(
        extract=ExtractOutput(
            case_context=_context(),
            claims=[
                ExtractedClaim(
                    claim_label="Unknown flag",
                    claim_text="Use --magic-flag.",
                    source_excerpt="Use --magic-flag.",
                    search_query="magic-flag",
                )
            ],
        ),
        verifies=[],
    )

    async def stub_retrieve(
        query: str, chunk_set_id: str, include_synthetic: bool, k: int
    ) -> tuple[list[str], list[RetrievedChunk]]:
        return [chunk_set_id], []

    settings = _settings()
    graph = build_audit_graph(
        chat_model=FakeAuditChatModel(script=script),
        settings=settings,
        retrieve_fn=stub_retrieve,
    )

    final_state = await graph.ainvoke(
        initial_audit_state(
            case_description="Case",
            resolution_note="Use --magic-flag.",
            settings=settings,
        )
    )

    assert final_state["note_verdict"] == "insufficient"
    assert len(final_state["claims"]) == 1
    assert final_state["claims"][0].verdict == "insufficient"
    assert final_state["claims"][0].evidence == []
    assert final_state["claims"][0].checked_docs == []
    assert [c.schema for c in script.calls] == ["ExtractOutput"]
