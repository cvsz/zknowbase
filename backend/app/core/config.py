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
    bootstrap_api_key_enabled: bool = True
    frontend_origin: str = "http://localhost:3000"

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "zknowbase"
    metadata_backend: Literal["sqlite", "postgres"] = "sqlite"
    metadata_db: Path = Path("data/zknowbase.db")
    postgres_url: str | None = None
    postgres_pool_min_size: int = Field(default=1, ge=1, le=50)
    postgres_pool_max_size: int = Field(default=10, ge=1, le=100)
    upload_dir: Path = Path("data/uploads")
    max_upload_mb: int = 25
    max_url_bytes: int = 5_000_000
    chunk_size: int = 1000
    chunk_overlap: int = 150

    worker_poll_seconds: float = Field(default=1.0, ge=0.1, le=60.0)
    worker_lease_seconds: int = Field(default=300, ge=30, le=3600)
    ingestion_job_max_attempts: int = Field(default=3, ge=1, le=10)

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
    def validate_runtime_configuration(self) -> "Settings":
        if (
            self.environment.lower() == "production"
            and self.bootstrap_api_key_enabled
            and self.api_key == "change-me-long-random-secret"
        ):
            raise ValueError("ZKB_API_KEY must be replaced before production startup")
        if self.metadata_backend == "postgres" and not self.postgres_url:
            raise ValueError("ZKB_POSTGRES_URL is required when ZKB_METADATA_BACKEND=postgres")
        if self.postgres_pool_max_size < self.postgres_pool_min_size:
            raise ValueError("ZKB_POSTGRES_POOL_MAX_SIZE must be >= ZKB_POSTGRES_POOL_MIN_SIZE")
        return self

    def ensure_paths(self) -> None:
        if self.metadata_backend == "sqlite":
            self.metadata_db.parent.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_paths()
    return settings
