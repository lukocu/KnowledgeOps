"""Fabryka modelu czatu dla grafu odpowiedzi."""

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.settings import Settings


class ModelNotConfiguredError(RuntimeError):
    """Brak `OPENAI_API_KEY`: odpowiedzi nie da się wygenerować."""


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
    effort = settings.chat_reasoning_effort
    base_url = settings.openai_base_url or None
    if base_url and "openrouter.ai" in base_url:
        extra_body: dict[str, Any] = {"provider": {"require_parameters": True}}
        if effort == "none":
            extra_body["reasoning"] = {"enabled": False}
        else:
            extra_body["reasoning"] = {"effort": effort}
        return ChatOpenAI(
            model=settings.chat_model,
            api_key=settings.openai_api_key,
            base_url=base_url,
            timeout=settings.chat_timeout_s,
            max_retries=0,
            extra_body=extra_body,
        )
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.openai_api_key,
        base_url=base_url,
        timeout=settings.chat_timeout_s,
        max_retries=0,
        reasoning_effort=None if effort == "none" else effort,
    )
