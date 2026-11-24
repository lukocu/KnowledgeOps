"""Fabryka modelu czatu dla grafu odpowiedzi."""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.settings import Settings


class ModelNotConfiguredError(RuntimeError):
    """Brak `OPENAI_API_KEY`: odpowiedzi nie da się wygenerować."""


def make_chat_model(settings: Settings) -> BaseChatModel:
    """Tworzy model OpenAI z limitem czasu jednego wywołania.

    Bez ponowień (`max_retries=0`): limit `chat_timeout_s` obejmuje wywołanie,
    a budżet całego zapytania pilnuje `answer_deadline_s`.
    """
    if settings.openai_api_key is None:
        raise ModelNotConfiguredError("brak OPENAI_API_KEY")
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.openai_api_key,
        timeout=settings.chat_timeout_s,
        max_retries=0,
        reasoning_effort=settings.chat_reasoning_effort or None,
    )
