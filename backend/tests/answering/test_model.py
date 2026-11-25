"""Fabryka modelu czatu: OpenAI domyślnie, OpenRouter przez `OPENAI_BASE_URL`."""

import pytest
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.answering.model import ModelNotConfiguredError, make_chat_model
from app.settings import Settings


def settings(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]


def test_missing_key_raises() -> None:
    with pytest.raises(ModelNotConfiguredError):
        make_chat_model(settings(openai_api_key=None))


def test_openai_default_sends_reasoning_effort_and_no_extra_body() -> None:
    model = make_chat_model(settings(openai_api_key=SecretStr("k")))
    assert isinstance(model, ChatOpenAI)
    assert model.reasoning_effort == "low"
    assert not model.extra_body
    assert model.max_retries == 0


def test_base_url_requires_parameters_and_disables_reasoning() -> None:
    model = make_chat_model(
        settings(
            openai_api_key=SecretStr("k"),
            openai_base_url="https://openrouter.ai/api/v1",
            chat_model="deepseek/deepseek-v4.1-flash",
            chat_reasoning_effort="none",
        )
    )
    assert isinstance(model, ChatOpenAI)
    assert model.openai_api_base == "https://openrouter.ai/api/v1"
    assert model.reasoning_effort is None
    assert model.extra_body == {
        "provider": {"require_parameters": True},
        "reasoning": {"enabled": False},
    }


def test_base_url_maps_effort_to_reasoning_object() -> None:
    model = make_chat_model(
        settings(
            openai_api_key=SecretStr("k"),
            openai_base_url="https://openrouter.ai/api/v1",
            chat_reasoning_effort="low",
        )
    )
    assert isinstance(model, ChatOpenAI)
    assert model.extra_body is not None
    assert model.extra_body["reasoning"] == {"effort": "low"}
