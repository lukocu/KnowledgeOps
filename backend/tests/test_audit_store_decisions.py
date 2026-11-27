"""Testy migracji `0005_audit_decisions_and_history.sql` i decyzji w `store.py`."""

import os
import shutil
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import psycopg
import pytest
from psycopg import AsyncConnection

from app.auditing.store import (
    AuditNotCompletedError,
    AuditNotFoundError,
    NewAuditClaim,
    complete_audit,
    create_audit,
    fail_audit,
    fail_orphaned_audits,
    get_audit_for_session,
    update_audit_progress,
    upsert_claim_decision,
)
from app.migrations import MIGRATIONS_DIR, apply_migrations
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


def _sample_claims() -> list[NewAuditClaim]:
    return [
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
        ),
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
        ),
    ]


def test_migration_0005_creates_tables_and_indexes(conn: psycopg.Connection) -> None:
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
    assert {"audit_claim_decisions", "audit_events"} <= tables
    assert {
        "audit_claim_decisions_audit_session_idx",
        "audit_events_audit_created_idx",
    } <= indexes


def test_migration_0005_backfills_existing_audits_and_is_idempotent(
    temp_database: str, tmp_path: Path
) -> None:
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    for name in (
        "0001_techqa_schema.sql",
        "0002_answers.sql",
        "0003_synthetic_and_conflicts.sql",
        "0004_audits.sql",
    ):
        shutil.copy2(MIGRATIONS_DIR / name, migrations_dir / name)

    queued_id = str(uuid.uuid4())
    completed_id = str(uuid.uuid4())
    failed_id = str(uuid.uuid4())
    session = hash_token("sesja-backfill")

    with psycopg.connect(temp_database, autocommit=True) as conn:
        apply_migrations(conn, migrations_dir)
        with conn.transaction():
            conn.execute(
                "INSERT INTO audits ("
                " id, session_hash, case_ref, case_description, resolution_note,"
                " status, stage, snapshot_id, chunk_set_ids, config,"
                " created_at, updated_at"
                ") VALUES ("
                " %s, %s, 'CASE-Q', 'Opis Q', 'Notatka Q',"
                " 'queued', 'queued', 'snap@1', ARRAY['s1'], '{}'::jsonb,"
                " '2026-01-01T10:00:00Z', '2026-01-01T10:00:00Z'"
                ")",
                (queued_id, session),
            )
            conn.execute(
                "INSERT INTO audits ("
                " id, session_hash, case_ref, case_description, resolution_note,"
                " status, stage, claims_total, claims_done, note_verdict,"
                " snapshot_id, chunk_set_ids, config,"
                " created_at, updated_at, completed_at"
                ") VALUES ("
                " %s, %s, 'CASE-C', 'Opis C', 'Notatka C',"
                " 'completed', 'completed', 3, 3, 'partial',"
                " 'snap@1', ARRAY['s1'], '{}'::jsonb,"
                " '2026-01-02T10:00:00Z', '2026-01-02T10:05:00Z',"
                " '2026-01-02T10:04:00Z'"
                ")",
                (completed_id, session),
            )
            conn.execute(
                "INSERT INTO audits ("
                " id, session_hash, case_ref, case_description, resolution_note,"
                " status, stage, error, snapshot_id, chunk_set_ids, config,"
                " created_at, updated_at"
                ") VALUES ("
                " %s, %s, NULL, 'Opis F', 'Notatka F',"
                " 'failed', 'failed', 'RuntimeError: secret', 'snap@1', ARRAY['s1'],"
                " '{}'::jsonb, '2026-01-03T10:00:00Z', '2026-01-03T10:02:00Z'"
                ")",
                (failed_id, session),
            )

        shutil.copy2(
            MIGRATIONS_DIR / "0005_audit_decisions_and_history.sql",
            migrations_dir / "0005_audit_decisions_and_history.sql",
        )
        assert apply_migrations(conn, migrations_dir) == [
            "0005_audit_decisions_and_history"
        ]
        assert apply_migrations(conn, migrations_dir) == []

        rows = conn.execute(
            "SELECT audit_id::text, event_type, actor_type, session_hash,"
            " role_label, payload, created_at"
            " FROM audit_events"
            " ORDER BY created_at ASC, id ASC"
        ).fetchall()

    by_audit: dict[str, list[tuple[object, ...]]] = {}
    for row in rows:
        by_audit.setdefault(str(row[0]), []).append(row)

    assert [r[1] for r in by_audit[queued_id]] == ["audit_created"]
    assert by_audit[queued_id][0][2] == "system"
    assert by_audit[queued_id][0][3] is None
    assert by_audit[queued_id][0][5] == {"case_ref": "CASE-Q"}

    assert [r[1] for r in by_audit[completed_id]] == [
        "audit_created",
        "evaluation_completed",
    ]
    assert by_audit[completed_id][1][5] == {
        "note_verdict": "partial",
        "claims_total": 3,
    }

    assert [r[1] for r in by_audit[failed_id]] == ["audit_created", "evaluation_failed"]
    assert by_audit[failed_id][0][5] == {"case_ref": None}
    assert by_audit[failed_id][1][5] == {}


@pytest.mark.anyio
async def test_db_check_constraints_reject_invalid_decisions_and_events(
    async_conn: AsyncConnection,
) -> None:
    session = hash_token("sesja-check")
    audit_id = await create_audit(
        async_conn,
        session_hash=session,
        case_description="Opis.",
        resolution_note="Notatka.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
    )
    await complete_audit(
        async_conn,
        audit_id,
        claims=_sample_claims()[:1],
        note_verdict="full",
    )
    stored = await get_audit_for_session(async_conn, audit_id, session)
    assert stored is not None
    claim_id = stored.claims[0].id

    for blank in ("", "   ", "\n\t "):
        with pytest.raises(psycopg.errors.CheckViolation):
            await upsert_claim_decision(
                async_conn,
                audit_id=audit_id,
                claim_id=claim_id,
                session_hash=session,
                decision="agree_with_system",
                justification=blank,
                role_label="editor",
            )

    with pytest.raises(psycopg.errors.CheckViolation):
        await async_conn.execute(
            "INSERT INTO audit_events ("
            " id, audit_id, session_hash, event_type, actor_type"
            ") VALUES (%s, %s, %s, 'audit_created', 'system')",
            (str(uuid.uuid4()), audit_id, session),
        )

    with pytest.raises(psycopg.errors.CheckViolation):
        await async_conn.execute(
            "INSERT INTO audit_events ("
            " id, audit_id, session_hash, event_type, actor_type"
            ") VALUES (%s, %s, NULL, 'decision_saved', 'human')",
            (str(uuid.uuid4()), audit_id),
        )


@pytest.mark.anyio
async def test_upsert_claim_decision_records_saved_then_updated_history(
    async_conn: AsyncConnection,
) -> None:
    session = hash_token("sesja-decyzja")
    audit_id = await create_audit(
        async_conn,
        session_hash=session,
        case_ref="CASE-101",
        case_description="Opis sprawy.",
        resolution_note="Zmieniono port na 8443 i zrestartowano usługę.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
    )
    await complete_audit(
        async_conn,
        audit_id,
        claims=_sample_claims(),
        note_verdict="partial",
    )
    stored = await get_audit_for_session(async_conn, audit_id, session)
    assert stored is not None
    assert [e.event_type for e in stored.history] == [
        "audit_created",
        "evaluation_completed",
    ]
    assert stored.history[0].payload == {"case_ref": "CASE-101"}
    assert stored.history[1].payload == {"note_verdict": "partial", "claims_total": 2}
    assert all(c.decision is None for c in stored.claims)

    second_claim = stored.claims[1]
    first_outcome = await upsert_claim_decision(
        async_conn,
        audit_id=audit_id,
        claim_id=second_claim.id,
        session_hash=session,
        decision="request_source_or_verify",
        justification="Brak potwierdzenia restartu w dokumentacji produktu.",
        role_label="editor",
    )
    assert first_outcome == "saved"

    second_outcome = await upsert_claim_decision(
        async_conn,
        audit_id=audit_id,
        claim_id=second_claim.id,
        session_hash=session,
        decision="consider_doc_update",
        justification="Potwierdzono z zespołem L3, wymaga dopisania do KB.",
        role_label="consultant",
    )
    assert second_outcome == "updated"

    refreshed = await get_audit_for_session(async_conn, audit_id, session)
    assert refreshed is not None
    assert refreshed.status == "completed"
    assert refreshed.claims[0].decision is None
    saved_decision = refreshed.claims[1].decision
    assert saved_decision is not None
    assert saved_decision.decision == "consider_doc_update"
    assert (
        saved_decision.justification
        == "Potwierdzono z zespołem L3, wymaga dopisania do KB."
    )
    assert saved_decision.role_label == "consultant"

    assert [e.event_type for e in refreshed.history] == [
        "audit_created",
        "evaluation_completed",
        "decision_saved",
        "decision_updated",
    ]
    saved_event, updated_event = refreshed.history[2], refreshed.history[3]
    assert saved_event.actor_type == "human"
    assert saved_event.role_label == "editor"
    assert saved_event.claim_id == second_claim.id
    assert saved_event.claim_index == 1
    assert saved_event.payload == {
        "decision": "request_source_or_verify",
        "claim_index": 1,
    }
    assert updated_event.actor_type == "human"
    assert updated_event.role_label == "consultant"
    assert updated_event.claim_id == second_claim.id
    assert updated_event.claim_index == 1
    assert updated_event.payload == {
        "decision": "consider_doc_update",
        "claim_index": 1,
    }


@pytest.mark.anyio
async def test_demo_audit_isolates_decisions_and_human_events_between_sessions(
    async_conn: AsyncConnection,
) -> None:
    owner = hash_token("sesja-owner")
    session_a = hash_token("sesja-a")
    session_b = hash_token("sesja-b")

    demo_id = await create_audit(
        async_conn,
        session_hash=owner,
        case_ref="DEMO-1",
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
        claims=_sample_claims()[:1],
        note_verdict="full",
    )
    demo = await get_audit_for_session(async_conn, demo_id, owner)
    assert demo is not None
    claim_id = demo.claims[0].id

    outcome_a = await upsert_claim_decision(
        async_conn,
        audit_id=demo_id,
        claim_id=claim_id,
        session_hash=session_a,
        decision="agree_with_system",
        justification="Uzasadnienie sesji A.",
        role_label="editor",
    )
    assert outcome_a == "saved"
    outcome_b = await upsert_claim_decision(
        async_conn,
        audit_id=demo_id,
        claim_id=claim_id,
        session_hash=session_b,
        decision="system_verdict_wrong",
        justification="Uzasadnienie sesji B.",
        role_label="consultant",
    )
    assert outcome_b == "saved"

    view_a = await get_audit_for_session(async_conn, demo_id, session_a)
    view_b = await get_audit_for_session(async_conn, demo_id, session_b)
    view_anon = await get_audit_for_session(async_conn, demo_id, None)

    assert view_a is not None and view_a.claims[0].decision is not None
    assert view_a.claims[0].decision.decision == "agree_with_system"
    assert view_a.claims[0].decision.justification == "Uzasadnienie sesji A."
    assert [e.event_type for e in view_a.history] == [
        "audit_created",
        "evaluation_completed",
        "decision_saved",
    ]
    assert view_a.history[2].payload == {
        "decision": "agree_with_system",
        "claim_index": 0,
    }

    assert view_b is not None and view_b.claims[0].decision is not None
    assert view_b.claims[0].decision.decision == "system_verdict_wrong"
    assert view_b.claims[0].decision.justification == "Uzasadnienie sesji B."
    assert [e.event_type for e in view_b.history] == [
        "audit_created",
        "evaluation_completed",
        "decision_saved",
    ]
    assert view_b.history[2].payload == {
        "decision": "system_verdict_wrong",
        "claim_index": 0,
    }

    assert view_anon is not None
    assert view_anon.claims[0].decision is None
    assert [e.event_type for e in view_anon.history] == [
        "audit_created",
        "evaluation_completed",
    ]


@pytest.mark.anyio
async def test_fail_audit_and_fail_orphaned_audits_record_system_events(
    async_conn: AsyncConnection,
) -> None:
    session = hash_token("sesja-fail-events")
    queued_id = await create_audit(
        async_conn,
        session_hash=session,
        case_description="Kolejka.",
        resolution_note="Notatka 1.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
    )
    failed_id = await create_audit(
        async_conn,
        session_hash=session,
        case_description="Błąd.",
        resolution_note="Notatka 2.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
    )
    await fail_audit(
        async_conn,
        failed_id,
        error="Traceback: sensitive internal detail",
    )

    orphaned_count = await fail_orphaned_audits(async_conn)
    assert orphaned_count == 1

    failed_audit = await get_audit_for_session(async_conn, failed_id, session)
    orphaned_audit = await get_audit_for_session(async_conn, queued_id, session)

    assert failed_audit is not None
    assert [e.event_type for e in failed_audit.history] == [
        "audit_created",
        "evaluation_failed",
    ]
    assert failed_audit.history[1].payload == {}

    assert orphaned_audit is not None
    assert [e.event_type for e in orphaned_audit.history] == [
        "audit_created",
        "evaluation_failed",
    ]
    assert orphaned_audit.history[1].payload == {"orphaned": True}


@pytest.mark.anyio
async def test_upsert_claim_decision_raises_not_found_and_not_completed(
    async_conn: AsyncConnection,
) -> None:
    owner = hash_token("sesja-err-owner")
    other = hash_token("sesja-err-other")

    queued_id = await create_audit(
        async_conn,
        session_hash=owner,
        case_description="W kolejce.",
        resolution_note="Notatka.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
    )
    completed_id = await create_audit(
        async_conn,
        session_hash=owner,
        case_description="Zakończony.",
        resolution_note="Notatka.",
        snapshot_id="techqa@v1",
        chunk_set_ids=["set-1"],
        config={},
    )
    await complete_audit(
        async_conn,
        completed_id,
        claims=_sample_claims()[:1],
        note_verdict="full",
    )
    completed = await get_audit_for_session(async_conn, completed_id, owner)
    assert completed is not None
    claim_id = completed.claims[0].id

    with pytest.raises(AuditNotFoundError):
        await upsert_claim_decision(
            async_conn,
            audit_id="nie-uuid",
            claim_id=claim_id,
            session_hash=owner,
            decision="agree_with_system",
            justification="OK",
            role_label="editor",
        )

    with pytest.raises(AuditNotFoundError):
        await upsert_claim_decision(
            async_conn,
            audit_id=completed_id,
            claim_id="nie-uuid",
            session_hash=owner,
            decision="agree_with_system",
            justification="OK",
            role_label="editor",
        )

    with pytest.raises(AuditNotFoundError):
        await upsert_claim_decision(
            async_conn,
            audit_id=completed_id,
            claim_id=claim_id,
            session_hash=other,
            decision="agree_with_system",
            justification="OK",
            role_label="editor",
        )

    with pytest.raises(AuditNotFoundError):
        await upsert_claim_decision(
            async_conn,
            audit_id=completed_id,
            claim_id=str(uuid.uuid4()),
            session_hash=owner,
            decision="agree_with_system",
            justification="OK",
            role_label="editor",
        )

    with pytest.raises(AuditNotCompletedError):
        await upsert_claim_decision(
            async_conn,
            audit_id=queued_id,
            claim_id=claim_id,
            session_hash=owner,
            decision="agree_with_system",
            justification="OK",
            role_label="editor",
        )

    await update_audit_progress(async_conn, queued_id, stage="verifying")
    with pytest.raises(AuditNotCompletedError):
        await upsert_claim_decision(
            async_conn,
            audit_id=queued_id,
            claim_id=claim_id,
            session_hash=owner,
            decision="agree_with_system",
            justification="OK",
            role_label="editor",
        )

    await fail_audit(async_conn, queued_id, error="Błąd")
    with pytest.raises(AuditNotCompletedError):
        await upsert_claim_decision(
            async_conn,
            audit_id=queued_id,
            claim_id=claim_id,
            session_hash=owner,
            decision="agree_with_system",
            justification="OK",
            role_label="editor",
        )
