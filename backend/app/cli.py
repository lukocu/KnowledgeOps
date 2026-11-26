"""Polecenia operatora: `python -m app.cli <polecenie>`."""

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import psycopg

from app.answering.model import make_chat_model, make_judge_model
from app.db import create_pool
from app.evals.agreement import evaluate_judge_agreement
from app.evals.dataset import load_verified_dataset_with_metadata
from app.evals.prepare import (
    FreezeSummary,
    PrepareReport,
    prepare_abstention_candidates,
    validate_and_freeze_labels,
)
from app.evals.report import (
    JudgeAgreementSummary,
    render_markdown_report,
    write_raw_run,
)
from app.evals.runner import (
    DEFAULT_LANGFUSE_DATASET_NAME,
    EvalRunArtifact,
    EvalSplit,
    confirm_eval_run,
    ensure_langfuse_ready,
    run_abstention_eval,
)
from app.evals.sampling import export_manual_audit, sample_for_manual_audit
from app.migrations import MIGRATIONS_DIR, apply_migrations
from app.settings import Settings
from app.techqa.chunking import ChunkerConfig
from app.techqa.importer import ImportReport, import_snapshot, load_manifest
from app.techqa.search import Method, SearchHit, search_chunks


def _migrate() -> int:
    with psycopg.connect(
        Settings().database_url, autocommit=True, connect_timeout=5
    ) as conn:
        applied = apply_migrations(conn, MIGRATIONS_DIR)
    if applied:
        for version in applied:
            print(f"Zastosowano migrację {version}")
    else:
        print("Schemat aktualny")
    return 0


def _print_report(report: ImportReport) -> None:
    print(f"Migawka: {report.snapshot_id}")
    print(f"Zestaw fragmentów: {report.chunk_set_id}")
    print(f"Pliki w corpus.zip: {report.files}")
    print(
        f"Dokumenty: {report.documents}, w tym kanonicznych: "
        f"{report.canonical_documents}"
    )
    print(f"Grupy duplikatów: {len(report.duplicate_groups)}")
    for canonical, copies in report.duplicate_groups:
        print(f"  {canonical} <- {', '.join(copies)}")
    print(
        f"Fragmenty: {report.chunks} (mediana na dokument: "
        f"{report.chunks_median_per_document:g}, maksimum: "
        f"{report.chunks_max_per_document})"
    )
    print(f"Dokumenty bez fragmentów: {len(report.documents_without_chunks)}")
    for doc_id in report.documents_without_chunks:
        print(f"  {doc_id}")
    train = report.train
    print(
        f"train.json: {train.records} rekordów, {train.references} odwołań, "
        f"{train.distinct_documents} różnych dokumentów, braków: {train.missing}"
    )
    print("Czasy etapów:")
    for stage, seconds in report.timings.items():
        print(f"  {stage}: {seconds:.1f} s")
    print(f"Hash stanu (SHA-256): {report.state_sha256}")
    print(f"Porównanie z poprzednim importem: {report.comparison}")
    if report.comparison == "różny":
        print(
            "OSTRZEŻENIE: hash stanu różni się od poprzedniego importu "
            "(zmiana kodu, konfiguracji lub danych)."
        )


def _import_techqa(data_dir: Path | None) -> int:
    directory = data_dir if data_dir is not None else Settings().techqa_dir
    manifest = load_manifest()
    with psycopg.connect(Settings().database_url, connect_timeout=5) as conn:
        report = import_snapshot(conn, directory, manifest, ChunkerConfig())
    _print_report(report)
    return 0


def _print_hits(hits: list[SearchHit]) -> None:
    for hit in hits:
        snippet = " ".join(hit.snippet.split())
        print(f"{hit.rank:>2}  {hit.score:8.3f}  {hit.doc_id}  {hit.chunk_id}")
        print(f"    {' > '.join(hit.headings)}")
        print(f"    {snippet}")


def _search(query: str, method: Method, k: int, chunk_set: str | None) -> int:
    if chunk_set is None:
        chunk_set = load_manifest().chunk_set_id(ChunkerConfig())
    with psycopg.connect(Settings().database_url, connect_timeout=5) as conn:
        hits = search_chunks(conn, query, method=method, chunk_set_id=chunk_set, k=k)
    print(f"Zestaw: {chunk_set}, metoda: {method}, wyniki: {len(hits)}")
    _print_hits(hits)
    if not hits:
        print("Brak wyników")
    return 0


def _default_techqa_dir() -> Path:
    env_dir = os.environ.get("TECHQA_DIR")
    if env_dir:
        return Path(env_dir)
    default = Settings.model_fields["techqa_dir"].default
    return default if isinstance(default, Path) else Path(str(default))


def _print_prepare_report(report: PrepareReport) -> None:
    print(f"Migawka: {report.snapshot_id}")
    print(f"Zestaw fragmentów: {report.chunk_set_id}")
    print(
        f"Rekordy train.json: {report.total_records}, po deduplikacji:"
        f" {report.deduplicated_records}, konflikty: {report.conflict_groups}"
        f" ({report.excluded_conflict_ids} wykluczonych ID)"
    )
    print(
        "Wybrani kandydaci is_impossible=true:"
        f" dev={report.selected_unanswerable_dev},"
        f" test={report.selected_unanswerable_test}"
    )
    print(
        "Wybrani kandydaci is_impossible=false:"
        f" dev={report.selected_answerable_dev},"
        f" test={report.selected_answerable_test}"
    )
    print(f"Przewodnik przeglądu: {report.review_markdown_path}")
    print(f"Szablon etykiet: {report.template_json_path}")


def _eval_prepare_abstention(
    out_dir: Path,
    unanswerable: int,
    answerable: int,
    k: int,
    chunk_set: str | None,
    data_dir: Path | None,
    force: bool = False,
) -> int:
    settings = Settings()
    directory = data_dir if data_dir is not None else settings.techqa_dir
    effective_chunk_set = (
        chunk_set
        if chunk_set is not None
        else load_manifest().chunk_set_id(ChunkerConfig())
    )
    with psycopg.connect(settings.database_url, connect_timeout=5) as conn:
        report = prepare_abstention_candidates(
            conn,
            techqa_dir=directory,
            chunk_set_id=effective_chunk_set,
            out_dir=out_dir,
            unanswerable_candidates=unanswerable,
            answerable_candidates=answerable,
            top_k=k,
            overwrite=force,
        )
    _print_prepare_report(report)
    return 0


def _print_freeze_summary(summary: FreezeSummary) -> None:
    print(f"Zapisano zamrożony zbiór: {summary.target_path}")
    print(f"Łącznie etykiet: {summary.total_items}")
    print(
        f"dev: verified_unanswerable={summary.dev_verified_unanswerable},"
        f" answerable_in_corpus={summary.dev_answerable_in_corpus},"
        f" ambiguous={summary.dev_ambiguous}"
    )
    print(
        f"test: verified_unanswerable={summary.test_verified_unanswerable},"
        f" answerable_in_corpus={summary.test_answerable_in_corpus},"
        f" ambiguous={summary.test_ambiguous}"
    )


def _eval_freeze_abstention(
    input_path: Path, output_path: Path, data_dir: Path | None
) -> int:
    directory = data_dir if data_dir is not None else _default_techqa_dir()
    summary = validate_and_freeze_labels(input_path, output_path, directory)
    _print_freeze_summary(summary)
    return 0


def _print_eval_summary(
    artifact: EvalRunArtifact,
    raw_path: Path,
    report_path: Path,
    audit_json_path: Path,
    audit_md_path: Path,
) -> None:
    s = artifact.summary
    abst = (
        f"{s.abstention_accuracy * 100:.1f}%"
        if s.abstention_accuracy is not None
        else "n/d"
    )
    frr = (
        f"{s.false_refusal_rate * 100:.1f}%"
        if s.false_refusal_rate is not None
        else "n/d"
    )
    print(f"Przebieg: {artifact.config.run_name}")
    print(f"Ocenione: {s.n_evaluated}/{s.n_total} (failed={s.n_failed})")
    print(
        f"Sprawdzian 2a: abstention_accuracy={abst}"
        f" (n={s.n_unanswerable_eval}), false_refusal_rate={frr}"
        f" (n={s.n_answerable_eval})"
    )
    if artifact.langfuse_run_id:
        print(
            f"Langfuse run: {artifact.langfuse_run_id}"
            f" ({artifact.langfuse_run_url or 'brak URL'})"
        )
    print(f"Surowy JSON: {raw_path}")
    print(f"Raport Markdown: {report_path}")
    print(f"Arkusz audytu JSON: {audit_json_path}")
    print(f"Arkusz audytu Markdown: {audit_md_path}")


def _eval_abstention(
    dataset_path: Path,
    split: EvalSplit,
    limit: int | None,
    concurrency: int,
    out_dir: Path,
    report_out: Path | None,
    no_langfuse: bool,
    yes: bool,
) -> int:
    settings = Settings()
    use_langfuse = not no_langfuse
    ensure_langfuse_ready(settings, use_langfuse=use_langfuse)

    loaded = load_verified_dataset_with_metadata(
        dataset_path, settings.techqa_dir, split=split
    )
    selected_items = (
        list(loaded.items[:limit]) if limit is not None else list(loaded.items)
    )
    chat_model = make_chat_model(settings)
    judge_model, judge_info = make_judge_model(settings)

    if not yes:
        confirmed = confirm_eval_run(
            items=selected_items,
            split=split,
            chat_model=settings.chat_model,
            chat_reasoning_effort=settings.chat_reasoning_effort,
            judge_model_info=judge_info,
            use_langfuse=use_langfuse,
            dataset_name=DEFAULT_LANGFUSE_DATASET_NAME,
        )
        if not confirmed:
            print("Przerwano przebieg ewaluacji.")
            return 0

    async def _run() -> EvalRunArtifact:
        pool = create_pool(settings.database_url)
        async with pool:
            return await run_abstention_eval(
                dataset=loaded,
                settings=settings,
                pool=pool,
                split=split,
                limit=limit,
                concurrency=concurrency,
                use_langfuse=use_langfuse,
                chat_model=chat_model,
                judge_model=judge_model,
                judge_model_info=judge_info,
            )

    artifact = asyncio.run(_run(), loop_factory=asyncio.SelectorEventLoop)
    raw_path = out_dir / f"{artifact.config.run_name}.json"
    write_raw_run(raw_path, artifact)

    md_path = (
        report_out
        if report_out is not None
        else out_dir / f"{artifact.config.run_name}.md"
    )
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown_report(artifact), encoding="utf-8")

    audit_entries = sample_for_manual_audit(artifact)
    audit_json_path, audit_md_path = export_manual_audit(
        audit_entries, out_dir, artifact.config.run_name
    )

    _print_eval_summary(artifact, raw_path, md_path, audit_json_path, audit_md_path)
    return 0


def _print_agreement_summary(summary: JudgeAgreementSummary) -> None:
    def _pct(val: float | None) -> str:
        return f"{val * 100:.1f}%" if val is not None else "n/d"

    def _kappa(val: float | None, note: str | None) -> str:
        if val is not None:
            return f"{val:.3f}"
        return f"n/d ({note})" if note else "n/d"

    print(f"Próbka / ocenione ręcznie: {summary.n_sampled} / {summary.n_reviewed}")
    print(
        f"Wsparcie cytatów (n={summary.n_citation_pairs}):"
        f" zgodność={_pct(summary.citation_agreement_rate)},"
        f" kappa={_kappa(summary.citation_cohens_kappa, summary.citation_kappa_note)}"
    )
    print(
        f"Zgodność referencyjna (n={summary.n_reference_pairs}):"
        f" zgodność={_pct(summary.reference_agreement_rate)},"
        f" kappa={_kappa(summary.reference_cohens_kappa, summary.reference_kappa_note)}"
    )
    if summary.n_abstained_sampled > 0:
        print(
            f"Warstwa abstained (przegląd jakościowy):"
            f" {summary.n_abstained_reviewed}/{summary.n_abstained_sampled} ocenionych"
            f" (uzasadnione={summary.abstained_justified_count},"
            f" nieuzasadnione={summary.abstained_unjustified_count})"
        )


def _eval_judge_agreement(
    run_path: Path,
    audit_path: Path,
    report_out: Path | None,
) -> int:
    summary = evaluate_judge_agreement(run_path, audit_path)
    _print_agreement_summary(summary)
    if report_out is not None:
        artifact = EvalRunArtifact.model_validate_json(
            run_path.read_text(encoding="utf-8")
        )
        report_out.parent.mkdir(parents=True, exist_ok=True)
        report_out.write_text(
            render_markdown_report(artifact, agreement=summary),
            encoding="utf-8",
        )
        print(f"Zaktualizowano raport Markdown: {report_out}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    # Konsola Windows domyślnie nie jest UTF-8; polskie komunikaty i treść dokumentów.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True, metavar="polecenie")
    commands.add_parser("migrate", help="stosuje brakujące migracje schematu")
    importer = commands.add_parser(
        "import-techqa", help="importuje migawkę TechQA do bazy"
    )
    importer.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="katalog z danymi (domyślnie TECHQA_DIR)",
    )
    searcher = commands.add_parser(
        "search", help="wyszukuje fragmenty (BM25 albo tsvector)"
    )
    searcher.add_argument("query", metavar="QUERY", help="zapytanie")
    searcher.add_argument("--method", choices=("bm25", "fts"), default="bm25")
    searcher.add_argument("--k", type=int, default=10, help="liczba wyników")
    searcher.add_argument(
        "--chunk-set",
        default=None,
        help="id zestawu (domyślnie techqa@<rewizja>/sections-v1)",
    )
    preparer = commands.add_parser(
        "eval-prepare-abstention",
        help="eksportuje kandydatów abstynencji z top-k BM25 do weryfikacji",
    )
    preparer.add_argument(
        "--out-dir",
        type=Path,
        default=Path("../data/evals"),
        help="katalog wyjściowy (domyślnie ../data/evals)",
    )
    preparer.add_argument(
        "--unanswerable",
        type=int,
        default=80,
        help="liczba kandydatów is_impossible=true (domyślnie 80)",
    )
    preparer.add_argument(
        "--answerable",
        type=int,
        default=60,
        help="liczba kandydatów is_impossible=false (domyślnie 60)",
    )
    preparer.add_argument(
        "--k",
        type=int,
        default=10,
        help="liczba trafień BM25 na kandydata (domyślnie 10)",
    )
    preparer.add_argument(
        "--chunk-set",
        default=None,
        help="id zestawu fragmentów (domyślnie techqa@<rewizja>/sections-v1)",
    )
    preparer.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="katalog z danymi TechQA (domyślnie TECHQA_DIR)",
    )
    preparer.add_argument(
        "--force",
        action="store_true",
        help="pozwól nadpisać istniejący plik abstention-labels-template.json",
    )
    freezer = commands.add_parser(
        "eval-freeze-abstention",
        help="waliduje szablon etykiet i zapisuje zamrożony plik abstention-dataset",
    )
    freezer.add_argument(
        "--input",
        dest="input_path",
        type=Path,
        required=True,
        help="ścieżka do uzupełnionego szablonu etykiet JSON",
    )
    freezer.add_argument(
        "--output",
        dest="output_path",
        type=Path,
        default=Path("evals/abstention-dataset.json"),
        help="docelowa ścieżka zamrożonego pliku etykiet",
    )
    freezer.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="katalog z danymi TechQA (domyślnie TECHQA_DIR)",
    )
    evaluator = commands.add_parser(
        "eval-abstention",
        help=(
            "uruchamia ewaluację abstynencji i jakości odpowiedzi (Sprawdzian 1b i 2a)"
        ),
    )
    evaluator.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/abstention-dataset.json"),
        help="ścieżka do zamrożonego pliku etykiet JSON",
    )
    evaluator.add_argument(
        "--split",
        choices=("dev", "test", "all"),
        default="all",
        help="split zbioru do ewaluacji (domyślnie all)",
    )
    evaluator.add_argument(
        "--limit",
        type=int,
        default=None,
        help="opcjonalny limit liczby pytań",
    )
    evaluator.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="maksymalna liczba równoległych pytań (domyślnie 2)",
    )
    evaluator.add_argument(
        "--out-dir",
        type=Path,
        default=Path("../data/evals"),
        help="katalog na surowy zapis JSON i domyślny raport MD",
    )
    evaluator.add_argument(
        "--report-out",
        type=Path,
        default=None,
        help="opcjonalna ścieżka docelowa raportu Markdown",
    )
    evaluator.add_argument(
        "--no-langfuse",
        action="store_true",
        help="uruchamia lokalnie bez zapisu eksperymentu w Langfuse Cloud",
    )
    evaluator.add_argument(
        "--yes",
        action="store_true",
        help="pomija bramkę potwierdzenia kosztu przed startem",
    )
    agreement_cmd = commands.add_parser(
        "eval-judge-agreement",
        help="oblicza zgodność sędziego LLM z ocenami człowieka (Cohen's kappa)",
    )
    agreement_cmd.add_argument(
        "--run",
        dest="run_path",
        type=Path,
        required=True,
        help="ścieżka do surowego zapisu przebiegu JSON",
    )
    agreement_cmd.add_argument(
        "--audit",
        dest="audit_path",
        type=Path,
        required=True,
        help="ścieżka do uzupełnionego pliku audytu ręcznego JSON",
    )
    agreement_cmd.add_argument(
        "--report-out",
        type=Path,
        default=None,
        help="opcjonalna ścieżka docelowa raportu Markdown z sekcją walidacji",
    )
    args = parser.parse_args(argv)

    try:
        if args.command == "migrate":
            return _migrate()
        if args.command == "import-techqa":
            return _import_techqa(args.data_dir)
        if args.command == "search":
            return _search(args.query, args.method, args.k, args.chunk_set)
        if args.command == "eval-prepare-abstention":
            return _eval_prepare_abstention(
                args.out_dir,
                args.unanswerable,
                args.answerable,
                args.k,
                args.chunk_set,
                args.data_dir,
                args.force,
            )
        if args.command == "eval-freeze-abstention":
            return _eval_freeze_abstention(
                args.input_path, args.output_path, args.data_dir
            )
        if args.command == "eval-abstention":
            return _eval_abstention(
                args.dataset,
                args.split,
                args.limit,
                args.concurrency,
                args.out_dir,
                args.report_out,
                args.no_langfuse,
                args.yes,
            )
        if args.command == "eval-judge-agreement":
            return _eval_judge_agreement(
                args.run_path, args.audit_path, args.report_out
            )
    except Exception as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
