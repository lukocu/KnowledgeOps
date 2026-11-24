"""Graf pytania: retrieve -> draft -> quote_check -> verify -> compose | abstain."""

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.answering.nodes import AnswerNodes, AnswerState, supported_claims
from app.db import AsyncPool
from app.settings import Settings

AnswerGraph = CompiledStateGraph[AnswerState, Any, AnswerState, AnswerState]


def initial_state(
    question: str, settings: Settings, *, chunk_set_id: str | None = None
) -> AnswerState:
    """Stan wejściowy: pytanie, zestaw fragmentów i k z ustawień."""
    return {
        "question": question,
        "chunk_set_id": chunk_set_id or settings.effective_chunk_set_id(),
        "k": settings.answer_k,
    }


def _after_retrieve(state: AnswerState) -> str:
    return "draft" if state["retrieved"] else "abstain"


def _after_draft(state: AnswerState) -> str:
    return "quote_check" if state["draft_claims"] else "abstain"


def _after_quote_check(state: AnswerState) -> str:
    # Gdy quote_check odrzucił wszystkie tezy, weryfikator nie ma czego oceniać:
    # pomijamy wywołanie modelu (i etap verify) i przechodzimy do abstencji.
    return "verify" if state["quoted"] else "abstain"


def _after_verify(state: AnswerState) -> str:
    return (
        "compose" if supported_claims(state["quoted"], state["verdicts"]) else "abstain"
    )


def build_answer_graph(
    *, chat_model: BaseChatModel, pool: AsyncPool, settings: Settings
) -> AnswerGraph:
    """Kompiluje graf odpowiedzi z wstrzykniętym modelem czatu i pulą połączeń.

    Zdarzenia etapów (`stream_mode="custom"`) pochodzą z węzłów; wynik jest w stanie
    końcowym (`outcome`, `answer`).
    """
    nodes = AnswerNodes(chat_model=chat_model, pool=pool, settings=settings)
    builder = StateGraph(AnswerState)
    builder.add_node("retrieve", nodes.retrieve)
    builder.add_node("draft", nodes.draft)
    builder.add_node("quote_check", nodes.quote_check)
    builder.add_node("verify", nodes.verify)
    builder.add_node("compose", nodes.compose)
    builder.add_node("abstain", nodes.abstain)

    builder.add_edge(START, "retrieve")
    builder.add_conditional_edges("retrieve", _after_retrieve, ["draft", "abstain"])
    builder.add_conditional_edges("draft", _after_draft, ["quote_check", "abstain"])
    builder.add_conditional_edges(
        "quote_check", _after_quote_check, ["verify", "abstain"]
    )
    builder.add_conditional_edges("verify", _after_verify, ["compose", "abstain"])
    builder.add_edge("compose", END)
    builder.add_edge("abstain", END)
    return builder.compile()
