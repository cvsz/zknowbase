from functools import lru_cache
from pathlib import Path

from psycopg_pool import ConnectionPool

from app.core.config import Settings
from app.postgres_store import (
    PostgresDocumentStore,
    PostgresSecurityStore,
    create_postgres_pool,
)
from app.queue_store import PostgresIngestionQueue, SQLiteIngestionQueue
from app.security_store import SecurityStore
from app.store import DocumentStore


@lru_cache(maxsize=4)
def _postgres_pool(dsn: str, min_size: int, max_size: int) -> ConnectionPool:
    return create_postgres_pool(dsn, min_size, max_size)


@lru_cache(maxsize=4)
def _postgres_document_store(
    dsn: str,
    min_size: int,
    max_size: int,
) -> PostgresDocumentStore:
    return PostgresDocumentStore(_postgres_pool(dsn, min_size, max_size))


@lru_cache(maxsize=4)
def _postgres_security_store(
    dsn: str,
    min_size: int,
    max_size: int,
) -> PostgresSecurityStore:
    return PostgresSecurityStore(_postgres_pool(dsn, min_size, max_size))


@lru_cache(maxsize=4)
def _postgres_ingestion_queue(
    dsn: str,
    min_size: int,
    max_size: int,
) -> PostgresIngestionQueue:
    return PostgresIngestionQueue(_postgres_pool(dsn, min_size, max_size))


@lru_cache(maxsize=8)
def _sqlite_ingestion_queue(db_path: str) -> SQLiteIngestionQueue:
    return SQLiteIngestionQueue(Path(db_path))


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


def ingestion_queue(settings: Settings):
    if settings.metadata_backend == "postgres":
        assert settings.postgres_url is not None
        return _postgres_ingestion_queue(
            settings.postgres_url,
            settings.postgres_pool_min_size,
            settings.postgres_pool_max_size,
        )
    return _sqlite_ingestion_queue(str(settings.metadata_db))
