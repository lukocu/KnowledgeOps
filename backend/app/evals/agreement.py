"""Walidacja zgodności sędziego LLM z ocenami człowieka (procent i Cohen's kappa)."""

import json
import math
from collections.abc import Sequence
from pathlib import Path

from pydantic import TypeAdapter

from app.evals.metrics import EvalItemExecution, evaluate_citation_support
from app.evals.report import JudgeAgreementSummary
from app.evals.runner import EvalRunArtifact
from app.evals.sampling import (
    AbstainedAuditRecord,
    AnsweredAuditRecord,
    ManualAuditFile,
    ManualAuditRecord,
)

CITATION_LABELS: tuple[str, ...] = ("supported", "unsupported")
REFERENCE_LABELS: tuple[str, ...] = ("full", "partial", "incorrect")
NO_VARIANCE_KAPPA_NOTE = "brak wariancji w ocenach (p_e = 1.0)"

_RECORDS_ADAPTER: TypeAdapter[list[ManualAuditRecord]] = TypeAdapter(
    list[ManualAuditRecord]
)


def compute_cohens_kappa(pairs: Sequence[tuple[str, str]]) -> float | None:
    """Oblicza współczynnik Cohen's kappa dla par `(ocena_a, ocena_b)`.

    Zwraca `None`, gdy lista par jest pusta lub gdy `p_e == 1.0`
    (brak wariancji w ocenach, np. 100% etykiety `supported`).
    """
    n = len(pairs)
    if n == 0:
        return None

    p_o = sum(1 for a, b in pairs if a == b) / n
    labels = {a for a, _ in pairs} | {b for _, b in pairs}

    p_e = 0.0
    for label in labels:
        frac_a = sum(1 for a, _ in pairs if a == label) / n
        frac_b = sum(1 for _, b in pairs if b == label) / n
        p_e += frac_a * frac_b

    if math.isclose(p_e, 1.0, abs_tol=1e-12) or p_e >= 1.0:
        return None

    return (p_o - p_e) / (1.0 - p_e)


def _build_confusion_matrix(
    pairs: Sequence[tuple[str, str]],
    labels: tuple[str, ...],
) -> dict[str, dict[str, int]]:
    if not pairs:
        return {}
    matrix: dict[str, dict[str, int]] = {
        judge_lbl: {human_lbl: 0 for human_lbl in labels} for judge_lbl in labels
    }
    for judge_lbl, human_lbl in pairs:
        matrix.setdefault(judge_lbl, {lbl: 0 for lbl in labels})
        matrix[judge_lbl][human_lbl] = matrix[judge_lbl].get(human_lbl, 0) + 1
    return matrix


def _agreement_rate(pairs: Sequence[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    return sum(1 for a, b in pairs if a == b) / len(pairs)


def _judge_citation_answer_label(item: EvalItemExecution) -> str | None:
    """Wyznacza binarny werdykt sędziego cytatów na poziomie całej odpowiedzi."""
    support = evaluate_citation_support(item)
    if support is None:
        return None
    supported, total = support
    return "supported" if supported == total else "unsupported"


def _load_audit_records(audit_path: Path) -> list[ManualAuditRecord]:
    raw = json.loads(audit_path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return _RECORDS_ADAPTER.validate_python(raw)
    return ManualAuditFile.model_validate(raw).entries


def evaluate_judge_agreement(
    run_path: Path,
    audit_path: Path,
) -> JudgeAgreementSummary:
    """Porównuje oceny sędziego LLM z ocenami człowieka w pliku audytu ręcznego.

    Waliduje kompletność ocen człowieka na pozycjach `answered` posiadających
    ważny werdykt sędziego; pomija pola sędziego dla warstwy `abstained` i
    podsumowuje ją jakościowo osobno.
    """
    run = EvalRunArtifact.model_validate_json(run_path.read_text(encoding="utf-8"))
    records = _load_audit_records(audit_path)
    if not records:
        raise ValueError("plik audytu ręcznego nie zawiera żadnych pozycji")

    run_by_id: dict[str, EvalItemExecution] = {
        item.question_id: item for item in run.items
    }
    seen_ids: set[str] = set()

    citation_pairs: list[tuple[str, str]] = []
    reference_pairs: list[tuple[str, str]] = []
    missing_citation: list[str] = []
    missing_reference: list[str] = []

    n_reviewed = 0
    n_abstained_sampled = 0
    n_abstained_reviewed = 0
    abstained_justified = 0
    abstained_unjustified = 0

    for record in records:
        qid = record.question_id
        if qid in seen_ids:
            raise ValueError(f"zduplikowane question_id w pliku audytu: {qid!r}")
        seen_ids.add(qid)

        run_item = run_by_id.get(qid)
        if run_item is None:
            raise ValueError(
                f"question_id={qid!r} z pliku audytu nie istnieje w przebiegu"
                f" {run.config.run_name!r}"
            )
        if run_item.outcome == "failed":
            raise ValueError(
                f"question_id={qid!r} ma status 'failed' w przebiegu i nie może być"
                " oceniany w audycie zgodności"
            )

        if run_item.outcome == "abstained":
            if not isinstance(record, AbstainedAuditRecord):
                raise ValueError(
                    f"question_id={qid!r} ma outcome='abstained' w przebiegu,"
                    f" ale {record.outcome!r} w pliku audytu"
                )
            n_abstained_sampled += 1
            if record.human_abstain_justified is not None:
                n_abstained_reviewed += 1
                n_reviewed += 1
                if record.human_abstain_justified:
                    abstained_justified += 1
                else:
                    abstained_unjustified += 1
            continue

        # outcome == "answered"
        if not isinstance(record, AnsweredAuditRecord):
            raise ValueError(
                f"question_id={qid!r} ma outcome='answered' w przebiegu,"
                f" ale {record.outcome!r} w pliku audytu"
            )

        judge_cit = _judge_citation_answer_label(run_item)
        if judge_cit is not None:
            if record.human_citation_supported is None:
                missing_citation.append(qid)
            else:
                human_cit = (
                    "supported" if record.human_citation_supported else "unsupported"
                )
                citation_pairs.append((judge_cit, human_cit))

        has_ref_judge = (
            run_item.reference_judge is not None
            and run_item.reference_judge.judge_error is None
            and run_item.reference_judge.output is not None
        )
        if has_ref_judge and run_item.reference_judge is not None:
            assert run_item.reference_judge.output is not None
            if record.human_reference_verdict is None:
                missing_reference.append(qid)
            else:
                reference_pairs.append(
                    (
                        run_item.reference_judge.output.verdict,
                        record.human_reference_verdict,
                    )
                )

        if (
            record.human_citation_supported is not None
            or record.human_reference_verdict is not None
        ):
            n_reviewed += 1

    errors: list[str] = []
    if missing_citation:
        errors.append(
            "brak `human_citation_supported` dla pozycji: "
            + ", ".join(missing_citation)
        )
    if missing_reference:
        errors.append(
            "brak `human_reference_verdict` dla pozycji: "
            + ", ".join(missing_reference)
        )
    if errors:
        raise ValueError("niekompletny arkusz audytu ręcznego: " + "; ".join(errors))

    cit_kappa = compute_cohens_kappa(citation_pairs)
    cit_kappa_note = (
        NO_VARIANCE_KAPPA_NOTE if citation_pairs and cit_kappa is None else None
    )

    ref_kappa = compute_cohens_kappa(reference_pairs)
    ref_kappa_note = (
        NO_VARIANCE_KAPPA_NOTE if reference_pairs and ref_kappa is None else None
    )

    return JudgeAgreementSummary(
        n_sampled=len(records),
        n_reviewed=n_reviewed,
        n_citation_pairs=len(citation_pairs),
        citation_agreement_rate=_agreement_rate(citation_pairs),
        citation_cohens_kappa=cit_kappa,
        citation_kappa_note=cit_kappa_note,
        citation_confusion_matrix=_build_confusion_matrix(
            citation_pairs, CITATION_LABELS
        ),
        n_reference_pairs=len(reference_pairs),
        reference_agreement_rate=_agreement_rate(reference_pairs),
        reference_cohens_kappa=ref_kappa,
        reference_kappa_note=ref_kappa_note,
        reference_confusion_matrix=_build_confusion_matrix(
            reference_pairs, REFERENCE_LABELS
        ),
        n_abstained_sampled=n_abstained_sampled,
        n_abstained_reviewed=n_abstained_reviewed,
        abstained_justified_count=abstained_justified,
        abstained_unjustified_count=abstained_unjustified,
    )
