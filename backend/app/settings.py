from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.techqa.chunking import ChunkerConfig
from app.techqa.importer import load_manifest


class Settings(BaseSettings):
    """Ustawienia aplikacji czytane ze zmiennych środowiskowych."""

    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    techqa_dir: Path = Path("/data/raw/techqa")
    chunk_set_id: str | None = None
    answer_k: int = 8
    evidence_context_chunks: int = 1

    def effective_chunk_set_id(self) -> str:
        """Id zestawu fragmentów: z ustawień, a gdy puste, z manifestu i chunkera."""
        if self.chunk_set_id:
            return self.chunk_set_id
        return load_manifest().chunk_set_id(ChunkerConfig())
