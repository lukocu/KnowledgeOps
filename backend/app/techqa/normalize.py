"""Normalizacja treści dokumentu TechQA (sześć reguł z profilu danych)."""

import html
import re
from html.entities import html5

NORMALIZER_VERSION = "norm-v1"

# Tylko encje zakończone średnikiem; ciągi bez średnika (`&param_x=`, `&#27`)
# zostają bez zmian, bo to część URL-i i kodu.
_ENTITY = re.compile(r"&(#[0-9]+;|#[xX][0-9a-fA-F]+;|[A-Za-z][A-Za-z0-9]*;)")

_BULLETS = frozenset("*•-o·+")


def _decode_entity(match: re.Match[str]) -> str:
    body = match.group(1)
    if body.startswith("#"):
        return html.unescape(match.group(0))
    return html5.get(body, match.group(0))


def normalize_body(body: str) -> str:
    """Usuwa szum zaobserwowany w profilu; kod, listy i powtórzenia zostają."""
    # 1. Encje ze średnikiem, jeden poziom (`&amp;lt;` daje `&lt;`).
    text = _ENTITY.sub(_decode_entity, body)
    # 2. CR, 3. NBSP.
    text = text.replace("\r", "").replace(" ", " ")
    # Dzielimy tylko po LF: `splitlines` rozcinałoby też po innych znakach.
    # 4. Białe znaki na końcu linii.
    lines = [line.rstrip() for line in text.split("\n")]
    # 5. Linie będące samym punktorem.
    lines = [line for line in lines if line.strip() not in _BULLETS]

    # 6. Trzy i więcej pustych linii z rzędu dają jedną; brzegi bez pustych linii.
    result: list[str] = []
    blanks = 0
    for line in lines:
        if line:
            if blanks:
                result.extend([""] * (1 if blanks >= 3 else blanks))
            blanks = 0
            result.append(line)
        else:
            blanks += 1
    # Puste linie na początku wycinamy tutaj; na końcu nie są dopisywane.
    while result and not result[0]:
        result.pop(0)
    return "\n".join(result)
