"""Wspólne pomocnicze funkcje testów TechQA."""

import hashlib
import json
import warnings
import zipfile
from pathlib import Path
from typing import Any

from app.techqa.chunking import Chunk, ChunkerConfig, chunk_document
from app.techqa.importer import Manifest

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "techqa"

REVISION = "0123456789abcdef0123456789abcdef01234567"
OTHER_REVISION = "fedcba9876543210fedcba9876543210fedcba98"
DUPLICATED_FIXTURE = "apar_template"
SNAPSHOT_ID = f"techqa@{REVISION}"
CHUNK_SET_ID = f"{SNAPSHOT_ID}/sections-v1"


def fixture_paths() -> list[Path]:
    return sorted(FIXTURES_DIR.glob("*.txt"))


def read_fixture(name: str) -> str:
    return (FIXTURES_DIR / f"{name}.txt").read_text(encoding="utf-8")


def check_chunk_invariants(text: str, config: ChunkerConfig) -> list[Chunk]:
    """Dzieli tekst i sprawdza niezmienniki chunkera; zwraca fragmenty."""
    chunks = chunk_document(text, config)
    assert chunks == chunk_document(text, config), "wynik nie jest deterministyczny"
    covered_to = 0
    for index, chunk in enumerate(chunks):
        assert chunk.ordinal == index
        assert text[chunk.start : chunk.end] == chunk.text
        assert 0 < len(chunk.text) <= config.max_chars
        assert not chunk.text[0].isspace()
        assert not chunk.text[-1].isspace()
        # Pokrycie: luka między kolejnymi fragmentami może zawierać tylko białe znaki.
        if chunk.start > covered_to:
            assert not text[covered_to : chunk.start].strip(), "niepokryty tekst"
        covered_to = max(covered_to, chunk.end)
    assert not text[covered_to:].strip(), "niepokryty koniec tekstu"
    return chunks


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_snapshot(
    root: Path,
    *,
    revision: str = REVISION,
    extra_reference: str | None = None,
    extra_entries: dict[str, bytes] | None = None,
    duplicate_entries: tuple[str, ...] = (),
    corpus_zip_bytes: bytes | None = None,
    train: list[dict[str, Any]] | None = None,
) -> tuple[Path, Manifest]:
    """Mini-migawka: fikstury fazy 2, a jedna z nich jako dwie identyczne kopie.

    Manifest zawsze zgodny z zapisanymi plikami (hashe liczone po zapisie), więc
    błąd zgłasza dopiero sprawdzenie, któremu służy dany wariant:
    `extra_entries` (pełna nazwa wpisu zip -> bajty) dodaje wpisy do archiwum,
    `duplicate_entries` zapisuje wskazane wpisy drugi raz, `corpus_zip_bytes`
    podmienia całe archiwum, `train` podmienia zawartość train.json.
    """
    data_dir = root / "techqa"
    data_dir.mkdir()
    entries: dict[str, bytes] = {}
    for path in fixture_paths():
        if path.stem == DUPLICATED_FIXTURE:
            continue
        entries[path.stem] = path.read_bytes()
    duplicated = (FIXTURES_DIR / f"{DUPLICATED_FIXTURE}.txt").read_bytes()
    entries["dup_b"] = duplicated
    entries["dup_a"] = duplicated

    zip_path = data_dir / "corpus.zip"
    if corpus_zip_bytes is not None:
        zip_path.write_bytes(corpus_zip_bytes)
    else:
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr("corpus/", b"")
            for name, data in entries.items():
                archive.writestr(f"corpus/{name}.txt", data)
            for name, data in (extra_entries or {}).items():
                archive.writestr(name, data)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)  # powtórzona nazwa
                for name in duplicate_entries:
                    archive.writestr(name, b"duplikat")

    if train is None:
        references = ["code_block", "dup_a", "code_block"]
        if extra_reference:
            references.append(extra_reference)
        train = [
            {
                "id": "TRAIN_Q000",
                "question": "q",
                "answer": "a",
                "is_impossible": False,
                "contexts": [
                    {"filename": f"{name}.txt", "text": "x"} for name in references
                ],
            },
            {"id": "TRAIN_Q001", "question": "q", "answer": "", "is_impossible": True},
        ]
    (data_dir / "train.json").write_text(json.dumps(train), encoding="utf-8")
    (data_dir / "README.md").write_text("# mini\n", encoding="utf-8")
    (data_dir / "revision.txt").write_text(revision + "\r\n", encoding="utf-8")

    expected = len(entries)
    for name in extra_entries or {}:
        if name.startswith("corpus/") and name.endswith(".txt"):
            expected += 1
    manifest = Manifest(
        source="test/mini",
        revision=revision,
        files={
            name: _sha((data_dir / name).read_bytes())
            for name in ("README.md", "train.json", "corpus.zip")
        },
        expected_documents=expected,
    )
    return data_dir, manifest
