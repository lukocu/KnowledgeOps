"""Testy jednostkowe quote_check i składania odpowiedzi (bez bazy i modelu)."""

from app.answering.nodes import (
    QuotedClaim,
    compose_answer,
    locate_quote,
    normalize_whitespace,
    quote_check,
    supported_claims,
)
from app.answering.schemas import ClaimVerdict, DraftClaim
from app.retrieval import RetrievedChunk


def make_chunk(rank: int, chunk_id: str, text: str) -> RetrievedChunk:
    return RetrievedChunk(
        rank=rank,
        score=10.0 - rank,
        chunk_id=chunk_id,
        doc_id=f"doc{rank}",
        title=f"Title {rank}",
        headings=["Section"],
        text=text,
    )


def make_claim(
    chunk_id: str, quote: str, text: str = "claim", code: str | None = None
) -> DraftClaim:
    return DraftClaim(text=text, code=code, chunk_id=chunk_id, quote=quote)


def verdict(index: int, value: str) -> ClaimVerdict:
    return ClaimVerdict.model_validate(
        {"claim_index": index, "reasoning": "r", "verdict": value}
    )


A = make_chunk(
    1, "c/a", "Set the variable\n   with   the  command.\n\nThen restart it."
)
B = make_chunk(2, "c/b", "Completely different text about queues.")


def test_normalize_collapses_whitespace_and_maps_positions() -> None:
    text = "  ab \n\t cd  "
    normalized, positions = normalize_whitespace(text)
    assert normalized == "ab cd"
    assert [text[p] for p in positions[:2]] == ["a", "b"]
    assert text[positions[2]].isspace()
    assert [text[p] for p in positions[3:]] == ["c", "d"]


def test_quote_with_different_whitespace_is_found() -> None:
    span = locate_quote(A.text, "variable with the command.")
    assert span is not None
    original = A.text[span[0] : span[1]]
    assert original == "variable\n   with   the  command."
    assert " ".join(original.split()) == "variable with the command."


def test_offsets_point_at_exactly_the_quote_in_the_original_text() -> None:
    text = "intro\n\n  Run   the\ttool  now.   Done."
    span = locate_quote(text, "the tool now.")
    assert span is not None
    assert text[span[0] : span[1]] == "the\ttool  now."


def test_quote_may_span_paragraph_break() -> None:
    span = locate_quote(A.text, "command. Then restart it.")
    assert span is not None
    assert A.text[span[0] : span[1]] == "command.\n\nThen restart it."


def test_quote_partly_outside_chunk_is_rejected() -> None:
    assert locate_quote(A.text, "Then restart it. And more") is None
    assert locate_quote(A.text, "Intro Set the variable") is None


def test_empty_or_blank_quote_is_rejected() -> None:
    assert locate_quote(A.text, "") is None
    assert locate_quote(A.text, "  \n ") is None


def test_quote_check_accepts_valid_and_records_offsets() -> None:
    quoted, rejected = quote_check([make_claim("c/a", "restart it.")], [A, B])
    assert not rejected
    assert len(quoted) == 1
    item = quoted[0]
    assert A.text[item.quote_start : item.quote_end] == "restart it."
    assert item.draft_index == 0


def test_quote_from_another_retrieved_chunk_is_rejected() -> None:
    claims = [make_claim("c/a", "text about queues")]  # cytat z B, nie z A
    quoted, rejected = quote_check(claims, [A, B])
    assert not quoted
    assert [(r.draft_index, r.reason) for r in rejected] == [(0, "quote_not_found")]


def test_unknown_chunk_id_is_rejected() -> None:
    claims = [make_claim("c/zzz", "restart it.")]
    quoted, rejected = quote_check(claims, [A, B])
    assert not quoted
    assert [(r.draft_index, r.reason) for r in rejected] == [(0, "unknown_chunk")]


def test_quote_check_keeps_draft_indexes_of_survivors() -> None:
    claims = [
        make_claim("c/a", "nope"),
        make_claim("c/b", "different text"),
        make_claim("c/a", "restart it."),
    ]
    quoted, rejected = quote_check(claims, [A, B])
    assert [q.draft_index for q in quoted] == [1, 2]
    assert [r.draft_index for r in rejected] == [0]


def _quoted(chunk: RetrievedChunk, quote: str, index: int, text: str) -> QuotedClaim:
    span = locate_quote(chunk.text, quote)
    assert span is not None
    return QuotedClaim(index, make_claim(chunk.chunk_id, quote, text), *span)


def test_supported_claims_ignores_other_verdicts_and_missing() -> None:
    quoted = [
        _quoted(A, "restart it.", 0, "x"),
        _quoted(B, "different text", 1, "y"),
        _quoted(A, "Set the variable", 2, "z"),
    ]
    verdicts = [verdict(0, "supported"), verdict(1, "contradicted")]
    assert [q.draft_index for q in supported_claims(quoted, verdicts)] == [0]


def test_supported_claims_first_verdict_wins_and_unknown_index_ignored() -> None:
    quoted = [_quoted(A, "restart it.", 0, "x")]
    verdicts = [
        verdict(0, "insufficient"),
        verdict(0, "supported"),
        verdict(9, "supported"),
    ]
    assert supported_claims(quoted, verdicts) == []


def test_compose_numbers_chunks_in_order_of_first_use_without_gaps() -> None:
    # Teza 0 odpadła, więc pierwsza pokazana pochodzi z B i dostaje numer 1.
    quoted = [
        _quoted(B, "different text", 1, "from B"),
        _quoted(A, "restart it.", 2, "from A"),
    ]
    result = compose_answer(quoted, [A, B], total_claims=3)
    assert [(c.text, c.citation) for c in result.claims] == [
        ("from B", 1),
        ("from A", 2),
    ]
    assert [(c.n, c.chunk_id) for c in result.citations] == [(1, "c/b"), (2, "c/a")]
    assert result.omitted_claims == 1


def test_two_claims_from_same_chunk_share_a_number_with_both_quotes() -> None:
    quoted = [
        _quoted(A, "Set the variable with the command.", 0, "first"),
        _quoted(B, "different text", 1, "other"),
        _quoted(A, "Then restart it.", 2, "second"),
    ]
    result = compose_answer(quoted, [A, B], total_claims=3)
    assert [c.citation for c in result.claims] == [1, 2, 1]
    first = result.citations[0]
    assert first.n == 1 and first.chunk_id == "c/a"
    assert [c.claim_index for c in first.claims] == [0, 2]
    for claim in first.claims:
        assert A.text[claim.quote_start : claim.quote_end] == claim.quote
    assert first.claims[0].quote == "Set the variable\n   with   the  command."
    assert first.claims[1].quote == "Then restart it."
    assert result.omitted_claims == 0


def test_compose_keeps_code_and_checked_chunks() -> None:
    claim = DraftClaim(text="t", code="run it", chunk_id="c/a", quote="restart it.")
    span = locate_quote(A.text, claim.quote)
    assert span is not None
    result = compose_answer([QuotedClaim(0, claim, *span)], [A, B], total_claims=1)
    assert result.claims[0].code == "run it"
    assert [c.chunk_id for c in result.checked_chunks] == ["c/a", "c/b"]
    assert [c.rank for c in result.checked_chunks] == [1, 2]
