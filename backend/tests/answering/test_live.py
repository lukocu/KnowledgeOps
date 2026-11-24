"""Kontrole na żywo: prawdziwy OpenAI i pełna migawka TechQA.

Pomijane domyślnie (`-m "not live"`) i bez `OPENAI_API_KEY`. Uruchomienie z `backend/`:

    set -a; . ../.env; set +a      # DATABASE_URL, OPENAI_API_KEY, opcjonalnie Langfuse
    uv run pytest -m live

Baza to `DATABASE_URL` (pełna migawka po imporcie), nie `temp_database`.
"""

import os
from typing import Any

import anyio
import pytest

from app.answering.graph import AnswerGraph, build_answer_graph, initial_state
from app.answering.model import make_chat_model
from app.answering.nodes import AnswerState
from app.answering.schemas import AbstainedResult, AnsweredResult
from app.db import AsyncPool
from app.observability import flush_traces, make_trace_handler, run_config
from app.settings import Settings
from tests.answering.helpers import run_graph

pytestmark = [pytest.mark.live, pytest.mark.anyio]

# TRAIN_Q000 (data/raw/techqa/train.json), dosłownie.
TRAIN_Q000 = (
    "User environment variables no longer getting picked up after upgrade to "
    "4.1.1.1 or 4.1.1.2?\n\n\n\n"
    "Have you found that after upgrade to Streams 4.1.1.1 or 4.1.1.2, that "
    "environment variables set in your .bashrc are no longer being set? For "
    "example ODBCINI is not set for the database toolkit and you get\n\n"
    "     An SQL operation failed. The SQL state is 08003, the SQL code\n"
    "     is 0 and the SQL message is [unixODBC][Driver\n"
    "     Manager]Connnection does not exist.\n"
)
Q000_DOC_ID = "swg21996508"

# Kontrola abstencji: TRAIN_Q002, dosłownie z abstention-check.md.
ABSTENTION_QUESTION = (
    "Why are replies going to the DLQ with reason 2189 MQRC_CLUSTER_RESOLUTION_ERROR"
    "\n\n"
    "I have changed my cluster receiver to match the IP address used and now I am "
    "seeing replies in my DLQ with 2189 MQRC_CLUSTER_RESOLUTION_ERROR. The reply "
    "queue is on a different cluster which this qmgr is a member of. The reply "
    "message uses replytoqmgr and queue name. The qmgr should see the replytoqmgr "
    "in the cluster and get the message over to the queue, but instead goes to "
    "dead letter queue. This queue manager is a repository to one cluster and a "
    "member of another. "
)


@pytest.fixture
def live_settings() -> Settings:
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("brak OPENAI_API_KEY")
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("brak DATABASE_URL")
    return Settings()


async def ask(
    question: str, pool: AsyncPool, settings: Settings
) -> tuple[AnswerState, list[dict[str, Any]]]:
    graph: AnswerGraph = build_answer_graph(
        chat_model=make_chat_model(settings), pool=pool, settings=settings
    )
    state = initial_state(question, settings)
    handler = make_trace_handler(settings)
    config = run_config(
        settings, chunk_set_id=state["chunk_set_id"], k=state["k"], handler=handler
    )
    try:
        events, final = await run_graph(graph, state, config)
    finally:
        await anyio.to_thread.run_sync(flush_traces)
    return final, events


async def test_train_q000_is_answered_with_citation_to_swg21996508(
    live_pool: AsyncPool, live_settings: Settings
) -> None:
    state, events = await ask(TRAIN_Q000, live_pool, live_settings)

    assert state["outcome"] == "answered", events
    result = state["answer"]
    assert isinstance(result, AnsweredResult)
    assert result.claims
    assert Q000_DOC_ID in {citation.doc_id for citation in result.citations}


async def test_abstention_control_question_abstains(
    live_pool: AsyncPool, live_settings: Settings
) -> None:
    state, events = await ask(ABSTENTION_QUESTION, live_pool, live_settings)

    assert state["outcome"] == "abstained", events
    result = state["answer"]
    assert isinstance(result, AbstainedResult)
    assert result.checked_chunks
