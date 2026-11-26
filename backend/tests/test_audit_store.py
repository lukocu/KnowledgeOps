"""Testy migracji `0004_audits.sql` i repozytorium `app.auditing.store`."""

import os
import uuid
from collections.abc import AsyncIterator

import psycopg
import pytest
from psycopg import AsyncConnection

from app.auditing.store import (
    NewAuditClaim,
    complete_audit,
    create_audit,
    fail_audit,
    fail_orphaned_audits,
    get_audit_for_session,
    update_audit_progress,
)
from app.session import hash_token

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="brak DATABASE_URL"),
]


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


def test_migration_creates_audit_tables_and_indexes(conn: psycopg.Connection) -> None:
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
    }
    indexes = {
        row[0]
        for row in conn.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
        ).fetchall()
    }
    assert {"audits", "audit_claims"} <= tables
    assert {"audits_session_created_idx", "audit_claims_audit_idx"} <= indexes


@pytest.mark.anyio
async def test_audit_lifecycle_and_ordered_claims(async_conn: AsyncConnection) -> None:
    session = hash_token("sesja-wlasciciela")
    audit_id = await create_audit(
        async_conn,
        session_hash=session,
        case_ref="CASE-42",
        case_description="Użytkownik zgłasza błąd połączenia z serwerem.",
        resolution_note="Zmieniono port na 8443 i zrestartowano usługę.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1", "synthetic-1"],
        config={"chat_model": "gpt-test", "k": 8},
    )

    queued = await get_audit_for_session(async_conn, audit_id, session)
    assert queued is not None
    assert queued.status == "queued"
    assert queued.stage == "queued"
    assert queued.claims_total == 0
    assert queued.claims_done == 0
    assert queued.note_verdict is None
    assert queued.case_context is None
    assert queued.completed_at is None
    assert queued.claims == []
    assert queued.chunk_set_ids == ["set-1", "synthetic-1"]

    await update_audit_progress(async_conn, audit_id, stage="extracting")
    case_context = {"product": "WebSphere", "error_codes": ["CWPKI0022E"]}
    await update_audit_progress(
        async_conn,
        audit_id,
        stage="retrieving",
        claims_total=2,
        case_context=case_context,
    )
    await update_audit_progress(
        async_conn,
        audit_id,
        stage="verifying",
        claims_done=1,
    )

    running = await get_audit_for_session(async_conn, audit_id, session)
    assert running is not None
    assert running.status == "running"
    assert running.stage == "verifying"
    assert running.claims_total == 2
    assert running.claims_done == 1
    assert running.case_context == case_context

    # Celowo przekazujemy tezy w odwrotnej kolejności `claim_index`,
    # aby zweryfikować sortowanie przy odczycie.
    claims = [
        NewAuditClaim(
            claim_index=1,
            claim_label="Restart usługi",
            claim_text="Należy zrestartować usługę po zmianie konfiguracji.",
            source_excerpt="zrestartowano usługę",
            source_start=25,
            source_end=45,
            search_query="restart service after port change",
            verdict="insufficient",
            rationale="Brak dokumentu opisującego restart.",
            checked_docs=[{"doc_id": "doc-2", "title": "Porty"}],
        ),
        NewAuditClaim(
            claim_index=0,
            claim_label="Zmiana portu na 8443",
            claim_text="Konfiguracja wymaga portu 8443.",
            source_excerpt="Zmieniono port na 8443",
            source_start=0,
            source_end=22,
            search_query="configure port 8443",
            verdict="supported",
            rationale="Dokumentacja potwierdza port 8443.",
            scope_note="Dotyczy wersji 9.x.",
            evidence=[{"chunk_id": "set-1/doc-1/0", "quote": "Use port 8443"}],
            checked_docs=[{"doc_id": "doc-1", "title": "SSL config"}],
        ),
    ]
    await complete_audit(
        async_conn,
        audit_id,
        claims=claims,
        note_verdict="partial",
        trace_id="trace-123",
        duration_ms=1450,
    )

    done = await get_audit_for_session(async_conn, audit_id, session)
    assert done is not None
    assert done.status == "completed"
    assert done.stage == "completed"
    assert done.note_verdict == "partial"
    assert done.claims_total == 2
    assert done.claims_done == 2
    assert done.case_context == case_context
    assert done.trace_id == "trace-123"
    assert done.duration_ms == 1450
    assert done.completed_at is not None
    assert [c.claim_index for c in done.claims] == [0, 1]
    assert done.claims[0].verdict == "supported"
    assert done.claims[0].evidence == [
        {"chunk_id": "set-1/doc-1/0", "quote": "Use port 8443"}
    ]
    assert done.claims[1].verdict == "insufficient"


@pytest.mark.anyio
async def test_complete_audit_is_atomic_on_claim_error(
    async_conn: AsyncConnection,
) -> None:
    session = hash_token("sesja-atomowa")
    audit_id = await create_audit(
        async_conn,
        session_hash=session,
        case_description="Opis sprawy.",
        resolution_note="Notatka.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
    )
    await update_audit_progress(async_conn, audit_id, stage="aggregating")

    duplicate_claims = [
        NewAuditClaim(
            claim_index=0,
            claim_label="Teza A",
            claim_text="Teza A.",
            source_excerpt="Notatka.",
            search_query="query a",
            verdict="supported",
            rationale="OK",
        ),
        NewAuditClaim(
            claim_index=0,
            claim_label="Duplikat",
            claim_text="Duplikat.",
            source_excerpt="Notatka.",
            search_query="query b",
            verdict="supported",
            rationale="Duplikat indeksu",
        ),
    ]
    with pytest.raises(psycopg.errors.UniqueViolation):
        await complete_audit(
            async_conn,
            audit_id,
            claims=duplicate_claims,
            note_verdict="full",
        )

    unchanged = await get_audit_for_session(async_conn, audit_id, session)
    assert unchanged is not None
    assert unchanged.status == "running"
    assert unchanged.stage == "aggregating"
    assert unchanged.completed_at is None
    assert unchanged.claims == []


@pytest.mark.anyio
async def test_session_isolation_and_demo_visibility(
    async_conn: AsyncConnection,
) -> None:
    owner = hash_token("sesja-a")
    other = hash_token("sesja-b")

    private_id = await create_audit(
        async_conn,
        session_hash=owner,
        case_description="Sprawa prywatna.",
        resolution_note="Notatka prywatna.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
        is_demo=False,
    )
    demo_id = await create_audit(
        async_conn,
        session_hash=owner,
        case_description="Sprawa demo.",
        resolution_note="Notatka demo.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
        is_demo=True,
    )

    assert await get_audit_for_session(async_conn, private_id, owner) is not None
    assert await get_audit_for_session(async_conn, private_id, other) is None
    assert await get_audit_for_session(async_conn, private_id, None) is None

    assert await get_audit_for_session(async_conn, demo_id, owner) is not None
    assert await get_audit_for_session(async_conn, demo_id, other) is not None
    assert await get_audit_for_session(async_conn, demo_id, None) is not None

    assert await get_audit_for_session(async_conn, str(uuid.uuid4()), owner) is None
    assert await get_audit_for_session(async_conn, "nie-uuid", owner) is None


@pytest.mark.anyio
async def test_fail_audit_and_fail_orphaned_audits(
    async_conn: AsyncConnection,
) -> None:
    session = hash_token("sesja-bledy")
    queued_id = await create_audit(
        async_conn,
        session_hash=session,
        case_description="Kolejka.",
        resolution_note="Notatka 1.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
    )
    running_id = await create_audit(
        async_conn,
        session_hash=session,
        case_description="W toku.",
        resolution_note="Notatka 2.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
    )
    await update_audit_progress(async_conn, running_id, stage="verifying")

    completed_id = await create_audit(
        async_conn,
        session_hash=session,
        case_description="Zakończony.",
        resolution_note="Notatka 3.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
    )
    await complete_audit(
        async_conn,
        completed_id,
        claims=[],
        note_verdict="insufficient",
    )

    already_failed_id = await create_audit(
        async_conn,
        session_hash=session,
        case_description="Już błędny.",
        resolution_note="Notatka 4.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
    )
    await fail_audit(
        async_conn,
        already_failed_id,
        error="TimeoutError: model",
        trace_id="trace-err",
        duration_ms=900,
    )

    updated = await fail_orphaned_audits(async_conn, reason="Restart serwera")
    assert updated == 2

    q_row = await get_audit_for_session(async_conn, queued_id, session)
    r_row = await get_audit_for_session(async_conn, running_id, session)
    c_row = await get_audit_for_session(async_conn, completed_id, session)
    f_row = await get_audit_for_session(async_conn, already_failed_id, session)

    assert q_row is not None and q_row.status == "failed" and q_row.stage == "failed"
    assert q_row.error == "Restart serwera"
    assert r_row is not None and r_row.status == "failed" and r_row.stage == "failed"
    assert r_row.error == "Restart serwera"
    assert c_row is not None and c_row.status == "completed" and c_row.error is None
    assert f_row is not None and f_row.status == "failed"
    assert f_row.error == "TimeoutError: model"
    assert f_row.trace_id == "trace-err"
    assert f_row.duration_ms == 900
