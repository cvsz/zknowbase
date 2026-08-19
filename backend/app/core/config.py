from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ZKB_", env_file=".env", extra="ignore")

    app_name: str = "zknowbase"
    environment: str = "development"
    api_key: str = Field(default="change-me-long-random-secret", min_length=16)
    frontend_origin: str = "http://localhost:3000"

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "zknowbase"
    metadata_db: Path = Path("data/zknowbase.db")
    upload_dir: Path = Path("data/uploads")
    max_upload_mb: int = 25
    max_url_bytes: int = 5_000_000
    chunk_size: int = 1000
    chunk_overlap: int = 150

    embedding_provider: Literal["ollama", "openai", "gemini"] = "ollama"
    embedding_model: str = "nomic-embed-text"
    llm_provider: Literal["ollama", "openai", "anthropic", "gemini"] = "ollama"
    llm_model: str = "qwen2.5:3b"
    ollama_base_url: str = "http://localhost:11434"
    openai_base_url: str = "https://api.openai.com/v1"

    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")

    request_timeout_seconds: float = 90.0

    @model_validator(mode="after")
    def validate_production_secret(self) -> "Settings":
        if self.environment.lower() == "production" and self.api_key == "change-me-long-random-secret":
            raise ValueError("ZKB_API_KEY must be replaced before production startup")
        return self

    def ensure_paths(self) -> None:
        self.metadata_db.parent.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_paths()
    return settings
