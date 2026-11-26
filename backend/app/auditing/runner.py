"""Zarządzanie zadaniami audytu w tle powiązanymi z cyklem życia aplikacji."""

import asyncio
import logging
import time
from typing import Annotated, cast

import anyio
from fastapi import Depends, Request
from fastapi.concurrency import run_in_threadpool
from langchain_core.language_models.chat_models import BaseChatModel
from langfuse.langchain import CallbackHandler

from app.auditing.graph import (
    AuditProgressUpdate,
    AuditState,
    build_audit_graph,
    initial_audit_state,
)
from app.auditing.prompts import prompt_versions
from app.auditing.store import (
    NoteVerdict,
    complete_audit,
    fail_audit,
    update_audit_progress,
)
from app.db import CONNECTION_TIMEOUT_S, AsyncPool
from app.observability import flush_traces, make_trace_handler, run_config
from app.settings import Settings

logger = logging.getLogger(__name__)


async def _mark_failed(
    pool: AsyncPool,
    audit_id: str,
    *,
    error: str,
    trace_id: str | None,
    duration_ms: int,
) -> None:
    """Zapisuje stan `failed` w krótkiej transakcji; loguje błąd przy awarii DB."""
    try:
        async with pool.connection(timeout=CONNECTION_TIMEOUT_S) as conn:
            await fail_audit(
                conn,
                audit_id,
                error=error,
                trace_id=trace_id,
                duration_ms=duration_ms,
            )
    except Exception:
        logger.warning("Nie udało się zapisać błędu audytu %s", audit_id, exc_info=True)


class AuditTaskManager:
    """Rejestr aktywnych zadań audytu w tle, zamykany przy shutdown aplikacji."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    def schedule(
        self,
        audit_id: str,
        *,
        pool: AsyncPool,
        settings: Settings,
        chat_model: BaseChatModel,
        case_description: str,
        resolution_note: str,
        chunk_set_id: str,
        include_synthetic: bool,
        k: int,
    ) -> asyncio.Task[None]:
        """Uruchamia graf audytu jako zarządzane zadanie `asyncio.Task`."""
        task = asyncio.create_task(
            self._run_audit(
                audit_id,
                pool=pool,
                settings=settings,
                chat_model=chat_model,
                case_description=case_description,
                resolution_note=resolution_note,
                chunk_set_id=chunk_set_id,
                include_synthetic=include_synthetic,
                k=k,
            ),
            name=f"audit-{audit_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def shutdown(self) -> None:
        """Anuluje wszystkie aktywne zadania audytu i czeka na ich zakończenie."""
        if not self._tasks:
            return
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def _run_audit(
        self,
        audit_id: str,
        *,
        pool: AsyncPool,
        settings: Settings,
        chat_model: BaseChatModel,
        case_description: str,
        resolution_note: str,
        chunk_set_id: str,
        include_synthetic: bool,
        k: int,
    ) -> None:
        started = time.monotonic()

        def duration_ms() -> int:
            return int((time.monotonic() - started) * 1000)

        handler: CallbackHandler | None = make_trace_handler(settings)

        async def _on_progress(update: AuditProgressUpdate) -> None:
            async with pool.connection(timeout=CONNECTION_TIMEOUT_S) as conn:
                await update_audit_progress(
                    conn,
                    audit_id,
                    stage=update.stage,
                    status="running",
                    claims_total=update.claims_total,
                    claims_done=update.claims_done,
                    case_context=update.case_context,
                )

        graph = build_audit_graph(
            chat_model=chat_model,
            settings=settings,
            pool=pool,
            on_progress=_on_progress,
        )
        run_cfg = run_config(
            settings,
            chunk_set_id=chunk_set_id,
            k=k,
            handler=handler,
            run_name="audit",
            prompt_versions_map=prompt_versions(),
            extra_metadata={
                "audit_id": audit_id,
                "include_synthetic": include_synthetic,
            },
        )
        state = initial_audit_state(
            case_description=case_description,
            resolution_note=resolution_note,
            settings=settings,
            chunk_set_id=chunk_set_id,
            include_synthetic=include_synthetic,
            k=k,
        )

        try:
            async with asyncio.timeout(settings.audit_deadline_s):
                raw_final = await graph.ainvoke(state, run_cfg)
            final_state = cast(AuditState, raw_final)
            trace_id = getattr(handler, "last_trace_id", None) if handler else None
            case_context_obj = final_state.get("case_context")
            case_context_dict = (
                case_context_obj.model_dump() if case_context_obj is not None else None
            )
            claims = final_state.get("claims", [])
            note_verdict: NoteVerdict = final_state.get("note_verdict", "insufficient")
            async with pool.connection(timeout=CONNECTION_TIMEOUT_S) as conn:
                await complete_audit(
                    conn,
                    audit_id,
                    claims=claims,
                    note_verdict=note_verdict,
                    case_context=case_context_dict,
                    trace_id=trace_id,
                    duration_ms=duration_ms(),
                )
        except asyncio.CancelledError:
            logger.info("Zadanie audytu %s zostało anulowane", audit_id)
            raise
        except TimeoutError:
            logger.warning("Audyt %s przekroczył limit czasu", audit_id)
            trace_id = getattr(handler, "last_trace_id", None) if handler else None
            await _mark_failed(
                pool,
                audit_id,
                error="Przekroczono limit czasu analizy notatki.",
                trace_id=trace_id,
                duration_ms=duration_ms(),
            )
        except Exception as exc:
            logger.warning("Audyt %s zakończył się błędem", audit_id, exc_info=True)
            trace_id = getattr(handler, "last_trace_id", None) if handler else None
            await _mark_failed(
                pool,
                audit_id,
                error=f"{type(exc).__name__}: {exc}",
                trace_id=trace_id,
                duration_ms=duration_ms(),
            )
        finally:
            if handler is not None:
                with anyio.CancelScope(shield=True):
                    await run_in_threadpool(flush_traces)


def get_audit_task_manager(request: Request) -> AuditTaskManager:
    """Zależność FastAPI zwracająca menedżer zadań audytu z `app.state`."""
    manager: AuditTaskManager = request.app.state.audit_tasks
    return manager


AuditTaskManagerDep = Annotated[AuditTaskManager, Depends(get_audit_task_manager)]
