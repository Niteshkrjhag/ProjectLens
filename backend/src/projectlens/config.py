"""Application configuration loaded from the repository's .env file."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for Supabase, model providers, and the API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Supabase: use the pooler connection string for server-side workloads.
    database_url: str
    supabase_url: str | None = None
    supabase_secret_key: SecretStr | None = None

    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.5-flash"
    ollama_api_key: SecretStr | None = None
    ollama_host: str = "https://ollama.com"
    ollama_model: str = "gpt-oss:120b"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
