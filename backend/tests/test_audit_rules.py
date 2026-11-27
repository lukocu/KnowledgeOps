"""Testy jednostkowe deterministycznych reguł audytu i ładowania promptów."""

import pytest

from app.auditing.prompts import (
    PROMPT_NAMES,
    load_prompt,
    prompt_version,
    prompt_versions,
)
from app.auditing.rules import (
    aggregate_note_verdict,
    build_checked_docs,
    normalize_extracted_claims,
    resolve_claim_verdict,
)
from app.auditing.schemas import ClaimVerdict, ClaimVerdictOutput, ExtractedClaim
from app.retrieval import RetrievedChunk


def _chunk(
    *,
    rank: int = 1,
    chunk_id: str = "cs1/doc-1/0",
    doc_id: str = "doc-1",
    title: str = "IBM WebSphere Guide",
    text: str = "Set maxConnections to 50 before restarting the server.",
    score: float = 4.2,
    snapshot_id: str = "snap-1",
    is_synthetic: bool = False,
) -> RetrievedChunk:
    return RetrievedChunk(
        rank=rank,
        score=score,
        chunk_id=chunk_id,
        doc_id=doc_id,
        title=title,
        headings=["Configuration"],
        text=text,
        snapshot_id=snapshot_id,
        is_synthetic=is_synthetic,
    )


# --- aggregate_note_verdict --------------------------------------------------


@pytest.mark.parametrize(
    ("verdicts", "expected"),
    [
        ([], "insufficient"),
        (["insufficient"], "insufficient"),
        (["insufficient", "insufficient"], "insufficient"),
        (["supported"], "full"),
        (["supported", "supported"], "full"),
        (["supported", "insufficient"], "partial"),
        (["insufficient", "supported", "insufficient"], "partial"),
        (["contradicted"], "contradiction"),
        (["supported", "contradicted"], "contradiction"),
        (["supported", "insufficient", "contradicted"], "contradiction"),
    ],
)
def test_aggregate_note_verdict_covers_all_four_categories(
    verdicts: list[ClaimVerdict], expected: str
) -> None:
    assert aggregate_note_verdict(verdicts) == expected


# --- resolve_claim_verdict ---------------------------------------------------


def test_resolve_supported_claim_with_verbatim_quote() -> None:
    chunk = _chunk(
        text="To fix pool exhaustion,\nset maxConnections   to 50 and restart."
    )
    raw = ClaimVerdictOutput(
        reasoning="Passage directly states setting maxConnections to 50.",
        verdict="supported",
        scope_relation="same_scope",
        scope_note=None,
        evidence_chunk_id=chunk.chunk_id,
        evidence_quote="set maxConnections to 50 and restart.",
    )

    resolved = resolve_claim_verdict(raw, [chunk])

    assert resolved.verdict == "supported"
    assert resolved.degraded_reason is None
    assert len(resolved.evidence) == 1
    ev = resolved.evidence[0]
    assert ev.chunk_id == chunk.chunk_id
    assert ev.document_id == chunk.doc_id
    assert ev.source_doc_id == chunk.doc_id
    assert ev.chunk_set_id == "cs1"
    assert ev.supports_claim is True
    assert chunk.text[ev.quote_start : ev.quote_end] == ev.quote


def test_resolve_contradicted_same_scope_stays_contradicted() -> None:
    chunk = _chunk(text="Do not exceed maxConnections of 20 on version 9.0.")
    raw = ClaimVerdictOutput(
        reasoning="Document explicitly forbids values above 20 in version 9.0.",
        verdict="contradicted",
        scope_relation="same_scope",
        scope_note="Both refer to version 9.0.",
        evidence_chunk_id=chunk.chunk_id,
        evidence_quote="Do not exceed maxConnections of 20",
    )

    resolved = resolve_claim_verdict(raw, [chunk])

    assert resolved.verdict == "contradicted"
    assert resolved.degraded_reason is None
    assert resolved.scope_note == "Both refer to version 9.0."
    assert len(resolved.evidence) == 1
    assert resolved.evidence[0].supports_claim is False


def test_resolve_contradicted_different_scope_degrades_to_insufficient() -> None:
    chunk = _chunk(text="In version 8.5, maxConnections defaults to 20.")
    raw = ClaimVerdictOutput(
        reasoning="Passage mentions 20, but applies to version 8.5 instead of 9.0.",
        verdict="contradicted",
        scope_relation="different_scope",
        scope_note="Document covers v8.5; case note targets v9.0.",
        evidence_chunk_id=chunk.chunk_id,
        evidence_quote="In version 8.5, maxConnections defaults to 20.",
    )

    resolved = resolve_claim_verdict(raw, [chunk])

    assert resolved.verdict == "insufficient"
    assert resolved.degraded_reason == "different_scope"
    assert resolved.scope_note == "Document covers v8.5; case note targets v9.0."
    assert len(resolved.evidence) == 1
    assert resolved.evidence[0].supports_claim is False


@pytest.mark.parametrize(
    ("chunk_id", "quote", "expected_reason"),
    [
        (None, None, "missing_evidence"),
        ("cs1/doc-1/0", "", "missing_evidence"),
        ("cs1/unknown/0", "Set maxConnections to 50", "unknown_chunk"),
        ("cs1/doc-1/0", "Fabricated quote not in passage.", "quote_not_found"),
    ],
)
def test_resolve_supported_without_verified_quote_degrades_with_closest_chunk(
    chunk_id: str | None,
    quote: str | None,
    expected_reason: str,
) -> None:
    chunk = _chunk()
    raw = ClaimVerdictOutput(
        reasoning="Model claimed support without a valid quote.",
        verdict="supported",
        scope_relation="same_scope",
        scope_note=None,
        evidence_chunk_id=chunk_id,
        evidence_quote=quote,
    )

    resolved = resolve_claim_verdict(raw, [chunk])

    assert resolved.verdict == "insufficient"
    assert resolved.degraded_reason == expected_reason
    assert len(resolved.evidence) == 1
    assert resolved.evidence[0].chunk_id == chunk.chunk_id
    assert resolved.evidence[0].supports_claim is False


def test_resolve_contradicted_without_verified_quote_degrades() -> None:
    chunk = _chunk()
    raw = ClaimVerdictOutput(
        reasoning="Claim contradicts doc.",
        verdict="contradicted",
        scope_relation="same_scope",
        scope_note=None,
        evidence_chunk_id=chunk.chunk_id,
        evidence_quote="Quote that does not exist in chunk.",
    )

    resolved = resolve_claim_verdict(raw, [chunk])

    assert resolved.verdict == "insufficient"
    assert resolved.degraded_reason == "quote_not_found"
    assert len(resolved.evidence) == 1
    assert resolved.evidence[0].supports_claim is False


def test_resolve_contradicted_with_unclear_scope_degrades_to_insufficient() -> None:
    chunk = _chunk()
    raw = ClaimVerdictOutput(
        reasoning="Scope cannot be confirmed as identical.",
        verdict="contradicted",
        scope_relation="unclear",
        scope_note="Target product version is not stated in the note.",
        evidence_chunk_id=chunk.chunk_id,
        evidence_quote="Set maxConnections to 50",
    )

    resolved = resolve_claim_verdict(raw, [chunk])

    assert resolved.verdict == "insufficient"
    assert resolved.degraded_reason == "different_scope"
    assert resolved.scope_note == "Target product version is not stated in the note."
    assert len(resolved.evidence) == 1
    assert resolved.evidence[0].supports_claim is False


def test_resolve_insufficient_attaches_closest_chunk_when_candidates_exist() -> None:
    top = _chunk(rank=1, chunk_id="cs1/doc-top/0", doc_id="doc-top", score=7.5)
    second = _chunk(rank=2, chunk_id="cs1/doc-2/0", doc_id="doc-2", score=2.1)
    raw = ClaimVerdictOutput(
        reasoning="Passages do not mention this parameter.",
        verdict="insufficient",
        scope_relation="unclear",
        scope_note=None,
        evidence_chunk_id=None,
        evidence_quote=None,
    )

    resolved = resolve_claim_verdict(raw, [top, second])

    assert resolved.verdict == "insufficient"
    assert resolved.degraded_reason is None
    assert len(resolved.evidence) == 1
    assert resolved.evidence[0].chunk_id == top.chunk_id
    assert resolved.evidence[0].supports_claim is False


def test_resolve_insufficient_with_no_candidates_has_empty_evidence() -> None:
    raw = ClaimVerdictOutput(
        reasoning="No passages provided.",
        verdict="insufficient",
        scope_relation="unclear",
        scope_note=None,
        evidence_chunk_id=None,
        evidence_quote=None,
    )

    resolved = resolve_claim_verdict(raw, [])

    assert resolved.verdict == "insufficient"
    assert resolved.evidence == []


# --- normalize_extracted_claims & build_checked_docs -------------------------


def test_normalize_extracted_claims_matches_spans_truncates_and_falls_back() -> None:
    note = "We increased   maxConnections to 50. Then restarted the JVM."
    raw_claims = [
        ExtractedClaim(
            claim_label="",
            claim_text="",
            source_excerpt="increased maxConnections to 50.",
            search_query="maxConnections 50",
        ),
        ExtractedClaim(
            claim_label="Restart JVM",
            claim_text="Restart the JVM after changing the setting.",
            source_excerpt="Excerpt absent from note",
            search_query="restart JVM",
        ),
        ExtractedClaim(
            claim_label="Overflow claim",
            claim_text="Should be truncated by max_claims.",
            source_excerpt="Then restarted the JVM.",
            search_query="truncated",
        ),
    ]

    prepared = normalize_extracted_claims(raw_claims, note, max_claims=2)

    assert len(prepared) == 2
    first, second = prepared
    assert first.claim_index == 0
    assert first.source_start is not None
    assert first.source_end is not None
    assert note[first.source_start : first.source_end] == first.source_excerpt
    assert first.claim_text == "increased maxConnections to 50."
    assert first.claim_label == "increased maxConnections to 50."

    assert second.claim_index == 1
    assert second.source_start is None
    assert second.source_end is None
    assert second.source_excerpt == "Excerpt absent from note"


def test_build_checked_docs_deduplicates_by_document() -> None:
    c1 = _chunk(
        rank=1,
        chunk_id="synth@v1/syn-1/0",
        doc_id="syn-1",
        score=9.1,
        is_synthetic=True,
    )
    c2 = _chunk(
        rank=2,
        chunk_id="synth@v1/syn-1/1",
        doc_id="syn-1",
        score=6.4,
        is_synthetic=True,
    )
    c3 = _chunk(rank=3, chunk_id="cs1/doc-2/0", doc_id="doc-2", score=5.0)

    docs = build_checked_docs([c1, c2, c3])

    summary = [
        (d.document_id, d.chunk_id, d.chunk_set_id, d.is_synthetic) for d in docs
    ]
    assert summary == [
        ("syn-1", "synth@v1/syn-1/0", "synth@v1", True),
        ("doc-2", "cs1/doc-2/0", "cs1", False),
    ]


# --- prompts loader ----------------------------------------------------------


def test_audit_prompts_load_and_version_as_12_char_hex() -> None:
    versions = prompt_versions()
    assert set(versions) == set(PROMPT_NAMES)
    for name in PROMPT_NAMES:
        content = load_prompt(name)
        assert len(content.strip()) > 50
        ver = prompt_version(name)
        assert len(ver) == 12
        assert all(ch in "0123456789abcdef" for ch in ver)
        assert versions[name] == ver

    with pytest.raises(ValueError, match="nieznany prompt audytu"):
        load_prompt("nonexistent")
