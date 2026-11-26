"""Lekki fałszywy model sędziego do testów jednostkowych (bez sieci i bez DB)."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class JudgeRecordedCall:
    """Zapis pojedynczego wywołania `with_structured_output`."""

    schema: str
    strict: bool | None
    messages: list[BaseMessage]


@dataclass(frozen=True)
class DelayedResponse:
    """Opóźniona odpowiedź (lub wyjątek) do testowania limitów czasu sędziego."""

    delay_s: float
    value: BaseModel | Exception


FakeResponse = BaseModel | Exception | DelayedResponse


class FakeJudgeChatModel(BaseChatModel):
    """Fałszywy `BaseChatModel` obsługujący dowolny schemat `with_structured_output`."""

    responses: list[FakeResponse] = Field(default_factory=list)
    calls: list[JudgeRecordedCall] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake-eval-judge"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise AssertionError("sędzia ma używać wyłącznie with_structured_output")

    def with_structured_output(
        self, schema: Any, *, strict: bool | None = None, **kwargs: Any
    ) -> Runnable[LanguageModelInput, Any]:
        model = self

        def _next_item(messages: LanguageModelInput) -> FakeResponse:
            assert isinstance(messages, Sequence)
            model.calls.append(
                JudgeRecordedCall(
                    schema=schema.__name__,
                    strict=strict,
                    messages=list(messages),  # type: ignore[arg-type]
                )
            )
            if not model.responses:
                raise AssertionError(
                    f"brak zaplanowanej odpowiedzi dla schematu {schema.__name__}"
                )
            return model.responses.pop(0)

        def _unwrap(item: BaseModel | Exception) -> Any:
            if isinstance(item, Exception):
                raise item
            return item

        def respond(messages: LanguageModelInput) -> Any:
            item = _next_item(messages)
            if isinstance(item, DelayedResponse):
                return _unwrap(item.value)
            return _unwrap(item)

        async def arespond(messages: LanguageModelInput) -> Any:
            item = _next_item(messages)
            if isinstance(item, DelayedResponse):
                await asyncio.sleep(item.delay_s)
                return _unwrap(item.value)
            return _unwrap(item)

        return RunnableLambda(respond, afunc=arespond)
