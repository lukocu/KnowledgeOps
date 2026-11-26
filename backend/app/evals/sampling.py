"""Deterministyczne stratyfikowane próbkowanie i eksport arkusza do audytu ręcznego."""

import math
import random
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.answering.schemas import (
    AbstainedResult,
    AnsweredResult,
    Citation,
    CitationClaim,
)
from app.evals.dataset import Split, VerifiedLabel
from app.evals.judge import ReferenceVerdict
from app.evals.metrics import EvalItemExecution
from app.evals.runner import EvalRunArtifact

DEFAULT_AUDIT_SEED = 20261125
AuditStratum = Literal["answered_omitted_claims", "abstained", "answered_regular"]


class AuditClaimContext(BaseModel):
    """Pełny kontekst pojedynczej tezy i cytatu do ślepego przeglądu przez człowieka."""

    model_config = ConfigDict(frozen=True)

    claim_index: int
    text: str
    code: str | None = None
    citation_n: int
    chunk_id: str
    doc_id: str
    title: str
    headings: list[str] = Field(default_factory=list)
    quote: str
    quote_start: int
    quote_end: int
    chunk_text: str = ""


class ManualAuditEntry(BaseModel):
    """Wpis próbki do audytu ręcznego (bez werdyktów sędziego LLM)."""

    model_config = ConfigDict(frozen=True)

    question_id: str
    split: Split
    verified_label: VerifiedLabel
    outcome: Literal["answered", "abstained"]
    stratum: AuditStratum
    question: str
    reference_answer: str = ""
    claims: list[AuditClaimContext] = Field(default_factory=list)
    omitted_claims: int = 0
    abstention_reason: str | None = None
    checked_chunks_count: int = 0
    human_citation_supported: bool | None = None
    human_reference_verdict: ReferenceVerdict | None = None
    human_abstain_justified: bool | None = None
    human_note: str = ""


class AnsweredAuditRecord(BaseModel):
    """Rekord JSON do uzupełnienia przez recenzenta dla pozycji `answered`."""

    model_config = ConfigDict(frozen=True)

    question_id: str
    split: Split
    verified_label: VerifiedLabel
    outcome: Literal["answered"] = "answered"
    stratum: AuditStratum
    human_citation_supported: bool | None = None
    human_reference_verdict: ReferenceVerdict | None = None
    human_note: str = ""


class AbstainedAuditRecord(BaseModel):
    """Rekord JSON do uzupełnienia przez recenzenta dla pozycji `abstained`."""

    model_config = ConfigDict(frozen=True)

    question_id: str
    split: Split
    verified_label: VerifiedLabel
    outcome: Literal["abstained"] = "abstained"
    stratum: AuditStratum
    human_abstain_justified: bool | None = None
    human_note: str = ""


ManualAuditRecord = Annotated[
    AnsweredAuditRecord | AbstainedAuditRecord,
    Field(discriminator="outcome"),
]


class ManualAuditFile(BaseModel):
    """Plik `<run_name>-manual-audit.json` wypełniany przez człowieka."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    run_name: str
    entries: list[ManualAuditRecord]


def _extract_claim_contexts(
    result: AnsweredResult,
    cited_chunk_texts: dict[str, str],
) -> list[AuditClaimContext]:
    citations_by_n: dict[int, Citation] = {c.n: c for c in result.citations}
    citation_claim_by_idx: dict[int, tuple[Citation, CitationClaim]] = {}
    for citation in result.citations:
        for cc in citation.claims:
            citation_claim_by_idx.setdefault(cc.claim_index, (citation, cc))

    contexts: list[AuditClaimContext] = []
    for idx, claim in enumerate(result.claims):
        matched = citation_claim_by_idx.get(idx)
        if matched is not None:
            citation, cc = matched
            quote = cc.quote
            quote_start = cc.quote_start
            quote_end = cc.quote_end
        else:
            fallback = citations_by_n.get(claim.citation)
            if fallback is None:
                continue
            citation = fallback
            quote = ""
            quote_start = 0
            quote_end = 0

        contexts.append(
            AuditClaimContext(
                claim_index=idx,
                text=claim.text,
                code=claim.code,
                citation_n=citation.n,
                chunk_id=citation.chunk_id,
                doc_id=citation.doc_id,
                title=citation.title,
                headings=list(citation.headings),
                quote=quote,
                quote_start=quote_start,
                quote_end=quote_end,
                chunk_text=cited_chunk_texts.get(citation.chunk_id, ""),
            )
        )
    return contexts


def _build_entry(
    item: EvalItemExecution,
    stratum: AuditStratum,
    run: EvalRunArtifact,
) -> ManualAuditEntry:
    question = run.item_questions.get(item.question_id, "")
    reference_answer = run.item_reference_answers.get(item.question_id, "")

    if item.outcome == "answered" and isinstance(item.answer, AnsweredResult):
        return ManualAuditEntry(
            question_id=item.question_id,
            split=item.split,
            verified_label=item.verified_label,
            outcome="answered",
            stratum=stratum,
            question=question,
            reference_answer=reference_answer,
            claims=_extract_claim_contexts(item.answer, item.cited_chunk_texts),
            omitted_claims=item.answer.omitted_claims,
            checked_chunks_count=len(item.answer.checked_chunks),
        )

    abstention_reason = item.abstention_reason
    omitted = 0
    checked = 0
    if isinstance(item.answer, AbstainedResult):
        abstention_reason = abstention_reason or item.answer.reason
        omitted = item.answer.omitted_claims
        checked = len(item.answer.checked_chunks)

    return ManualAuditEntry(
        question_id=item.question_id,
        split=item.split,
        verified_label=item.verified_label,
        outcome="abstained",
        stratum=stratum,
        question=question,
        reference_answer=reference_answer,
        omitted_claims=omitted,
        abstention_reason=abstention_reason,
        checked_chunks_count=checked,
    )


def _shuffled(
    items: Sequence[EvalItemExecution], rng: random.Random
) -> list[EvalItemExecution]:
    ordered = sorted(items, key=lambda item: item.question_id)
    rng.shuffle(ordered)
    return ordered


def sample_for_manual_audit(
    run: EvalRunArtifact,
    *,
    min_samples: int = 20,
    answer_fraction: float = 0.25,
    max_omitted_layer: int = 5,
    max_abstained_layer: int = 5,
    seed: int = DEFAULT_AUDIT_SEED,
) -> list[ManualAuditEntry]:
    """Deterministycznie wybiera warstwową próbkę przypadków do audytu ręcznego.

    Rozmiar próbki:
    `target = min(n_non_failed, max(min_samples, ceil(f * n_answered)))`.
    Kolejność warstw:
    1. Do `max_omitted_layer` odpowiedzi z `omitted_claims > 0`.
    2. Do `max_abstained_layer` przypadków `abstained` (przegląd jakościowy).
    3. Pozostały budżet z pozostałych `answered` (z ewentualnym dopełnieniem z
       niewykorzystanych pul, aby osiągnąć `target`).
    """
    if min_samples < 0:
        raise ValueError("min_samples musi być >= 0")
    if answer_fraction < 0:
        raise ValueError("answer_fraction musi być >= 0")
    if max_omitted_layer < 0 or max_abstained_layer < 0:
        raise ValueError("limity warstw muszą być >= 0")

    non_failed = [item for item in run.items if item.outcome != "failed"]
    if not non_failed:
        return []

    n_non_failed = len(non_failed)
    n_answered = sum(1 for item in non_failed if item.outcome == "answered")
    target = min(
        n_non_failed,
        max(min_samples, math.ceil(answer_fraction * n_answered)),
    )
    if target == 0:
        return []

    omitted_pool: list[EvalItemExecution] = []
    regular_answered_pool: list[EvalItemExecution] = []
    abstained_pool: list[EvalItemExecution] = []

    for item in non_failed:
        if item.outcome == "answered":
            has_omitted = (
                isinstance(item.answer, AnsweredResult)
                and item.answer.omitted_claims > 0
            )
            if has_omitted:
                omitted_pool.append(item)
            else:
                regular_answered_pool.append(item)
        else:
            abstained_pool.append(item)

    rng = random.Random(seed)
    omitted_shuffled = _shuffled(omitted_pool, rng)
    abstained_shuffled = _shuffled(abstained_pool, rng)
    regular_shuffled = _shuffled(regular_answered_pool, rng)

    selected: list[tuple[EvalItemExecution, AuditStratum]] = []

    take_omitted = min(max_omitted_layer, target, len(omitted_shuffled))
    selected.extend(
        (item, "answered_omitted_claims") for item in omitted_shuffled[:take_omitted]
    )

    rem = target - len(selected)
    take_abstained = min(max_abstained_layer, rem, len(abstained_shuffled))
    selected.extend((item, "abstained") for item in abstained_shuffled[:take_abstained])

    rem = target - len(selected)
    take_regular = min(rem, len(regular_shuffled))
    selected.extend(
        (item, "answered_regular") for item in regular_shuffled[:take_regular]
    )

    # Dopełnienie budżetu, jeśli pozostały wolne sloty (np. mało `answered`).
    if len(selected) < target:
        rem = target - len(selected)
        extra_omitted = omitted_shuffled[take_omitted : take_omitted + rem]
        selected.extend((item, "answered_omitted_claims") for item in extra_omitted)
    if len(selected) < target:
        rem = target - len(selected)
        extra_abstained = abstained_shuffled[take_abstained : take_abstained + rem]
        selected.extend((item, "abstained") for item in extra_abstained)

    return [_build_entry(item, stratum, run) for item, stratum in selected]


def _entry_to_record(entry: ManualAuditEntry) -> ManualAuditRecord:
    if entry.outcome == "answered":
        return AnsweredAuditRecord(
            question_id=entry.question_id,
            split=entry.split,
            verified_label=entry.verified_label,
            stratum=entry.stratum,
            human_citation_supported=entry.human_citation_supported,
            human_reference_verdict=entry.human_reference_verdict,
            human_note=entry.human_note,
        )
    return AbstainedAuditRecord(
        question_id=entry.question_id,
        split=entry.split,
        verified_label=entry.verified_label,
        stratum=entry.stratum,
        human_abstain_justified=entry.human_abstain_justified,
        human_note=entry.human_note,
    )


def render_manual_audit_markdown(
    entries: Sequence[ManualAuditEntry],
    run_name: str,
) -> str:
    """Generuje czytelny arkusz Markdown dla recenzenta bez werdyktów sędziego LLM."""
    lines: list[str] = [
        f"# Audyt ręczny sędziego — `{run_name}`",
        "",
        "Arkusz do niezależnej, ślepej oceny przez człowieka (werdykty sędziego LLM"
        " zostały celowo ukryte, aby uniknąć efektu zakotwiczenia).",
        f"Uzupełnij swoje oceny w pliku `{run_name}-manual-audit.json`:",
        "- dla pozycji `answered`: `human_citation_supported` (`true`/`false`),"
        ' `human_reference_verdict` (`"full"` / `"partial"` / `"incorrect"`,'
        " gdy dostępna jest odpowiedź referencyjna TechQA) oraz opcjonalnie"
        " `human_note`,",
        "- dla pozycji `abstained`: `human_abstain_justified` (`true`/`false`)"
        " oraz opcjonalnie `human_note`.",
        "",
        f"Liczba pozycji w próbce: **{len(entries)}**.",
        "",
    ]

    for idx, entry in enumerate(entries, start=1):
        lines.extend(
            [
                (
                    f"## {idx}. `{entry.question_id}` (`{entry.outcome}`,"
                    f" warstwa: `{entry.stratum}`, split: `{entry.split}`)"
                ),
                "",
                f"- Etykieta zbioru: `{entry.verified_label}`",
                f"- Pominięte tezy (`omitted_claims`): `{entry.omitted_claims}`",
                f"- Sprawdzone fragmenty: `{entry.checked_chunks_count}`",
            ]
        )
        if entry.outcome == "abstained":
            reason = entry.abstention_reason or "nieznana"
            lines.append(f"- Przyczyna abstencji: `{reason}`")
        lines.append("")

        question_text = entry.question.strip() or "(brak treści pytania w artefakcie)"
        lines.extend(["### Pytanie", "", question_text, ""])

        if entry.outcome == "answered":
            lines.extend(["### Tezy i cytaty", ""])
            if not entry.claims:
                lines.append("(brak tez)")
                lines.append("")
            for claim in entry.claims:
                heading_path = (
                    " > ".join(claim.headings) if claim.headings else "(brak sekcji)"
                )
                claim_heading = (
                    f"#### Teza {claim.claim_index + 1} (cytat `[{claim.citation_n}]`)"
                )
                lines.extend(
                    [
                        claim_heading,
                        "",
                        claim.text,
                        "",
                    ]
                )
                if claim.code:
                    lines.extend(["```", claim.code, "```", ""])
                lines.extend(
                    [
                        (
                            f"- Źródło: `{claim.doc_id}` — {claim.title}"
                            f" (`{heading_path}`, chunk: `{claim.chunk_id}`,"
                            f" zakres: `[{claim.quote_start}:{claim.quote_end})`)"
                        ),
                        "",
                        "**Dosłowny cytat:**",
                        "",
                        f"> {claim.quote}",
                        "",
                        "**Kontekst fragmentu:**",
                        "",
                    ]
                )
                if claim.chunk_text:
                    lines.extend(["```text", claim.chunk_text, "```", ""])
                else:
                    lines.extend(["(brak pełnego tekstu fragmentu w artefakcie)", ""])

        lines.extend(["### Odpowiedź referencyjna TechQA", ""])
        if entry.reference_answer.strip():
            lines.extend([entry.reference_answer.strip(), ""])
        else:
            lines.extend(["(brak — pytanie bez odpowiedzi referencyjnej w TechQA)", ""])
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def export_manual_audit(
    entries: Sequence[ManualAuditEntry],
    out_dir: Path,
    run_name: str,
) -> tuple[Path, Path]:
    """Zapisuje `<run_name>-manual-audit.json` i `<run_name>-manual-audit.md`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{run_name}-manual-audit.json"
    md_path = out_dir / f"{run_name}-manual-audit.md"

    audit_file = ManualAuditFile(
        run_name=run_name,
        entries=[_entry_to_record(entry) for entry in entries],
    )
    json_path.write_text(audit_file.model_dump_json(indent=2) + "\n", encoding="utf-8")
    md_path.write_text(
        render_manual_audit_markdown(entries, run_name), encoding="utf-8"
    )
    return json_path, md_path
