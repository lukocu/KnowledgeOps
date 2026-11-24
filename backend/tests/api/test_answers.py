"""API odpowiedzi na fałszywym modelu: strumień SSE, sesja, zapis i odczyt."""

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable, RunnableLambda

from app.answering.schemas import ClaimVerdict, DraftClaim, DraftOutput, VerifyOutput
from app.api.answers import ChatModelFactory, get_chat_model_factory
from app.main import app
from app.settings import Settings
from app.techqa.chunking import ChunkerConfig
from app.techqa.importer import import_snapshot
from app.techqa.search import search_chunks
from tests.answering.fakes import Script, ScriptedChatModel
from tests.techqa.helpers import CHUNK_SET_ID, SNAPSHOT_ID, build_snapshot

pytestmark = pytest.mark.db

QUESTION = "information about this problem"
COOKIE = "kops_session"


class FailingChatModel(BaseChatModel):
    """Model, którego każde wywołanie kończy się limitem czasu."""

    @property
    def _llm_type(self) -> str:
        return "failing-fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise AssertionError("graf ma używać wyłącznie with_structured_output")

    def with_structured_output(
        self, schema: Any, **kwargs: Any
    ) -> Runnable[LanguageModelInput, Any]:
        def fail(_: LanguageModelInput) -> Any:
            raise TimeoutError("limit czasu modelu")

        return RunnableLambda(fail)


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


def scripted_answer(conn: psycopg.Connection) -> ScriptedChatModel:
    """Model, który cytuje dwa najlepsze fragmenty i je uznaje za poparte."""
    hits = search_chunks(conn, QUESTION, method="bm25", chunk_set_id=CHUNK_SET_ID, k=8)
    assert len(hits) >= 2, "mini-migawka ma za mało trafień"
    claims = [
        DraftClaim(
            text=f"Claim {i}.",
            code=None,
            chunk_id=hit.chunk_id,
            quote=hit.snippet[:40].strip(),
        )
        for i, hit in enumerate(hits[:2])
    ]
    verdicts = [
        ClaimVerdict(claim_index=i, reasoning="r", verdict="supported")
        for i in range(len(claims))
    ]
    script = Script(
        drafts=[DraftOutput(claims=claims)], verifies=[VerifyOutput(verdicts=verdicts)]
    )
    return ScriptedChatModel(script=script)


def parse_sse(text: str) -> list[tuple[str, Any]]:
    events: list[tuple[str, Any]] = []
    for block in text.split("\n\n"):
        name = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data += line.removeprefix("data:").strip()
        if name:
            events.append((name, json.loads(data)))
    return events


def post(client: TestClient, question: str = QUESTION) -> list[tuple[str, Any]]:
    response = client.post("/api/answers", json={"question": question})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return parse_sse(response.text)


def count_answers(conn: psycopg.Connection) -> int:
    row = conn.execute("SELECT count(*) FROM answers").fetchone()
    assert row is not None
    return int(row[0])


def test_stream_has_stages_in_order_and_ends_with_result(
    api_client: TestClient,
    imported_conn: psycopg.Connection,
    use_model: Callable[[BaseChatModel], None],
) -> None:
    use_model(scripted_answer(imported_conn))
    events = post(api_client)

    names = [name for name, _ in events]
    assert set(names[:-1]) == {"stage"}
    assert names[-1] == "result"
    stages = [(d["stage"], d["status"]) for name, d in events if name == "stage"]
    assert stages == [
        ("retrieve", "started"),
        ("retrieve", "done"),
        ("draft", "started"),
        ("draft", "done"),
        ("quote_check", "started"),
        ("quote_check", "done"),
        ("verify", "started"),
        ("verify", "done"),
        ("compose", "started"),
        ("compose", "done"),
    ]
    result = events[-1][1]
    assert result["outcome"] == "answered"
    assert count_answers(imported_conn) == 1


def test_session_cookie_is_issued_httponly_and_only_hash_is_stored(
    api_client: TestClient,
    imported_conn: psycopg.Connection,
    use_model: Callable[[BaseChatModel], None],
) -> None:
    use_model(scripted_answer(imported_conn))
    response = api_client.post("/api/answers", json={"question": QUESTION})
    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith(f"{COOKIE}=")
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/api" in set_cookie
    assert "Secure" not in set_cookie

    token = api_client.cookies[COOKIE]
    row = imported_conn.execute("SELECT session_hash FROM answers").fetchone()
    assert row is not None
    assert row[0] != token
    assert len(row[0]) == 64


def test_get_in_same_session_returns_saved_result(
    api_client: TestClient,
    imported_conn: psycopg.Connection,
    use_model: Callable[[BaseChatModel], None],
) -> None:
    use_model(scripted_answer(imported_conn))
    answer_id = post(api_client)[-1][1]["answer_id"]

    response = api_client.get(f"/api/answers/{answer_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == answer_id
    assert body["question"] == QUESTION
    assert body["outcome"] == "answered"
    assert body["snapshot_id"] == SNAPSHOT_ID
    assert body["chunk_set_id"] == CHUNK_SET_ID
    assert [c["text"] for c in body["result"]["claims"]] == ["Claim 0.", "Claim 1."]
    assert body["config"]["k"] == 8
    assert set(body["config"]["prompt_versions"]) == {"draft", "verify"}
    assert body["duration_ms"] is not None


def test_other_or_missing_cookie_is_404(
    api_client: TestClient,
    imported_conn: psycopg.Connection,
    use_model: Callable[[BaseChatModel], None],
) -> None:
    use_model(scripted_answer(imported_conn))
    answer_id = post(api_client)[-1][1]["answer_id"]

    api_client.cookies.clear()
    api_client.cookies.set(COOKIE, "inna-sesja", domain="testserver", path="/api")
    assert api_client.get(f"/api/answers/{answer_id}").status_code == 404

    # Druga, prawdziwa sesja (wydana przez POST) też nie widzi cudzej odpowiedzi.
    api_client.cookies.clear()
    use_model(scripted_answer(imported_conn))
    post(api_client, "Inne pytanie drugiej sesji")
    assert COOKIE in api_client.cookies
    assert api_client.get(f"/api/answers/{answer_id}").status_code == 404

    api_client.cookies.clear()
    response = api_client.get(f"/api/answers/{answer_id}")
    assert response.status_code == 404
    assert "set-cookie" not in response.headers


def test_unknown_or_malformed_id_is_404(api_client: TestClient) -> None:
    api_client.cookies.set(COOKIE, "jakas-sesja", domain="testserver", path="/api")
    unknown = "00000000-0000-4000-8000-000000000000"
    assert api_client.get(f"/api/answers/{unknown}").status_code == 404
    assert api_client.get("/api/answers/nie-uuid").status_code == 404


def test_model_failure_saves_failed_row_and_sends_error(
    api_client: TestClient,
    imported_conn: psycopg.Connection,
    use_model: Callable[[BaseChatModel], None],
) -> None:
    use_model(FailingChatModel())
    events = post(api_client)

    name, data = events[-1]
    assert name == "error"
    assert data["code"] == "model_unavailable"
    assert data["answer_id"] is not None
    row = imported_conn.execute(
        "SELECT outcome, result, error FROM answers WHERE id = %s", (data["answer_id"],)
    ).fetchone()
    assert row is not None
    assert row[0] == "failed"
    assert row[1] is None
    assert "TimeoutError" in row[2]

    record = api_client.get(f"/api/answers/{data['answer_id']}").json()
    assert record["outcome"] == "failed"
    assert record["result"] is None


def test_missing_api_key_sends_error_without_row(
    api_client: TestClient, imported_conn: psycopg.Connection
) -> None:
    events = post(api_client)
    assert len(events) == 1
    name, data = events[0]
    assert name == "error"
    assert data["code"] == "model_not_configured"
    assert data["answer_id"] is None
    assert count_answers(imported_conn) == 0


@pytest.mark.parametrize("question", ["", "   ", "x" * 2001])
def test_invalid_question_is_422(api_client: TestClient, question: str) -> None:
    response = api_client.post("/api/answers", json={"question": question})
    assert response.status_code == 422


def test_answer_survives_snapshot_reimport(
    api_client: TestClient,
    imported_conn: psycopg.Connection,
    use_model: Callable[[BaseChatModel], None],
    tmp_path: Path,
) -> None:
    use_model(scripted_answer(imported_conn))
    answer_id = post(api_client)[-1][1]["answer_id"]

    again = tmp_path / "again"
    again.mkdir()
    data_dir, manifest = build_snapshot(again)
    import_snapshot(imported_conn, data_dir, manifest, ChunkerConfig())

    assert count_answers(imported_conn) == 1
    record = api_client.get(f"/api/answers/{answer_id}")
    assert record.status_code == 200
    assert record.json()["outcome"] == "answered"
