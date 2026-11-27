"""Testy idempotentnego seedera przykładów demo (`import-demo-audits`)."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg.types.json import Jsonb

from app.answering.nodes import locate_quote
from app.auditing.demo_seed import (
    DEMO_AUDITS_PATH,
    DEMO_SESSION_HASH,
    DemoSeedError,
    _extract_quote_span,
    demo_audit_id,
    demo_claim_id,
    import_demo_audits,
    load_demo_audits,
)
from app.auditing.schemas import CaseContext, CheckedDoc, ClaimEvidence
from app.techqa.chunking import ChunkerConfig, chunk_document
from app.techqa.normalize import normalize_body

PILOT_SNAPSHOT_ID = "techqa@pilot-test"
PILOT_CHUNK_SET_ID = f"{PILOT_SNAPSHOT_ID}/sections-v1"

_PILOT_DOCS: dict[str, tuple[str, str]] = {
    "swg21648497": (
        "Recommended ulimit settings for WebSphere Application Server on Linux",
        (
            "PROBLEM(ABSTRACT)\n"
            "Native OutOfMemoryError on Linux when running WebSphere Application "
            "Server.\n\n"
            "RESOLVING THE PROBLEM\n"
            "WebSphere Application Server Support recommends setting ulimit -u "
            "(nproc) to 131072 on Linux systems so threads can be created safely.\n"
        ),
    ),
    "swg21675316": (
        "Netcool/Impact IPL Exit() behavior inside a user defined function",
        (
            "CAUSE\n"
            "Calling Exit() inside an IPL user defined function exits only the "
            "immediate function scope rather than the entire policy.\n\n"
            "ANSWER\n"
            "To stop the enclosing policy, set a flag variable and check it "
            "immediately after the user defined function returns.\n"
        ),
    ),
    "swg21996508": (
        "IBM Streams 4.1.1.1/4.1.1.2 jobs do not inherit .bashrc when run as service",
        (
            "ABSTRACT\n"
            "When IBM Streams 4.1.1.1 or 4.1.1.2 runs as a system service, "
            "submitted jobs do not inherit environment variables from .bashrc.\n\n"
            "PROBLEM SOLUTION\n"
            "Set required application environment variables directly on the "
            "instance by running streamtool setproperty with --application-ev.\n"
        ),
    ),
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _seed_pilot_corpus(
    conn: psycopg.Connection,
    *,
    doc_ids: tuple[str, ...] = ("swg21648497", "swg21675316", "swg21996508"),
) -> tuple[str, str]:
    config = ChunkerConfig()
    with conn.transaction():
        conn.execute(
            "INSERT INTO snapshots (id, source, revision, manifest)"
            " VALUES (%s, %s, %s, %s)",
            (PILOT_SNAPSHOT_ID, "test/pilot", "pilot-test", Jsonb({})),
        )
        conn.execute(
            "INSERT INTO chunk_sets (id, snapshot_id, variant, config, config_sha256,"
            " chunk_count, state_sha256) VALUES (%s, %s, %s, %s, %s, 0, NULL)",
            (
                PILOT_CHUNK_SET_ID,
                PILOT_SNAPSHOT_ID,
                config.variant,
                Jsonb({"variant": config.variant}),
                config.config_sha256(),
            ),
        )
        chunk_count = 0
        for doc_id in doc_ids:
            title, raw_body = _PILOT_DOCS[doc_id]
            text = normalize_body(raw_body)
            conn.execute(
                "INSERT INTO documents (snapshot_id, doc_id, canonical_doc_id, title,"
                " raw_text, raw_sha256, text, text_sha256, is_synthetic)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, false)",
                (
                    PILOT_SNAPSHOT_ID,
                    doc_id,
                    doc_id,
                    title,
                    raw_body,
                    _sha(raw_body),
                    text,
                    _sha(text),
                ),
            )
            for chunk in chunk_document(text, config):
                conn.execute(
                    "INSERT INTO chunks (id, chunk_set_id, snapshot_id, doc_id,"
                    " ordinal, headings, start_offset, end_offset, text, text_sha256)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        f"{PILOT_CHUNK_SET_ID}/{doc_id}/{chunk.ordinal}",
                        PILOT_CHUNK_SET_ID,
                        PILOT_SNAPSHOT_ID,
                        doc_id,
                        chunk.ordinal,
                        list(chunk.headings),
                        chunk.start,
                        chunk.end,
                        chunk.text,
                        _sha(chunk.text),
                    ),
                )
                chunk_count += 1
        conn.execute(
            "UPDATE chunk_sets SET chunk_count = %s WHERE id = %s",
            (chunk_count, PILOT_CHUNK_SET_ID),
        )
    return PILOT_SNAPSHOT_ID, PILOT_CHUNK_SET_ID


def test_demo_audits_json_is_complete_and_clean() -> None:
    specs = load_demo_audits(DEMO_AUDITS_PATH)
    assert [spec.case_ref for spec in specs] == [
        "SIM-P08",
        "SIM-P11",
        "SIM-P04",
        "SIM-P01",
    ]
    assert {spec.note_verdict for spec in specs} == {
        "contradiction",
        "insufficient",
        "partial",
        "full",
    }

    referenced_docs = {
        ev.doc_id
        for spec in specs
        for claim in spec.claims
        for ev in claim.evidence_specs
    }
    assert referenced_docs == {"swg21648497", "swg21675316", "swg21996508"}

    offsets = [spec.created_offset_minutes for spec in specs]
    assert offsets == sorted(offsets) and len(set(offsets)) == len(offsets)

    for spec in specs:
        for claim in spec.claims:
            assert locate_quote(spec.resolution_note, claim.source_excerpt) is not None
            for ev in claim.evidence_specs:
                for term in ev.anchor_terms:
                    assert len(term) <= 40

    raw_text = DEMO_AUDITS_PATH.read_text(encoding="utf-8")
    assert "TECHNOTE (TROUBLESHOOTING)" not in raw_text
    assert "PROBLEM(ABSTRACT)" not in raw_text


def test_extract_quote_span_returns_verbatim_substring() -> None:
    text = (
        "Introductory context about Linux limits. "
        "WebSphere Application Server Support recommends nproc of 131072 on Linux. "
        "Additional trailing notes."
    )
    start, end = _extract_quote_span(text, ["131072", "nproc"], max_chars=90)
    quote = text[start:end]
    assert 0 <= start < end <= len(text)
    assert len(quote) <= 90
    assert "131072" in quote
    assert quote == quote.strip()

    fb_start, fb_end = _extract_quote_span(text, ["nonexistent-term"], max_chars=50)
    assert 0 <= fb_start < fb_end <= len(text)
    assert text[fb_start:fb_end] == text[fb_start:fb_end].strip()


@pytest.mark.db
def test_import_demo_audits_is_idempotent_and_validates_evidence(
    conn: psycopg.Connection,
) -> None:
    snapshot_id, chunk_set_id = _seed_pilot_corpus(conn)

    first = import_demo_audits(conn, DEMO_AUDITS_PATH, chunk_set_id=chunk_set_id)
    second = import_demo_audits(conn, DEMO_AUDITS_PATH, chunk_set_id=chunk_set_id)

    assert first.snapshot_id == snapshot_id
    assert first.chunk_set_id == chunk_set_id
    assert first.audits_count == 4
    assert first.claims_count == 6
    assert first.comparison == "pierwszy import"
    assert second.comparison == "identyczny"
    assert first.state_sha256 == second.state_sha256

    assert conn.execute(
        "SELECT count(*) FROM audits WHERE is_demo = true AND session_hash = %s",
        (DEMO_SESSION_HASH,),
    ).fetchone() == (4,)
    assert conn.execute("SELECT count(*) FROM audit_claims").fetchone() == (6,)
    # 2 zdarzenia systemowe per audyt (audit_created, evaluation_completed).
    assert conn.execute("SELECT count(*) FROM audit_events").fetchone() == (8,)

    # Kolejność po created_at DESC odpowiada układowi z S5.
    ordered_refs = [
        row[0]
        for row in conn.execute(
            "SELECT case_ref FROM audits WHERE is_demo = true ORDER BY created_at DESC"
        ).fetchall()
    ]
    assert ordered_refs == ["SIM-P08", "SIM-P11", "SIM-P04", "SIM-P01"]

    # Walidacja case_context, evidence i checked_docs wobec modeli API i tekstu chunków.
    for row in conn.execute(
        "SELECT case_context FROM audits WHERE is_demo = true"
    ).fetchall():
        CaseContext.model_validate(row[0])

    claim_rows = conn.execute(
        "SELECT verdict, evidence, checked_docs FROM audit_claims"
    ).fetchall()
    assert len(claim_rows) == 6
    for verdict, raw_evidence, raw_checked in claim_rows:
        assert len(raw_evidence) >= 1
        assert len(raw_checked) >= 1
        for item in raw_evidence:
            ev = ClaimEvidence.model_validate(item)
            assert ev.supports_claim is (verdict == "supported")
            chunk_row = conn.execute(
                "SELECT text FROM chunks WHERE id = %s",
                (ev.chunk_id,),
            ).fetchone()
            assert chunk_row is not None
            chunk_text = str(chunk_row[0])
            assert chunk_text[ev.quote_start : ev.quote_end] == ev.quote
        for item in raw_checked:
            CheckedDoc.model_validate(item)


@pytest.mark.db
def test_reseed_preserves_session_decisions(conn: psycopg.Connection) -> None:
    _, chunk_set_id = _seed_pilot_corpus(conn)
    import_demo_audits(conn, DEMO_AUDITS_PATH, chunk_set_id=chunk_set_id)

    audit_id = demo_audit_id("sim-p08")
    claim_id = demo_claim_id("sim-p08", 0)
    session_hash = "a" * 64
    decision_id = str(uuid.uuid4())
    event_id = str(uuid.uuid4())

    with conn.transaction():
        conn.execute(
            "INSERT INTO audit_claim_decisions ("
            " id, audit_id, claim_id, session_hash, decision, justification, role_label"
            ") VALUES (%s, %s, %s, %s, 'agree_with_system', %s, 'editor')",
            (
                decision_id,
                audit_id,
                claim_id,
                session_hash,
                "Potwierdzono sprzeczność z dokumentem TechQA.",
            ),
        )
        conn.execute(
            "INSERT INTO audit_events ("
            " id, audit_id, claim_id, session_hash, event_type,"
            " actor_type, role_label, payload"
            ") VALUES (%s, %s, %s, %s, 'decision_saved', 'human', 'editor', %s)",
            (
                event_id,
                audit_id,
                claim_id,
                session_hash,
                Jsonb({"decision": "agree_with_system", "claim_index": 0}),
            ),
        )

    reseeded = import_demo_audits(conn, DEMO_AUDITS_PATH, chunk_set_id=chunk_set_id)
    assert reseeded.comparison == "identyczny"

    saved = conn.execute(
        "SELECT decision, justification, role_label"
        " FROM audit_claim_decisions"
        " WHERE claim_id = %s AND session_hash = %s",
        (claim_id, session_hash),
    ).fetchone()
    assert saved == (
        "agree_with_system",
        "Potwierdzono sprzeczność z dokumentem TechQA.",
        "editor",
    )

    human_events = conn.execute(
        "SELECT count(*) FROM audit_events"
        " WHERE audit_id = %s AND actor_type = 'human' AND session_hash = %s",
        (audit_id, session_hash),
    ).fetchone()
    assert human_events == (1,)


@pytest.mark.db
def test_missing_techqa_snapshot_raises_demo_seed_error(
    conn: psycopg.Connection,
) -> None:
    with pytest.raises(DemoSeedError, match="import-techqa"):
        import_demo_audits(
            conn,
            DEMO_AUDITS_PATH,
            chunk_set_id="techqa@missing/sections-v1",
        )


@pytest.mark.db
def test_missing_pilot_document_raises_demo_seed_error(
    conn: psycopg.Connection,
) -> None:
    _, chunk_set_id = _seed_pilot_corpus(conn, doc_ids=("swg21648497",))

    with pytest.raises(DemoSeedError, match="swg21675316") as exc_info:
        import_demo_audits(conn, DEMO_AUDITS_PATH, chunk_set_id=chunk_set_id)
    assert "import-techqa" in str(exc_info.value)


def test_load_demo_audits_rejects_wrong_version(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.json"
    bad_file.write_text(
        '{"version": "demo-audits@v999", "audits": []}',
        encoding="utf-8",
    )
    with pytest.raises(DemoSeedError):
        load_demo_audits(bad_file)
