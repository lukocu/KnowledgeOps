"""Uruchamianie grafu w testach: zdarzenia etapów i stan końcowy."""

from typing import Any, cast

from langchain_core.runnables import RunnableConfig

from app.answering.graph import AnswerGraph
from app.answering.nodes import AnswerState


async def run_graph(
    graph: AnswerGraph, state: AnswerState, config: RunnableConfig | None = None
) -> tuple[list[dict[str, Any]], AnswerState]:
    """Zwraca zdarzenia etapów (tryb `custom`) i stan końcowy (tryb `values`)."""
    events: list[dict[str, Any]] = []
    final: AnswerState = {}
    async for mode, chunk in graph.astream(
        state, config, stream_mode=["custom", "values"]
    ):
        if mode == "custom":
            events.append(cast(dict[str, Any], chunk))
        else:
            final = cast(AnswerState, chunk)
    return events, final
