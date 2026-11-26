"""Testy integracyjne API `/api/audits`: 202, postęp, wynik, sesja, walidacja."""

import asyncio
import threading
import time
import uuid
from collections.abc import Callable, Iterator
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

from app.api.answers import ChatModelFactory, get_chat_model_factory
from app.auditing.schemas import (
    CaseContext,
    ClaimVerdictOutput,
    ExtractedClaim,
    ExtractOutput,
)
from app.main import app
from app.session import hash_token
from app.settings import Settings
from app.techqa.search import search_chunks
from tests.conftest import LOOP_OPTIONS
from tests.techqa.helpers import CHUNK_SET_ID, SNAPSHOT_ID

pytestmark = pytest.mark.db

COOKIE = "kops_session"
QUERY_TERM = "information about this problem"


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
