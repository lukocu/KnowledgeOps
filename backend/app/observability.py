"""Ślad Langfuse: jeden ślad na pytanie. Bez kluczy ślad jest wyłączony (no-op)."""

import logging
import os

from langchain_core.runnables import RunnableConfig
from langfuse import Langfuse, get_client
from langfuse.langchain import CallbackHandler

from app.answering.prompts import prompt_versions
from app.settings import Settings

logger = logging.getLogger(__name__)

_client: Langfuse | None = None


def _keys_in_environment() -> bool:
    return bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
    )


def tracing_enabled(settings: Settings) -> bool:
    return (
        settings.langfuse_public_key is not None
        and settings.langfuse_secret_key is not None
    ) or _keys_in_environment()


def get_langfuse_client(settings: Settings) -> Langfuse | None:
    """Zwraca singleton klienta Langfuse albo `None`, gdy brak kluczy."""
    global _client
    if (
        settings.langfuse_public_key is not None
        and settings.langfuse_secret_key is not None
    ):
        if _client is None:
            _client = Langfuse(
                public_key=settings.langfuse_public_key.get_secret_value(),
                secret_key=settings.langfuse_secret_key.get_secret_value(),
                base_url=settings.langfuse_base_url,
            )
        return _client
    if _keys_in_environment():
        if _client is None:
            _client = get_client()
        return _client
    return None


def make_trace_handler(settings: Settings) -> CallbackHandler | None:
    """Handler śladu albo `None`, gdy nie ustawiono kluczy (bez ostrzeżeń i sieci)."""
    if get_langfuse_client(settings) is None:
        return None
    return CallbackHandler()


def flush_traces() -> None:
    """Wysyła zaległe ślady. Blokujące: wołaj w wątku. Bezpieczne bez kluczy."""
    if _client is None and not _keys_in_environment():
        return
    try:
        (_client or get_client()).flush()
    except Exception:
        logger.warning("Nie udało się wysłać śladów do Langfuse", exc_info=True)


def run_config(
    settings: Settings,
    *,
    chunk_set_id: str,
    k: int,
    handler: CallbackHandler | None,
) -> RunnableConfig:
    """Konfiguracja przebiegu grafu: nazwa `answer`, metadane i handler śladu.

    Identyfikatory pobranych fragmentów są znane dopiero po `retrieve`, więc
    trafiają do śladu jako wyjście spanu tego węzła, nie jako metadane.
    Do śladu nie trafia identyfikator sesji ani jego hash.
    """
    metadata: dict[str, object] = {
        "chunk_set_id": chunk_set_id,
        "k": k,
        "chat_model": settings.chat_model,
        "chat_reasoning_effort": settings.chat_reasoning_effort,
        "prompt_versions": prompt_versions(),
    }
    return RunnableConfig(
        run_name="answer",
        metadata=metadata,
        callbacks=[handler] if handler is not None else [],
    )
