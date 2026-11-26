"""Graf odpowiedzi na fałszywym modelu i mini-migawce (bez OpenAI i Langfuse)."""

from typing import Any

import pytest
from psycopg import AsyncConnection

from app.answering.graph import build_answer_graph, initial_state
from app.answering.nodes import AnswerState
from app.answering.schemas import (
    AbstainedResult,
    AnsweredResult,
    ClaimVerdict,
    ConflictCheckOutput,
    ConflictComparisonOutput,
    ConflictingResult,
    DraftClaim,
    DraftOutput,
    VerifyOutput,
)
from app.db import AsyncPool
from app.retrieval import RetrievedChunk, search_bm25
from app.settings import Settings
from tests.answering.fakes import Script, ScriptedChatModel
from tests.answering.helpers import run_graph
from tests.techqa.helpers import CHUNK_SET_ID

pytestmark = [pytest.mark.db, pytest.mark.anyio]

QUESTION = "information about this problem"


def verdict(index: int, value: str) -> ClaimVerdict:
    return ClaimVerdict.model_validate(
        {"claim_index": index, "reasoning": "r", "verdict": value}
    )


def claim_from(hit: RetrievedChunk, text: str = "A claim.") -> DraftClaim:
    """Teza z cytatem z początku fragmentu (dosłownie z jego tekstu)."""
    return DraftClaim(text=text, code=None, chunk_id=hit.chunk_id, quote=hit.text[:40])


async def top_hits(conn: AsyncConnection, count: int = 3) -> list[RetrievedChunk]:
    hits = await search_bm25(conn, QUESTION, chunk_set_id=CHUNK_SET_ID, k=8)
    assert len({h.chunk_id for h in hits}) >= count, "mini-migawka ma za mało trafień"
    return hits


async def run(
    pool: AsyncPool,
    settings: Settings,
    script: Script,
    question: str = QUESTION,
) -> tuple[list[dict[str, Any]], AnswerState]:
    graph = build_answer_graph(
        chat_model=ScriptedChatModel(script=script), pool=pool, settings=settings
    )
    return await run_graph(graph, initial_state(question, settings))


def stages(events: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(e["stage"], e["status"]) for e in events]


def no_conflict() -> ConflictCheckOutput:
    return ConflictCheckOutput(
        reasoning="Claims complement each other.",
        has_conflict=False,
        scope_relation=None,
        side_a_claim_indices=[],
        side_b_claim_indices=[],
        conflicting_doc_ids=[],
        summary=None,
        comparison=None,
        refine_hint=None,
    )


def answered(state: AnswerState) -> AnsweredResult:
    assert state["outcome"] == "answered"
    result = state["answer"]
    assert isinstance(result, AnsweredResult)
    return result


def conflicting(state: AnswerState) -> ConflictingResult:
    assert state["outcome"] == "conflicting"
    result = state["answer"]
    assert isinstance(result, ConflictingResult)
    return result


def abstained(state: AnswerState) -> AbstainedResult:
    assert state["outcome"] == "abstained"
    result = state["answer"]
    assert isinstance(result, AbstainedResult)
    return result


async def test_full_answer(
    async_imported_conn: AsyncConnection, pool: AsyncPool, answer_settings: Settings
) -> None:
    hits = await top_hits(async_imported_conn)
    two_docs = hits[0].doc_id != hits[1].doc_id
    script = Script(
        drafts=[
            DraftOutput(
                claims=[
                    claim_from(hits[0], "First."),
                    claim_from(hits[1], "Second."),
                ]
            )
        ],
        verifies=[
            VerifyOutput(verdicts=[verdict(0, "supported"), verdict(1, "supported")])
        ],
        conflicts=[no_conflict()] if two_docs else [],
    )
    events, state = await run(pool, answer_settings, script)

    result = answered(state)
    assert [(c.text, c.citation) for c in result.claims] == [
        ("First.", 1),
        ("Second.", 2),
    ]
    assert [c.chunk_id for c in result.citations] == [
        hits[0].chunk_id,
        hits[1].chunk_id,
    ]
    assert result.omitted_claims == 0
    assert [c.chunk_id for c in result.checked_chunks] == [h.chunk_id for h in hits]
    assert state["retrieved_chunk_ids"] == [h.chunk_id for h in hits]
    for citation in result.citations:
        hit = next(h for h in hits if h.chunk_id == citation.chunk_id)
        only = citation.claims[0]
        assert hit.text[only.quote_start : only.quote_end] == only.quote

    # Wywołania są strict; weryfikator nie widzi pytania.
    expected_calls = [
        ("DraftOutput", True),
        ("VerifyOutput", True),
    ]
    if two_docs:
        expected_calls.append(("ConflictCheckOutput", True))
    assert [(c.schema, c.strict) for c in script.calls] == expected_calls
    assert QUESTION in str(script.calls[0].messages[1].content)
    assert "Question:" not in str(script.calls[1].messages[1].content)
    assert "Claims to check" in str(script.calls[1].messages[1].content)


async def test_stage_events_in_order(
    async_imported_conn: AsyncConnection, pool: AsyncPool, answer_settings: Settings
) -> None:
    hits = await top_hits(async_imported_conn)
    script = Script(
        drafts=[DraftOutput(claims=[claim_from(hits[0])])],
        verifies=[VerifyOutput(verdicts=[verdict(0, "supported")])],
    )
    events, _ = await run(pool, answer_settings, script)

    assert stages(events) == [
        ("retrieve", "started"),
        ("retrieve", "done"),
        ("draft", "started"),
        ("draft", "done"),
        ("quote_check", "started"),
        ("quote_check", "done"),
        ("verify", "started"),
        ("verify", "done"),
        ("compose", "started"),
        ("compose", "done"),
    ]
    # Jeden dokument: dokładnie 2 wywołania modelu, bez detect_conflict.
    assert [(c.schema, c.strict) for c in script.calls] == [
        ("DraftOutput", True),
        ("VerifyOutput", True),
    ]
    by_stage = {(e["stage"], e["status"]): e["data"] for e in events}
    assert by_stage[("retrieve", "done")] == {"checked": len(hits)}
    assert by_stage[("verify", "done")] == {"supported": 1, "omitted": 0}
    assert by_stage[("retrieve", "started")] == {}


async def test_partial_answer_omits_unsupported_without_number_gaps(
    async_imported_conn: AsyncConnection, pool: AsyncPool, answer_settings: Settings
) -> None:
    hits = await top_hits(async_imported_conn)
    two_docs = hits[0].doc_id != hits[2].doc_id
    script = Script(
        drafts=[
            DraftOutput(
                claims=[
                    claim_from(hits[0], "One."),
                    claim_from(hits[1], "Two."),
                    claim_from(hits[2], "Three."),
                ]
            )
        ],
        verifies=[
            VerifyOutput(
                verdicts=[
                    verdict(0, "supported"),
                    verdict(1, "insufficient"),
                    verdict(2, "supported"),
                ]
            )
        ],
        conflicts=[no_conflict()] if two_docs else [],
    )
    events, state = await run(pool, answer_settings, script)

    result = answered(state)
    assert [(c.text, c.citation) for c in result.claims] == [("One.", 1), ("Three.", 2)]
    assert [(c.n, c.chunk_id) for c in result.citations] == [
        (1, hits[0].chunk_id),
        (2, hits[2].chunk_id),
    ]
    assert result.omitted_claims == 1
    verify_done = next(
        e for e in events if (e["stage"], e["status"]) == ("verify", "done")
    )
    assert verify_done["data"] == {"supported": 2, "omitted": 1}


async def test_two_claims_from_one_chunk_share_a_citation(
    async_imported_conn: AsyncConnection, pool: AsyncPool, answer_settings: Settings
) -> None:
    hits = await top_hits(async_imported_conn)
    two_docs = hits[0].doc_id != hits[1].doc_id
    first = DraftClaim(
        text="A", code=None, chunk_id=hits[0].chunk_id, quote=hits[0].text[:20]
    )
    second = DraftClaim(
        text="B", code="cmd", chunk_id=hits[0].chunk_id, quote=hits[0].text[-20:]
    )
    script = Script(
        drafts=[DraftOutput(claims=[first, claim_from(hits[1], "C"), second])],
        verifies=[
            VerifyOutput(
                verdicts=[
                    verdict(0, "supported"),
                    verdict(1, "supported"),
                    verdict(2, "supported"),
                ]
            )
        ],
        conflicts=[no_conflict()] if two_docs else [],
    )
    _, state = await run(pool, answer_settings, script)

    result = answered(state)
    assert [c.citation for c in result.claims] == [1, 2, 1]
    assert result.claims[2].code == "cmd"
    shared = result.citations[0]
    assert [c.claim_index for c in shared.claims] == [0, 2]
    assert shared.claims[0].quote == hits[0].text[:20]
    assert shared.claims[1].quote == hits[0].text[-20:]


async def test_abstains_with_no_hits_without_calling_the_model(
    pool: AsyncPool, answer_settings: Settings
) -> None:
    script = Script()
    events, state = await run(pool, answer_settings, script, question="zzqqxxnomatch")

    result = abstained(state)
    assert result.reason == "no_hits"
    assert result.checked_chunks == []
    assert result.omitted_claims == 0
    assert script.calls == []
    assert stages(events) == [
        ("retrieve", "started"),
        ("retrieve", "done"),
        ("abstain", "started"),
        ("abstain", "done"),
    ]
    assert events[1]["data"] == {"checked": 0}
    assert events[3]["data"] == {"reason": "no_hits"}


async def test_abstains_when_draft_has_no_claims(
    async_imported_conn: AsyncConnection, pool: AsyncPool, answer_settings: Settings
) -> None:
    hits = await top_hits(async_imported_conn)
    script = Script(drafts=[DraftOutput(claims=[])])
    events, state = await run(pool, answer_settings, script)

    result = abstained(state)
    assert result.reason == "no_claims"
    assert [c.chunk_id for c in result.checked_chunks] == [h.chunk_id for h in hits]
    assert result.omitted_claims == 0
    assert [c.schema for c in script.calls] == ["DraftOutput"]
    assert ("verify", "started") not in stages(events)
    assert stages(events)[-2:] == [("abstain", "started"), ("abstain", "done")]


async def test_abstains_when_no_claim_is_supported(
    async_imported_conn: AsyncConnection, pool: AsyncPool, answer_settings: Settings
) -> None:
    hits = await top_hits(async_imported_conn)
    script = Script(
        drafts=[DraftOutput(claims=[claim_from(hits[0]), claim_from(hits[1])])],
        verifies=[
            VerifyOutput(
                verdicts=[verdict(0, "insufficient"), verdict(1, "contradicted")]
            )
        ],
    )
    events, state = await run(pool, answer_settings, script)

    result = abstained(state)
    assert result.reason == "none_supported"
    assert result.omitted_claims == 2
    assert len(result.checked_chunks) == len(hits)
    assert ("compose", "started") not in stages(events)
    assert {e["stage"]: e["data"] for e in events}["abstain"] == {
        "reason": "none_supported"
    }


async def test_quote_outside_the_chunk_is_rejected_by_quote_check(
    async_imported_conn: AsyncConnection, pool: AsyncPool, answer_settings: Settings
) -> None:
    hits = await top_hits(async_imported_conn)
    invented = DraftClaim(
        text="Invented.",
        code=None,
        chunk_id=hits[0].chunk_id,
        quote="This sentence does not occur in any fixture.",
    )
    script = Script(
        drafts=[DraftOutput(claims=[invented, claim_from(hits[1], "Real.")])],
        # Weryfikator dostaje tylko ocalałą tezę (claim_index 1 ze szkicu).
        verifies=[VerifyOutput(verdicts=[verdict(1, "supported")])],
    )
    events, state = await run(pool, answer_settings, script)

    assert [(r.draft_index, r.reason) for r in state["rejected"]] == [
        (0, "quote_not_found")
    ]
    result = answered(state)
    assert [c.text for c in result.claims] == ["Real."]
    assert result.omitted_claims == 1
    verify_message = str(script.calls[1].messages[1].content)
    assert "Invented." not in verify_message
    assert "claim_index: 1" in verify_message
    done = next(
        e for e in events if (e["stage"], e["status"]) == ("quote_check", "done")
    )
    assert done["data"] == {"accepted": 1, "rejected": 1}


async def test_quote_from_other_retrieved_chunk_is_rejected(
    async_imported_conn: AsyncConnection, pool: AsyncPool, answer_settings: Settings
) -> None:
    hits = await top_hits(async_imported_conn)
    other = next(h for h in hits if h.text[:40] not in hits[0].text)
    crossed = DraftClaim(
        text="Crossed.", code=None, chunk_id=hits[0].chunk_id, quote=other.text[:40]
    )
    script = Script(drafts=[DraftOutput(claims=[crossed])])
    _, state = await run(pool, answer_settings, script)

    assert [r.reason for r in state["rejected"]] == ["quote_not_found"]
    assert abstained(state).reason == "none_supported"


async def test_chunk_id_outside_retrieved_is_rejected(
    async_imported_conn: AsyncConnection, pool: AsyncPool, answer_settings: Settings
) -> None:
    hits = await top_hits(async_imported_conn)
    stranger = DraftClaim(
        text="Stranger.",
        code=None,
        chunk_id=f"{CHUNK_SET_ID}/no-such-doc/0",
        quote=hits[0].text[:40],
    )
    script = Script(
        drafts=[DraftOutput(claims=[stranger, claim_from(hits[0], "Real.")])],
        verifies=[VerifyOutput(verdicts=[verdict(1, "supported")])],
    )
    _, state = await run(pool, answer_settings, script)

    assert [(r.draft_index, r.reason) for r in state["rejected"]] == [
        (0, "unknown_chunk")
    ]
    result = answered(state)
    assert [c.text for c in result.claims] == ["Real."]
    assert result.omitted_claims == 1


async def test_all_claims_rejected_skips_verification_and_abstains(
    async_imported_conn: AsyncConnection, pool: AsyncPool, answer_settings: Settings
) -> None:
    hits = await top_hits(async_imported_conn)
    invented = DraftClaim(
        text="Invented.", code=None, chunk_id=hits[0].chunk_id, quote="not in chunk"
    )
    script = Script(drafts=[DraftOutput(claims=[invented])])
    events, state = await run(pool, answer_settings, script)

    result = abstained(state)
    assert (result.reason, result.omitted_claims) == ("none_supported", 1)
    assert [c.schema for c in script.calls] == ["DraftOutput"]
    assert [s for s, _ in stages(events)] == [
        "retrieve",
        "retrieve",
        "draft",
        "draft",
        "quote_check",
        "quote_check",
        "abstain",
        "abstain",
    ]


async def test_contradicted_claim_is_omitted(
    async_imported_conn: AsyncConnection, pool: AsyncPool, answer_settings: Settings
) -> None:
    hits = await top_hits(async_imported_conn)
    script = Script(
        drafts=[
            DraftOutput(
                claims=[claim_from(hits[0], "Good."), claim_from(hits[1], "Opposite.")]
            )
        ],
        verifies=[
            VerifyOutput(verdicts=[verdict(0, "supported"), verdict(1, "contradicted")])
        ],
    )
    _, state = await run(pool, answer_settings, script)

    result = answered(state)
    assert [c.text for c in result.claims] == ["Good."]
    assert result.omitted_claims == 1
    assert [c.n for c in result.citations] == [1]


async def test_claim_without_verdict_is_omitted(
    async_imported_conn: AsyncConnection, pool: AsyncPool, answer_settings: Settings
) -> None:
    hits = await top_hits(async_imported_conn)
    script = Script(
        drafts=[DraftOutput(claims=[claim_from(hits[0]), claim_from(hits[1])])],
        verifies=[VerifyOutput(verdicts=[verdict(0, "supported")])],
    )
    _, state = await run(pool, answer_settings, script)

    result = answered(state)
    assert len(result.claims) == 1
    assert result.omitted_claims == 1


async def test_two_claims_from_same_doc_skip_detect_conflict(
    async_imported_conn: AsyncConnection, pool: AsyncPool, answer_settings: Settings
) -> None:
    hits = await top_hits(async_imported_conn)
    first = DraftClaim(
        text="First.", code=None, chunk_id=hits[0].chunk_id, quote=hits[0].text[:20]
    )
    second = DraftClaim(
        text="Second.", code=None, chunk_id=hits[0].chunk_id, quote=hits[0].text[-20:]
    )
    script = Script(
        drafts=[DraftOutput(claims=[first, second])],
        verifies=[
            VerifyOutput(verdicts=[verdict(0, "supported"), verdict(1, "supported")])
        ],
    )
    events, state = await run(pool, answer_settings, script)

    assert answered(state).claims[0].text == "First."
    assert [(c.schema, c.strict) for c in script.calls] == [
        ("DraftOutput", True),
        ("VerifyOutput", True),
    ]
    assert ("detect_conflict", "started") not in stages(events)


async def test_multi_doc_conflict_routes_to_compose_conflict(
    async_imported_conn: AsyncConnection, pool: AsyncPool, answer_settings: Settings
) -> None:
    hits = await top_hits(async_imported_conn)
    first = hits[0]
    second = next(h for h in hits[1:] if h.doc_id != first.doc_id)
    script = Script(
        drafts=[
            DraftOutput(
                claims=[
                    claim_from(first, "Use value A."),
                    claim_from(second, "Use value B."),
                ]
            )
        ],
        verifies=[
            VerifyOutput(verdicts=[verdict(0, "supported"), verdict(1, "supported")])
        ],
        conflicts=[
            ConflictCheckOutput(
                reasoning="Documents give mutually exclusive values.",
                has_conflict=True,
                scope_relation="same_scope",
                side_a_claim_indices=[0],
                side_b_claim_indices=[1],
                conflicting_doc_ids=[first.doc_id, second.doc_id],
                summary="Two documents disagree on the recommended value.",
                comparison=ConflictComparisonOutput(
                    value_label="setting",
                    side_a_value="value A",
                    side_b_value="value B",
                ),
                refine_hint="Specify the target environment.",
            )
        ],
    )
    events, state = await run(pool, answer_settings, script)

    result = conflicting(state)
    assert result.conflict_type == "contradiction"
    assert [c.schema for c in script.calls] == [
        "DraftOutput",
        "VerifyOutput",
        "ConflictCheckOutput",
    ]
    assert stages(events) == [
        ("retrieve", "started"),
        ("retrieve", "done"),
        ("draft", "started"),
        ("draft", "done"),
        ("quote_check", "started"),
        ("quote_check", "done"),
        ("verify", "started"),
        ("verify", "done"),
        ("detect_conflict", "started"),
        ("detect_conflict", "done"),
        ("compose", "started"),
        ("compose", "done"),
    ]
    side_a, side_b = result.sides
    assert (side_a.label, side_a.doc_id) == ("A", first.doc_id)
    assert (side_b.label, side_b.doc_id) == ("B", second.doc_id)
    assert first.text[side_a.quote_start : side_a.quote_end] == side_a.quote
    assert second.text[side_b.quote_start : side_b.quote_end] == side_b.quote


async def test_invalid_conflict_indices_fall_back_to_answered(
    async_imported_conn: AsyncConnection, pool: AsyncPool, answer_settings: Settings
) -> None:
    hits = await top_hits(async_imported_conn)
    first = hits[0]
    second = next(h for h in hits[1:] if h.doc_id != first.doc_id)
    script = Script(
        drafts=[
            DraftOutput(
                claims=[claim_from(first, "First."), claim_from(second, "Second.")]
            )
        ],
        verifies=[
            VerifyOutput(verdicts=[verdict(0, "supported"), verdict(1, "supported")])
        ],
        conflicts=[
            ConflictCheckOutput(
                reasoning="Bad indices returned by model.",
                has_conflict=True,
                scope_relation="same_scope",
                side_a_claim_indices=[42],
                side_b_claim_indices=[99],
                conflicting_doc_ids=[first.doc_id, second.doc_id],
                summary="Invalid conflict.",
                comparison=None,
                refine_hint=None,
            )
        ],
    )
    _, state = await run(pool, answer_settings, script)

    result = answered(state)
    assert [c.text for c in result.claims] == ["First.", "Second."]
