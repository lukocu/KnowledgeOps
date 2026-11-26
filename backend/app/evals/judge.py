"""Niezależny sędzia LLM dla wsparcia cytatów i zgodności z odpowiedzią referencyjną.

Kolejność pól w schematach wyjścia ma znaczenie: `reasoning` stoi przed `verdict`,
aby model uzasadnił ocenę przed wyborem etykiety.
"""

import asyncio
from collections.abc import Mapping, Sequence
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from app.answering.schemas import AnswerClaim, Citation, CitationClaim
from app.evals.prompts import load_prompt

CitationVerdict = Literal["supported", "unsupported"]
ReferenceVerdict = Literal["full", "partial", "incorrect"]

REFERENCE_AGREEMENT_SCORES: dict[ReferenceVerdict, float] = {
    "full": 1.0,
    "partial": 0.5,
    "incorrect": 0.0,
}


class CitationJudgeVerdict(BaseModel):
    """Werdykt sędziego dla pojedynczej tezy i jej cytatu."""

    claim_index: int
    reasoning: str
    verdict: CitationVerdict


class CitationJudgeOutput(BaseModel):
    """Strukturalna odpowiedź sędziego wsparcia cytatów."""

    verdicts: list[CitationJudgeVerdict]


class CitationJudgeResult(BaseModel):
    """Wynik oceny cytatów z jawną izolacją błędu/timeoutu sędziego."""

    model_config = ConfigDict(frozen=True)

    verdicts: list[CitationJudgeVerdict] = Field(default_factory=list)
    judge_error: str | None = None


class ReferenceAgreementOutput(BaseModel):
    """Strukturalna odpowiedź sędziego zgodności z odpowiedzią referencyjną TechQA."""

    reasoning: str
    verdict: ReferenceVerdict


class ReferenceJudgeResult(BaseModel):
    """Wynik oceny referencyjnej z izolacją błędu/timeoutu sędziego."""

    model_config = ConfigDict(frozen=True)

    output: ReferenceAgreementOutput | None = None
    judge_error: str | None = None


def reference_agreement_score(verdict: ReferenceVerdict) -> float:
    """Mapuje kategorię zgodności referencyjnej na wartość liczbową dla Langfuse."""
    return REFERENCE_AGREEMENT_SCORES[verdict]


def citation_support_message(
    claims: Sequence[AnswerClaim],
    citations: Sequence[Citation],
    chunk_texts: Mapping[str, str],
) -> str:
    """Buduje komunikat dla sędziego wsparcia cytatów (tezy, cytaty i fragmenty)."""
    citations_by_number = {citation.n: citation for citation in citations}
    citation_claim_by_index: dict[int, tuple[Citation, CitationClaim]] = {}
    for citation in citations:
        for cc in citation.claims:
            citation_claim_by_index.setdefault(cc.claim_index, (citation, cc))

    blocks: list[str] = []
    for index, claim in enumerate(claims):
        matched = citation_claim_by_index.get(index)
        if matched is not None:
            citation, cc = matched
            quote = cc.quote
            passage = chunk_texts.get(citation.chunk_id, "")
        else:
            fallback_citation = citations_by_number.get(claim.citation)
            quote = ""
            passage = (
                chunk_texts.get(fallback_citation.chunk_id, "")
                if fallback_citation is not None
                else ""
            )

        code = f"\nCode: {claim.code}" if claim.code else ""
        blocks.append(
            f"claim_index: {index}\n"
            f"Claim: {claim.text}{code}\n"
            f"Quote: {quote}\n"
            f"Passage:\n{passage}"
        )

    return "Claims to audit:\n\n" + "\n\n---\n\n".join(blocks)


def reference_agreement_message(
    question: str,
    reference_answer: str,
    claims: Sequence[AnswerClaim],
) -> str:
    """Buduje komunikat dla sędziego zgodności z odpowiedzią referencyjną TechQA."""
    claim_lines: list[str] = []
    for index, claim in enumerate(claims, start=1):
        code = f"\nCode: {claim.code}" if claim.code else ""
        claim_lines.append(f"{index}. {claim.text}{code}")
    claims_block = "\n\n".join(claim_lines)
    return (
        f"Question:\n{question}\n\n"
        f"Reference answer:\n{reference_answer}\n\n"
        f"Generated claims:\n{claims_block}"
    )


class EvalJudge:
    """Sędzia LLM dla wsparcia cytatów i zgodności z odpowiedzią referencyjną."""

    def __init__(
        self,
        *,
        model: BaseChatModel,
        timeout_s: float = 20.0,
    ) -> None:
        self._model = model
        self._timeout_s = timeout_s

    async def _call_model[T: BaseModel](
        self, schema: type[T], system: str, human: str
    ) -> T:
        runnable = self._model.with_structured_output(schema, strict=True)
        async with asyncio.timeout(self._timeout_s):
            raw = await runnable.ainvoke(
                [SystemMessage(content=system), HumanMessage(content=human)]
            )
        return schema.model_validate(raw)

    async def judge_citations(
        self,
        claims: Sequence[AnswerClaim],
        citations: Sequence[Citation],
        chunk_texts: Mapping[str, str],
    ) -> CitationJudgeResult:
        """Ocenia binarnie, czy cytat i fragment wspierają konkretną tezę."""
        if not claims:
            return CitationJudgeResult()
        try:
            output = await self._call_model(
                CitationJudgeOutput,
                load_prompt("citation_support"),
                citation_support_message(claims, citations, chunk_texts),
            )
            return CitationJudgeResult(verdicts=output.verdicts)
        except TimeoutError:
            return CitationJudgeResult(
                judge_error=f"timeout sędziego cytatów po {self._timeout_s:g}s"
            )
        except Exception as exc:
            return CitationJudgeResult(judge_error=f"{type(exc).__name__}: {exc}")

    async def judge_reference(
        self,
        question: str,
        reference_answer: str,
        claims: Sequence[AnswerClaim],
    ) -> ReferenceJudgeResult:
        """Ocenia zgodność tez odpowiedzi z odpowiedzią referencyjną TechQA."""
        if not claims:
            return ReferenceJudgeResult(
                judge_error="brak tez do porównania z odpowiedzią referencyjną"
            )
        try:
            output = await self._call_model(
                ReferenceAgreementOutput,
                load_prompt("reference_agreement"),
                reference_agreement_message(question, reference_answer, claims),
            )
            return ReferenceJudgeResult(output=output)
        except TimeoutError:
            return ReferenceJudgeResult(
                judge_error=f"timeout sędziego referencji po {self._timeout_s:g}s"
            )
        except Exception as exc:
            return ReferenceJudgeResult(judge_error=f"{type(exc).__name__}: {exc}")
