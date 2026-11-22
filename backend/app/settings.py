from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Ustawienia aplikacji czytane ze zmiennych środowiskowych."""

    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
