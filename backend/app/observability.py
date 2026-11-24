"""Ślad Langfuse: jeden ślad na pytanie. Bez kluczy ślad jest wyłączony (no-op)."""

import logging
import os
from collections.abc import Sequence

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


def make_trace_handler(settings: Settings) -> CallbackHandler | None:
    """Handler śladu albo `None`, gdy nie ustawiono kluczy (bez ostrzeżeń i sieci)."""
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
    elif not _keys_in_environment():
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
    retrieved_chunk_ids: Sequence[str] | None = None,
) -> RunnableConfig:
    """Konfiguracja przebiegu grafu: nazwa `answer`, metadane i handler śladu.

    Identyfikatory pobranych fragmentów są znane dopiero po `retrieve`, więc
    trafiają do śladu jako wynik tego węzła; tu można je podać tylko, gdy są znane.
    Do śladu nie trafia identyfikator sesji ani jego hash.
    """
    metadata: dict[str, object] = {
        "chunk_set_id": chunk_set_id,
        "k": k,
        "chat_model": settings.chat_model,
        "prompt_versions": prompt_versions(),
    }
    if retrieved_chunk_ids is not None:
        metadata["retrieved_chunk_ids"] = list(retrieved_chunk_ids)
    return RunnableConfig(
        run_name="answer",
        metadata=metadata,
        callbacks=[handler] if handler is not None else [],
    )
