"""Polecenia operatora: `python -m app.cli <polecenie>`."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import psycopg

from app.migrations import MIGRATIONS_DIR, apply_migrations
from app.settings import Settings
from app.techqa.chunking import ChunkerConfig
from app.techqa.importer import ImportReport, import_snapshot, load_manifest


def _migrate() -> int:
    with psycopg.connect(Settings().database_url, autocommit=True) as conn:
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
    with psycopg.connect(Settings().database_url) as conn:
        report = import_snapshot(conn, directory, manifest, ChunkerConfig())
    _print_report(report)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
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
    args = parser.parse_args(argv)

    try:
        if args.command == "migrate":
            return _migrate()
        if args.command == "import-techqa":
            return _import_techqa(args.data_dir)
    except Exception as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
