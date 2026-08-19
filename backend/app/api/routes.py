import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import Settings, get_settings
from app.core.security import Principal, require_scopes
from app.models.schemas import (
    AuditRecord,
    ChunkPreview,
    DocumentRecord,
    HealthResponse,
    IngestResponse,
    PreviewResponse,
    QueryRequest,
    QueryResponse,
    SearchRequest,
    SearchResponse,
    ServiceKeyCreateRequest,
    ServiceKeyCreateResponse,
    ServiceKeyRecord,
    UrlIngestRequest,
)
from app.rag.chunking import split_text
from app.rag.loaders import fetch_url_text, parse_bytes
from app.rag.providers import AIProviders
from app.rag.service import RAGService
from app.rag.vector_store import VectorStore
from app.store_factory import document_store, security_store

router = APIRouter()
read_secure = APIRouter(dependencies=[Depends(require_scopes("knowledge:read"))])
write_secure = APIRouter(dependencies=[Depends(require_scopes("knowledge:write"))])


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _index(record: DocumentRecord, text: str, settings: Settings) -> DocumentRecord:
    chunks = split_text(text, settings)
    if not chunks:
        raise ValueError("No extractable text found")
    vectors = await AIProviders(settings).embed(chunks)
    vector_store = VectorStore(settings)
    await vector_store.delete_document(record.id)
    await vector_store.upsert_chunks(record.id, record.name, record.source_uri, chunks, vectors)
    record.status = "ready"
    record.chunk_count = len(chunks)
    record.updated_at = utcnow()
    record.error = None
    return document_store(settings).upsert(record)


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    qdrant_ok = await VectorStore(settings).healthy()
    try:
        document_store(settings).list()
        security_store(settings).list_keys()
        db = "ok"
    except Exception:
        db = "error"
    return HealthResponse(
        status="ok" if qdrant_ok and db == "ok" else "degraded",
        qdrant="ok" if qdrant_ok else "error",
        metadata_store=db,
    )


@write_secure.post("/ingest", response_model=IngestResponse)
async def ingest_file(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
) -> IngestResponse:
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "File exceeds upload limit")
    filename = Path(file.filename or "upload").name
    doc_id = str(uuid4())
    now = utcnow()
    record = DocumentRecord(
        id=doc_id,
        name=filename,
        source_type="file",
        content_type=file.content_type,
        status="processing",
        size_bytes=len(data),
        created_at=now,
        updated_at=now,
    )
    document_store(settings).upsert(record)
    try:
        text = parse_bytes(filename, data)
        saved = settings.upload_dir / f"{doc_id}{Path(filename).suffix.lower()}"
        saved.write_bytes(data)
        record.source_uri = str(saved)
        record = await _index(record, text, settings)
    except Exception as exc:
        record.status, record.error, record.updated_at = "failed", str(exc), utcnow()
        document_store(settings).upsert(record)
        raise HTTPException(422, f"Ingestion failed: {exc}") from exc
    return IngestResponse(document=record)


@write_secure.post("/ingest/url", response_model=IngestResponse)
async def ingest_url(
    body: UrlIngestRequest,
    settings: Settings = Depends(get_settings),
) -> IngestResponse:
    url = str(body.url)
    doc_id = str(uuid4())
    now = utcnow()
    record = DocumentRecord(
        id=doc_id,
        name=url,
        source_type="url",
        source_uri=url,
        status="processing",
        created_at=now,
        updated_at=now,
    )
    document_store(settings).upsert(record)
    try:
        text, content_type = await fetch_url_text(url, settings)
        record.content_type = content_type
        record.size_bytes = len(text.encode())
        record = await _index(record, text, settings)
    except Exception as exc:
        record.status, record.error, record.updated_at = "failed", str(exc), utcnow()
        document_store(settings).upsert(record)
        raise HTTPException(422, f"URL ingestion failed: {exc}") from exc
    return IngestResponse(document=record)


@write_secure.post("/ingest/preview", response_model=PreviewResponse)
async def preview(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
) -> PreviewResponse:
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "File exceeds upload limit")
    try:
        chunks = split_text(parse_bytes(Path(file.filename or "upload").name, data), settings)
    except Exception as exc:
        raise HTTPException(422, str(exc)) from exc
    return PreviewResponse(
        total_chunks=len(chunks),
        chunks=[
            ChunkPreview(index=i, text=chunk, characters=len(chunk))
            for i, chunk in enumerate(chunks[:20])
        ],
    )


@read_secure.get("/documents", response_model=list[DocumentRecord])
def list_documents(settings: Settings = Depends(get_settings)) -> list[DocumentRecord]:
    return document_store(settings).list()


@write_secure.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    settings: Settings = Depends(get_settings),
) -> None:
    docs = document_store(settings)
    record = docs.get(doc_id)
    if not record:
        raise HTTPException(404, "Document not found")
    await VectorStore(settings).delete_document(doc_id)
    if record.source_type == "file" and record.source_uri:
        Path(record.source_uri).unlink(missing_ok=True)
    docs.delete(doc_id)


@write_secure.post("/documents/{doc_id}/reindex", response_model=IngestResponse)
async def reindex_document(
    doc_id: str,
    settings: Settings = Depends(get_settings),
) -> IngestResponse:
    docs = document_store(settings)
    record = docs.get(doc_id)
    if not record:
        raise HTTPException(404, "Document not found")
    try:
        if record.source_type == "url" and record.source_uri:
            text, record.content_type = await fetch_url_text(record.source_uri, settings)
        elif record.source_uri:
            path = Path(record.source_uri)
            text = parse_bytes(path.name, path.read_bytes())
        else:
            raise ValueError("Document source is unavailable")
        record.status, record.updated_at = "processing", utcnow()
        docs.upsert(record)
        record = await _index(record, text, settings)
    except Exception as exc:
        record.status, record.error, record.updated_at = "failed", str(exc), utcnow()
        docs.upsert(record)
        raise HTTPException(422, f"Reindex failed: {exc}") from exc
    return IngestResponse(document=record)


@read_secure.post("/search", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    settings: Settings = Depends(get_settings),
) -> SearchResponse:
    results = await RAGService(settings).search(body.query, body.top_k, body.filters)
    return SearchResponse(results=results)


@read_secure.post("/query", response_model=QueryResponse)
async def query(
    body: QueryRequest,
    settings: Settings = Depends(get_settings),
):
    rag = RAGService(settings)
    if not body.stream:
        return await rag.answer(body.question, body.top_k, body.filters)

    sources, token_stream = await rag.answer_stream(body.question, body.top_k, body.filters)

    async def events():
        yield f"event: sources\ndata: {json.dumps([s.model_dump() for s in sources])}\n\n"
        async for token in token_stream:
            yield f"event: token\ndata: {json.dumps({'text': token})}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.post("/service-keys", response_model=ServiceKeyCreateResponse, status_code=201)
def create_service_key(
    body: ServiceKeyCreateRequest,
    principal: Principal = Depends(require_scopes("keys:admin")),
    settings: Settings = Depends(get_settings),
) -> ServiceKeyCreateResponse:
    sec = security_store(settings)
    record, raw_key = sec.create_key(body.name, list(body.scopes), body.expires_at)
    sec.audit(
        principal.id,
        principal.key_prefix,
        "service_key.create",
        record.id,
        "success",
        f"name={record.name};scopes={','.join(record.scopes)}",
    )
    return ServiceKeyCreateResponse(key=record, secret=raw_key)


@router.get("/service-keys", response_model=list[ServiceKeyRecord])
def list_service_keys(
    _principal: Principal = Depends(require_scopes("keys:admin")),
    settings: Settings = Depends(get_settings),
) -> list[ServiceKeyRecord]:
    return security_store(settings).list_keys()


@router.post("/service-keys/{key_id}/rotate", response_model=ServiceKeyCreateResponse)
def rotate_service_key(
    key_id: str,
    principal: Principal = Depends(require_scopes("keys:admin")),
    settings: Settings = Depends(get_settings),
) -> ServiceKeyCreateResponse:
    sec = security_store(settings)
    rotated = sec.rotate(key_id)
    if rotated is None:
        raise HTTPException(404, "Active service key not found")
    record, raw_key = rotated
    sec.audit(
        principal.id,
        principal.key_prefix,
        "service_key.rotate",
        key_id,
        "success",
        f"replacement={record.id}",
    )
    return ServiceKeyCreateResponse(key=record, secret=raw_key)


@router.delete("/service-keys/{key_id}", status_code=204)
def revoke_service_key(
    key_id: str,
    principal: Principal = Depends(require_scopes("keys:admin")),
    settings: Settings = Depends(get_settings),
) -> None:
    sec = security_store(settings)
    if not sec.revoke(key_id):
        raise HTTPException(404, "Service key not found")
    sec.audit(
        principal.id,
        principal.key_prefix,
        "service_key.revoke",
        key_id,
        "success",
    )


@router.get("/audit", response_model=list[AuditRecord])
def list_security_audit(
    limit: int = Query(default=100, ge=1, le=500),
    _principal: Principal = Depends(require_scopes("audit:read")),
    settings: Settings = Depends(get_settings),
) -> list[AuditRecord]:
    return security_store(settings).list_audit(limit)


router.include_router(read_secure)
router.include_router(write_secure)
