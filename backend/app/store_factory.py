from functools import lru_cache

from app.core.config import Settings
from app.postgres_store import PostgresDocumentStore, PostgresSecurityStore
from app.security_store import SecurityStore
from app.store import DocumentStore


@lru_cache(maxsize=4)
def _postgres_document_store(
    dsn: str,
    min_size: int,
    max_size: int,
) -> PostgresDocumentStore:
    return PostgresDocumentStore(dsn, min_size, max_size)


@lru_cache(maxsize=4)
def _postgres_security_store(
    dsn: str,
    min_size: int,
    max_size: int,
) -> PostgresSecurityStore:
    return PostgresSecurityStore(dsn, min_size, max_size)


def document_store(settings: Settings):
    if settings.metadata_backend == "postgres":
        assert settings.postgres_url is not None
        return _postgres_document_store(
            settings.postgres_url,
            settings.postgres_pool_min_size,
            settings.postgres_pool_max_size,
        )
    return DocumentStore(settings.metadata_db)


def security_store(settings: Settings):
    if settings.metadata_backend == "postgres":
        assert settings.postgres_url is not None
        return _postgres_security_store(
            settings.postgres_url,
            settings.postgres_pool_min_size,
            settings.postgres_pool_max_size,
        )
    return SecurityStore(settings.metadata_db)
