"""Niezmienniki na pełnym korpusie TechQA (lokalnie, wymaga `corpus.zip`)."""

import os
import re
import zipfile
from html.entities import html5
from pathlib import Path

import pytest

from app.settings import Settings
from app.techqa.chunking import ChunkerConfig
from app.techqa.importer import load_manifest
from app.techqa.normalize import normalize_body
from app.techqa.parse import parse_document
from tests.techqa.helpers import check_chunk_invariants

pytestmark = pytest.mark.corpus

# Ciągi `&…` bez średnika, które normalizacja zostawia bez zmian.
_UNTERMINATED = re.compile(
    r"&(#[0-9]+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*)(?![0-9A-Za-z;])"
)


def _looks_like_entity(name: str) -> bool:
    """Czy ciąg po `&` byłby encją po dopisaniu średnika (np. `para`, `#27`)."""
    return name.startswith("#") or f"{name};" in html5


def _corpus_zip() -> Path:
    # `Settings()` wymaga DATABASE_URL, więc czytamy tylko domyślne `techqa_dir`.
    directory = (
        os.environ.get("TECHQA_DIR") or Settings.model_fields["techqa_dir"].default
    )
    return Path(directory) / "corpus.zip"


@pytest.mark.skipif(not _corpus_zip().exists(), reason="brak corpus.zip (TECHQA_DIR)")
def test_full_corpus_invariants(capsys: pytest.CaptureFixture[str]) -> None:
    config = ChunkerConfig()
    documents = 0
    total_chunks = 0
    with_unterminated = 0
    with zipfile.ZipFile(_corpus_zip()) as archive:
        for info in sorted(archive.infolist(), key=lambda i: i.filename):
            if info.is_dir():
                continue
            name = info.filename
            raw = archive.read(info).decode("utf-8")
            try:
                parsed = parse_document(raw)
                body = normalize_body(parsed.body)
                assert normalize_body(body) == body, (
                    "normalizacja nie jest idempotentna"
                )
                total_chunks += len(check_chunk_invariants(body, config))
            except Exception as exc:
                raise AssertionError(f"{name}: {exc}") from exc
            if any(_looks_like_entity(m) for m in _UNTERMINATED.findall(body)):
                with_unterminated += 1
            documents += 1

    with capsys.disabled():
        print(
            f"\nKorpus: dokumentów={documents}, fragmentów={total_chunks}, "
            f"dokumentów z ciągami '&…' bez średnika={with_unterminated}"
        )
    assert documents == load_manifest().expected_documents
