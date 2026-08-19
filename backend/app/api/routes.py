import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import Settings, get_settings
from app.core.security import require_api_key
from app.models.schemas import (
    ChunkPreview, DocumentRecord, HealthResponse, IngestResponse, PreviewResponse,
    QueryRequest, QueryResponse, SearchRequest, SearchResponse, UrlIngestRequest,
)
from app.rag.chunking import split_text
from app.rag.loaders import fetch_url_text, parse_bytes
from app.rag.providers import AIProviders
from app.rag.service import RAGService
from app.rag.vector_store import VectorStore
from app.store import DocumentStore

router = APIRouter()
secure = APIRouter(dependencies=[Depends(require_api_key)])


def store(settings: Settings) -> DocumentStore:
    return DocumentStore(settings.metadata_db)


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
    record.updated_at = DocumentStore.now()
    record.error = None
    return store(settings).upsert(record)


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    qdrant_ok = await VectorStore(settings).healthy()
    try:
        store(settings).list()
        db = "ok"
    except Exception:
        db = "error"
    return HealthResponse(
        status="ok" if qdrant_ok and db == "ok" else "degraded",
        qdrant="ok" if qdrant_ok else "error",
        metadata_store=db,
    )


@secure.post("/ingest", response_model=IngestResponse)
async def ingest_file(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
) -> IngestResponse:
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "File exceeds upload limit")
    filename = Path(file.filename or "upload").name
    doc_id = str(uuid4())
    now = DocumentStore.now()
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
    store(settings).upsert(record)
    try:
        text = parse_bytes(filename, data)
        saved = settings.upload_dir / f"{doc_id}{Path(filename).suffix.lower()}"
        saved.write_bytes(data)
        record.source_uri = str(saved)
        record = await _index(record, text, settings)
    except Exception as exc:
        record.status, record.error, record.updated_at = "failed", str(exc), DocumentStore.now()
        store(settings).upsert(record)
        raise HTTPException(422, f"Ingestion failed: {exc}") from exc
    return IngestResponse(document=record)


@secure.post("/ingest/url", response_model=IngestResponse)
async def ingest_url(
    body: UrlIngestRequest,
    settings: Settings = Depends(get_settings),
) -> IngestResponse:
    url = str(body.url)
    doc_id = str(uuid4())
    now = DocumentStore.now()
    record = DocumentRecord(
        id=doc_id,
        name=url,
        source_type="url",
        source_uri=url,
        status="processing",
        created_at=now,
        updated_at=now,
    )
    store(settings).upsert(record)
    try:
        text, content_type = await fetch_url_text(url, settings)
        record.content_type = content_type
        record.size_bytes = len(text.encode())
        record = await _index(record, text, settings)
    except Exception as exc:
        record.status, record.error, record.updated_at = "failed", str(exc), DocumentStore.now()
        store(settings).upsert(record)
        raise HTTPException(422, f"URL ingestion failed: {exc}") from exc
    return IngestResponse(document=record)


@secure.post("/ingest/preview", response_model=PreviewResponse)
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


@secure.get("/documents", response_model=list[DocumentRecord])
def list_documents(settings: Settings = Depends(get_settings)) -> list[DocumentRecord]:
    return store(settings).list()


@secure.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    settings: Settings = Depends(get_settings),
) -> None:
    record = store(settings).get(doc_id)
    if not record:
        raise HTTPException(404, "Document not found")
    await VectorStore(settings).delete_document(doc_id)
    if record.source_type == "file" and record.source_uri:
        Path(record.source_uri).unlink(missing_ok=True)
    store(settings).delete(doc_id)


@secure.post("/documents/{doc_id}/reindex", response_model=IngestResponse)
async def reindex_document(
    doc_id: str,
    settings: Settings = Depends(get_settings),
) -> IngestResponse:
    record = store(settings).get(doc_id)
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
        record.status, record.updated_at = "processing", DocumentStore.now()
        store(settings).upsert(record)
        record = await _index(record, text, settings)
    except Exception as exc:
        record.status, record.error, record.updated_at = "failed", str(exc), DocumentStore.now()
        store(settings).upsert(record)
        raise HTTPException(422, f"Reindex failed: {exc}") from exc
    return IngestResponse(document=record)


@secure.post("/search", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    settings: Settings = Depends(get_settings),
) -> SearchResponse:
    results = await RAGService(settings).search(body.query, body.top_k, body.filters)
    return SearchResponse(results=results)


@secure.post("/query", response_model=QueryResponse)
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


router.include_router(secure)
