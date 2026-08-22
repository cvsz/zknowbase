from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile

from app.content_identity import file_document_id, sha256_content
from app.core.config import Settings, get_settings
from app.core.security import Principal, require_scopes
from app.models.schemas import (
    AsyncIngestResponse,
    AsyncReindexRequest,
    DocumentRecord,
    IngestionJobRecord,
    UrlIngestRequest,
)
from app.observability import INGESTION_JOBS
from app.rag.loaders import ALLOWED_SUFFIXES
from app.store_factory import document_store, ingestion_queue
from app.tenant_queue_store import ActiveIngestionJobError
from app.upload_security import UploadSecurity, UploadSecurityError

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
    try:
        await UploadSecurity(settings).inspect(filename, data)
    except UploadSecurityError as exc:
        raise HTTPException(422, f"Upload rejected: {exc}") from exc

    content_hash = sha256_content(data)
    doc_id = file_document_id(principal.tenant_id, content_hash)
    docs = document_store(settings)
    queue = ingestion_queue(settings)
    existing = docs.get(doc_id)
    if existing is not None and existing.tenant_id != principal.tenant_id:
        raise HTTPException(409, "Document content identity collides with another tenant")
    if existing is not None:
        if existing.status not in {"failed", "cancelled"} or queue.active_for_document(
            doc_id, principal.tenant_id
        ):
            raise HTTPException(
                409,
                detail={
                    "message": "Duplicate file content already exists for this tenant",
                    "document_id": existing.id,
                    "status": existing.status,
                    "content_hash": f"sha256:{content_hash}",
                },
            )

    if existing is not None and existing.source_type == "file" and existing.source_uri:
        saved = Path(existing.source_uri)
    else:
        saved = settings.upload_dir / f"{doc_id}{suffix}"
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
        created_at=existing.created_at if existing is not None else now,
        updated_at=now,
    )

    if not docs.reserve(record):
        current = docs.get(doc_id)
        if current is None:
            raise HTTPException(409, "Document content reservation changed; retry request")
        if current.tenant_id != principal.tenant_id:
            raise HTTPException(409, "Document content identity collides with another tenant")
        raise HTTPException(
            409,
            detail={
                "message": "Duplicate file content already exists for this tenant",
                "document_id": current.id,
                "status": current.status,
                "content_hash": f"sha256:{content_hash}",
            },
        )

    try:
        saved.write_bytes(data)
        job = queue.enqueue(
            record.id,
            "file",
            str(saved),
            settings.ingestion_job_max_attempts,
            tenant_id=principal.tenant_id,
        )
    except Exception as exc:
        # Some queue backends may fail after durably recording a job. Preserve
        # the reservation/source if a job is now active so the worker never loses
        # state owned by a successful enqueue.
        if not queue.active_for_document(doc_id, principal.tenant_id):
            saved.unlink(missing_ok=True)
            current = docs.get(record.id)
            if (
                current is not None
                and current.tenant_id == principal.tenant_id
                and current.status == "queued"
            ):
                docs.delete(record.id)
        raise HTTPException(503, f"Unable to queue ingestion: {exc}") from exc
    INGESTION_JOBS.labels(outcome="enqueued").inc()
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
        INGESTION_JOBS.labels(outcome="enqueued").inc()
    except Exception as exc:
        docs.delete(record.id)
        raise HTTPException(503, f"Unable to queue ingestion: {exc}") from exc
    return AsyncIngestResponse(document=record, job=job)


@router.post(
    "/documents/{doc_id}/reindex/async",
    response_model=AsyncIngestResponse,
    status_code=202,
)
def enqueue_reindex(
    doc_id: str,
    body: AsyncReindexRequest = Body(default_factory=AsyncReindexRequest),
    principal: Principal = Depends(require_scopes("knowledge:write")),
    settings: Settings = Depends(get_settings),
) -> AsyncIngestResponse:
    docs = document_store(settings)
    record = docs.get(doc_id)
    if record is None or record.tenant_id != principal.tenant_id:
        raise HTTPException(404, "Document not found")
    if not record.source_uri:
        raise HTTPException(409, "Document source is unavailable")
    if record.source_type not in {"file", "url"}:
        raise HTTPException(422, f"Unsupported reindex source type: {record.source_type}")

    queue = ingestion_queue(settings)
    if queue.active_for_document(doc_id, principal.tenant_id):
        raise HTTPException(409, "Document has an active ingestion job")

    prior_status = record.status
    prior_error = record.error
    prior_updated_at = record.updated_at
    now = docs.now()
    available_at = now + timedelta(seconds=body.run_after_seconds)
    record.status = "queued"
    record.error = None
    record.updated_at = now
    docs.upsert(record)
    try:
        job = queue.enqueue_if_inactive(
            record.id,
            record.source_type,
            record.source_uri,
            settings.ingestion_job_max_attempts,
            available_at=available_at,
            tenant_id=principal.tenant_id,
            prior_status=prior_status,
            prior_error=prior_error,
            prior_updated_at=prior_updated_at,
        )
    except ActiveIngestionJobError as exc:
        # Another concurrent request won the database-level reservation after the
        # optimistic pre-check. Its active job owns the queued document state.
        raise HTTPException(409, "Document has an active ingestion job") from exc
    except Exception as exc:
        # The tenant queue insert is atomic. Restore the exact prior state only if
        # no concurrent request successfully established an active job.
        if not queue.active_for_document(doc_id, principal.tenant_id):
            record.status = prior_status
            record.error = prior_error
            record.updated_at = prior_updated_at
            docs.upsert(record)
        raise HTTPException(503, f"Unable to queue reindex: {exc}") from exc
    INGESTION_JOBS.labels(outcome="enqueued").inc()
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
    prior_reindex_state = queue.reindex_prior_state(job_id, principal.tenant_id)
    if not queue.cancel(job_id, principal.tenant_id):
        raise HTTPException(409, "Only queued ingestion jobs can be cancelled")
    INGESTION_JOBS.labels(outcome="cancelled").inc()

    docs = document_store(settings)
    record = docs.get(job.document_id)
    if prior_reindex_state is not None:
        if record is not None and record.tenant_id == principal.tenant_id:
            prior_status, prior_error, prior_updated_at = prior_reindex_state
            record.status = prior_status
            record.error = prior_error
            record.updated_at = prior_updated_at
            docs.upsert(record)
        queue.clear_reindex_state(job_id)
        return

    if record is not None and record.tenant_id == principal.tenant_id:
        record.status = "cancelled"
        record.updated_at = docs.now()
        record.error = None
        docs.upsert(record)
        if record.source_type == "file" and record.source_uri:
            Path(record.source_uri).unlink(missing_ok=True)
