from pathlib import Path

import pytest

from app.techqa.normalize import NORMALIZER_VERSION, normalize_body
from app.techqa.parse import parse_document
from tests.techqa.helpers import fixture_paths, read_fixture


def test_version_constant() -> None:
    assert NORMALIZER_VERSION == "norm-v1"


def test_decodes_named_and_numeric_entities() -> None:
    assert (
        normalize_body("a &lt;b&gt; &amp; &quot;c&quot; &apos;d&apos;")
        == "a <b> & \"c\" 'd'"
    )
    assert normalize_body("&#65;&#x42;&#X43;") == "ABC"


def test_entity_decoding_is_single_level() -> None:
    assert normalize_body("&amp;lt;") == "&lt;"
    assert normalize_body("&amp;amp;") == "&amp;"


def test_second_pass_boundary_for_nested_entity() -> None:
    # Świadoma granica: idempotencja nie obejmuje encji zagnieżdżonych ze średnikiem.
    once = normalize_body("&amp;lt;")
    assert once == "&lt;"
    assert normalize_body(once) == "<"


def test_entity_without_semicolon_after_amp_is_decoded_once_and_stable() -> None:
    once = normalize_body("&amp;#27")
    assert once == "&#27"
    assert normalize_body(once) == once


def test_strings_without_semicolon_stay_unchanged() -> None:
    text = 'http://x/?a=1&param=1&amp=2 and "&amp" and &para and &copy'
    assert normalize_body(text) == text


def test_unknown_entity_name_stays() -> None:
    assert normalize_body("&notanentity; &Foo;") == "&notanentity; &Foo;"


def test_cr_removed_including_entity_cr() -> None:
    assert normalize_body("a\r\nb&#13;\nc\rd") == "a\nb\ncd"


def test_nbsp_becomes_space() -> None:
    assert normalize_body("a b&#160;c") == "a b c"


def test_trailing_whitespace_removed() -> None:
    assert normalize_body("a  \nb\t\nc  ") == "a\nb\nc"


@pytest.mark.parametrize("bullet", ["*", "•", "-", "o", "·", "+", "  -  "])
def test_empty_bullet_lines_removed(bullet: str) -> None:
    assert normalize_body(f"a\n{bullet}\nb") == "a\nb"


def test_lines_with_text_after_bullet_stay() -> None:
    text = "- item\no option\n* star\n+ plus\n• dot"
    assert normalize_body(text) == text


def test_code_and_repeated_lines_stay() -> None:
    text = "cmd --flag\ncmd --flag\ncmd --flag"
    assert normalize_body(text) == text


def test_three_or_more_blank_lines_collapse_to_one() -> None:
    assert normalize_body("a\n\n\n\nb") == "a\n\nb"
    assert normalize_body("a\n\n\n\n\n\nb") == "a\n\nb"


def test_exactly_two_blank_lines_stay() -> None:
    assert normalize_body("a\n\n\nb") == "a\n\n\nb"


def test_one_blank_line_stays() -> None:
    assert normalize_body("a\n\nb") == "a\n\nb"


def test_leading_and_trailing_blank_lines_removed() -> None:
    assert normalize_body("\n\n\nabc\n\n\n") == "abc"


def test_bullet_removal_before_blank_collapse() -> None:
    assert normalize_body("a\n\n\n•\n\n\nb") == "a\n\nb"


def test_empty_input() -> None:
    assert normalize_body("") == ""


@pytest.mark.parametrize(
    "path",
    [p for p in fixture_paths() if p.stem != "nested_entities"],
    ids=lambda p: p.stem,
)
def test_idempotent_on_fixtures_without_nested_entities(path: Path) -> None:
    body = parse_document(path.read_text(encoding="utf-8")).body
    once = normalize_body(body)
    assert normalize_body(once) == once


def test_nested_entities_fixture_documents_boundary() -> None:
    body = parse_document(read_fixture("nested_entities")).body
    once = normalize_body(body)
    assert "&lt;b&gt;" in once
    assert "&amp;" in once  # z `&amp;amp;`
    assert "&#27" in once
    assert "&param=1&amp=2&para=3" in once
    assert '"&amp"' in once
    assert normalize_body(once) != once
