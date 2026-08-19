from pathlib import Path

from app.core.config import Settings
from app.models.schemas import DocumentRecord, IngestionJobRecord
from app.rag.chunking import split_text
from app.rag.loaders import fetch_url_text, parse_bytes
from app.rag.providers import AIProviders
from app.rag.vector_store import VectorStore
from app.store_factory import document_store
from app.upload_security import UploadSecurity


async def index_document(
    record: DocumentRecord,
    text: str,
    settings: Settings,
) -> DocumentRecord:
    chunks = split_text(text, settings)
    if not chunks:
        raise ValueError("No extractable text found")
    vectors = await AIProviders(settings).embed(chunks)
    vector_store = VectorStore(settings)
    await vector_store.delete_document(record.tenant_id, record.id)
    await vector_store.upsert_chunks(
        record.tenant_id,
        record.id,
        record.name,
        record.source_uri,
        chunks,
        vectors,
    )
    docs = document_store(settings)
    record.status = "ready"
    record.chunk_count = len(chunks)
    record.updated_at = docs.now()
    record.error = None
    return docs.upsert(record)


async def process_ingestion_job(
    job: IngestionJobRecord,
    settings: Settings,
) -> DocumentRecord:
    docs = document_store(settings)
    record = docs.get(job.document_id)
    if record is None:
        raise ValueError(f"Document {job.document_id} no longer exists")
    if record.tenant_id != job.tenant_id:
        raise ValueError("Ingestion job tenant ownership does not match document tenant")

    record.status = "processing"
    record.error = None
    record.updated_at = docs.now()
    docs.upsert(record)

    if job.source_type == "url":
        text, content_type = await fetch_url_text(job.source_uri, settings)
        record.content_type = content_type
        record.size_bytes = len(text.encode("utf-8"))
    elif job.source_type == "file":
        path = Path(job.source_uri)
        if not path.is_file():
            raise ValueError("Queued document source file is unavailable")
        data = path.read_bytes()
        await UploadSecurity(settings).inspect(path.name, data)
        text = parse_bytes(path.name, data)
        record.size_bytes = len(data)
    else:
        raise ValueError(f"Unsupported ingestion source type: {job.source_type}")

    return await index_document(record, text, settings)
