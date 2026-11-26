"""Fabryki modeli czatu dla grafu odpowiedzi i sędziego ewaluacji."""

from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.settings import Settings


class ModelNotConfiguredError(RuntimeError):
    """Brak klucza API modelu: wywołania nie da się wykonać."""


@dataclass(frozen=True)
class JudgeModelInfo:
    """Metadane aktywnego modelu sędziego ewaluacji (w tym jawny fallback)."""

    model: str
    reasoning_effort: str
    is_fallback_to_chat_model: bool


def _build_openai_chat(
    *,
    model: str,
    api_key: SecretStr,
    base_url: str | None,
    timeout_s: float,
    reasoning_effort: str,
) -> ChatOpenAI:
    """Buduje klienta `ChatOpenAI` z obsługą OpenRouter i innych dostawców."""
    normalized_base_url = base_url or None
    if normalized_base_url and "openrouter.ai" in normalized_base_url:
        extra_body: dict[str, Any] = {"provider": {"require_parameters": True}}
        if reasoning_effort == "none":
            extra_body["reasoning"] = {"enabled": False}
        else:
            extra_body["reasoning"] = {"effort": reasoning_effort}
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=normalized_base_url,
            timeout=timeout_s,
            max_retries=0,
            extra_body=extra_body,
        )
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=normalized_base_url,
        timeout=timeout_s,
        max_retries=0,
        reasoning_effort=None if reasoning_effort == "none" else reasoning_effort,
    )


def make_chat_model(settings: Settings) -> BaseChatModel:
    """Tworzy model czatu z limitem czasu jednego wywołania.

    Bez ponowień (`max_retries=0`): limit `chat_timeout_s` obejmuje wywołanie,
    a budżet całego zapytania pilnuje `answer_deadline_s`.

    `OPENAI_BASE_URL` wskazuje dostawcę zgodnego z OpenAI. Dla OpenRouter żądanie
    wymusza dostawcę z obsługą parametrów (strict json_schema), a rozumowanie
    ustawia obiekt `reasoning` (`CHAT_REASONING_EFFORT=none` je wyłącza). Inni
    dostawcy (np. Gemini) dostają zwykły `reasoning_effort`; `none` go pomija.
    """
    if settings.openai_api_key is None:
        raise ModelNotConfiguredError("brak OPENAI_API_KEY")
    return _build_openai_chat(
        model=settings.chat_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout_s=settings.chat_timeout_s,
        reasoning_effort=settings.chat_reasoning_effort,
    )


def make_judge_model(settings: Settings) -> tuple[BaseChatModel, JudgeModelInfo]:
    """Tworzy model sędziego ewaluacji z jawnym fallbackiem na ustawienia `CHAT_*`.

    Gdy `EVAL_JUDGE_MODEL` nie jest ustawiony, używa `CHAT_MODEL` i oznacza to
    flagą `is_fallback_to_chat_model=True` w `JudgeModelInfo`.
    """
    api_key = (
        settings.eval_judge_api_key
        if settings.eval_judge_api_key is not None
        else settings.openai_api_key
    )
    if api_key is None:
        raise ModelNotConfiguredError("brak EVAL_JUDGE_API_KEY ani OPENAI_API_KEY")

    is_fallback = not settings.eval_judge_model
    model_name = settings.eval_judge_model or settings.chat_model
    reasoning_effort = (
        settings.eval_judge_reasoning_effort or settings.chat_reasoning_effort
    )
    base_url = settings.eval_judge_base_url or settings.openai_base_url or None

    client = _build_openai_chat(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        timeout_s=settings.eval_judge_timeout_s,
        reasoning_effort=reasoning_effort,
    )
    info = JudgeModelInfo(
        model=model_name,
        reasoning_effort=reasoning_effort,
        is_fallback_to_chat_model=is_fallback,
    )
    return client, info
