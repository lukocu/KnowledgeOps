"""Testy jednostkowe wykrywania konfliktu, strażnika zakresu i składania A vs B."""

import pytest

from app.answering.nodes import (
    QuotedClaim,
    compose_answer,
    compose_conflict_result,
    locate_quote,
    resolve_conflict_type,
    select_conflict_sides,
)
from app.answering.schemas import (
    AnsweredResult,
    Citation,
    ConflictCheckOutput,
    ConflictComparisonOutput,
    ConflictType,
    DraftClaim,
    ScopeRelation,
)
from app.retrieval import RetrievedChunk


def _chunk(
    rank: int,
    doc_id: str,
    text: str,
    *,
    snapshot_id: str = "techqa@rev",
    is_synthetic: bool = False,
    doc_date: str | None = None,
    product_version: str | None = None,
    audience: str | None = None,
    chunk_id: str | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        rank=rank,
        score=10.0 - rank,
        chunk_id=chunk_id or f"{snapshot_id}/sections-v1/{doc_id}/0",
        doc_id=doc_id,
        title=f"Title {doc_id}",
        headings=["Section A"],
        text=text,
        snapshot_id=snapshot_id,
        is_synthetic=is_synthetic,
        doc_date=doc_date,
        product_version=product_version,
        audience=audience,
    )


def _quoted(
    chunk: RetrievedChunk,
    quote: str,
    index: int,
    text: str,
    *,
    code: str | None = None,
) -> QuotedClaim:
    span = locate_quote(chunk.text, quote)
    assert span is not None
    return QuotedClaim(
        draft_index=index,
        claim=DraftClaim(text=text, code=code, chunk_id=chunk.chunk_id, quote=quote),
        quote_start=span[0],
        quote_end=span[1],
    )


@pytest.mark.parametrize(
    ("scope_relation", "ver_a", "ver_b", "aud_a", "aud_b", "expected"),
    [
        # Ten sam zakres i zgodne metadane -> contradiction.
        ("same_scope", "WAS 8.5", "WAS 8.5", "admins", "admins", "contradiction"),
        ("same_scope", "  WAS   8.5 ", "was 8.5", None, None, "contradiction"),
        ("same_scope", None, None, None, None, "contradiction"),
        # Różne wersje produktu -> nigdy contradiction (US-03).
        ("same_scope", "WAS 8.5", "WAS 9.0", None, None, "different_recommendations"),
        (
            "same_scope",
            "WAS 8.5",
            "WAS 9.0",
            "admins",
            "admins",
            "different_recommendations",
        ),
        # Jedna strona ma konkretną wersję, druga nieznaną -> different_recommendations.
        ("same_scope", "WAS 8.5", None, None, None, "different_recommendations"),
        ("same_scope", None, "WAS 9.0", None, None, "different_recommendations"),
        # Różni odbiorcy lub jeden nieustalony -> different_recommendations.
        (
            "same_scope",
            None,
            None,
            "platform team",
            "IBM customers",
            "different_recommendations",
        ),
        ("same_scope", None, None, "platform team", None, "different_recommendations"),
        ("same_scope", None, None, None, "platform team", "different_recommendations"),
        # Brak same_scope z modelu -> different_recommendations mimo zgodnych pól.
        (
            "different_scope",
            "WAS 8.5",
            "WAS 8.5",
            "admins",
            "admins",
            "different_recommendations",
        ),
        (
            "unknown_scope",
            "WAS 8.5",
            "WAS 8.5",
            "admins",
            "admins",
            "different_recommendations",
        ),
        (None, "WAS 8.5", "WAS 8.5", "admins", "admins", "different_recommendations"),
    ],
)
def test_resolve_conflict_type_matrix(
    scope_relation: ScopeRelation | None,
    ver_a: str | None,
    ver_b: str | None,
    aud_a: str | None,
    aud_b: str | None,
    expected: ConflictType,
) -> None:
    doc_a = _chunk(1, "docA", "text a", product_version=ver_a, audience=aud_a)
    doc_b = _chunk(2, "docB", "text b", product_version=ver_b, audience=aud_b)
    assert resolve_conflict_type(scope_relation, doc_a, doc_b) == expected


def test_compose_conflict_orders_sides_by_retrieval_rank_and_aligns_comparison() -> (
    None
):
    chunk_top = _chunk(
        1,
        "swg21648497",
        "Set nproc to 131072 for the WebSphere user on Linux.",
        snapshot_id="techqa@rev",
        is_synthetic=False,
        doc_date=None,
        product_version=None,
        audience=None,
    )
    chunk_syn = _chunk(
        2,
        "SYN-KB-0007",
        "Keep nproc at the RHEL default of 1024 for the WebSphere user.",
        snapshot_id="synthetic@v1",
        is_synthetic=True,
        doc_date="2019-03",
        product_version=None,
        audience="platform team, application servers",
    )
    q_top = _quoted(
        chunk_top,
        "Set nproc to 131072",
        0,
        "Set nproc to 131072.",
        code="ulimit -u 131072",
    )
    q_syn = _quoted(
        chunk_syn, "Keep nproc at the RHEL default of 1024", 1, "Keep nproc at 1024."
    )

    # Model zwrócił strony w odwrotnej kolejności (rank 2 jako A, rank 1 jako B).
    check = ConflictCheckOutput(
        reasoning="Documents recommend different nproc limits.",
        has_conflict=True,
        scope_relation="same_scope",
        side_a_claim_indices=[1],
        side_b_claim_indices=[0],
        conflicting_doc_ids=["SYN-KB-0007", "swg21648497"],
        summary="The sources recommend different nproc limits (131072 vs 1024).",
        comparison=ConflictComparisonOutput(
            value_label="nproc limit",
            side_a_value="1024",
            side_b_value="131072",
        ),
        refine_hint="Specify whether this is an internal platform server.",
    )

    result = compose_conflict_result(
        check, [q_top, q_syn], [chunk_top, chunk_syn], total_claims=3
    )

    assert result.outcome == "conflicting"
    # Strażnik zakresu degraduje same_scope przez różne `audience` (None vs zespół).
    assert result.conflict_type == "different_recommendations"
    assert result.omitted_claims == 1
    assert result.extra_conflicting_docs == 0
    assert result.refine_hint == "Specify whether this is an internal platform server."

    side_a, side_b = result.sides
    assert (side_a.label, side_a.doc_id, side_a.snapshot_id, side_a.is_synthetic) == (
        "A",
        "swg21648497",
        "techqa@rev",
        False,
    )
    assert (side_b.label, side_b.doc_id, side_b.snapshot_id, side_b.is_synthetic) == (
        "B",
        "SYN-KB-0007",
        "synthetic@v1",
        True,
    )
    assert side_a.code == "ulimit -u 131072"
    assert side_b.doc_date == "2019-03"
    assert side_b.audience == "platform team, application servers"

    # Dosłowna zgodność offsetów cytatów po obu stronach.
    assert chunk_top.text[side_a.quote_start : side_a.quote_end] == side_a.quote
    assert chunk_syn.text[side_b.quote_start : side_b.quote_end] == side_b.quote

    # Tabela porównania jest dopasowana do zamienionej kolejności stron A i B.
    rows = {row.kind: row for row in result.comparison_rows}
    assert rows["recommendation"].label == "nproc limit"
    assert rows["recommendation"].side_a == "131072"
    assert rows["recommendation"].side_b == "1024"
    assert rows["audience"].side_a is None
    assert rows["audience"].side_b == "platform team, application servers"
    assert rows["doc_date"].side_a is None
    assert rows["doc_date"].side_b == "2019-03"
    assert rows["product_version"].side_a is None
    assert rows["product_version"].side_b is None
    assert [c.chunk_id for c in result.checked_chunks] == [
        chunk_top.chunk_id,
        chunk_syn.chunk_id,
    ]


def test_three_or_more_conflicting_docs_sets_extra_conflicting_docs() -> None:
    c1 = _chunk(1, "doc1", "Set timeout to 30 seconds.", product_version="App 2.0")
    c2 = _chunk(2, "doc2", "Set timeout to 120 seconds.", product_version="App 2.0")
    c3 = _chunk(3, "doc3", "Set timeout to 300 seconds.", product_version="App 2.0")
    c4 = _chunk(4, "doc4", "Unrelated note about logging.", product_version="App 2.0")
    q1 = _quoted(c1, "Set timeout to 30 seconds.", 0, "Timeout is 30s.")
    q2 = _quoted(c2, "Set timeout to 120 seconds.", 1, "Timeout is 120s.")
    q3 = _quoted(c3, "Set timeout to 300 seconds.", 2, "Timeout is 300s.")

    check = ConflictCheckOutput(
        reasoning="Three documents give conflicting timeouts for App 2.0.",
        has_conflict=True,
        scope_relation="same_scope",
        side_a_claim_indices=[0],
        side_b_claim_indices=[1, 2],
        # Zawiera też zmyślony doc_id, który ma zostać zignorowany.
        conflicting_doc_ids=["doc1", "doc2", "doc3", "hallucinated_doc"],
        summary="Three docs disagree on timeout.",
        comparison=None,
        refine_hint=None,
    )

    result = compose_conflict_result(
        check, [q1, q2, q3], [c1, c2, c3, c4], total_claims=3
    )

    assert result.conflict_type == "contradiction"
    assert (result.sides[0].doc_id, result.sides[1].doc_id) == ("doc1", "doc2")
    assert result.extra_conflicting_docs == 1
    assert len(result.checked_chunks) == 4


@pytest.mark.parametrize(
    "check",
    [
        ConflictCheckOutput(
            reasoning="No conflict.",
            has_conflict=False,
            scope_relation=None,
            side_a_claim_indices=[],
            side_b_claim_indices=[],
            conflicting_doc_ids=[],
            summary=None,
            comparison=None,
            refine_hint=None,
        ),
        ConflictCheckOutput(
            reasoning="Out of range indices.",
            has_conflict=True,
            scope_relation="same_scope",
            side_a_claim_indices=[99],
            side_b_claim_indices=[100],
            conflicting_doc_ids=["doc1", "doc2"],
            summary="Bad indices",
            comparison=None,
            refine_hint=None,
        ),
        ConflictCheckOutput(
            reasoning="Both sides point to the same document.",
            has_conflict=True,
            scope_relation="same_scope",
            side_a_claim_indices=[0],
            side_b_claim_indices=[0],
            conflicting_doc_ids=["doc1"],
            summary="Same doc",
            comparison=None,
            refine_hint=None,
        ),
        ConflictCheckOutput(
            reasoning="Empty side B.",
            has_conflict=True,
            scope_relation="same_scope",
            side_a_claim_indices=[0],
            side_b_claim_indices=[],
            conflicting_doc_ids=["doc1", "doc2"],
            summary="Missing B",
            comparison=None,
            refine_hint=None,
        ),
    ],
)
def test_select_conflict_sides_falls_back_safely_on_invalid_output(
    check: ConflictCheckOutput,
) -> None:
    c1 = _chunk(1, "doc1", "First recommendation text.")
    c2 = _chunk(2, "doc2", "Second recommendation text.")
    q1 = _quoted(c1, "First recommendation", 0, "First.")
    q2 = _quoted(c2, "Second recommendation", 1, "Second.")
    assert select_conflict_sides(check, [q1, q2], [c1, c2]) is None


def test_historical_citation_without_new_metadata_fields_validates() -> None:
    legacy_payload = {
        "outcome": "answered",
        "claims": [{"text": "Restart service.", "code": None, "citation": 1}],
        "citations": [
            {
                "n": 1,
                "chunk_id": "techqa@rev/sections-v1/doc1/0",
                "doc_id": "doc1",
                "title": "Legacy Doc",
                "headings": ["Ops"],
                "claims": [
                    {
                        "claim_index": 0,
                        "quote": "Restart service.",
                        "quote_start": 0,
                        "quote_end": 16,
                    }
                ],
            }
        ],
        "checked_chunks": [],
        "omitted_claims": 0,
    }
    parsed = AnsweredResult.model_validate(legacy_payload)
    cit: Citation = parsed.citations[0]
    assert cit.snapshot_id is None
    assert cit.is_synthetic is False
    assert cit.doc_date is None
    assert cit.product_version is None


def test_compose_answer_populates_citation_metadata() -> None:
    c = _chunk(
        1,
        "SYN-KB-0007",
        "Keep nproc at 1024.",
        snapshot_id="synthetic@v1",
        is_synthetic=True,
        doc_date="2019-03",
        product_version="WAS 9.0",
    )
    q = _quoted(c, "Keep nproc at 1024.", 0, "Keep nproc at 1024.")
    result = compose_answer([q], [c], total_claims=1)
    cit = result.citations[0]
    assert cit.snapshot_id == "synthetic@v1"
    assert cit.is_synthetic is True
    assert cit.doc_date == "2019-03"
    assert cit.product_version == "WAS 9.0"
