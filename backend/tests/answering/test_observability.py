"""Obserwowalność bez kluczy: brak wyjątków, handlera i połączeń sieciowych."""

import pytest
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.answering.model import ModelNotConfiguredError, make_chat_model
from app.answering.prompts import prompt_version, prompt_versions
from app.observability import flush_traces, make_trace_handler, run_config
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
    assert set(versions) == {"draft", "verify"}
    for name, version in versions.items():
        assert version == prompt_version(name)
        assert len(version) == 12
        int(version, 16)
    assert versions["draft"] != versions["verify"]
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
