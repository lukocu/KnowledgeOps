import re
from pathlib import Path

import pytest

from app.techqa.chunking import (
    DEFAULT_HEADING_PATTERN,
    Chunk,
    ChunkerConfig,
    chunk_document,
)
from app.techqa.normalize import NORMALIZER_VERSION, normalize_body
from app.techqa.parse import parse_document
from tests.techqa.helpers import check_chunk_invariants, fixture_paths, read_fixture

CONFIG = ChunkerConfig()
_VERSION = re.compile(r"\bV?\d+(?:\.\d+){2,}")


def _chunks(name: str) -> tuple[str, list[Chunk]]:
    body = normalize_body(parse_document(read_fixture(name)).body)
    return body, check_chunk_invariants(body, CONFIG)


def test_default_config() -> None:
    assert CONFIG.variant == "sections-v1"
    assert CONFIG.max_chars == 1500
    assert CONFIG.overlap_chars == 150
    assert CONFIG.heading_pattern == DEFAULT_HEADING_PATTERN
    assert CONFIG.normalizer == NORMALIZER_VERSION


def test_config_sha256_is_stable_and_sensitive() -> None:
    assert CONFIG.config_sha256() == ChunkerConfig().config_sha256()
    assert len(CONFIG.config_sha256()) == 64
    assert ChunkerConfig(max_chars=1000).config_sha256() != CONFIG.config_sha256()


@pytest.mark.parametrize("path", fixture_paths(), ids=lambda p: p.stem)
def test_invariants_on_every_fixture(path: Path) -> None:
    body = normalize_body(parse_document(path.read_text(encoding="utf-8")).body)
    chunks = check_chunk_invariants(body, CONFIG)
    assert chunks, "każda fikstura ma treść"


def test_empty_text_gives_no_chunks() -> None:
    assert chunk_document("", CONFIG) == []


def test_short_apar_sections_are_merged() -> None:
    body, chunks = _chunks("apar_template")
    assert len(body) <= CONFIG.max_chars
    assert len(chunks) == 1
    assert "ERROR DESCRIPTION" in chunks[0].headings
    assert "PROBLEM CONCLUSION" in chunks[0].headings
    assert len(chunks[0].headings) >= 5


def test_document_without_headings() -> None:
    body, chunks = _chunks("no_headings")
    assert len(chunks) == 1
    assert chunks[0].headings == ()
    assert chunks[0].text == body


def test_text_before_first_heading_is_headingless_section() -> None:
    text = "Intro line.\n\nCAUSE\nSome cause."
    chunks = check_chunk_invariants(text, ChunkerConfig(max_chars=15, overlap_chars=0))
    assert chunks[0].headings == ()
    assert chunks[0].text == "Intro line."
    assert chunks[1].headings == ("CAUSE",)


def test_heading_must_follow_blank_line() -> None:
    text = "intro\nCAUSE\nbody"
    chunks = check_chunk_invariants(text, CONFIG)
    assert chunks[0].headings == ()


def test_long_section_is_split_with_overlap() -> None:
    body, chunks = _chunks("long_section")
    assert len(body) > 4000
    split = [c for c in chunks if c.headings == ("RESOLVING THE PROBLEM",)]
    assert len(split) >= 3
    for previous, current in zip(split, split[1:], strict=False):
        overlap = previous.end - current.start
        assert 0 < overlap <= CONFIG.overlap_chars
        assert current.start > previous.start
        # Nakładanie zaczyna się od początku tokenu.
        assert body[current.start - 1].isspace()


def test_long_line_hard_cut_keeps_version_numbers_whole() -> None:
    body, chunks = _chunks("long_line_versions")
    assert len(body) > CONFIG.max_chars
    assert len(chunks) >= 3
    versions = set(_VERSION.findall(body))
    assert {"8.5.5.1", "V9.0.0.7"} <= versions
    for version in versions:
        assert any(version in chunk.text for chunk in chunks), version
    # Cięcie wypada na białym znaku, a nie w środku tokenu.
    for chunk in chunks:
        assert chunk.start == 0 or body[chunk.start - 1].isspace()
        assert chunk.end == len(body) or body[chunk.end].isspace()


def test_hard_cut_inside_token_only_without_whitespace() -> None:
    text = "x" * 4000
    chunks = check_chunk_invariants(text, CONFIG)
    assert len(chunks) >= 3


def test_code_block_splits_on_newline_not_hard_cut() -> None:
    body, chunks = _chunks("code_block")
    block = [c for c in chunks if c.headings == ("DIAGNOSING THE PROBLEM",)]
    assert len(block) >= 2
    for chunk in block:
        assert chunk.start == 0 or body[chunk.start - 1] == "\n"
        assert chunk.end == len(body) or body[chunk.end] == "\n"
    # Nakładanie: kolejny fragment zaczyna się od pełnej linii przed końcem.
    assert block[1].start < block[0].end


def test_unusual_headings_pinned_for_sections_v1() -> None:
    _, chunks = _chunks("unusual_headings")
    headings = [h for c in chunks for h in c.headings]
    assert "CI62KML" in headings
    # Linia logu wielkimi literami jest nagłówkiem; zwykła wielkość liter nie.
    assert "APPHDL  : 0-270 APPID: *LOCAL.sample.123" not in headings
    assert "Problem Description:" not in headings


def test_log_line_in_all_caps_is_heading() -> None:
    text = "INTRO\nx\n\nAPPHDL  : 0-270 APPID:\nmsg\n"
    chunks = check_chunk_invariants(text, ChunkerConfig(max_chars=12, overlap_chars=0))
    assert "APPHDL  : 0-270 APPID:" in [h for c in chunks for h in c.headings]


def test_mixed_case_heading_merges_with_previous_section() -> None:
    body, chunks = _chunks("unusual_headings")
    holder = next(c for c in chunks if "Problem Description:" in c.text)
    assert "Mixed case text" in holder.text
    assert body[holder.start : holder.end] == holder.text


def test_deterministic() -> None:
    body, _ = _chunks("long_section")
    assert chunk_document(body, CONFIG) == chunk_document(body, CONFIG)


def test_small_limits_keep_invariants() -> None:
    body = normalize_body(parse_document(read_fixture("long_section")).body)
    for max_chars, overlap in [(200, 30), (80, 20), (50, 0)]:
        check_chunk_invariants(
            body, ChunkerConfig(max_chars=max_chars, overlap_chars=overlap)
        )


@pytest.mark.parametrize(
    ("max_chars", "overlap_chars"),
    [(100, 100), (100, 150), (100, -1), (0, 0), (-5, 0)],
)
def test_invalid_config_is_rejected(max_chars: int, overlap_chars: int) -> None:
    with pytest.raises(ValueError):
        ChunkerConfig(max_chars=max_chars, overlap_chars=overlap_chars)
