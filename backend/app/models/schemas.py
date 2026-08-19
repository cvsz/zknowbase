from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl

ServiceKeyScope = Literal[
    "knowledge:read",
    "knowledge:write",
    "keys:admin",
    "audit:read",
]

IngestionJobStatus = Literal["queued", "processing", "completed", "failed", "cancelled"]
TENANT_ID_PATTERN = r"^[a-z0-9][a-z0-9._-]{0,62}$"


class DocumentRecord(BaseModel):
    id: str
    name: str
    source_type: str
    source_uri: str | None = None
    content_type: str | None = None
    status: str
    chunk_count: int = 0
    size_bytes: int = 0
    created_at: datetime
    updated_at: datetime
    error: str | None = None


class IngestResponse(BaseModel):
    document: DocumentRecord


class UrlIngestRequest(BaseModel):
    url: HttpUrl


class ChunkPreview(BaseModel):
    index: int
    text: str
    characters: int


class PreviewResponse(BaseModel):
    chunks: list[ChunkPreview]
    total_chunks: int


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=20_000)
    top_k: int = Field(default=5, ge=1, le=20)
    stream: bool = False
    filters: dict[str, Any] | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=20_000)
    top_k: int = Field(default=5, ge=1, le=50)
    filters: dict[str, Any] | None = None


class SourceCitation(BaseModel):
    document_id: str
    document_name: str
    chunk_id: str
    chunk_index: int
    score: float
    text: str
    source_uri: str | None = None


class SearchResponse(BaseModel):
    results: list[SourceCitation]


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceCitation]


class HealthResponse(BaseModel):
    status: str
    qdrant: str
    metadata_store: str
    scanner: str = "validation-only"


class ServiceKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[ServiceKeyScope] = Field(min_length=1, max_length=4)
    expires_at: datetime | None = None


class ServiceKeyRecord(BaseModel):
    id: str
    name: str
    tenant_id: str = Field(default="default", min_length=1, max_length=63, pattern=TENANT_ID_PATTERN)
    key_prefix: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None
    rotated_from: str | None = None


class ServiceKeyCreateResponse(BaseModel):
    key: ServiceKeyRecord
    secret: str


class AuditRecord(BaseModel):
    id: str
    principal_id: str | None = None
    key_prefix: str | None = None
    action: str
    resource: str
    outcome: str
    detail: str | None = None
    created_at: datetime


class IngestionJobRecord(BaseModel):
    id: str
    document_id: str
    source_type: Literal["file", "url"]
    source_uri: str
    status: IngestionJobStatus
    attempts: int = 0
    max_attempts: int = 3
    worker_id: str | None = None
    lease_expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    error: str | None = None


class AsyncIngestResponse(BaseModel):
    document: DocumentRecord
    job: IngestionJobRecord
