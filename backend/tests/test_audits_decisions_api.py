"""Testy API decyzji redaktora dla tez audytu (`PUT .../decision` i `GET`)."""

import uuid
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app.api.audits import MAX_JUSTIFICATION_LENGTH
from app.auditing.store import (
    AuditStage,
    AuditStatus,
    DecisionStatus,
    NoteVerdict,
    compute_decision_status,
)
from app.session import hash_token
from tests.techqa.helpers import CHUNK_SET_ID, SNAPSHOT_ID

COOKIE = "kops_session"


def _seed_audit(
    conn: psycopg.Connection,
    *,
    session_token: str,
    status: AuditStatus = "completed",
    stage: AuditStage | None = None,
    claims_count: int = 2,
    note_verdict: NoteVerdict | None = "partial",
    case_ref: str | None = "CASE-200",
    error: str | None = None,
) -> tuple[str, list[str]]:
    """Tworzy audyt z tezami i zdarzeniami systemowymi bezpośrednio w bazie testowej."""
    audit_id = str(uuid.uuid4())
    resolved_stage: AuditStage = stage or (
        "completed"
        if status == "completed"
        else "failed"
        if status == "failed"
        else "verifying"
        if status == "running"
        else "queued"
    )
    resolved_verdict = note_verdict if status == "completed" else None
    claim_ids: list[str] = []
    with conn.transaction():
        conn.execute(
            "INSERT INTO audits ("
            " id, session_hash, is_demo, case_ref, case_description,"
            " resolution_note, status, stage, claims_total, claims_done,"
            " note_verdict, snapshot_id, chunk_set_ids, config, error,"
            " completed_at"
            ") VALUES ("
            " %s, %s, false, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
            " '{}'::jsonb, %s, CASE WHEN %s = 'completed' THEN now() ELSE NULL END"
            ")",
            (
                audit_id,
                hash_token(session_token),
                case_ref,
                "Opis zgłoszenia testowego.",
                "Notatka z rozwiązaniem testowym.",
                status,
                resolved_stage,
                claims_count if status == "completed" else 0,
                claims_count if status == "completed" else 0,
                resolved_verdict,
                SNAPSHOT_ID,
                [CHUNK_SET_ID],
                error,
                status,
            ),
        )
        conn.execute(
            "INSERT INTO audit_events ("
            " id, audit_id, claim_id, session_hash, event_type,"
            " actor_type, role_label, payload"
            ") VALUES (%s, %s, NULL, NULL, 'audit_created', 'system', NULL, %s)",
            (str(uuid.uuid4()), audit_id, Jsonb({"case_ref": case_ref})),
        )
        if status == "completed":
            for index in range(claims_count):
                claim_id = str(uuid.uuid4())
                claim_ids.append(claim_id)
                conn.execute(
                    "INSERT INTO audit_claims ("
                    " id, audit_id, claim_index, claim_label, claim_text,"
                    " source_excerpt, source_start, source_end, search_query,"
                    " verdict, rationale, scope_note, evidence, checked_docs, error"
                    ") VALUES ("
                    " %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL,"
                    " '[]'::jsonb, '[]'::jsonb, NULL"
                    ")",
                    (
                        claim_id,
                        audit_id,
                        index,
                        f"Teza {index + 1}",
                        f"Treść tezy numer {index + 1}.",
                        f"Fragment {index + 1}",
                        index * 10,
                        index * 10 + 10,
                        f"query {index + 1}",
                        "supported" if index == 0 else "insufficient",
                        f"Uzasadnienie systemu dla tezy {index + 1}.",
                    ),
                )
            conn.execute(
                "INSERT INTO audit_events ("
                " id, audit_id, claim_id, session_hash, event_type,"
                " actor_type, role_label, payload"
                ") VALUES ("
                " %s, %s, NULL, NULL, 'evaluation_completed', 'system', NULL, %s"
                ")",
                (
                    str(uuid.uuid4()),
                    audit_id,
                    Jsonb(
                        {
                            "note_verdict": resolved_verdict,
                            "claims_total": claims_count,
                        }
                    ),
                ),
            )
        elif status == "failed":
            conn.execute(
                "INSERT INTO audit_events ("
                " id, audit_id, claim_id, session_hash, event_type,"
                " actor_type, role_label, payload"
                ") VALUES ("
                " %s, %s, NULL, NULL, 'evaluation_failed', 'system', NULL, '{}'::jsonb"
                ")",
                (str(uuid.uuid4()), audit_id),
            )
    return audit_id, claim_ids


@pytest.mark.parametrize(
    ("audit_status", "claims_total", "decisions_count", "expected"),
    [
        ("queued", 0, 0, "pending"),
        ("queued", 2, 0, "pending"),
        ("running", 0, 0, "pending"),
        ("running", 3, 1, "pending"),
        ("failed", 0, 0, "not_applicable"),
        ("failed", 2, 2, "not_applicable"),
        ("completed", 0, 0, "not_applicable"),
        ("completed", 2, 0, "pending"),
        ("completed", 2, 1, "in_progress"),
        ("completed", 3, 2, "in_progress"),
        ("completed", 1, 1, "saved"),
        ("completed", 2, 2, "saved"),
    ],
)
def test_compute_decision_status_all_combinations(
    audit_status: AuditStatus,
    claims_total: int,
    decisions_count: int,
    expected: DecisionStatus,
) -> None:
    assert (
        compute_decision_status(audit_status, claims_total, decisions_count) == expected
    )


@pytest.mark.db
@pytest.mark.parametrize(
    "payload",
    [
        {"decision": "agree_with_system", "justification": ""},
        {"decision": "agree_with_system", "justification": "   \n\t "},
        {
            "decision": "agree_with_system",
            "justification": "x" * (MAX_JUSTIFICATION_LENGTH + 1),
        },
        {"decision": "unknown_category", "justification": "Poprawne uzasadnienie."},
        {
            "decision": "agree_with_system",
            "justification": "Poprawne uzasadnienie.",
            "role_label": "admin",
        },
    ],
)
def test_put_decision_invalid_payload_returns_422(
    api_client: TestClient,
    imported_conn: psycopg.Connection,
    payload: dict[str, Any],
) -> None:
    session_token = "sesja-walidacja"
    audit_id, claim_ids = _seed_audit(imported_conn, session_token=session_token)
    api_client.cookies.set(COOKIE, session_token)

    resp = api_client.put(
        f"/api/audits/{audit_id}/claims/{claim_ids[0]}/decision",
        json=payload,
    )
    assert resp.status_code == 422


@pytest.mark.db
def test_put_decision_session_isolation_and_not_found_cases(
    api_client: TestClient,
    imported_conn: psycopg.Connection,
) -> None:
    owner_token = "sesja-owner-404"
    other_token = "sesja-other-404"
    audit_id, claim_ids = _seed_audit(imported_conn, session_token=owner_token)
    other_audit_id, other_claim_ids = _seed_audit(
        imported_conn, session_token=owner_token
    )
    valid_body = {
        "decision": "agree_with_system",
        "justification": "Potwierdzam ocenę systemu.",
    }

    # Brak ciasteczka -> 404 bez ustawiania nowego ciasteczka.
    api_client.cookies.clear()
    no_cookie = api_client.put(
        f"/api/audits/{audit_id}/claims/{claim_ids[0]}/decision",
        json=valid_body,
    )
    assert no_cookie.status_code == 404
    assert "set-cookie" not in no_cookie.headers

    # Obca sesja -> 404.
    api_client.cookies.set(COOKIE, other_token)
    other_session_resp = api_client.put(
        f"/api/audits/{audit_id}/claims/{claim_ids[0]}/decision",
        json=valid_body,
    )
    assert other_session_resp.status_code == 404

    # Własna sesja: nieistniejący claim_id, teza z innego audytu lub zły UUID -> 404.
    api_client.cookies.set(COOKIE, owner_token)
    unknown_claim = str(uuid.uuid4())
    assert (
        api_client.put(
            f"/api/audits/{audit_id}/claims/{unknown_claim}/decision",
            json=valid_body,
        ).status_code
        == 404
    )
    assert (
        api_client.put(
            f"/api/audits/{audit_id}/claims/{other_claim_ids[0]}/decision",
            json=valid_body,
        ).status_code
        == 404
    )
    assert (
        api_client.put(
            f"/api/audits/{other_audit_id}/claims/nie-uuid/decision",
            json=valid_body,
        ).status_code
        == 404
    )


@pytest.mark.db
@pytest.mark.parametrize("audit_status", ["queued", "running", "failed"])
def test_put_decision_for_non_completed_audit_returns_409(
    api_client: TestClient,
    imported_conn: psycopg.Connection,
    audit_status: AuditStatus,
) -> None:
    session_token = f"sesja-409-{audit_status}"
    audit_id, _ = _seed_audit(
        imported_conn,
        session_token=session_token,
        status=audit_status,
        claims_count=0,
        error="Błąd testowy" if audit_status == "failed" else None,
    )
    api_client.cookies.set(COOKIE, session_token)

    resp = api_client.put(
        f"/api/audits/{audit_id}/claims/{uuid.uuid4()}/decision",
        json={
            "decision": "agree_with_system",
            "justification": "Próba zapisu dla niezakończonego audytu.",
        },
    )
    assert resp.status_code == 409
    assert "AuditNotCompletedError" not in resp.json()["detail"]


@pytest.mark.db
def test_put_decision_lifecycle_transitions_and_history_events(
    api_client: TestClient,
    imported_conn: psycopg.Connection,
) -> None:
    session_token = "sesja-cykl-decyzji"
    audit_id, claim_ids = _seed_audit(
        imported_conn,
        session_token=session_token,
        status="completed",
        claims_count=2,
        note_verdict="partial",
    )
    api_client.cookies.set(COOKIE, session_token)

    # Stan początkowy przed zapisaniem decyzji.
    initial_resp = api_client.get(f"/api/audits/{audit_id}")
    assert initial_resp.status_code == 200
    initial = initial_resp.json()
    assert initial["status"] == "completed"
    assert initial["decision_status"] == "pending"
    assert initial["decisions_count"] == 0
    assert [c["decision"] for c in initial["claims"]] == [None, None]
    assert [e["event_type"] for e in initial["history"]] == [
        "audit_created",
        "evaluation_completed",
    ]
    assert initial["history"][1]["note_verdict"] == "partial"
    assert initial["history"][1]["claims_total"] == 2

    # 1. Zapis decyzji dla pierwszej z 2 tez -> in_progress + decision_saved.
    first_resp = api_client.put(
        f"/api/audits/{audit_id}/claims/{claim_ids[0]}/decision",
        json={
            "decision": "agree_with_system",
            "justification": "  Teza pokrywa się z dokumentacją produktu.  ",
        },
    )
    assert first_resp.status_code == 200
    first = first_resp.json()
    assert first["status"] == "completed"
    assert first["decision_status"] == "in_progress"
    assert first["decisions_count"] == 1
    assert first["claims"][0]["decision"] is not None
    assert first["claims"][0]["decision"]["decision"] == "agree_with_system"
    assert (
        first["claims"][0]["decision"]["justification"]
        == "Teza pokrywa się z dokumentacją produktu."
    )
    assert first["claims"][0]["decision"]["role_label"] == "editor"
    assert first["claims"][1]["decision"] is None
    assert [e["event_type"] for e in first["history"]] == [
        "audit_created",
        "evaluation_completed",
        "decision_saved",
    ]
    saved_event = first["history"][2]
    assert saved_event["actor_type"] == "human"
    assert saved_event["role_label"] == "editor"
    assert saved_event["claim_id"] == claim_ids[0]
    assert saved_event["claim_index"] == 0
    assert saved_event["decision"] == "agree_with_system"

    # 2. Zapis decyzji dla drugiej z 2 tez -> saved.
    second_resp = api_client.put(
        f"/api/audits/{audit_id}/claims/{claim_ids[1]}/decision",
        json={
            "decision": "consider_doc_update",
            "justification": "Warto uzupełnić procedurę w bazie wiedzy.",
            "role_label": "consultant",
        },
    )
    assert second_resp.status_code == 200
    second = second_resp.json()
    assert second["status"] == "completed"
    assert second["decision_status"] == "saved"
    assert second["decisions_count"] == 2
    assert second["claims"][1]["decision"]["decision"] == "consider_doc_update"
    assert second["claims"][1]["decision"]["role_label"] == "consultant"
    assert [e["event_type"] for e in second["history"]] == [
        "audit_created",
        "evaluation_completed",
        "decision_saved",
        "decision_saved",
    ]

    # 3. Ponowny zapis dla pierwszej tezy -> nadpisuje decyzję i dopisuje update.
    updated_resp = api_client.put(
        f"/api/audits/{audit_id}/claims/{claim_ids[0]}/decision",
        json={
            "decision": "request_source_or_verify",
            "justification": "Wymaga dodatkowej weryfikacji z zespołem L3.",
            "role_label": "editor",
        },
    )
    assert updated_resp.status_code == 200
    updated = updated_resp.json()
    assert updated["status"] == "completed"
    assert updated["decision_status"] == "saved"
    assert updated["decisions_count"] == 2
    assert updated["claims"][0]["decision"]["decision"] == "request_source_or_verify"
    assert (
        updated["claims"][0]["decision"]["justification"]
        == "Wymaga dodatkowej weryfikacji z zespołem L3."
    )
    assert [e["event_type"] for e in updated["history"]] == [
        "audit_created",
        "evaluation_completed",
        "decision_saved",
        "decision_saved",
        "decision_updated",
    ]
    updated_event = updated["history"][4]
    assert updated_event["actor_type"] == "human"
    assert updated_event["role_label"] == "editor"
    assert updated_event["claim_id"] == claim_ids[0]
    assert updated_event["claim_index"] == 0
    assert updated_event["decision"] == "request_source_or_verify"


@pytest.mark.db
def test_completed_audit_with_zero_claims_has_not_applicable_decision_status(
    api_client: TestClient,
    imported_conn: psycopg.Connection,
) -> None:
    session_token = "sesja-zero-tez"
    audit_id, _ = _seed_audit(
        imported_conn,
        session_token=session_token,
        status="completed",
        claims_count=0,
        note_verdict="insufficient",
    )
    api_client.cookies.set(COOKIE, session_token)

    resp = api_client.get(f"/api/audits/{audit_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["claims_total"] == 0
    assert body["claims"] == []
    assert body["decision_status"] == "not_applicable"
    assert body["decisions_count"] == 0
    assert [e["event_type"] for e in body["history"]] == [
        "audit_created",
        "evaluation_completed",
    ]
    assert body["history"][1]["claims_total"] == 0


@pytest.mark.db
def test_demo_audit_http_isolates_decisions_and_history_between_sessions(
    api_client: TestClient,
    imported_conn: psycopg.Connection,
) -> None:
    owner_token = "sesja-demo-owner"
    other_token = "sesja-demo-other"
    audit_id, claim_ids = _seed_audit(
        imported_conn,
        session_token=owner_token,
        claims_count=1,
    )
    with imported_conn.transaction():
        imported_conn.execute(
            "UPDATE audits SET is_demo = true WHERE id = %s",
            (audit_id,),
        )

    # Sesja 1 zapisuje decyzję na audycie demo.
    api_client.cookies.set(COOKIE, owner_token)
    resp_owner = api_client.put(
        f"/api/audits/{audit_id}/claims/{claim_ids[0]}/decision",
        json={
            "decision": "agree_with_system",
            "justification": "Decyzja sesji 1 na przykładzie demo.",
            "role_label": "editor",
        },
    )
    assert resp_owner.status_code == 200
    owner_body = resp_owner.json()
    assert owner_body["decision_status"] == "saved"
    assert owner_body["decisions_count"] == 1
    assert owner_body["claims"][0]["decision"]["decision"] == "agree_with_system"
    assert [e["event_type"] for e in owner_body["history"]] == [
        "audit_created",
        "evaluation_completed",
        "decision_saved",
    ]

    # Sesja 2 widzi ten sam audyt demo, ale bez decyzji i zdarzeń człowieka sesji 1.
    api_client.cookies.set(COOKIE, other_token)
    resp_other_get = api_client.get(f"/api/audits/{audit_id}")
    assert resp_other_get.status_code == 200
    other_body = resp_other_get.json()
    assert other_body["decision_status"] == "pending"
    assert other_body["decisions_count"] == 0
    assert other_body["claims"][0]["decision"] is None
    assert [e["event_type"] for e in other_body["history"]] == [
        "audit_created",
        "evaluation_completed",
    ]

    # Sesja 2 zapisuje własną decyzję — nie nadpisuje decyzji sesji 1.
    resp_other_put = api_client.put(
        f"/api/audits/{audit_id}/claims/{claim_ids[0]}/decision",
        json={
            "decision": "system_verdict_wrong",
            "justification": "Odrębna decyzja sesji 2 na przykładzie demo.",
            "role_label": "editor",
        },
    )
    assert resp_other_put.status_code == 200
    assert (
        resp_other_put.json()["claims"][0]["decision"]["decision"]
        == "system_verdict_wrong"
    )

    api_client.cookies.set(COOKIE, owner_token)
    resp_owner_again = api_client.get(f"/api/audits/{audit_id}")
    assert resp_owner_again.status_code == 200
    assert (
        resp_owner_again.json()["claims"][0]["decision"]["decision"]
        == "agree_with_system"
    )
