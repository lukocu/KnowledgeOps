"""Testy integracyjne API `/api/audits`: 202, postęp, wynik, sesja, walidacja."""

import asyncio
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from psycopg.types.json import Jsonb

import app.api.audits as audits_api
from app.api.answers import ChatModelFactory, get_chat_model_factory
from app.auditing.schemas import (
    CaseContext,
    ClaimVerdictOutput,
    ExtractedClaim,
    ExtractOutput,
)
from app.auditing.store import (
    AuditSourceFilter,
    AuditStage,
    AuditStatus,
    ClaimVerdict,
    DecisionStatus,
    NoteVerdict,
    StoredAudit,
    StoredAuditClaim,
    StoredAuditListItem,
    StoredAuditListResult,
)
from app.db import get_pool
from app.main import app
from app.session import hash_token
from app.settings import Settings
from app.techqa.search import search_chunks
from tests.conftest import LOOP_OPTIONS
from tests.techqa.helpers import CHUNK_SET_ID, SNAPSHOT_ID

COOKIE = "kops_session"
QUERY_TERM = "information about this problem"


class _StubPool:
    @asynccontextmanager
    async def connection(self, timeout: float) -> Any:
        yield object()


class GatedAuditChatModel(BaseChatModel):
    """Fałszywy model audytu z bramką synchronizacyjną na etapie `extract`."""

    extract_output: ExtractOutput
    verdict_outputs: list[ClaimVerdictOutput]
    extract_started: threading.Event | None = None
    allow_extract_finish: threading.Event | None = None

    @property
    def _llm_type(self) -> str:
        return "gated-audit-fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise AssertionError("graf audytu ma używać wyłącznie with_structured_output")

    def with_structured_output(
        self, schema: Any, **kwargs: Any
    ) -> Runnable[LanguageModelInput, Any]:
        extract_output = self.extract_output
        verdict_outputs = list(self.verdict_outputs)
        started = self.extract_started
        allow_finish = self.allow_extract_finish

        async def respond(_: LanguageModelInput) -> Any:
            if schema is ExtractOutput:
                if started is not None:
                    started.set()
                if allow_finish is not None:
                    while not allow_finish.is_set():
                        await asyncio.sleep(0.01)
                return extract_output
            if schema is ClaimVerdictOutput:
                return verdict_outputs.pop(0)
            raise AssertionError(f"nieoczekiwany schemat: {schema}")

        return RunnableLambda(respond)


class SlowAuditChatModel(BaseChatModel):
    """Model przekraczający limit czasu audytu."""

    @property
    def _llm_type(self) -> str:
        return "slow-audit-fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise AssertionError("graf audytu ma używać wyłącznie with_structured_output")

    def with_structured_output(
        self, schema: Any, **kwargs: Any
    ) -> Runnable[LanguageModelInput, Any]:
        async def slow(_: LanguageModelInput) -> Any:
            await asyncio.sleep(5)
            raise AssertionError("limit czasu audytu powinien minąć wcześniej")

        return RunnableLambda(slow)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHUNK_SET_ID", CHUNK_SET_ID)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)


@pytest.fixture
def use_model() -> Iterator[Callable[[BaseChatModel], None]]:
    """Podmienia fabrykę modelu czatu w aplikacji."""

    def install(model: BaseChatModel) -> None:
        def factory(_: Settings) -> BaseChatModel:
            return model

        def provider() -> ChatModelFactory:
            return factory

        app.dependency_overrides[get_chat_model_factory] = provider

    yield install
    app.dependency_overrides.pop(get_chat_model_factory, None)


def _scripted_audit_model(
    conn: psycopg.Connection,
    *,
    extract_started: threading.Event | None = None,
    allow_extract_finish: threading.Event | None = None,
) -> tuple[GatedAuditChatModel, str]:
    hits = search_chunks(
        conn, QUERY_TERM, method="bm25", chunk_set_id=CHUNK_SET_ID, k=5
    )
    assert hits, "mini-migawka powinna zwrócić co najmniej jedno trafienie BM25"
    hit = hits[0]
    quote = hit.snippet[:40].strip()
    note = "Verified step from documentation."
    model = GatedAuditChatModel(
        extract_output=ExtractOutput(
            case_context=CaseContext(
                problem="Issue reported in ticket.",
                environment="Test environment",
                solution=note,
                constraints=["No downtime"],
                missing_info=[],
            ),
            claims=[
                ExtractedClaim(
                    claim_label="Documented step",
                    claim_text=note,
                    source_excerpt=note,
                    search_query=QUERY_TERM,
                )
            ],
        ),
        verdict_outputs=[
            ClaimVerdictOutput(
                reasoning="Documentation directly supports the resolution step.",
                verdict="supported",
                scope_relation="same_scope",
                scope_note=None,
                evidence_chunk_id=hit.chunk_id,
                evidence_quote=quote,
            )
        ],
        extract_started=extract_started,
        allow_extract_finish=allow_extract_finish,
    )
    return model, note


def _poll_until_terminal(
    client: TestClient, audit_id: str, *, timeout_s: float = 5.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/audits/{audit_id}")
        assert response.status_code == 200
        last = response.json()
        if last["status"] in ("completed", "failed"):
            return last
        time.sleep(0.02)
    raise AssertionError(f"Audyt {audit_id} nie zakończył się w {timeout_s}s: {last}")


def _count_audits(conn: psycopg.Connection) -> int:
    row = conn.execute("SELECT count(*) FROM audits").fetchone()
    assert row is not None
    return int(row[0])


@pytest.mark.db
def test_post_and_poll_audit_lifecycle_with_progress_and_result(
    api_client: TestClient,
    imported_conn: psycopg.Connection,
    use_model: Callable[[BaseChatModel], None],
) -> None:
    started = threading.Event()
    release = threading.Event()
    model, note = _scripted_audit_model(
        imported_conn,
        extract_started=started,
        allow_extract_finish=release,
    )
    use_model(model)

    create_resp = api_client.post(
        "/api/audits",
        json={
            "case_ref": "  INC-4242  ",
            "case_description": "Customer reports error in logs.",
            "resolution_note": note,
        },
    )
    assert create_resp.status_code == 202
    created = create_resp.json()
    audit_id = created["audit_id"]
    assert created["status"] == "queued"
    assert created["stage"] == "queued"

    set_cookie = create_resp.headers["set-cookie"]
    assert set_cookie.startswith(f"{COOKIE}=")
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/api" in set_cookie

    token = api_client.cookies[COOKIE]
    row = imported_conn.execute(
        "SELECT session_hash FROM audits WHERE id = %s", (audit_id,)
    ).fetchone()
    assert row is not None
    assert row[0] == hash_token(token)
    assert row[0] != token

    assert started.wait(timeout=3.0), "graf nie wszedł w etap extract"
    in_progress_resp = api_client.get(f"/api/audits/{audit_id}")
    assert in_progress_resp.status_code == 200
    in_progress = in_progress_resp.json()
    assert in_progress["status"] == "running"
    assert in_progress["stage"] == "extracting"

    release.set()
    final = _poll_until_terminal(api_client, audit_id)

    assert final["audit_id"] == audit_id
    assert final["is_demo"] is False
    assert final["case_ref"] == "INC-4242"
    assert final["case_description"] == "Customer reports error in logs."
    assert final["resolution_note"] == note
    assert final["status"] == "completed"
    assert final["stage"] == "completed"
    assert final["claims_total"] == 1
    assert final["claims_done"] == 1
    assert final["note_verdict"] == "full"
    assert final["case_context"]["problem"] == "Issue reported in ticket."
    assert final["snapshot_id"] == SNAPSHOT_ID
    assert final["chunk_set_ids"] == [CHUNK_SET_ID]
    assert final["include_synthetic"] is True
    assert set(final["config"]["prompt_versions"]) == {"extract", "verify_claim"}
    assert final["error"] is None
    assert final["duration_ms"] is not None
    assert final["completed_at"] is not None

    assert len(final["claims"]) == 1
    claim = final["claims"][0]
    assert claim["claim_id"]
    assert claim["claim_index"] == 0
    assert claim["claim_label"] == "Documented step"
    assert claim["source_start"] == 0
    assert claim["source_end"] == len(note)
    assert claim["verdict"] == "supported"
    assert claim["error"] is None
    assert len(claim["evidence"]) == 1
    assert claim["evidence"][0]["supports_claim"] is True
    assert len(claim["checked_docs"]) >= 1


@pytest.mark.db
def test_get_audit_session_isolation_and_unknown_ids(
    api_client: TestClient,
    imported_conn: psycopg.Connection,
    use_model: Callable[[BaseChatModel], None],
) -> None:
    model, note = _scripted_audit_model(imported_conn)
    use_model(model)
    create_resp = api_client.post(
        "/api/audits",
        json={
            "case_description": "Private case.",
            "resolution_note": note,
        },
    )
    assert create_resp.status_code == 202
    audit_id = create_resp.json()["audit_id"]
    _poll_until_terminal(api_client, audit_id)

    # Inna sesja dostaje 404.
    api_client.cookies.clear()
    api_client.cookies.set(COOKIE, "inna-sesja", domain="testserver", path="/api")
    assert api_client.get(f"/api/audits/{audit_id}").status_code == 404

    # Brak ciasteczka daje 404 i nie tworzy nowego ciasteczka.
    api_client.cookies.clear()
    no_cookie_resp = api_client.get(f"/api/audits/{audit_id}")
    assert no_cookie_resp.status_code == 404
    assert "set-cookie" not in no_cookie_resp.headers

    # Nieistniejący UUID i błędny format ID dają 404.
    api_client.cookies.set(COOKIE, "jakas-sesja", domain="testserver", path="/api")
    unknown = "00000000-0000-4000-8000-000000000000"
    assert api_client.get(f"/api/audits/{unknown}").status_code == 404
    assert api_client.get("/api/audits/nie-uuid").status_code == 404


@pytest.mark.db
@pytest.mark.parametrize(
    "payload",
    [
        {"case_description": "", "resolution_note": "ok"},
        {"case_description": "   \n\t ", "resolution_note": "ok"},
        {"case_description": "x" * 4001, "resolution_note": "ok"},
        {"case_description": "ok", "resolution_note": ""},
        {"case_description": "ok", "resolution_note": "   "},
        {"case_description": "ok", "resolution_note": "y" * 4001},
        {
            "case_ref": "R" * 121,
            "case_description": "ok",
            "resolution_note": "ok",
        },
    ],
)
def test_create_audit_invalid_payload_returns_422(
    api_client: TestClient, payload: dict[str, str]
) -> None:
    response = api_client.post("/api/audits", json=payload)
    assert response.status_code == 422


@pytest.mark.db
def test_create_audit_missing_api_key_returns_503_without_row(
    api_client: TestClient, imported_conn: psycopg.Connection
) -> None:
    response = api_client.post(
        "/api/audits",
        json={
            "case_description": "Problem description.",
            "resolution_note": "Resolution note.",
        },
    )
    assert response.status_code == 503
    assert _count_audits(imported_conn) == 0


@pytest.mark.db
def test_audit_deadline_marks_audit_failed(
    api_client: TestClient,
    use_model: Callable[[BaseChatModel], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUDIT_DEADLINE_S", "0.2")
    use_model(SlowAuditChatModel())

    create_resp = api_client.post(
        "/api/audits",
        json={
            "case_description": "Slow case.",
            "resolution_note": "Slow resolution note.",
        },
    )
    assert create_resp.status_code == 202
    audit_id = create_resp.json()["audit_id"]

    final = _poll_until_terminal(api_client, audit_id)
    assert final["status"] == "failed"
    assert final["stage"] == "failed"
    assert final["error"]
    assert final["duration_ms"] is not None


@pytest.mark.db
def test_lifespan_marks_orphaned_audits_failed_on_startup(
    imported_conn: psycopg.Connection,
    temp_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_token = "sesja-osierocona"
    session_hash = hash_token(session_token)
    queued_id = str(uuid.uuid4())
    running_id = str(uuid.uuid4())
    for audit_id, audit_status, audit_stage in (
        (queued_id, "queued", "queued"),
        (running_id, "running", "verifying"),
    ):
        imported_conn.execute(
            "INSERT INTO audits ("
            " id, session_hash, is_demo, case_description, resolution_note,"
            " status, stage, snapshot_id, chunk_set_ids, config"
            ") VALUES (%s, %s, false, %s, %s, %s, %s, %s, %s, '{}'::jsonb)",
            (
                audit_id,
                session_hash,
                "Orphaned case.",
                "Orphaned note.",
                audit_status,
                audit_stage,
                SNAPSHOT_ID,
                [CHUNK_SET_ID],
            ),
        )

    monkeypatch.setenv("DATABASE_URL", temp_database)
    with TestClient(app, backend_options=LOOP_OPTIONS) as client:
        client.cookies.set(COOKIE, session_token)
        for audit_id in (queued_id, running_id):
            resp = client.get(f"/api/audits/{audit_id}")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "failed"
            assert body["stage"] == "failed"
            assert body["error"]


def _seed_audit_row(
    conn: psycopg.Connection,
    *,
    session_token: str,
    is_demo: bool = False,
    case_ref: str | None = "CASE-LIST",
    case_description: str = "Opis zgłoszenia testowego.",
    case_context: dict[str, Any] | None = None,
    status: AuditStatus = "completed",
    stage: AuditStage | None = None,
    note_verdict: NoteVerdict | None = "partial",
    claim_verdicts: Sequence[ClaimVerdict] = ("supported", "insufficient"),
) -> tuple[str, list[str]]:
    """Wstawia rekord audytu z tezami i zdarzeniami systemowymi do bazy."""
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
    claims_count = len(claim_verdicts) if status == "completed" else 0
    claim_ids: list[str] = []
    with conn.transaction():
        conn.execute(
            "INSERT INTO audits ("
            " id, session_hash, is_demo, case_ref, case_description,"
            " resolution_note, status, stage, claims_total, claims_done,"
            " note_verdict, case_context, snapshot_id, chunk_set_ids, config,"
            " completed_at"
            ") VALUES ("
            " %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
            " '{}'::jsonb, CASE WHEN %s = 'completed' THEN now() ELSE NULL END"
            ")",
            (
                audit_id,
                hash_token(session_token),
                is_demo,
                case_ref,
                case_description,
                "Notatka z rozwiązaniem testowym.",
                status,
                resolved_stage,
                claims_count,
                claims_count,
                resolved_verdict,
                Jsonb(case_context) if case_context is not None else None,
                SNAPSHOT_ID,
                [CHUNK_SET_ID],
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
            for index, verdict in enumerate(claim_verdicts):
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
                        f"Treść tezy {index + 1}.",
                        f"Fragment {index + 1}",
                        index * 10,
                        index * 10 + 10,
                        f"query {index + 1}",
                        verdict,
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
    return audit_id, claim_ids


def test_list_audits_stub_passes_filters_and_optional_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    demo_id = str(uuid.uuid4())
    captured: list[dict[str, Any]] = []

    async def fake_list(
        _conn: Any,
        session_hash: str | None,
        *,
        q: str | None = None,
        decision_status: DecisionStatus | None = None,
        note_verdict: NoteVerdict | None = None,
        source: AuditSourceFilter = "all",
    ) -> StoredAuditListResult:
        captured.append(
            {
                "session_hash": session_hash,
                "q": q,
                "decision_status": decision_status,
                "note_verdict": note_verdict,
                "source": source,
            }
        )
        return StoredAuditListResult(
            items=[
                StoredAuditListItem(
                    id=demo_id,
                    is_demo=True,
                    case_ref="DEMO-1",
                    problem_summary="Skrót problemu demo.",
                    status="completed",
                    stage="completed",
                    note_verdict="contradiction",
                    claims_total=2,
                    claims_done=2,
                    claims_supported=1,
                    claims_contradicted=1,
                    claims_insufficient=0,
                    decisions_count=0,
                    decision_status="pending",
                    created_at=now,
                    updated_at=now,
                    last_activity_at=now,
                )
            ],
            demo_count=1,
            session_count=0,
            pending_count=1,
            in_progress_count=0,
            saved_count=0,
            next_pending_audit_id=demo_id,
            next_pending_case_ref="DEMO-1",
        )

    monkeypatch.setattr(audits_api, "list_audits_for_session", fake_list)
    app.dependency_overrides[get_pool] = lambda: _StubPool()
    try:
        client = TestClient(app)
        resp_no_cookie = client.get("/api/audits")
        assert resp_no_cookie.status_code == 200
        assert "set-cookie" not in resp_no_cookie.headers
        body = resp_no_cookie.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["audit_id"] == demo_id
        assert body["items"][0]["is_demo"] is True
        assert body["summary"] == {
            "demo_count": 1,
            "session_count": 0,
            "pending_count": 1,
            "in_progress_count": 0,
            "saved_count": 0,
            "next_pending_audit_id": demo_id,
            "next_pending_case_ref": "DEMO-1",
        }
        assert captured[-1] == {
            "session_hash": None,
            "q": None,
            "decision_status": None,
            "note_verdict": None,
            "source": "all",
        }

        client.cookies.set(COOKIE, "sesja-stub")
        resp_filtered = client.get(
            "/api/audits",
            params={
                "q": "ssl",
                "decision_status": "pending",
                "note_verdict": "contradiction",
                "source": "demo",
            },
        )
        assert resp_filtered.status_code == 200
        assert captured[-1] == {
            "session_hash": hash_token("sesja-stub"),
            "q": "ssl",
            "decision_status": "pending",
            "note_verdict": "contradiction",
            "source": "demo",
        }

        resp_invalid = client.get("/api/audits", params={"source": "invalid"})
        assert resp_invalid.status_code == 422
    finally:
        app.dependency_overrides.pop(get_pool, None)


def test_demo_get_and_put_decision_stub_without_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    demo_id = str(uuid.uuid4())
    claim_id = str(uuid.uuid4())
    get_sessions: list[str | None] = []
    put_sessions: list[str] = []

    def _stored_demo() -> StoredAudit:
        return StoredAudit(
            id=demo_id,
            session_hash="demo-owner-hash",
            is_demo=True,
            case_ref="DEMO-STUB",
            case_description="Opis sprawy demo.",
            resolution_note="Notatka demo.",
            status="completed",
            stage="completed",
            claims_total=1,
            claims_done=1,
            note_verdict="full",
            case_context=None,
            snapshot_id=SNAPSHOT_ID,
            chunk_set_ids=[CHUNK_SET_ID],
            config={},
            error=None,
            trace_id=None,
            duration_ms=100,
            created_at=now,
            updated_at=now,
            completed_at=now,
            claims=[
                StoredAuditClaim(
                    id=claim_id,
                    audit_id=demo_id,
                    claim_index=0,
                    claim_label="Teza demo",
                    claim_text="Treść tezy demo.",
                    source_excerpt="Notatka demo.",
                    search_query="demo",
                    verdict="supported",
                    rationale="Zgodne z dokumentacją.",
                )
            ],
            history=[],
        )

    async def fake_get(
        _conn: Any, audit_id: str, session_hash: str | None
    ) -> StoredAudit | None:
        get_sessions.append(session_hash)
        if audit_id != demo_id:
            return None
        return _stored_demo()

    async def fake_upsert(
        _conn: Any,
        *,
        audit_id: str,
        claim_id: str,
        session_hash: str,
        decision: Any,
        justification: str,
        role_label: Any,
    ) -> str:
        put_sessions.append(session_hash)
        return "saved"

    monkeypatch.setattr(audits_api, "get_audit_for_session", fake_get)
    monkeypatch.setattr(audits_api, "upsert_claim_decision", fake_upsert)
    app.dependency_overrides[get_pool] = lambda: _StubPool()
    try:
        client = TestClient(app)
        resp_get = client.get(f"/api/audits/{demo_id}")
        assert resp_get.status_code == 200
        assert "set-cookie" not in resp_get.headers
        assert resp_get.json()["is_demo"] is True
        assert get_sessions == [None]

        resp_put = client.put(
            f"/api/audits/{demo_id}/claims/{claim_id}/decision",
            json={
                "decision": "agree_with_system",
                "justification": "Potwierdzam ocenę demo.",
            },
        )
        assert resp_put.status_code == 200
        assert resp_put.headers["set-cookie"].startswith(f"{COOKIE}=")
        minted_token = client.cookies[COOKIE]
        assert put_sessions == [hash_token(minted_token)]
        assert get_sessions[-1] == hash_token(minted_token)
    finally:
        app.dependency_overrides.pop(get_pool, None)


@pytest.mark.db
def test_list_audits_without_cookie_returns_only_demo_and_no_set_cookie(
    api_client: TestClient,
    imported_conn: psycopg.Connection,
) -> None:
    demo_id, _ = _seed_audit_row(
        imported_conn,
        session_token="demo-seed",
        is_demo=True,
        case_ref="DEMO-VISIBLE",
        note_verdict="contradiction",
        claim_verdicts=("contradicted",),
    )
    _seed_audit_row(
        imported_conn,
        session_token="private-session",
        is_demo=False,
        case_ref="PRIV-HIDDEN",
        note_verdict="full",
        claim_verdicts=("supported",),
    )

    api_client.cookies.clear()
    resp = api_client.get("/api/audits")
    assert resp.status_code == 200
    assert "set-cookie" not in resp.headers
    body = resp.json()
    assert [item["audit_id"] for item in body["items"]] == [demo_id]
    assert body["items"][0]["is_demo"] is True
    assert body["summary"]["demo_count"] == 1
    assert body["summary"]["session_count"] == 0
    assert body["summary"]["pending_count"] == 1
    assert body["summary"]["next_pending_audit_id"] == demo_id
    assert body["summary"]["next_pending_case_ref"] == "DEMO-VISIBLE"


@pytest.mark.db
def test_get_audit_without_cookie_allows_demo_and_hides_session_audit(
    api_client: TestClient,
    imported_conn: psycopg.Connection,
) -> None:
    demo_id, _ = _seed_audit_row(
        imported_conn,
        session_token="demo-seed",
        is_demo=True,
        case_ref="DEMO-OPEN",
        claim_verdicts=("supported",),
    )
    session_id, _ = _seed_audit_row(
        imported_conn,
        session_token="private-owner",
        is_demo=False,
        case_ref="PRIV-ONLY",
        claim_verdicts=("supported",),
    )

    api_client.cookies.clear()
    demo_resp = api_client.get(f"/api/audits/{demo_id}")
    assert demo_resp.status_code == 200
    assert "set-cookie" not in demo_resp.headers
    assert demo_resp.json()["is_demo"] is True
    assert demo_resp.json()["audit_id"] == demo_id

    private_resp = api_client.get(f"/api/audits/{session_id}")
    assert private_resp.status_code == 404
    assert "set-cookie" not in private_resp.headers


@pytest.mark.db
def test_put_decision_on_demo_without_cookie_mints_session_and_isolates_others(
    api_client: TestClient,
    imported_conn: psycopg.Connection,
) -> None:
    demo_id, claim_ids = _seed_audit_row(
        imported_conn,
        session_token="demo-seed",
        is_demo=True,
        case_ref="DEMO-DECISION",
        claim_verdicts=("supported",),
    )

    api_client.cookies.clear()
    put_resp = api_client.put(
        f"/api/audits/{demo_id}/claims/{claim_ids[0]}/decision",
        json={
            "decision": "agree_with_system",
            "justification": "Pierwszy zapis decyzji bez wcześniejszego ciasteczka.",
            "role_label": "editor",
        },
    )
    assert put_resp.status_code == 200
    set_cookie = put_resp.headers["set-cookie"]
    assert set_cookie.startswith(f"{COOKIE}=")
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/api" in set_cookie

    put_body = put_resp.json()
    assert put_body["is_demo"] is True
    assert put_body["decisions_count"] == 1
    assert put_body["decision_status"] == "saved"

    # Ta sama sesja widzi zapisaną decyzję na liście.
    own_list = api_client.get("/api/audits")
    assert own_list.status_code == 200
    assert own_list.json()["items"][0]["decisions_count"] == 1
    assert own_list.json()["items"][0]["decision_status"] == "saved"

    # Kolejna wizyta bez ciasteczka nadal widzi 0 decyzji i nie dostaje ciasteczka.
    api_client.cookies.clear()
    fresh_list = api_client.get("/api/audits")
    assert fresh_list.status_code == 200
    assert "set-cookie" not in fresh_list.headers
    assert fresh_list.json()["items"][0]["decisions_count"] == 0
    assert fresh_list.json()["items"][0]["decision_status"] == "pending"

    fresh_detail = api_client.get(f"/api/audits/{demo_id}")
    assert fresh_detail.status_code == 200
    assert "set-cookie" not in fresh_detail.headers
    assert fresh_detail.json()["decisions_count"] == 0
    assert fresh_detail.json()["decision_status"] == "pending"


@pytest.mark.db
def test_list_audits_isolates_session_audits_between_sessions(
    api_client: TestClient,
    imported_conn: psycopg.Connection,
    use_model: Callable[[BaseChatModel], None],
) -> None:
    model, note = _scripted_audit_model(imported_conn)
    use_model(model)

    create_resp = api_client.post(
        "/api/audits",
        json={
            "case_ref": "SESJA-A-1",
            "case_description": "Sprawa utworzona w sesji A.",
            "resolution_note": note,
        },
    )
    assert create_resp.status_code == 202
    audit_id = create_resp.json()["audit_id"]
    _poll_until_terminal(api_client, audit_id)
    session_a_token = api_client.cookies[COOKIE]

    # Sesja A widzi własną analizę na liście.
    list_a = api_client.get("/api/audits")
    assert list_a.status_code == 200
    body_a = list_a.json()
    assert [item["audit_id"] for item in body_a["items"]] == [audit_id]
    assert body_a["items"][0]["is_demo"] is False
    assert body_a["summary"]["session_count"] == 1

    # Sesja B nigdy nie widzi analizy sesji A.
    api_client.cookies.clear()
    api_client.cookies.set(COOKIE, "sesja-b-obca")
    list_b = api_client.get("/api/audits")
    assert list_b.status_code == 200
    body_b = list_b.json()
    assert audit_id not in [item["audit_id"] for item in body_b["items"]]
    assert body_b["summary"]["session_count"] == 0

    # Powrót do sesji A nadal widzi analizę.
    api_client.cookies.clear()
    api_client.cookies.set(COOKIE, session_a_token)
    list_a_again = api_client.get("/api/audits")
    assert list_a_again.status_code == 200
    assert [item["audit_id"] for item in list_a_again.json()["items"]] == [audit_id]


@pytest.mark.db
def test_list_audits_query_filters_narrow_items_but_keep_full_summary(
    api_client: TestClient,
    imported_conn: psycopg.Connection,
) -> None:
    session_token = "sesja-filtry"

    def _ctx(problem: str) -> dict[str, Any]:
        return {
            "problem": problem,
            "environment": "WebSphere 9.0 / Linux",
            "solution": "Korekta konfiguracji",
            "constraints": [],
            "missing_info": [],
        }

    demo_id, _ = _seed_audit_row(
        imported_conn,
        session_token="demo-seed",
        is_demo=True,
        case_ref="DEMO-SSL",
        case_description="Błąd certyfikatu SSL w WebSphere.",
        case_context=_ctx("Wygasły certyfikat SSL"),
        note_verdict="contradiction",
        claim_verdicts=("contradicted", "supported"),
    )
    in_progress_id, in_progress_claims = _seed_audit_row(
        imported_conn,
        session_token=session_token,
        is_demo=False,
        case_ref="INC-DB2",
        case_description="Timeout połączenia z DB2.",
        case_context=_ctx("Przekroczony limit czasu DB2"),
        note_verdict="partial",
        claim_verdicts=("supported", "insufficient"),
    )
    saved_id, saved_claims = _seed_audit_row(
        imported_conn,
        session_token=session_token,
        is_demo=False,
        case_ref="INC-OK",
        case_description="Konfiguracja puli wątków.",
        case_context=_ctx("Zbyt mała pula wątków"),
        note_verdict="full",
        claim_verdicts=("supported",),
    )

    api_client.cookies.set(COOKIE, session_token)
    assert (
        api_client.put(
            f"/api/audits/{in_progress_id}/claims/{in_progress_claims[0]}/decision",
            json={
                "decision": "agree_with_system",
                "justification": "Pierwsza z dwóch tez rozstrzygnięta.",
            },
        ).status_code
        == 200
    )
    assert (
        api_client.put(
            f"/api/audits/{saved_id}/claims/{saved_claims[0]}/decision",
            json={
                "decision": "agree_with_system",
                "justification": "Wszystkie tezy rozstrzygnięte.",
            },
        ).status_code
        == 200
    )

    expected_summary_counts = {
        "demo_count": 1,
        "session_count": 2,
        "pending_count": 1,
        "in_progress_count": 1,
        "saved_count": 1,
    }

    for params, expected_ids in (
        ({"source": "demo"}, [demo_id]),
        ({"source": "session"}, [in_progress_id, saved_id]),
        ({"decision_status": "pending"}, [demo_id]),
        ({"decision_status": "in_progress"}, [in_progress_id]),
        ({"decision_status": "saved"}, [saved_id]),
        ({"note_verdict": "contradiction"}, [demo_id]),
        ({"note_verdict": "partial"}, [in_progress_id]),
        ({"q": "db2"}, [in_progress_id]),
        ({"q": "certyfikat"}, [demo_id]),
    ):
        resp = api_client.get("/api/audits", params=params)
        assert resp.status_code == 200
        body = resp.json()
        assert [item["audit_id"] for item in body["items"]] == expected_ids
        for key, value in expected_summary_counts.items():
            assert body["summary"][key] == value
        assert body["summary"]["next_pending_audit_id"] in {demo_id, in_progress_id}
