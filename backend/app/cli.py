"""Polecenia operatora: `python -m app.cli <polecenie>`."""

import argparse
import sys
from collections.abc import Sequence

import psycopg

from app.migrations import MIGRATIONS_DIR, apply_migrations
from app.settings import Settings


def _migrate() -> int:
    with psycopg.connect(Settings().database_url, autocommit=True) as conn:
        applied = apply_migrations(conn, MIGRATIONS_DIR)
    if applied:
        for version in applied:
            print(f"Zastosowano migrację {version}")
    else:
        print("Schemat aktualny")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True, metavar="polecenie")
    commands.add_parser("migrate", help="stosuje brakujące migracje schematu")
    args = parser.parse_args(argv)

    try:
        if args.command == "migrate":
            return _migrate()
    except Exception as exc:
        print(f"Błąd: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
