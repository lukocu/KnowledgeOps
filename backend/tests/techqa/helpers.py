"""Wspólne pomocnicze funkcje testów TechQA."""

from pathlib import Path

from app.techqa.chunking import Chunk, ChunkerConfig, chunk_document

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "techqa"


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
