"""Obserwowalność bez kluczy: brak wyjątków, handlera i połączeń sieciowych."""

import pytest
from fastapi import HTTPException
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from starlette.requests import Request

from app.answering.model import ModelNotConfiguredError, make_chat_model
from app.answering.prompts import prompt_version, prompt_versions
from app.observability import flush_traces, make_trace_handler, run_config
from app.session import COOKIE_NAME, hash_token, make_require_session, require_session
from app.settings import Settings


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return Settings(database_url="postgresql://x/y")


def test_no_handler_and_safe_flush_without_keys(settings: Settings) -> None:
    assert make_trace_handler(settings) is None
    flush_traces()


def test_run_config_has_name_metadata_and_no_session_data(settings: Settings) -> None:
    config = run_config(settings, chunk_set_id="set", k=8, handler=None)
    assert config["run_name"] == "answer"
    assert config["callbacks"] == []
    metadata = config["metadata"]
    assert metadata == {
        "chunk_set_id": "set",
        "k": 8,
        "chat_model": settings.chat_model,
        "chat_reasoning_effort": settings.chat_reasoning_effort,
        "prompt_versions": prompt_versions(),
    }
    assert not any("session" in key for key in metadata)


def test_prompt_version_is_12_hex_chars_and_distinct() -> None:
    versions = prompt_versions()
    assert set(versions) == {"draft", "verify", "detect_conflict"}
    for name, version in versions.items():
        assert version == prompt_version(name)
        assert len(version) == 12
        int(version, 16)
    assert len(set(versions.values())) == 3
    with pytest.raises(ValueError):
        prompt_version("nope")


def test_make_chat_model_requires_api_key(settings: Settings) -> None:
    with pytest.raises(ModelNotConfiguredError):
        make_chat_model(settings)


def test_make_chat_model_sets_timeout_and_model(settings: Settings) -> None:
    configured = Settings(
        database_url="postgresql://x/y",
        openai_api_key=SecretStr("sk-test"),
        chat_model="some-model",
        chat_timeout_s=7,
    )
    model = make_chat_model(configured)
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "some-model"
    assert model.request_timeout == 7


def test_run_config_supports_custom_name_prompts_and_metadata(
    settings: Settings,
) -> None:
    config = run_config(
        settings,
        chunk_set_id="set",
        k=6,
        handler=None,
        run_name="audit",
        prompt_versions_map={"extract": "aaaaaaaaaaaa", "verify": "bbbbbbbbbbbb"},
        extra_metadata={"audit_id": "abc-123", "claims_total": 4},
    )
    assert config["run_name"] == "audit"
    assert config["callbacks"] == []
    assert config["metadata"] == {
        "chunk_set_id": "set",
        "k": 6,
        "chat_model": settings.chat_model,
        "chat_reasoning_effort": settings.chat_reasoning_effort,
        "prompt_versions": {"extract": "aaaaaaaaaaaa", "verify": "bbbbbbbbbbbb"},
        "audit_id": "abc-123",
        "claims_total": 4,
    }


def test_run_config_rejects_session_keys_in_extra_metadata(settings: Settings) -> None:
    with pytest.raises(ValueError, match="sesji"):
        run_config(
            settings,
            chunk_set_id="set",
            k=8,
            handler=None,
            extra_metadata={"session_hash": "secret"},
        )


def test_settings_audit_defaults(settings: Settings) -> None:
    assert settings.audit_k == 8
    assert settings.audit_deadline_s == 90
    assert settings.audit_claim_concurrency == 3
    assert settings.audit_max_claims == 12


def test_make_require_session_custom_detail_and_cookie_hash() -> None:
    empty_request = Request({"type": "http", "headers": []})
    with pytest.raises(HTTPException) as answer_exc:
        require_session(empty_request)
    assert answer_exc.value.status_code == 404
    assert answer_exc.value.detail == "Nie znaleziono odpowiedzi"

    require_audit = make_require_session("Nie znaleziono analizy")
    with pytest.raises(HTTPException) as audit_exc:
        require_audit(empty_request)
    assert audit_exc.value.status_code == 404
    assert audit_exc.value.detail == "Nie znaleziono analizy"

    with_cookie = Request(
        {"type": "http", "headers": [(b"cookie", f"{COOKIE_NAME}=tok-123".encode())]}
    )
    assert require_audit(with_cookie) == hash_token("tok-123")
