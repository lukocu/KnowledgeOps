import pytest

from app.techqa.parse import parse_document


def test_simple_envelope() -> None:
    doc = parse_document(
        "Title: IBM Sample title - United States\n\nText:\nBody line\n"
    )
    assert doc.title == "IBM Sample title"
    assert doc.body == "Body line\n"


def test_multiline_title_joined_with_space() -> None:
    doc = parse_document(
        "Title: IBM First part\nsecond part - United States\n\nText:\nX"
    )
    assert doc.title == "IBM First part second part"
    assert doc.body == "X"


def test_title_without_united_states_suffix() -> None:
    doc = parse_document("Title: IBM Plain title\n\nText:\nX")
    assert doc.title == "IBM Plain title"


def test_splits_on_first_separator_only() -> None:
    doc = parse_document("Title: T\n\nText:\nA\n\nText:\nB")
    assert doc.body == "A\n\nText:\nB"


def test_missing_text_marker_raises() -> None:
    with pytest.raises(ValueError, match="separatora"):
        parse_document("Title: IBM T - United States\n\nBody without marker")


def test_missing_title_raises() -> None:
    with pytest.raises(ValueError, match="Title"):
        parse_document("Heading\n\nText:\nBody")
