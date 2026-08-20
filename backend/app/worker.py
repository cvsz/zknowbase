import asyncio
import logging
import os
import signal
import socket
from contextlib import suppress
from uuid import uuid4

from app.core.config import get_settings
from app.ingestion_service import process_ingestion_job
from app.maintenance import async_mutation_lock
from app.observability import INGESTION_FAILURES, INGESTION_JOBS, configure_tracing, tracer
from app.store_factory import document_store, ingestion_queue

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("zknowbase.worker")


async def _heartbeat(queue, job_id: str, worker_id: str, lease_seconds: int) -> None:
    interval = max(5.0, lease_seconds / 3)
    while True:
        await asyncio.sleep(interval)
        if not queue.renew(job_id, worker_id, lease_seconds):
            raise RuntimeError("Ingestion job lease ownership was lost")


def _tenant_document(docs, job):
    record = docs.get(job.document_id)
    if record is None:
        return None
    if record.tenant_id != job.tenant_id:
        raise RuntimeError("Ingestion job tenant ownership does not match document tenant")
    return record


def _reap_and_reconcile(queue, settings) -> None:
    docs = document_store(settings)
    for job in queue.reap_expired():
        record = _tenant_document(docs, job)
        if record is None:
            continue
        if job.status == "failed" and not queue.active_for_document(job.document_id, job.tenant_id):
            record.status = "failed"
            record.error = job.error or "job lease expired"
            record.updated_at = docs.now()
            docs.upsert(record)
            INGESTION_FAILURES.inc()
            INGESTION_JOBS.labels(outcome="lease_expired_failed").inc()
            logger.error(
                "ingestion_lease_expired_terminal job_id=%s document_id=%s tenant_id=%s",
                job.id,
                job.document_id,
                job.tenant_id,
            )
        elif job.status == "queued":
            record.status = "queued"
            record.error = "worker lease expired; retry queued"
            record.updated_at = docs.now()
            docs.upsert(record)
            INGESTION_JOBS.labels(outcome="lease_expired_requeued").inc()
            logger.warning(
                "ingestion_lease_expired_requeued job_id=%s document_id=%s tenant_id=%s attempt=%s/%s",
                job.id,
                job.document_id,
                job.tenant_id,
                job.attempts,
                job.max_attempts,
            )


async def _run_job(queue, job, worker_id: str, settings) -> None:
    with tracer("zknowbase.worker").start_as_current_span("ingestion.process") as span:
        span.set_attribute("tenant.id", job.tenant_id)
        span.set_attribute("ingestion.job_id", job.id)
        span.set_attribute("ingestion.document_id", job.document_id)
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
            INGESTION_JOBS.labels(outcome="completed").inc()
            logger.info(
                "ingestion_completed job_id=%s document_id=%s tenant_id=%s chunks=%s",
                job.id,
                result.id,
                job.tenant_id,
                result.chunk_count,
            )
        except Exception as exc:
            if not processing.done():
                processing.cancel()
                with suppress(asyncio.CancelledError):
                    await processing

            transitioned = False
            with suppress(Exception):
                transitioned = queue.fail(job.id, worker_id, str(exc))
            if transitioned:
                INGESTION_JOBS.labels(outcome="failed_or_requeued").inc()
                with suppress(Exception):
                    current = queue.get(job.id)
                    docs = document_store(settings)
                    record = _tenant_document(docs, job)
                    if record is not None and current is not None and current.tenant_id == job.tenant_id:
                        record.status = "queued" if current.status == "queued" else "failed"
                        record.error = str(exc)[:4000]
                        record.updated_at = docs.now()
                        docs.upsert(record)
                        if current.status == "failed":
                            INGESTION_FAILURES.inc()
            logger.exception(
                "ingestion_failed job_id=%s document_id=%s tenant_id=%s",
                job.id,
                job.document_id,
                job.tenant_id,
            )
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat


async def _wait_for_work_or_stop(stop_event: asyncio.Event, poll_seconds: float) -> None:
    if stop_event.is_set():
        return
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
    except TimeoutError:
        pass


async def run_worker(stop_event: asyncio.Event | None = None) -> None:
    settings = get_settings()
    configure_tracing(settings)
    queue = ingestion_queue(settings)
    worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
    stop_event = stop_event or asyncio.Event()
    logger.info(
        "worker_started worker_id=%s metadata_backend=%s",
        worker_id,
        settings.metadata_backend,
    )
    try:
        while not stop_event.is_set():
            async with async_mutation_lock(settings.maintenance_lock_path, exclusive=False):
                _reap_and_reconcile(queue, settings)
                # A shutdown signal may arrive while acquiring the maintenance lock.
                # Do not claim new work after the drain boundary has been requested.
                if stop_event.is_set():
                    break
                job = queue.claim_next(worker_id, settings.worker_lease_seconds)
                if job is not None:
                    INGESTION_JOBS.labels(outcome="claimed").inc()
                    logger.info(
                        "ingestion_claimed job_id=%s document_id=%s tenant_id=%s attempt=%s/%s",
                        job.id,
                        job.document_id,
                        job.tenant_id,
                        job.attempts,
                        job.max_attempts,
                    )
                    # Deliberately drain the active lease to a terminal/requeued queue
                    # transition before observing stop_event again. This prevents a
                    # graceful SIGTERM from abandoning a claimed job mid-mutation.
                    await _run_job(queue, job, worker_id, settings)
                    continue
            await _wait_for_work_or_stop(stop_event, settings.worker_poll_seconds)
    finally:
        logger.info("worker_stopped worker_id=%s", worker_id)


async def _run_worker_with_signals() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    registered: list[signal.Signals] = []

    def request_stop() -> None:
        if not stop_event.is_set():
            logger.info("worker_shutdown_requested")
            stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, request_stop)
        except (NotImplementedError, RuntimeError):
            continue
        registered.append(sig)

    try:
        await run_worker(stop_event)
    finally:
        for sig in registered:
            with suppress(NotImplementedError, RuntimeError):
                loop.remove_signal_handler(sig)


def main() -> None:
    asyncio.run(_run_worker_with_signals())


if __name__ == "__main__":
    main()
