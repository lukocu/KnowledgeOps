"""Prompty w plikach `*.md`; wersją promptu jest skrót SHA-256 bajtów pliku.

Pliki są czytane raz na proces (cache), więc zapisana wersja zawsze odpowiada
treści faktycznie wysłanej do modelu. Zmiana promptu wymaga restartu backendu.
"""

import hashlib
from functools import cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent
PROMPT_NAMES = ("draft", "verify")


def _path(name: str) -> Path:
    if name not in PROMPT_NAMES:
        raise ValueError(f"nieznany prompt: {name}")
    return PROMPTS_DIR / f"{name}.md"


@cache
def _read(name: str) -> bytes:
    return _path(name).read_bytes()


@cache
def load_prompt(name: str) -> str:
    return _path(name).read_text(encoding="utf-8")


def prompt_version(name: str) -> str:
    """Pierwsze 12 znaków hex SHA-256 bajtów pliku promptu."""
    return hashlib.sha256(_read(name)).hexdigest()[:12]


def prompt_versions() -> dict[str, str]:
    return {name: prompt_version(name) for name in PROMPT_NAMES}
