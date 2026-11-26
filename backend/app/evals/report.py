"""Eksport surowego przebiegu JSON i generator raportu Markdown (Sprawdzian 1b i 2a)."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.answering.schemas import AnsweredResult
from app.evals.metrics import LATENCY_BUDGET_MS, EvalItemExecution
from app.evals.runner import EvalRunArtifact

MAX_ERROR_EXAMPLES_PER_CATEGORY = 10


class JudgeAgreementSummary(BaseModel):
    """Podsumowanie ręcznej walidacji zgodności sędziego LLM (Faza 4)."""

    model_config = ConfigDict(frozen=True)

    n_sampled: int = 0
    n_reviewed: int = 0
    n_citation_pairs: int = 0
    citation_agreement_rate: float | None = None
    citation_cohens_kappa: float | None = None
    citation_kappa_note: str | None = None
    citation_confusion_matrix: dict[str, dict[str, int]] = Field(default_factory=dict)
    n_reference_pairs: int = 0
    reference_agreement_rate: float | None = None
    reference_cohens_kappa: float | None = None
    reference_kappa_note: str | None = None
    reference_confusion_matrix: dict[str, dict[str, int]] = Field(default_factory=dict)
    n_abstained_sampled: int = 0
    n_abstained_reviewed: int = 0
    abstained_justified_count: int = 0
    abstained_unjustified_count: int = 0
    notes: str | None = None


def write_raw_run(path: Path, run: EvalRunArtifact) -> None:
    """Zapisuje kompletny, odtwarzalny zapis przebiegu do pliku JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(run.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "n/d"
    return f"{value * 100:.1f}%"


def _fmt_float(value: float | None, *, digits: int = 3) -> str:
    if value is None:
        return "n/d"
    return f"{value:.{digits}f}"


def _fmt_ms(value: float | None) -> str:
    if value is None:
        return "n/d"
    return f"{value:.0f} ms"


def _fmt_dict(mapping: dict[str, str]) -> str:
    if not mapping:
        return "brak"
    return ", ".join(f"`{key}={value}`" for key, value in sorted(mapping.items()))


def _diagnose_answered_error(item: EvalItemExecution) -> str:
    parts: list[str] = []
    if isinstance(item.answer, AnsweredResult):
        parts.append(
            f"tezy={len(item.answer.claims)}, cytaty={len(item.answer.citations)}"
        )
    if item.citation_invariants is not None and not item.citation_invariants.passed:
        parts.append(
            f"naruszenia inwariantów: {'; '.join(item.citation_invariants.violations)}"
        )
    if item.citation_judge is not None:
        if item.citation_judge.judge_error:
            parts.append(f"błąd sędziego cytatów: {item.citation_judge.judge_error}")
        elif item.citation_judge.verdicts:
            supported = sum(
                1 for v in item.citation_judge.verdicts if v.verdict == "supported"
            )
            total_v = len(item.citation_judge.verdicts)
            parts.append(f"sędzia cytatów: {supported}/{total_v} supported")
    return "; ".join(parts) if parts else "wygenerowano odpowiedź zamiast abstencji"


def _render_error_section(run: EvalRunArtifact) -> list[str]:
    lines: list[str] = ["## Przykłady błędów", ""]

    missed_abstentions = [
        item
        for item in run.items
        if item.verified_label == "verified_unanswerable" and item.outcome == "answered"
    ]
    false_refusals = [
        item
        for item in run.items
        if item.verified_label == "answerable_in_corpus" and item.outcome == "abstained"
    ]
    failed_items = [item for item in run.items if item.outcome == "failed"]
    invariant_failures = [
        item
        for item in run.items
        if item.outcome == "answered"
        and item.citation_invariants is not None
        and not item.citation_invariants.passed
    ]

    lines.append("### Błędne odpowiedzi na pytania bez odpowiedzi (missed abstentions)")
    if not missed_abstentions:
        lines.append("- Brak błędów w tej kategorii.")
    else:
        for item in missed_abstentions[:MAX_ERROR_EXAMPLES_PER_CATEGORY]:
            diag = _diagnose_answered_error(item)
            lines.append(f"- `{item.question_id}` (`{item.split}`) — {diag}")
        if len(missed_abstentions) > MAX_ERROR_EXAMPLES_PER_CATEGORY:
            lines.append(
                f"- …oraz {len(missed_abstentions) - MAX_ERROR_EXAMPLES_PER_CATEGORY}"
                " kolejnych przypadków w surowym pliku JSON."
            )
    lines.append("")

    lines.append("### Fałszywe odmowy (false refusals)")
    if not false_refusals:
        lines.append("- Brak błędów w tej kategorii.")
    else:
        for item in false_refusals[:MAX_ERROR_EXAMPLES_PER_CATEGORY]:
            cause = item.abstention_reason or "nieznana"
            lines.append(
                f"- `{item.question_id}` (`{item.split}`)"
                f" — przyczyna abstencji: `{cause}`"
            )
        if len(false_refusals) > MAX_ERROR_EXAMPLES_PER_CATEGORY:
            lines.append(
                f"- …oraz {len(false_refusals) - MAX_ERROR_EXAMPLES_PER_CATEGORY}"
                " kolejnych przypadków w surowym pliku JSON."
            )
    lines.append("")

    if invariant_failures:
        lines.append("### Naruszenia inwariantów cytatów")
        for item in invariant_failures[:MAX_ERROR_EXAMPLES_PER_CATEGORY]:
            violations = (
                "; ".join(item.citation_invariants.violations)
                if item.citation_invariants is not None
                else ""
            )
            lines.append(f"- `{item.question_id}` (`{item.split}`) — {violations}")
        lines.append("")

    if failed_items:
        lines.append("### Błędy wykonania (`failed`, wykluczone z mianowników)")
        for item in failed_items[:MAX_ERROR_EXAMPLES_PER_CATEGORY]:
            err = item.error or "nieznany błąd"
            lines.append(f"- `{item.question_id}` (`{item.split}`) — {err}")
        if len(failed_items) > MAX_ERROR_EXAMPLES_PER_CATEGORY:
            lines.append(
                f"- …oraz {len(failed_items) - MAX_ERROR_EXAMPLES_PER_CATEGORY}"
                " kolejnych błędów w surowym pliku JSON."
            )
        lines.append("")

    return lines


def _fmt_kappa(value: float | None, note: str | None) -> str:
    if value is not None:
        return f"{value:.3f}"
    if note:
        return f"n/d ({note})"
    return "n/d"


def _render_confusion_matrix(
    title: str,
    matrix: dict[str, dict[str, int]],
    labels: tuple[str, ...],
) -> list[str]:
    if not matrix:
        return []
    header = "| Sędzia \\ Człowiek | " + " | ".join(f"`{lbl}`" for lbl in labels) + " |"
    sep = "| --- | " + " | ".join("---" for _ in labels) + " |"
    rows = ["", f"### {title}", "", header, sep]
    for judge_lbl in labels:
        row_counts = matrix.get(judge_lbl, {})
        cells = " | ".join(f"`{row_counts.get(h_lbl, 0)}`" for h_lbl in labels)
        rows.append(f"| `{judge_lbl}` | {cells} |")
    return rows


def _render_agreement_section(agreement: JudgeAgreementSummary | None) -> list[str]:
    lines: list[str] = ["## Walidacja ręczna sędziego", ""]
    if agreement is None:
        lines.extend(
            [
                "Ręczna walidacja zgodności sędziego LLM (człowiek vs sędzia,"
                " Cohen's kappa) nie została jeszcze wykonana"
                " — sekcja do uzupełnienia w Fazie 4.",
                "",
            ]
        )
        return lines

    cit_n = f" (`n={agreement.n_citation_pairs}`)" if agreement.n_citation_pairs else ""
    ref_n = (
        f" (`n={agreement.n_reference_pairs}`)" if agreement.n_reference_pairs else ""
    )
    cit_kappa = _fmt_kappa(
        agreement.citation_cohens_kappa, agreement.citation_kappa_note
    )
    ref_kappa = _fmt_kappa(
        agreement.reference_cohens_kappa, agreement.reference_kappa_note
    )
    lines.extend(
        [
            "| Metryka walidacji | Wartość |",
            "| --- | --- |",
            (
                "| Próbka / ocenione ręcznie |"
                f" `{agreement.n_sampled}` / `{agreement.n_reviewed}` |"
            ),
            (
                "| Zgodność sędziego cytatów (procent / Cohen's kappa) |"
                f" {_fmt_pct(agreement.citation_agreement_rate)}"
                f" / {cit_kappa}{cit_n} |"
            ),
            (
                "| Zgodność sędziego referencji (procent / Cohen's kappa) |"
                f" {_fmt_pct(agreement.reference_agreement_rate)}"
                f" / {ref_kappa}{ref_n} |"
            ),
        ]
    )
    lines.extend(
        _render_confusion_matrix(
            "Macierz pomyłek — wsparcie cytatów",
            agreement.citation_confusion_matrix,
            ("supported", "unsupported"),
        )
    )
    lines.extend(
        _render_confusion_matrix(
            "Macierz pomyłek — zgodność z odpowiedzią referencyjną",
            agreement.reference_confusion_matrix,
            ("full", "partial", "incorrect"),
        )
    )
    if agreement.n_abstained_sampled > 0:
        lines.extend(
            [
                "",
                "### Przegląd jakościowy warstwy `abstained`",
                "",
                (
                    f"- W próbce: `{agreement.n_abstained_sampled}`,"
                    f" ocenione ręcznie: `{agreement.n_abstained_reviewed}`"
                    f" (uzasadnione: `{agreement.abstained_justified_count}`,"
                    f" nieuzasadnione: `{agreement.abstained_unjustified_count}`)."
                ),
            ]
        )
    if agreement.notes:
        lines.extend(["", f"Uwagi: {agreement.notes}"])
    lines.append("")
    return lines


def render_markdown_report(
    run: EvalRunArtifact,
    *,
    agreement: JudgeAgreementSummary | None = None,
) -> str:
    """Generuje raport Markdown (Sprawdzian 1b i 2a) z pełną odtwarzalnością."""
    cfg = run.config
    ds = run.dataset
    s = run.summary

    lines: list[str] = [
        "# Raport ewaluacji abstynencji i jakości odpowiedzi (Sprawdzian 1b i 2a)",
        "",
    ]

    if not cfg.use_langfuse:
        lines.extend(
            [
                "> [!WARNING]",
                "> **Tryb `--no-langfuse`**: Przebieg uruchomiono lokalnie bez zapisu"
                " eksperymentu i śladów w Langfuse Cloud.",
                "",
            ]
        )

    if cfg.judge_model_info.is_fallback_to_chat_model:
        lines.extend(
            [
                "> [!WARNING]",
                "> **Fallback `EVAL_JUDGE_MODEL`**: Nie skonfigurowano osobnego modelu"
                f" sędziego — użyto modelu odpowiedzi (`{cfg.judge_model_info.model}`)."
                " Wyniki sędziego mogą być obciążone stronniczością self-preference.",
                "",
            ]
        )

    langfuse_status = (
        f"`{run.langfuse_run_id}` ({run.langfuse_run_url or 'brak URL'})"
        if cfg.use_langfuse and run.langfuse_run_id
        else "wyłączony (`--no-langfuse`)"
    )

    lines.extend(
        [
            "## Metadane i odtwarzalność",
            "",
            "| Parametr | Wartość |",
            "| --- | --- |",
            f"| Nazwa przebiegu | `{cfg.run_name}` |",
            f"| Czas przebiegu (UTC) | `{run.started_at}` -> `{run.finished_at}` |",
            (
                "| Split / limit / współbieżność |"
                f" `{cfg.split}` / `{cfg.limit}` / `{cfg.concurrency}` |"
            ),
            (
                "| Migawka / rewizja |"
                f" `{cfg.repro_info.snapshot_id}` / `{cfg.repro_info.revision}` |"
            ),
            (
                "| Zestaw fragmentów / wariant |"
                f" `{cfg.repro_info.chunk_set_id}` / `{cfg.repro_info.variant}` |"
            ),
            (
                "| Hash konfiguracji chunkera (`config_sha256`) |"
                f" `{cfg.repro_info.config_sha256}` |"
            ),
            (
                "| Hash stanu fragmentów (`state_sha256`) |"
                f" `{cfg.repro_info.state_sha256 or 'brak'}` |"
            ),
            (f"| Hash `train.json` (`train_json_sha256`) | `{ds.train_json_sha256}` |"),
            (
                "| Ziarno / proporcja splitu (`dev_ratio`) |"
                f" `{ds.split_seed}` / `{ds.dev_ratio}` |"
            ),
            (
                "| Zbiór etykiet (łącznie / ambiguous / aktywne) |"
                f" `{ds.total_labeled}` / `{ds.ambiguous_count}`"
                f" / `{ds.active_count}` |"
            ),
            (
                "| Model odpowiedzi |"
                f" `{cfg.chat_model}` (reasoning: `{cfg.chat_reasoning_effort}`,"
                f" `k={cfg.k}`) |"
            ),
            (
                "| Wersje promptów odpowiedzi |"
                f" {_fmt_dict(cfg.answer_prompt_versions)} |"
            ),
            (
                "| Model sędziego |"
                f" `{cfg.judge_model_info.model}`"
                f" (reasoning: `{cfg.judge_model_info.reasoning_effort}`,"
                f" fallback: `{cfg.judge_model_info.is_fallback_to_chat_model}`) |"
            ),
            (f"| Wersje promptów sędziego | {_fmt_dict(cfg.judge_prompt_versions)} |"),
            (
                "| Hash konfiguracji przebiegu (`config_sha256`) |"
                f" `{cfg.config_sha256}` |"
            ),
            f"| Langfuse Cloud (`experiment_id` / URL) | {langfuse_status} |",
            "",
            "## Podsumowanie Sprawdzianu 2a (Abstencja i fałszywe odmowy)",
            "",
            "| Metryka | Wartość | Próba |",
            "| --- | --- | --- |",
            (
                "| Trafność abstencji (`abstention_accuracy`) |"
                f" **{_fmt_pct(s.abstention_accuracy)}** |"
                f" `n={s.n_unanswerable_eval}` (`verified_unanswerable`) |"
            ),
            (
                "| Odsetek fałszywych odmów (`false_refusal_rate`) |"
                f" **{_fmt_pct(s.false_refusal_rate)}** |"
                f" `n={s.n_answerable_eval}` (`answerable_in_corpus`) |"
            ),
            (
                "| Ocenione / odpowiedzi / abstencje |"
                f" `{s.n_evaluated}` / `{s.n_answered}` / `{s.n_abstained}` |"
                f" `n_total={s.n_total}` |"
            ),
            (
                "| Błędy wykonania (`n_failed`, poza mianownikami) |"
                f" `{s.n_failed}` | `n_total={s.n_total}` |"
            ),
            "",
            (
                "## Podsumowanie Sprawdzianu 1b"
                " (Cytaty, zgodność z referencją i opóźnienie)"
            ),
            "",
            "| Metryka | Wartość |",
            "| --- | --- |",
            (
                "| Zgodność z inwariantami cytatów"
                " (`citation_invariants_pass_rate`) |"
                f" {_fmt_pct(s.citation_invariants_pass_rate)} |"
            ),
            (
                "| Wsparcie cytatów — poziom tezy"
                " (`citation_support_claim_rate`) |"
                f" {_fmt_pct(s.citation_support_claim_rate)} |"
            ),
            (
                "| Wsparcie cytatów — pełne odpowiedzi"
                " (`citation_support_answer_rate`) |"
                f" {_fmt_pct(s.citation_support_answer_rate)} |"
            ),
            (
                "| Zgodność z odpowiedzią referencyjną (`reference_agreement_mean`) |"
                f" {_fmt_float(s.reference_agreement_mean)}"
                f" (`full={s.reference_agreement_counts.get('full', 0)}`,"
                f" `partial={s.reference_agreement_counts.get('partial', 0)}`,"
                f" `incorrect={s.reference_agreement_counts.get('incorrect', 0)}`) |"
            ),
            (
                "| Opóźnienie grafu S-02 `p50` / `p95` |"
                f" {_fmt_ms(s.latency_p50_ms)} / {_fmt_ms(s.latency_p95_ms)} |"
            ),
            (
                f"| W budżecie opóźnienia (`< {int(LATENCY_BUDGET_MS)} ms`) |"
                f" {_fmt_pct(s.within_latency_budget_rate)} |"
            ),
            (
                "| Błędy wykonania (`n_failed`) / błędy sędziego"
                f" (`n_judge_failed`) | `{s.n_failed}` / `{s.n_judge_failed}` |"
            ),
            "",
            "## Rozbicie przyczyn abstencji",
            "",
            "| Przyczyna | Liczba |",
            "| --- | --- |",
        ]
    )

    for cause, count in s.abstention_reasons.items():
        lines.append(f"| `{cause}` | `{count}` |")
    lines.append("")

    lines.extend(_render_error_section(run))

    lines.extend(_render_agreement_section(agreement))

    lines.extend(
        [
            "## Ograniczenia",
            "",
            "- Przypadki `failed` (przekroczenie `answer_deadline_s` lub błąd grafu) są"
            " wykluczone z mianowników metryk jakości i percentyli opóźnień `p50`/`p95`"
            " i raportowane osobno jako `n_failed`.",
            "- Pomiar `latency_ms` obejmuje wyłącznie wykonanie grafu odpowiedzi S-02"
            " (od `retrieve` do `compose`/`abstain`), bez czasu wywołań sędziego LLM.",
            "- Ocena dotyczy pojedynczego wariantu wyszukiwania BM25 (`k="
            f"{cfg.k}`) na zamrożonej migawce `{cfg.repro_info.snapshot_id}`;"
            " pytania oznaczone jako `ambiguous` (`"
            f"{ds.ambiguous_count}`) zostały wykluczone z aktywnej próby.",
            "- Metryki wsparcia cytatów i zgodności z odpowiedzią referencyjną opierają"
            " się na sędzim LLM i wymagają okresowej walidacji ręcznej.",
            "",
        ]
    )

    return "\n".join(lines)
