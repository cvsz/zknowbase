import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_local_first_defaults_use_sqlite_and_ollama():
    settings = Settings(api_key="this-is-a-test-secret-key")
    assert settings.metadata_backend == "sqlite"
    assert settings.embedding_provider == "ollama"
    assert settings.llm_provider == "ollama"
    assert settings.postgres_url is None


def test_postgres_backend_requires_dsn():
    with pytest.raises(ValidationError, match="ZKB_POSTGRES_URL"):
        Settings(
            api_key="this-is-a-test-secret-key",
            metadata_backend="postgres",
        )


def test_postgres_pool_bounds_are_validated():
    with pytest.raises(ValidationError, match="POOL_MAX_SIZE"):
        Settings(
            api_key="this-is-a-test-secret-key",
            metadata_backend="postgres",
            postgres_url="postgresql://local/local",
            postgres_pool_min_size=4,
            postgres_pool_max_size=2,
        )
