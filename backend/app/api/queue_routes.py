from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.core.config import Settings, get_settings
from app.core.security import Principal, require_scopes
from app.models.schemas import (
    AsyncIngestResponse,
    DocumentRecord,
    IngestionJobRecord,
    UrlIngestRequest,
)
from app.rag.loaders import ALLOWED_SUFFIXES
from app.store_factory import document_store, ingestion_queue

router = APIRouter()


@router.post(
    "/ingest/async",
    response_model=AsyncIngestResponse,
    status_code=202,
)
async def enqueue_file(
    file: UploadFile = File(...),
    principal: Principal = Depends(require_scopes("knowledge:write")),
    settings: Settings = Depends(get_settings),
) -> AsyncIngestResponse:
    filename = Path(file.filename or "upload").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(415, f"Unsupported file type: {suffix or 'unknown'}")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(413, "File exceeds upload limit")

    doc_id = str(uuid4())
    saved = settings.upload_dir / f"{doc_id}{suffix}"
    docs = document_store(settings)
    queue = ingestion_queue(settings)
    now = docs.now()
    record = DocumentRecord(
        id=doc_id,
        name=filename,
        tenant_id=principal.tenant_id,
        source_type="file",
        source_uri=str(saved),
        content_type=file.content_type,
        status="queued",
        size_bytes=len(data),
        created_at=now,
        updated_at=now,
    )

    try:
        saved.write_bytes(data)
        docs.upsert(record)
        job = queue.enqueue(
            record.id,
            "file",
            str(saved),
            settings.ingestion_job_max_attempts,
            tenant_id=principal.tenant_id,
        )
    except Exception as exc:
        saved.unlink(missing_ok=True)
        docs.delete(record.id)
        raise HTTPException(503, f"Unable to queue ingestion: {exc}") from exc
    return AsyncIngestResponse(document=record, job=job)


@router.post(
    "/ingest/url/async",
    response_model=AsyncIngestResponse,
    status_code=202,
)
def enqueue_url(
    body: UrlIngestRequest,
    principal: Principal = Depends(require_scopes("knowledge:write")),
    settings: Settings = Depends(get_settings),
) -> AsyncIngestResponse:
    url = str(body.url)
    doc_id = str(uuid4())
    docs = document_store(settings)
    queue = ingestion_queue(settings)
    now = docs.now()
    record = DocumentRecord(
        id=doc_id,
        name=url,
        tenant_id=principal.tenant_id,
        source_type="url",
        source_uri=url,
        status="queued",
        created_at=now,
        updated_at=now,
    )
    try:
        docs.upsert(record)
        job = queue.enqueue(
            record.id,
            "url",
            url,
            settings.ingestion_job_max_attempts,
            tenant_id=principal.tenant_id,
        )
    except Exception as exc:
        docs.delete(record.id)
        raise HTTPException(503, f"Unable to queue ingestion: {exc}") from exc
    return AsyncIngestResponse(document=record, job=job)


@router.get(
    "/ingest/jobs",
    response_model=list[IngestionJobRecord],
)
def list_ingestion_jobs(
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require_scopes("knowledge:read")),
    settings: Settings = Depends(get_settings),
) -> list[IngestionJobRecord]:
    return ingestion_queue(settings).list(limit, principal.tenant_id)


@router.get(
    "/ingest/jobs/{job_id}",
    response_model=IngestionJobRecord,
)
def get_ingestion_job(
    job_id: str,
    principal: Principal = Depends(require_scopes("knowledge:read")),
    settings: Settings = Depends(get_settings),
) -> IngestionJobRecord:
    job = ingestion_queue(settings).get(job_id, principal.tenant_id)
    if job is None:
        raise HTTPException(404, "Ingestion job not found")
    return job


@router.delete(
    "/ingest/jobs/{job_id}",
    status_code=204,
)
def cancel_ingestion_job(
    job_id: str,
    principal: Principal = Depends(require_scopes("knowledge:write")),
    settings: Settings = Depends(get_settings),
) -> None:
    queue = ingestion_queue(settings)
    job = queue.get(job_id, principal.tenant_id)
    if job is None:
        raise HTTPException(404, "Ingestion job not found")
    if not queue.cancel(job_id, principal.tenant_id):
        raise HTTPException(409, "Only queued ingestion jobs can be cancelled")

    docs = document_store(settings)
    record = docs.get(job.document_id)
    if record is not None and record.tenant_id == principal.tenant_id:
        record.status = "cancelled"
        record.updated_at = docs.now()
        record.error = None
        docs.upsert(record)
        if record.source_type == "file" and record.source_uri:
            Path(record.source_uri).unlink(missing_ok=True)
