from pathlib import Path
from typing import Annotated

from fastapi import Depends
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.synthetic.importer import synthetic_chunk_set_id
from app.techqa.chunking import ChunkerConfig
from app.techqa.importer import load_manifest


class Settings(BaseSettings):
    """Ustawienia aplikacji czytane ze zmiennych środowiskowych."""

    model_config = SettingsConfigDict(extra="ignore", env_ignore_empty=True)

    database_url: str
    techqa_dir: Path = Path("/data/raw/techqa")
    chunk_set_id: str | None = None
    # Nakładka dokumentów syntetycznych (synthetic@v1) na bazę TechQA.
    include_synthetic: bool = True
    synthetic_chunk_set_id: str | None = None
    answer_k: int = 8
    evidence_context_chunks: int = 1

    # Model czatu (OpenAI). Bez klucza endpoint odpowiedzi zgłasza błąd konfiguracji.
    openai_api_key: SecretStr | None = None
    # Opcjonalny adres API zgodnego z OpenAI (np. https://openrouter.ai/api/v1).
    openai_base_url: str | None = None
    chat_model: str = "gpt-6-luna"
    # Wysiłek rozumowania modelu; `none` wyłącza parametr (modele bez rozumowania).
    # Pusta wartość w środowisku jest ignorowana i zostaje domyślne `low`.
    chat_reasoning_effort: str = "low"
    # Limit jednego wywołania modelu i całego zapytania (egzekwuje go API).
    chat_timeout_s: float = 12
    answer_deadline_s: float = 25

    # Limity audytu notatki ze sprawy (FR-006..FR-009).
    audit_k: int = 8
    audit_deadline_s: float = 90
    audit_claim_concurrency: int = 3
    audit_max_claims: int = 12

    # Opcjonalny model sędziego ewaluacji; brak `eval_judge_model` -> `CHAT_*`.
    eval_judge_model: str | None = None
    eval_judge_base_url: str | None = None
    eval_judge_api_key: SecretStr | None = None
    eval_judge_reasoning_effort: str | None = None
    eval_judge_timeout_s: float = 20

    # Langfuse (ślad zapytania). Bez kluczy ślad jest wyłączony.
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_base_url: str | None = None

    # Ciasteczko sesji z flagą Secure (włącz za HTTPS).
    session_cookie_secure: bool = False

    def effective_chunk_set_id(self) -> str:
        """Id zestawu fragmentów: z ustawień, a gdy puste, z manifestu i chunkera."""
        if self.chunk_set_id:
            return self.chunk_set_id
        return load_manifest().chunk_set_id(ChunkerConfig())

    def effective_synthetic_chunk_set_id(self) -> str:
        """Id zestawu syntetycznego: z ustawień, a gdy puste, z chunkera."""
        if self.synthetic_chunk_set_id:
            return self.synthetic_chunk_set_id
        return synthetic_chunk_set_id(ChunkerConfig())


def get_settings() -> Settings:
    """Zależność FastAPI: ustawienia czytane ze środowiska przy każdym żądaniu."""
    return Settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]
