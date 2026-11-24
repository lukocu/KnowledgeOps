"""Fałszywy model czatu ze skryptowanymi odpowiedziami strukturalnymi."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import LanguageModelInput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.runnables import Runnable, RunnableLambda

from app.answering.schemas import DraftOutput, VerifyOutput


@dataclass
class RecordedCall:
    schema: str
    strict: bool | None
    messages: list[BaseMessage]


@dataclass
class Script:
    """Kolejki odpowiedzi dla `draft` i `verify` oraz zapis wywołań."""

    drafts: list[DraftOutput] = field(default_factory=list)
    verifies: list[VerifyOutput] = field(default_factory=list)
    calls: list[RecordedCall] = field(default_factory=list)


class ScriptedChatModel(BaseChatModel):
    """Model, który przez `with_structured_output` zwraca skryptowane obiekty."""

    script: Script

    @property
    def _llm_type(self) -> str:
        return "scripted-fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise AssertionError("graf ma używać wyłącznie with_structured_output")

    def with_structured_output(
        self, schema: Any, *, strict: bool | None = None, **kwargs: Any
    ) -> Runnable[LanguageModelInput, Any]:
        script = self.script

        def respond(messages: LanguageModelInput) -> Any:
            assert isinstance(messages, Sequence)
            script.calls.append(
                RecordedCall(
                    schema=schema.__name__,
                    strict=strict,
                    messages=list(messages),  # type: ignore[arg-type]
                )
            )
            if schema is DraftOutput:
                return script.drafts.pop(0)
            if schema is VerifyOutput:
                return script.verifies.pop(0)
            raise AssertionError(f"nieoczekiwany schemat: {schema}")

        return RunnableLambda(respond)
