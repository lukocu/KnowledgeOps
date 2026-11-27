"""Testy jednostkowe i bazodanowe dla listowania analiz (`store.py`, `session.py`)."""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import psycopg
import pytest
from fastapi import Request
from psycopg import AsyncConnection

from app.auditing.store import (
    AuditStatus,
    DecisionStatus,
    NewAuditClaim,
    _derive_problem_summary,
    complete_audit,
    compute_decision_status,
    create_audit,
    fail_audit,
    get_audit_for_session,
    list_audits_for_session,
    update_audit_progress,
    upsert_claim_decision,
)
from app.session import (
    COOKIE_NAME,
    MAX_TOKEN_LENGTH,
    get_optional_session,
    hash_token,
)


@pytest.fixture
async def async_conn(
    conn: psycopg.Connection, temp_database: str
) -> AsyncIterator[AsyncConnection]:
    """Połączenie async (autocommit) z bazą po migracjach."""
    del conn
    async with await AsyncConnection.connect(
        temp_database, autocommit=True
    ) as connection:
        yield connection


def _make_request(cookie_header: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if cookie_header is not None:
        headers.append((b"cookie", cookie_header.encode("latin-1")))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/audits",
            "headers": headers,
        }
    )


def _make_claims() -> list[NewAuditClaim]:
    return [
        NewAuditClaim(
            claim_index=0,
            claim_label="Port 8443",
            claim_text="Konfiguracja wymaga portu 8443.",
            source_excerpt="port 8443",
            search_query="port 8443",
            verdict="supported",
            rationale="Potwierdzone.",
        ),
        NewAuditClaim(
            claim_index=1,
            claim_label="Wyłączenie TLS",
            claim_text="Należy wyłączyć TLS 1.2.",
            source_excerpt="wyłączyć TLS",
            search_query="disable TLS",
            verdict="contradicted",
            rationale="Sprzeczne z dokumentacją.",
        ),
        NewAuditClaim(
            claim_index=2,
            claim_label="Restart węzła",
            claim_text="Wymagany jest restart węzła.",
            source_excerpt="restart węzła",
            search_query="node restart",
            verdict="insufficient",
            rationale="Brak źródeł.",
        ),
    ]


def test_compute_decision_status_cases() -> None:
    expected_cases: list[tuple[AuditStatus, int, int, DecisionStatus]] = [
        ("queued", 0, 0, "pending"),
        ("running", 3, 1, "pending"),
        ("failed", 3, 0, "not_applicable"),
        ("completed", 0, 0, "not_applicable"),
        ("completed", 3, 0, "pending"),
        ("completed", 3, 1, "in_progress"),
        ("completed", 3, 3, "saved"),
        ("completed", 3, 4, "saved"),
    ]
    for audit_status, claims_total, decisions_count, expected in expected_cases:
        assert (
            compute_decision_status(audit_status, claims_total, decisions_count)
            == expected
        )


def test_derive_problem_summary_prefers_case_context_problem() -> None:
    assert (
        _derive_problem_summary(
            {"problem": "  Błąd certyfikatu SSL  "}, "Opis sprawy z formularza"
        )
        == "Błąd certyfikatu SSL"
    )
    assert (
        _derive_problem_summary({"problem": "   "}, "Opis sprawy z formularza")
        == "Opis sprawy z formularza"
    )
    assert (
        _derive_problem_summary({"product": "WebSphere"}, "Opis sprawy")
        == "Opis sprawy"
    )
    assert _derive_problem_summary(None, "  Opis sprawy  ") == "Opis sprawy"


def test_get_optional_session_returns_hash_or_none_without_error() -> None:
    assert get_optional_session(_make_request()) is None
    assert get_optional_session(_make_request(f"{COOKIE_NAME}=")) is None

    too_long = "a" * (MAX_TOKEN_LENGTH + 1)
    assert get_optional_session(_make_request(f"{COOKIE_NAME}={too_long}")) is None

    token = "valid-session-token-123"
    assert get_optional_session(_make_request(f"{COOKIE_NAME}={token}")) == hash_token(
        token
    )


@pytest.mark.db
@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="brak DATABASE_URL")
def test_migration_0006_creates_partial_demo_index(conn: psycopg.Connection) -> None:
    row = conn.execute(
        "SELECT indexdef FROM pg_indexes"
        " WHERE schemaname = 'public' AND indexname = 'audits_demo_updated_idx'"
    ).fetchone()
    assert row is not None
    indexdef = str(row[0]).lower()
    assert "on public.audits" in indexdef
    assert "updated_at desc" in indexdef
    assert "where (is_demo = true)" in indexdef


@pytest.mark.db
@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="brak DATABASE_URL")
@pytest.mark.anyio
async def test_list_without_session_returns_only_demo_audits(
    async_conn: AsyncConnection,
) -> None:
    owner = hash_token("sesja-owner")
    demo_id = await create_audit(
        async_conn,
        session_hash=owner,
        case_ref="DEMO-01",
        case_description="Sprawa demo.",
        resolution_note="Notatka demo.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
        is_demo=True,
    )
    await complete_audit(
        async_conn,
        demo_id,
        claims=_make_claims(),
        note_verdict="contradiction",
        case_context={"problem": "Konflikt konfiguracji TLS"},
    )
    await create_audit(
        async_conn,
        session_hash=owner,
        case_ref="PRIV-01",
        case_description="Sprawa prywatna.",
        resolution_note="Notatka prywatna.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
        is_demo=False,
    )

    result = await list_audits_for_session(async_conn, None)

    assert [item.id for item in result.items] == [demo_id]
    assert result.demo_count == 1
    assert result.session_count == 0
    assert result.pending_count == 1
    assert result.in_progress_count == 0
    assert result.saved_count == 0
    assert result.next_pending_audit_id == demo_id
    assert result.next_pending_case_ref == "DEMO-01"

    item = result.items[0]
    assert item.is_demo is True
    assert item.problem_summary == "Konflikt konfiguracji TLS"
    assert item.claims_total == 3
    assert item.claims_supported == 1
    assert item.claims_contradicted == 1
    assert item.claims_insufficient == 1
    assert item.decisions_count == 0
    assert item.decision_status == "pending"


@pytest.mark.db
@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="brak DATABASE_URL")
@pytest.mark.anyio
async def test_list_isolates_private_audits_between_sessions(
    async_conn: AsyncConnection,
) -> None:
    session_a = hash_token("sesja-a")
    session_b = hash_token("sesja-b")

    demo_id = await create_audit(
        async_conn,
        session_hash=session_a,
        case_ref="DEMO-SHARED",
        case_description="Demo.",
        resolution_note="Notatka demo.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
        is_demo=True,
    )
    private_a = await create_audit(
        async_conn,
        session_hash=session_a,
        case_ref="A-01",
        case_description="Sprawa sesji A.",
        resolution_note="Notatka A.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
    )
    private_b = await create_audit(
        async_conn,
        session_hash=session_b,
        case_ref="B-01",
        case_description="Sprawa sesji B.",
        resolution_note="Notatka B.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
    )

    res_a = await list_audits_for_session(async_conn, session_a)
    res_b = await list_audits_for_session(async_conn, session_b)

    assert {item.id for item in res_a.items} == {demo_id, private_a}
    assert private_b not in {item.id for item in res_a.items}
    assert res_a.demo_count == 1
    assert res_a.session_count == 1

    assert {item.id for item in res_b.items} == {demo_id, private_b}
    assert private_a not in {item.id for item in res_b.items}
    assert res_b.demo_count == 1
    assert res_b.session_count == 1


@pytest.mark.db
@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="brak DATABASE_URL")
@pytest.mark.anyio
async def test_demo_decision_updates_status_and_last_activity_only_for_acting_session(
    async_conn: AsyncConnection,
) -> None:
    owner = hash_token("sesja-owner")
    session_a = hash_token("sesja-a")
    session_b = hash_token("sesja-b")

    demo_id = await create_audit(
        async_conn,
        session_hash=owner,
        case_ref="DEMO-DEC",
        case_description="Demo z decyzją.",
        resolution_note="Notatka demo.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
        is_demo=True,
    )
    await complete_audit(
        async_conn,
        demo_id,
        claims=_make_claims()[:2],
        note_verdict="partial",
    )
    base_ts = datetime(2026, 1, 10, 10, 0, 0, tzinfo=UTC)
    decision_ts = datetime(2026, 1, 12, 15, 30, 0, tzinfo=UTC)
    await async_conn.execute(
        "UPDATE audits SET created_at = %s, updated_at = %s WHERE id = %s",
        (base_ts, base_ts, demo_id),
    )

    stored = await get_audit_for_session(async_conn, demo_id, session_a)
    assert stored is not None
    await upsert_claim_decision(
        async_conn,
        audit_id=demo_id,
        claim_id=stored.claims[0].id,
        session_hash=session_a,
        decision="agree_with_system",
        justification="Zgodne z dokumentacją.",
        role_label="editor",
    )
    await async_conn.execute(
        "UPDATE audit_claim_decisions SET updated_at = %s"
        " WHERE audit_id = %s AND session_hash = %s",
        (decision_ts, demo_id, session_a),
    )

    res_a = await list_audits_for_session(async_conn, session_a)
    res_b = await list_audits_for_session(async_conn, session_b)
    res_anon = await list_audits_for_session(async_conn, None)

    item_a = res_a.items[0]
    assert item_a.decisions_count == 1
    assert item_a.decision_status == "in_progress"
    assert item_a.last_activity_at == decision_ts
    assert res_a.in_progress_count == 1
    assert res_a.pending_count == 0

    for other_res in (res_b, res_anon):
        other_item = other_res.items[0]
        assert other_item.decisions_count == 0
        assert other_item.decision_status == "pending"
        assert other_item.last_activity_at == base_ts
        assert other_res.pending_count == 1
        assert other_res.in_progress_count == 0


@pytest.mark.db
@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="brak DATABASE_URL")
@pytest.mark.anyio
async def test_priority_sorting_and_next_pending_selection(
    async_conn: AsyncConnection,
) -> None:
    session = hash_token("sesja-sort")

    async def _seed_audit(case_ref: str, *, ts: datetime, is_demo: bool = False) -> str:
        audit_id = await create_audit(
            async_conn,
            session_hash=session,
            case_ref=case_ref,
            case_description=f"Opis {case_ref}",
            resolution_note=f"Notatka {case_ref}",
            snapshot_id="techqa@v1",
            chunk_set_ids=["set-1"],
            config={},
            is_demo=is_demo,
        )
        await async_conn.execute(
            "UPDATE audits SET created_at = %s, updated_at = %s WHERE id = %s",
            (ts, ts, audit_id),
        )
        return audit_id

    # Grupa 2: saved (najnowszy znacznik czasu, ale trafia na koniec przez grupę 2)
    saved_id = await _seed_audit(
        "SAVED-NEWEST", ts=datetime(2026, 2, 10, 12, 0, tzinfo=UTC)
    )
    await complete_audit(
        async_conn, saved_id, claims=_make_claims()[:1], note_verdict="full"
    )
    saved_stored = await get_audit_for_session(async_conn, saved_id, session)
    assert saved_stored is not None
    await upsert_claim_decision(
        async_conn,
        audit_id=saved_id,
        claim_id=saved_stored.claims[0].id,
        session_hash=session,
        decision="agree_with_system",
        justification="Zatwierdzone.",
        role_label="editor",
    )
    await async_conn.execute(
        "UPDATE audits SET updated_at = %s WHERE id = %s",
        (datetime(2026, 2, 10, 12, 0, tzinfo=UTC), saved_id),
    )
    await async_conn.execute(
        "UPDATE audit_claim_decisions SET updated_at = %s WHERE audit_id = %s",
        (datetime(2026, 2, 10, 12, 5, tzinfo=UTC), saved_id),
    )

    # Grupa 2: failed (starszy niż saved)
    failed_id = await _seed_audit("FAILED", ts=datetime(2026, 2, 9, 12, 0, tzinfo=UTC))
    await fail_audit(async_conn, failed_id, error="Błąd")
    await async_conn.execute(
        "UPDATE audits SET updated_at = %s WHERE id = %s",
        (datetime(2026, 2, 9, 12, 0, tzinfo=UTC), failed_id),
    )

    # Grupa 1: queued (starszy) i running (nowszy)
    queued_id = await _seed_audit("QUEUED", ts=datetime(2026, 2, 8, 12, 0, tzinfo=UTC))
    running_id = await _seed_audit(
        "RUNNING", ts=datetime(2026, 2, 9, 12, 0, tzinfo=UTC)
    )
    await update_audit_progress(async_conn, running_id, stage="verifying")
    await async_conn.execute(
        "UPDATE audits SET updated_at = %s WHERE id = %s",
        (datetime(2026, 2, 9, 12, 0, tzinfo=UTC), running_id),
    )

    # Grupa 0: pending (starszy) i in_progress (nowsza aktywność przez decyzję)
    pending_id = await _seed_audit(
        "PENDING-OLD", ts=datetime(2026, 2, 1, 10, 0, tzinfo=UTC)
    )
    await complete_audit(
        async_conn, pending_id, claims=_make_claims()[:2], note_verdict="partial"
    )
    await async_conn.execute(
        "UPDATE audits SET updated_at = %s WHERE id = %s",
        (datetime(2026, 2, 1, 10, 0, tzinfo=UTC), pending_id),
    )

    in_progress_id = await _seed_audit(
        "IN-PROGRESS-ACTIVE", ts=datetime(2026, 2, 1, 8, 0, tzinfo=UTC)
    )
    await complete_audit(
        async_conn, in_progress_id, claims=_make_claims()[:2], note_verdict="partial"
    )
    await async_conn.execute(
        "UPDATE audits SET updated_at = %s WHERE id = %s",
        (datetime(2026, 2, 1, 8, 0, tzinfo=UTC), in_progress_id),
    )
    in_prog_stored = await get_audit_for_session(async_conn, in_progress_id, session)
    assert in_prog_stored is not None
    await upsert_claim_decision(
        async_conn,
        audit_id=in_progress_id,
        claim_id=in_prog_stored.claims[0].id,
        session_hash=session,
        decision="request_source_or_verify",
        justification="Wymaga doprecyzowania.",
        role_label="editor",
    )
    await async_conn.execute(
        "UPDATE audit_claim_decisions SET updated_at = %s WHERE audit_id = %s",
        (datetime(2026, 2, 5, 10, 0, tzinfo=UTC), in_progress_id),
    )

    result = await list_audits_for_session(async_conn, session)

    assert [item.id for item in result.items] == [
        in_progress_id,
        pending_id,
        running_id,
        queued_id,
        saved_id,
        failed_id,
    ]
    assert result.next_pending_audit_id == in_progress_id
    assert result.next_pending_case_ref == "IN-PROGRESS-ACTIVE"
    assert result.pending_count == 1
    assert result.in_progress_count == 1
    assert result.saved_count == 1


@pytest.mark.db
@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="brak DATABASE_URL")
@pytest.mark.anyio
async def test_filters_and_unfiltered_summary_counters(
    async_conn: AsyncConnection,
) -> None:
    session = hash_token("sesja-filtry")

    demo_id = await create_audit(
        async_conn,
        session_hash=session,
        case_ref="INC-100",
        case_description="Awaria puli połączeń DB2 w produkcji.",
        resolution_note="Zwiększono limit puli.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
        is_demo=True,
    )
    await complete_audit(
        async_conn,
        demo_id,
        claims=_make_claims()[:1],
        note_verdict="full",
        case_context={"problem": "Limit połączeń WebSphere"},
    )

    session_saved_id = await create_audit(
        async_conn,
        session_hash=session,
        case_ref="INC-200",
        case_description="Błąd certyfikatu klienta.",
        resolution_note="Wgrano nowy truststore.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
    )
    await complete_audit(
        async_conn,
        session_saved_id,
        claims=_make_claims()[:1],
        note_verdict="contradiction",
    )
    saved_stored = await get_audit_for_session(async_conn, session_saved_id, session)
    assert saved_stored is not None
    await upsert_claim_decision(
        async_conn,
        audit_id=session_saved_id,
        claim_id=saved_stored.claims[0].id,
        session_hash=session,
        decision="consider_doc_update",
        justification="Potrzebna aktualizacja dokumentacji.",
        role_label="editor",
    )

    session_in_progress_id = await create_audit(
        async_conn,
        session_hash=session,
        case_ref="INC-300",
        case_description="Problem z pamięcią heap JVM.",
        resolution_note="Zmieniono flagę Xmx.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
    )
    await complete_audit(
        async_conn,
        session_in_progress_id,
        claims=_make_claims()[:2],
        note_verdict="partial",
    )
    in_prog_stored = await get_audit_for_session(
        async_conn, session_in_progress_id, session
    )
    assert in_prog_stored is not None
    await upsert_claim_decision(
        async_conn,
        audit_id=session_in_progress_id,
        claim_id=in_prog_stored.claims[0].id,
        session_hash=session,
        decision="agree_with_system",
        justification="Częściowo potwierdzone.",
        role_label="editor",
    )

    # Filtr po source="demo" nie zmienia liczników pełnego zbioru.
    by_demo = await list_audits_for_session(async_conn, session, source="demo")
    assert [item.id for item in by_demo.items] == [demo_id]
    assert by_demo.demo_count == 1
    assert by_demo.session_count == 2
    assert by_demo.pending_count == 1
    assert by_demo.in_progress_count == 1
    assert by_demo.saved_count == 1
    assert by_demo.next_pending_audit_id in {demo_id, session_in_progress_id}

    by_session = await list_audits_for_session(async_conn, session, source="session")
    assert {item.id for item in by_session.items} == {
        session_saved_id,
        session_in_progress_id,
    }

    # Filtr po decision_status i note_verdict
    by_saved = await list_audits_for_session(
        async_conn, session, decision_status="saved"
    )
    assert [item.id for item in by_saved.items] == [session_saved_id]
    assert by_saved.pending_count == 1
    assert by_saved.in_progress_count == 1
    assert by_saved.saved_count == 1

    by_verdict = await list_audits_for_session(
        async_conn, session, note_verdict="partial"
    )
    assert [item.id for item in by_verdict.items] == [session_in_progress_id]

    # Filtr tekstowy `q` (case-insensitive: case_ref, problem_summary, case_description)
    by_ref = await list_audits_for_session(async_conn, session, q="inc-200")
    assert [item.id for item in by_ref.items] == [session_saved_id]

    by_summary = await list_audits_for_session(async_conn, session, q="WEBSPHERE")
    assert [item.id for item in by_summary.items] == [demo_id]

    by_desc = await list_audits_for_session(async_conn, session, q="db2")
    assert [item.id for item in by_desc.items] == [demo_id]

    # Pusty / białe znaki w `q` nie filtrują
    by_blank_q = await list_audits_for_session(async_conn, session, q="   ")
    assert len(by_blank_q.items) == 3

    # Brak dopasowania daje pustą listę, ale liczniki nadal pokazują cały zbiór
    no_match = await list_audits_for_session(async_conn, session, q="nie-istnieje-xyz")
    assert no_match.items == []
    assert no_match.demo_count == 1
    assert no_match.session_count == 2
    assert no_match.pending_count == 1
    assert no_match.in_progress_count == 1
    assert no_match.saved_count == 1
