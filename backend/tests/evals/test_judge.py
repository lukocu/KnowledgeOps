"""Testy jednostkowe sędziego LLM, promptów i fallbacku `EVAL_JUDGE_MODEL`."""

from typing import Any

import pytest
from pydantic import SecretStr

from app.answering import model as answering_model
from app.answering.model import ModelNotConfiguredError, make_judge_model
from app.answering.schemas import AnswerClaim, Citation, CitationClaim
from app.evals.judge import (
    CitationJudgeOutput,
    CitationJudgeVerdict,
    EvalJudge,
    ReferenceAgreementOutput,
    reference_agreement_score,
)
from app.evals.prompts import load_prompt, prompt_version, prompt_versions
from app.settings import Settings
from tests.evals.fakes import DelayedResponse, FakeJudgeChatModel


def _settings(**kwargs: object) -> Settings:
    kwargs.setdefault("database_url", "postgresql://test")
    return Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]


def _sample_claims_and_citations() -> tuple[
    list[AnswerClaim], list[Citation], dict[str, str]
]:
    text = "Run db2start to start the DB2 instance."
    claims = [
        AnswerClaim(text="Run db2start to start DB2.", code="db2start", citation=1)
    ]
    citations = [
        Citation(
            n=1,
            chunk_id="c1",
            doc_id="doc1",
            title="DB2 Start",
            headings=["Start"],
            claims=[
                CitationClaim(
                    claim_index=0,
                    quote="Run db2start",
                    quote_start=0,
                    quote_end=12,
                )
            ],
        )
    ]
    return claims, citations, {"c1": text}


# --- prompty -----------------------------------------------------------------


def test_eval_prompts_loaded_and_versioned() -> None:
    versions = prompt_versions()
    assert set(versions) == {"citation_support", "reference_agreement"}
    for name, version in versions.items():
        text = load_prompt(name)
        assert len(text.strip()) > 50
        assert len(version) == 12
        assert version == prompt_version(name)
        assert all(ch in "0123456789abcdef" for ch in version)

    with pytest.raises(ValueError, match="nieznany prompt"):
        load_prompt("nonexistent")


# --- EvalJudge.judge_citations -----------------------------------------------


@pytest.mark.anyio
async def test_judge_citations_returns_verdicts_with_strict_schema() -> None:
    expected = CitationJudgeOutput(
        verdicts=[
            CitationJudgeVerdict(
                claim_index=0,
                reasoning="The quote explicitly mentions running db2start.",
                verdict="supported",
            )
        ]
    )
    fake = FakeJudgeChatModel(responses=[expected])
    judge = EvalJudge(model=fake, timeout_s=5.0)
    claims, citations, chunk_texts = _sample_claims_and_citations()

    result = await judge.judge_citations(claims, citations, chunk_texts)

    assert result.judge_error is None
    assert result.verdicts == expected.verdicts
    assert len(fake.calls) == 1
    assert fake.calls[0].schema == "CitationJudgeOutput"
    assert fake.calls[0].strict is True
    assert "db2start" in str(fake.calls[0].messages[1].content)


@pytest.mark.anyio
async def test_judge_citations_empty_claims_skips_model_call() -> None:
    fake = FakeJudgeChatModel()
    judge = EvalJudge(model=fake, timeout_s=5.0)

    result = await judge.judge_citations([], [], {})

    assert result.judge_error is None
    assert result.verdicts == []
    assert fake.calls == []


@pytest.mark.anyio
async def test_judge_citations_timeout_returns_judge_error() -> None:
    fake = FakeJudgeChatModel(
        responses=[
            DelayedResponse(
                delay_s=0.5,
                value=CitationJudgeOutput(verdicts=[]),
            )
        ]
    )
    judge = EvalJudge(model=fake, timeout_s=0.02)
    claims, citations, chunk_texts = _sample_claims_and_citations()

    result = await judge.judge_citations(claims, citations, chunk_texts)

    assert result.verdicts == []
    assert result.judge_error is not None
    assert "timeout" in result.judge_error


@pytest.mark.anyio
async def test_judge_citations_exception_returns_judge_error() -> None:
    fake = FakeJudgeChatModel(responses=[RuntimeError("upstream 503")])
    judge = EvalJudge(model=fake, timeout_s=5.0)
    claims, citations, chunk_texts = _sample_claims_and_citations()

    result = await judge.judge_citations(claims, citations, chunk_texts)

    assert result.verdicts == []
    assert result.judge_error == "RuntimeError: upstream 503"


# --- EvalJudge.judge_reference -----------------------------------------------


@pytest.mark.anyio
async def test_judge_reference_returns_agreement_and_score_mapping() -> None:
    expected = ReferenceAgreementOutput(
        reasoning="Matches the reference command and goal.",
        verdict="full",
    )
    fake = FakeJudgeChatModel(responses=[expected])
    judge = EvalJudge(model=fake, timeout_s=5.0)
    claims, _, _ = _sample_claims_and_citations()

    result = await judge.judge_reference("How to start DB2?", "Run db2start.", claims)

    assert result.judge_error is None
    assert result.output == expected
    assert reference_agreement_score("full") == 1.0
    assert reference_agreement_score("partial") == 0.5
    assert reference_agreement_score("incorrect") == 0.0
    assert len(fake.calls) == 1
    assert fake.calls[0].schema == "ReferenceAgreementOutput"
    assert fake.calls[0].strict is True


@pytest.mark.anyio
async def test_judge_reference_timeout_and_error_isolated() -> None:
    fake = FakeJudgeChatModel(
        responses=[
            DelayedResponse(
                delay_s=0.5,
                value=ReferenceAgreementOutput(reasoning="late", verdict="full"),
            ),
            ValueError("bad schema"),
        ]
    )
    judge = EvalJudge(model=fake, timeout_s=0.02)
    claims, _, _ = _sample_claims_and_citations()

    timed_out = await judge.judge_reference("Q?", "Ref.", claims)
    assert timed_out.output is None
    assert timed_out.judge_error is not None
    assert "timeout" in timed_out.judge_error

    errored = await judge.judge_reference("Q?", "Ref.", claims)
    assert errored.output is None
    assert errored.judge_error == "ValueError: bad schema"


# --- make_judge_model & fallback ---------------------------------------------


def test_make_judge_model_missing_keys_raises() -> None:
    with pytest.raises(ModelNotConfiguredError):
        make_judge_model(_settings(openai_api_key=None, eval_judge_api_key=None))


def test_make_judge_model_fallback_to_chat_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, Any]] = []

    def fake_chat_openai(**kwargs: Any) -> FakeJudgeChatModel:
        captured.append(kwargs)
        return FakeJudgeChatModel()

    monkeypatch.setattr(answering_model, "ChatOpenAI", fake_chat_openai)

    client, info = make_judge_model(
        _settings(
            openai_api_key=SecretStr("chat-key"),
            openai_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            chat_model="gemini-3.5-flash-lite",
            chat_reasoning_effort="low",
            eval_judge_model=None,
            eval_judge_timeout_s=25.0,
        )
    )

    assert isinstance(client, FakeJudgeChatModel)
    assert info.is_fallback_to_chat_model is True
    assert info.model == "gemini-3.5-flash-lite"
    assert info.reasoning_effort == "low"
    assert len(captured) == 1
    assert captured[0]["model"] == "gemini-3.5-flash-lite"
    assert captured[0]["api_key"].get_secret_value() == "chat-key"
    assert captured[0]["timeout"] == 25.0
    assert captured[0]["max_retries"] == 0
    assert captured[0]["reasoning_effort"] == "low"


def test_make_judge_model_dedicated_openrouter_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, Any]] = []

    def fake_chat_openai(**kwargs: Any) -> FakeJudgeChatModel:
        captured.append(kwargs)
        return FakeJudgeChatModel()

    monkeypatch.setattr(answering_model, "ChatOpenAI", fake_chat_openai)

    client, info = make_judge_model(
        _settings(
            openai_api_key=SecretStr("chat-key"),
            chat_model="gemini-3.5-flash-lite",
            eval_judge_model="openai/gpt-4o-mini",
            eval_judge_base_url="https://openrouter.ai/api/v1",
            eval_judge_api_key=SecretStr("judge-key"),
            eval_judge_reasoning_effort="none",
            eval_judge_timeout_s=30.0,
        )
    )

    assert isinstance(client, FakeJudgeChatModel)
    assert info.is_fallback_to_chat_model is False
    assert info.model == "openai/gpt-4o-mini"
    assert info.reasoning_effort == "none"
    assert len(captured) == 1
    assert captured[0]["model"] == "openai/gpt-4o-mini"
    assert captured[0]["api_key"].get_secret_value() == "judge-key"
    assert captured[0]["base_url"] == "https://openrouter.ai/api/v1"
    assert captured[0]["timeout"] == 30.0
    assert captured[0]["extra_body"] == {
        "provider": {"require_parameters": True},
        "reasoning": {"enabled": False},
    }
