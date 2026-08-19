import asyncio
import logging
import os
import socket
from contextlib import suppress
from uuid import uuid4

from app.core.config import get_settings
from app.ingestion_service import process_ingestion_job
from app.store_factory import document_store, ingestion_queue

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("zknowbase.worker")


async def _heartbeat(queue, job_id: str, worker_id: str, lease_seconds: int) -> None:
    interval = max(5.0, lease_seconds / 3)
    while True:
        await asyncio.sleep(interval)
        if not queue.renew(job_id, worker_id, lease_seconds):
            raise RuntimeError("Ingestion job lease ownership was lost")


async def _run_job(queue, job, worker_id: str, settings) -> None:
    processing = asyncio.create_task(process_ingestion_job(job, settings))
    heartbeat = asyncio.create_task(
        _heartbeat(queue, job.id, worker_id, settings.worker_lease_seconds)
    )
    try:
        done, _pending = await asyncio.wait(
            {processing, heartbeat},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if heartbeat in done:
            heartbeat.result()
            raise RuntimeError("Ingestion heartbeat stopped unexpectedly")

        result = processing.result()
        if not queue.complete(job.id, worker_id):
            raise RuntimeError("Ingestion job completion rejected after lease loss")
        logger.info(
            "ingestion_completed job_id=%s document_id=%s chunks=%s",
            job.id,
            result.id,
            result.chunk_count,
        )
    except Exception as exc:
        if not processing.done():
            processing.cancel()
            with suppress(asyncio.CancelledError):
                await processing
        with suppress(Exception):
            queue.fail(job.id, worker_id, str(exc))
            current = queue.get(job.id)
            docs = document_store(settings)
            record = docs.get(job.document_id)
            if record is not None and current is not None:
                record.status = "queued" if current.status == "queued" else "failed"
                record.error = str(exc)[:4000]
                record.updated_at = docs.now()
                docs.upsert(record)
        logger.exception("ingestion_failed job_id=%s document_id=%s", job.id, job.document_id)
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat


async def run_worker() -> None:
    settings = get_settings()
    queue = ingestion_queue(settings)
    worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
    logger.info(
        "worker_started worker_id=%s metadata_backend=%s",
        worker_id,
        settings.metadata_backend,
    )
    while True:
        job = queue.claim_next(worker_id, settings.worker_lease_seconds)
        if job is None:
            await asyncio.sleep(settings.worker_poll_seconds)
            continue
        logger.info(
            "ingestion_claimed job_id=%s document_id=%s attempt=%s/%s",
            job.id,
            job.document_id,
            job.attempts,
            job.max_attempts,
        )
        await _run_job(queue, job, worker_id, settings)


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
