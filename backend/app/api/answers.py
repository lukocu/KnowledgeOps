"""Endpointy odpowiedzi: strumień SSE (postęp, wynik) i odczyt zapisanej odpowiedzi."""

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from datetime import datetime
from typing import Annotated, Any, Literal, cast

import anyio
import openai
import psycopg
import psycopg_pool
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.sse import EventSourceResponse, ServerSentEvent
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from langfuse.langchain import CallbackHandler
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, StringConstraints, ValidationError

from app.answering.graph import build_answer_graph, initial_state
from app.answering.model import ModelNotConfiguredError, make_chat_model
from app.answering.nodes import AnswerState
from app.answering.prompts import prompt_versions
from app.answering.schemas import AnswerResult
from app.db import CONNECTION_TIMEOUT_S, PoolDep, http_connection
from app.observability import flush_traces, make_trace_handler, run_config
from app.retrieval import get_corpus_info
from app.session import ExistingSessionDep, SessionDep
from app.settings import Settings, SettingsDep

logger = logging.getLogger(__name__)

MAX_QUESTION_LENGTH = 2000

router = APIRouter(prefix="/api", tags=["answers"])

ChatModelFactory = Callable[[Settings], BaseChatModel]
ErrorCode = Literal[
    "model_unavailable", "model_not_configured", "database_unavailable", "internal"
]

# Błędy po stronie modelu: limity czasu, odpowiedź poza schematem, błąd API.
MODEL_ERRORS = (
    TimeoutError,
    ValidationError,
    OutputParserException,
    openai.OpenAIError,
)
DATABASE_ERRORS = (psycopg.OperationalError, psycopg_pool.PoolTimeout)

ERROR_MESSAGES: dict[ErrorCode, str] = {
    "model_unavailable": "Model nie odpowiedział poprawnie w wymaganym czasie.",
    "model_not_configured": "Brak klucza modelu (OPENAI_API_KEY) w konfiguracji.",
    "database_unavailable": "Baza danych jest niedostępna.",
    "internal": "Wystąpił nieoczekiwany błąd.",
}


def get_chat_model_factory() -> ChatModelFactory:
    """Zależność: fabryka modelu czatu (testy podmieniają ją fałszywym modelem)."""
    return make_chat_model


ChatModelFactoryDep = Annotated[ChatModelFactory, Depends(get_chat_model_factory)]


class AnswerRequest(BaseModel):
    question: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_LENGTH
        ),
    ]


class StageEvent(BaseModel):
    """Zdarzenie etapu grafu (`event: stage`)."""

    stage: Literal[
        "retrieve",
        "draft",
        "quote_check",
        "verify",
        "detect_conflict",
        "compose",
        "abstain",
    ]
    status: Literal["started", "done"]
    data: dict[str, Any] = Field(default_factory=dict)


class ResultEvent(BaseModel):
    """Odpowiedź zapisana, czytelna przez `GET /api/answers/{id}` (`event: result`)."""

    answer_id: str
    outcome: Literal["answered", "abstained", "conflicting"]


class ErrorEvent(BaseModel):
    """Błąd przebiegu (`event: error`); `answer_id` gdy zapisano wiersz `failed`."""

    answer_id: str | None
    code: ErrorCode
    message: str


class AnswerRecord(BaseModel):
    id: str
    question: str
    outcome: Literal["answered", "abstained", "conflicting", "failed"]
    result: Annotated[AnswerResult, Field(discriminator="outcome")] | None
    snapshot_id: str
    chunk_set_id: str
    config: dict[str, Any]
    created_at: datetime
    duration_ms: int | None


def _error_event(code: ErrorCode, answer_id: str | None = None) -> ServerSentEvent:
    return ServerSentEvent(
        event="error",
        data=ErrorEvent(answer_id=answer_id, code=code, message=ERROR_MESSAGES[code]),
    )


async def _insert_answer(
    pool: PoolDep,
    *,
    answer_id: str,
    session_hash: str,
    question: str,
    outcome: str,
    snapshot_id: str,
    chunk_set_id: str,
    result: AnswerResult | None,
    config: dict[str, Any],
    error: str | None,
    trace_id: str | None,
    duration_ms: int,
) -> None:
    async with pool.connection(timeout=CONNECTION_TIMEOUT_S) as conn:
        await conn.execute(
            "INSERT INTO answers (id, session_hash, question, outcome, snapshot_id,"
            " chunk_set_id, result, config, error, trace_id, duration_ms)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                answer_id,
                session_hash,
                question,
                outcome,
                snapshot_id,
                chunk_set_id,
                Jsonb(result.model_dump(mode="json")) if result is not None else None,
                Jsonb(config),
                error,
                trace_id,
                duration_ms,
            ),
        )


def _classify(exc: Exception) -> ErrorCode:
    if isinstance(exc, MODEL_ERRORS):
        return "model_unavailable"
    return "internal"


@router.post(
    "/answers",
    response_class=EventSourceResponse,
    responses={
        200: {
            "description": (
                "Strumień zdarzeń: `stage` (postęp), potem `result` albo `error`."
            ),
            "model": StageEvent | ResultEvent | ErrorEvent,
        }
    },
)
async def create_answer(
    body: AnswerRequest,
    pool: PoolDep,
    session_hash: SessionDep,
    settings: SettingsDep,
    chat_model_factory: ChatModelFactoryDep,
) -> AsyncIterator[ServerSentEvent]:
    started = time.monotonic()
    handler: CallbackHandler | None = None
    try:
        try:
            chat_model = chat_model_factory(settings)
        except ModelNotConfiguredError:
            yield _error_event("model_not_configured")
            return

        chunk_set_id = settings.effective_chunk_set_id()
        try:
            async with pool.connection(timeout=CONNECTION_TIMEOUT_S) as conn:
                snapshot_id = (await get_corpus_info(conn, chunk_set_id)).snapshot_id
        except DATABASE_ERRORS:
            logger.warning("Baza niedostępna", exc_info=True)
            yield _error_event("database_unavailable")
            return
        except LookupError:
            logger.exception("Brak zaimportowanego zestawu fragmentów")
            yield _error_event("internal")
            return

        config: dict[str, Any] = {
            "chat_model": settings.chat_model,
            "chat_reasoning_effort": settings.chat_reasoning_effort,
            "k": settings.answer_k,
            "chunk_set_id": chunk_set_id,
            "prompt_versions": prompt_versions(),
        }
        answer_id = str(uuid.uuid4())
        question = body.question

        def duration_ms() -> int:
            return int((time.monotonic() - started) * 1000)

        handler = make_trace_handler(settings)
        graph = build_answer_graph(chat_model=chat_model, pool=pool, settings=settings)
        run_cfg = run_config(
            settings,
            chunk_set_id=chunk_set_id,
            k=settings.answer_k,
            handler=handler,
        )
        final: AnswerState = {}
        failure: ErrorCode | None = None
        failure_detail = ""
        stream = cast(
            AsyncGenerator[tuple[str, Any]],
            graph.astream(
                initial_state(question, settings, chunk_set_id=chunk_set_id),
                run_cfg,
                stream_mode=["custom", "values"],
            ),
        )
        # Termin obejmuje tylko pobranie kolejnego zdarzenia grafu, nie `yield`:
        # anulowanie w trakcie zapisu do klienta nie zamieni się w TimeoutError
        # poza blokiem (PEP 789), więc przekroczenie zawsze daje `failed`.
        deadline = asyncio.get_running_loop().time() + settings.answer_deadline_s
        try:
            while True:
                async with asyncio.timeout_at(deadline):
                    try:
                        mode, chunk = await anext(stream)
                    except StopAsyncIteration:
                        break
                if mode == "custom":
                    yield ServerSentEvent(
                        event="stage",
                        data=StageEvent.model_validate(chunk),
                    )
                else:
                    final = cast(AnswerState, chunk)
        except DATABASE_ERRORS:
            logger.warning("Baza niedostępna w trakcie odpowiedzi", exc_info=True)
            yield _error_event("database_unavailable")
            return
        except Exception as exc:
            logger.warning("Przebieg odpowiedzi nie powiódł się", exc_info=True)
            failure = _classify(exc)
            failure_detail = f"{type(exc).__name__}: {exc}"
        finally:
            await stream.aclose()

        trace_id = getattr(handler, "last_trace_id", None) if handler else None
        config["chunk_set_ids"] = final.get("chunk_set_ids", [chunk_set_id])

        if failure is not None or "answer" not in final:
            code: ErrorCode = failure or "internal"
            try:
                await _insert_answer(
                    pool,
                    answer_id=answer_id,
                    session_hash=session_hash,
                    question=question,
                    outcome="failed",
                    snapshot_id=snapshot_id,
                    chunk_set_id=chunk_set_id,
                    result=None,
                    config=config,
                    error=failure_detail or code,
                    trace_id=trace_id,
                    duration_ms=duration_ms(),
                )
            except DATABASE_ERRORS:
                logger.warning("Nie zapisano nieudanej odpowiedzi", exc_info=True)
                yield _error_event(code)
                return
            yield _error_event(code, answer_id)
            return

        result = final["answer"]
        outcome = result.outcome
        try:
            await _insert_answer(
                pool,
                answer_id=answer_id,
                session_hash=session_hash,
                question=question,
                outcome=outcome,
                snapshot_id=snapshot_id,
                chunk_set_id=chunk_set_id,
                result=result,
                config=config,
                error=None,
                trace_id=trace_id,
                duration_ms=duration_ms(),
            )
        except DATABASE_ERRORS:
            logger.warning("Nie zapisano odpowiedzi", exc_info=True)
            yield _error_event("database_unavailable")
            return
        yield ServerSentEvent(
            event="result", data=ResultEvent(answer_id=answer_id, outcome=outcome)
        )
    finally:
        if handler is not None:
            # Blokujące wysyłanie śladów poza pętlą zdarzeń; osłonięte przed anulowaniem
            # (np. po rozłączeniu klienta).
            with anyio.CancelScope(shield=True):
                await run_in_threadpool(flush_traces)


@router.get(
    "/answers/{answer_id}",
    response_model=AnswerRecord,
    responses={404: {"description": "Brak odpowiedzi w tej sesji"}},
)
async def get_answer(
    answer_id: str, pool: PoolDep, session_hash: ExistingSessionDep
) -> AnswerRecord:
    not_found = HTTPException(status.HTTP_404_NOT_FOUND, "Nie znaleziono odpowiedzi")
    try:
        uuid.UUID(answer_id)
    except ValueError:
        raise not_found from None
    async with http_connection(pool) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id::text AS id, question, outcome, result, snapshot_id,"
                " chunk_set_id, config, created_at, duration_ms FROM answers"
                " WHERE id = %s AND session_hash = %s",
                (answer_id, session_hash),
            )
            row = await cur.fetchone()
    if row is None:
        raise not_found
    return AnswerRecord.model_validate(row)
