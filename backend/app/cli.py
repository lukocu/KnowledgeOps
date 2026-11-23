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
from app.techqa.search import Method, SearchHit, search_chunks


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


def _print_hits(hits: list[SearchHit]) -> None:
    for hit in hits:
        snippet = " ".join(hit.snippet.split())
        print(f"{hit.rank:>2}  {hit.score:8.3f}  {hit.doc_id}  {hit.chunk_id}")
        print(f"    {' > '.join(hit.headings)}")
        print(f"    {snippet}")


def _search(query: str, method: Method, k: int, chunk_set: str | None) -> int:
    if chunk_set is None:
        chunk_set = load_manifest().chunk_set_id(ChunkerConfig())
    with psycopg.connect(Settings().database_url) as conn:
        hits = search_chunks(conn, query, method=method, chunk_set_id=chunk_set, k=k)
    print(f"Zestaw: {chunk_set}, metoda: {method}, wyniki: {len(hits)}")
    _print_hits(hits)
    if not hits:
        print("Brak wyników")
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
    args = parser.parse_args(argv)

    # Konsola Windows domyślnie nie jest UTF-8; polskie komunikaty i treść dokumentów.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    try:
        if args.command == "migrate":
            return _migrate()
        if args.command == "import-techqa":
            return _import_techqa(args.data_dir)
        if args.command == "search":
            return _search(args.query, args.method, args.k, args.chunk_set)
    except Exception as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
