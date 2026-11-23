"""Chunker `sections-v1`: fragmenty do `max_chars` wzdłuż sekcji TechQA z offsetami."""

import hashlib
import io
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from app.techqa.normalize import NORMALIZER_VERSION, normalize_body
from app.techqa.parse import parse_document

DEFAULT_HEADING_PATTERN = r"^(?=[^a-z]*[A-Z]{3})[A-Z0-9][A-Z0-9 ()/&,\-:'.]{2,79}$"

_SEPARATORS = ("\n\n", "\n")


@dataclass(frozen=True)
class ChunkerConfig:
    variant: str = "sections-v1"
    max_chars: int = 1500
    overlap_chars: int = 150
    heading_pattern: str = DEFAULT_HEADING_PATTERN
    normalizer: str = NORMALIZER_VERSION

    def config_sha256(self) -> str:
        canonical = json.dumps(
            asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    headings: tuple[str, ...]
    start: int
    end: int
    text: str


Span = tuple[int, int]


def _trim(text: str, start: int, end: int) -> Span | None:
    """Zawęża zakres do niebiałych znaków; None, gdy zakres jest pusty."""
    piece = text[start:end]
    stripped = piece.strip()
    if not stripped:
        return None
    left = len(piece) - len(piece.lstrip())
    return start + left, start + left + len(stripped)


def _sections(text: str, heading_re: re.Pattern[str]) -> list[tuple[Span, str | None]]:
    """Sekcje jako (zakres po przycięciu, nagłówek). Nagłówek: linia po pustej linii."""
    starts: list[tuple[int, str]] = []
    pos = 0
    previous_blank = True
    for line in text.split("\n"):
        stripped = line.strip()
        if previous_blank and stripped and heading_re.fullmatch(stripped):
            starts.append((pos, stripped))
        previous_blank = not stripped
        pos += len(line) + 1

    boundaries: list[tuple[int, str | None]] = []
    if not starts or starts[0][0] > 0:
        boundaries.append((0, None))
    boundaries.extend(starts)

    sections: list[tuple[Span, str | None]] = []
    for index, (start, heading) in enumerate(boundaries):
        end = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(text)
        span = _trim(text, start, end)
        if span is not None:
            sections.append((span, heading))
    return sections


def _hard_cut(text: str, start: int, end: int, config: ChunkerConfig) -> list[Span]:
    """Twarde cięcie z cofnięciem do ostatniego białego znaku w limicie."""
    spans: list[Span] = []
    pos = start
    first = True
    while end - pos > 0:
        # Kolejne części są krótsze o nakładanie, żeby zmieściło się przed nimi.
        limit = config.max_chars if first else config.max_chars - config.overlap_chars
        first = False
        if end - pos <= limit:
            spans.append((pos, end))
            break
        cut = next((k for k in range(pos + limit, pos, -1) if text[k].isspace()), None)
        if cut is None:
            spans.append((pos, pos + limit))
            pos += limit
            continue
        spans.append((pos, cut))
        pos = cut
        while pos < end and text[pos].isspace():
            pos += 1
    trimmed = [_trim(text, a, b) for a, b in spans]
    return [s for s in trimmed if s is not None]


def _atoms(
    text: str, start: int, end: int, separators: tuple[str, ...], config: ChunkerConfig
) -> list[Span]:
    """Rekurencyjnie dzieli zakres na części nieprzekraczające limitu."""
    if end - start <= config.max_chars:
        return [(start, end)]
    if not separators:
        return _hard_cut(text, start, end, config)
    pieces: list[Span] = []
    pos = start
    for part in text[start:end].split(separators[0]):
        span = _trim(text, pos, pos + len(part))
        if span is not None:
            pieces.append(span)
        pos += len(part) + len(separators[0])
    if len(pieces) <= 1:
        return _atoms(text, start, end, separators[1:], config)
    atoms: list[Span] = []
    for a, b in pieces:
        atoms.extend(_atoms(text, a, b, separators[1:], config))
    return atoms


def _overlap_start(
    text: str, prev: Span, own_start: int, end: int, config: ChunkerConfig
) -> int:
    """Początek fragmentu z nakładaniem na poprzedni; całość mieści się w limicie."""
    low = max(prev[1] - config.overlap_chars, end - config.max_chars, prev[0] + 1)
    if low >= own_start:
        return own_start

    def skip_whitespace(pos: int) -> int:
        while pos < own_start and text[pos].isspace():
            pos += 1
        return pos

    # Najpierw początek pełnej linii (blok kodu i logów), potem najbliższy biały znak.
    if low == 0 or text[low - 1] == "\n":
        line_start: int | None = low
    else:
        newline = text.find("\n", low, own_start)
        line_start = newline + 1 if newline != -1 else None
    if line_start is not None:
        candidate = skip_whitespace(line_start)
        if candidate < own_start:
            return candidate

    pos = low
    if not text[low - 1].isspace():
        while pos < own_start and not text[pos].isspace():
            pos += 1
    candidate = skip_whitespace(pos)
    return candidate if candidate < own_start else own_start


def _split_section(
    text: str, start: int, end: int, config: ChunkerConfig
) -> list[Span]:
    """Dzieli sekcję dłuższą niż limit: części łączone zachłannie, z nakładaniem."""
    spans: list[Span] = []
    current: Span | None = None
    for atom in _atoms(text, start, end, _SEPARATORS, config):
        # Poza pierwszym fragmentem rezerwujemy miejsce na nakładanie.
        budget = (
            config.max_chars if not spans else config.max_chars - config.overlap_chars
        )
        if current is not None and atom[1] - current[0] <= budget:
            current = (current[0], atom[1])
        else:
            if current is not None:
                spans.append(current)
            current = atom
    if current is not None:
        spans.append(current)

    result: list[Span] = []
    for index, (span_start, span_end) in enumerate(spans):
        if index:
            span_start = _overlap_start(text, result[-1], span_start, span_end, config)
        result.append((span_start, span_end))
    return result


def chunk_document(text: str, config: ChunkerConfig) -> list[Chunk]:
    """Dzieli znormalizowaną treść na fragmenty; `text[start:end] == chunk.text`."""
    heading_re = re.compile(config.heading_pattern)
    pieces: list[tuple[Span, tuple[str, ...]]] = []

    group: Span | None = None
    group_headings: list[str] = []

    def flush() -> None:
        nonlocal group, group_headings
        if group is not None:
            pieces.append((group, tuple(group_headings)))
        group = None
        group_headings = []

    for (start, end), heading in _sections(text, heading_re):
        if end - start > config.max_chars:
            flush()
            headings = (heading,) if heading else ()
            pieces.extend(
                (span, headings) for span in _split_section(text, start, end, config)
            )
        elif group is not None and end - group[0] <= config.max_chars:
            group = (group[0], end)
            if heading:
                group_headings.append(heading)
        else:
            flush()
            group = (start, end)
            group_headings = [heading] if heading else []
    flush()

    return [
        Chunk(ordinal=i, headings=headings, start=a, end=b, text=text[a:b])
        for i, ((a, b), headings) in enumerate(pieces)
    ]


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Użycie: python -m app.techqa.chunking <ścieżka.txt>", file=sys.stderr)
        return 2
    # Konsola Windows bywa w cp1250: wypisujemy zawsze w UTF-8.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    raw = Path(argv[0]).read_text(encoding="utf-8")
    document = parse_document(raw)
    body = normalize_body(document.body)
    chunks = chunk_document(body, ChunkerConfig())
    print(f"Tytuł: {document.title}")
    print(f"Znormalizowana treść: {len(body)} znaków, fragmentów: {len(chunks)}")
    for chunk in chunks:
        print("=" * 72)
        print(
            f"#{chunk.ordinal} nagłówki={list(chunk.headings)} "
            f"offsety=[{chunk.start}, {chunk.end}) długość={len(chunk.text)}"
        )
        print(chunk.text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
