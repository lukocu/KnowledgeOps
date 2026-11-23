"""Runner migracji SQL: stosuje brakujące pliki `NNNN_*.sql` po kolei."""

import hashlib
import re
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# Stały klucz blokady doradczej, wspólny dla wszystkich uruchomień runnera.
ADVISORY_LOCK_KEY = 7_202_611_230_001

_FILE_PATTERN = re.compile(r"^\d{4}_\w+\.sql$")


class MigrationError(Exception):
    """Stan migracji w bazie nie zgadza się z plikami."""


def _migration_files(directory: Path) -> list[Path]:
    return sorted(
        (p for p in directory.iterdir() if p.is_file() and _FILE_PATTERN.match(p.name)),
        key=lambda p: p.name,
    )


def apply_migrations(conn: psycopg.Connection, directory: Path) -> list[str]:
    """Stosuje brakujące migracje i zwraca wersje zastosowane w tym uruchomieniu.

    Połączenie nie może mieć otwartej transakcji: każdy plik idzie w osobnej
    transakcji razem z wpisem do `schema_migrations`.
    """
    files = _migration_files(directory)
    with conn.transaction():
        conn.execute("SELECT pg_advisory_lock(%s)", (ADVISORY_LOCK_KEY,))
    try:
        with conn.transaction():
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " version text PRIMARY KEY,"
                " sha256 text NOT NULL,"
                " applied_at timestamptz NOT NULL DEFAULT now())"
            )
            rows = conn.execute(
                "SELECT version, sha256 FROM schema_migrations"
            ).fetchall()
        recorded: dict[str, str] = {str(r[0]): str(r[1]) for r in rows}

        contents = {p.stem: p.read_bytes() for p in files}
        missing = sorted(set(recorded) - set(contents))
        if missing:
            raise MigrationError(
                "Brak plików dla zastosowanych migracji: " + ", ".join(missing)
            )
        for version, sha in recorded.items():
            if hashlib.sha256(contents[version]).hexdigest() != sha:
                raise MigrationError(
                    f"Zmieniono treść zastosowanej migracji {version}"
                    " (SHA-256 się nie zgadza)"
                )

        applied: list[str] = []
        for version, body in contents.items():
            if version in recorded:
                continue
            with conn.transaction():
                conn.execute(body)
                conn.execute(
                    "INSERT INTO schema_migrations (version, sha256) VALUES (%s, %s)",
                    (version, hashlib.sha256(body).hexdigest()),
                )
            applied.append(version)
        return applied
    finally:
        with conn.transaction():
            conn.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_KEY,))
