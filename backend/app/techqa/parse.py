"""Koperta dokumentu TechQA: tytuł i treść."""

from dataclasses import dataclass

_TITLE_PREFIX = "Title: "
_TITLE_SUFFIX = " - United States"
_TEXT_SEPARATOR = "\n\nText:\n"


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    body: str


def parse_document(raw: str) -> ParsedDocument:
    """Dzieli surowy plik po pierwszym `\n\nText:\n` na tytuł i treść."""
    head, separator, body = raw.partition(_TEXT_SEPARATOR)
    if not separator:
        raise ValueError(f"Brak koperty: nie znaleziono separatora {_TEXT_SEPARATOR!r}")
    if not head.startswith(_TITLE_PREFIX):
        raise ValueError(f"Brak koperty: dokument nie zaczyna się od {_TITLE_PREFIX!r}")
    # Tytuł bywa wieloliniowy (133 dokumenty w korpusie): linie łączymy spacją.
    title = " ".join(line.strip() for line in head[len(_TITLE_PREFIX) :].split("\n"))
    title = title.strip()
    if title.endswith(_TITLE_SUFFIX):
        title = title[: -len(_TITLE_SUFFIX)].rstrip()
    return ParsedDocument(title=title, body=body)
