from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

from fastapi import Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from app.core.config import Settings
from app.store_factory import ingestion_queue

logger = logging.getLogger("zknowbase.observability")

HTTP_REQUESTS = Counter(
    "zkb_http_requests_total",
    "HTTP requests handled by zknowbase",
    ("method", "route", "status"),
)
HTTP_DURATION = Histogram(
    "zkb_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ("method", "route"),
)
QUERY_DURATION = Histogram("zkb_query_duration_seconds", "RAG answer latency in seconds")
SEARCH_DURATION = Histogram("zkb_search_duration_seconds", "Retrieval latency in seconds")
EMBEDDING_DURATION = Histogram(
    "zkb_embedding_duration_seconds", "Embedding provider latency in seconds", ("provider",)
)
LLM_DURATION = Histogram("zkb_llm_duration_seconds", "LLM provider latency in seconds", ("provider",))
QDRANT_DURATION = Histogram(
    "zkb_qdrant_duration_seconds", "Qdrant operation latency in seconds", ("operation",)
)
QDRANT_ERRORS = Counter(
    "zkb_qdrant_errors_total", "Qdrant operation failures", ("operation",)
)
INGESTION_JOBS = Counter(
    "zkb_ingestion_jobs_total",
    "Ingestion job lifecycle transitions",
    ("outcome",),
)
INGESTION_QUEUE_DEPTH = Gauge(
    "zkb_ingestion_queue_depth", "Queued plus processing ingestion jobs"
)
INGESTION_FAILURES = Counter(
    "zkb_ingestion_failures_total", "Terminal or processing ingestion failures"
)
AUTH_FAILURES = Counter("zkb_auth_failures_total", "Authentication failures")
AUTHORIZATION_DENIALS = Counter(
    "zkb_authorization_denials_total", "Authorization denials", ("reason",)
)
DATABASE_ERRORS = Counter(
    "zkb_database_errors_total", "Metadata database operational failures", ("backend",)
)
UPLOAD_SCAN_DURATION = Histogram(
    "zkb_upload_scan_duration_seconds", "Upload validation/scanning latency in seconds", ("mode",)
)
UPLOAD_SCAN_FAILURES = Counter(
    "zkb_upload_scan_failures_total", "Upload validation/scanning failures", ("mode",)
)

_tracing_configured = False


def configure_tracing(settings: Settings) -> None:
    """Configure OTLP tracing when an endpoint is explicitly configured.

    Core retrieval must remain available if telemetry is absent or temporarily broken,
    so exporter initialization is best-effort and never mutates application policy.
    """
    global _tracing_configured
    if _tracing_configured or not settings.otel_exporter_otlp_endpoint:
        return
    try:
        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": settings.otel_service_name,
                    "deployment.environment": settings.environment,
                }
            )
        )
        exporter = OTLPSpanExporter(
            endpoint=settings.otel_exporter_otlp_endpoint.rstrip("/") + "/v1/traces",
            timeout=settings.otel_export_timeout_seconds,
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracing_configured = True
    except Exception:
        logger.exception("otel_initialization_failed")


def tracer(name: str):
    return trace.get_tracer(name)


@contextmanager
def timed(metric: Histogram, labels: dict[str, str] | None = None) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        target = metric.labels(**labels) if labels else metric
        target.observe(time.perf_counter() - started)


def refresh_queue_depth(settings: Settings) -> None:
    """Refresh a bounded queue-depth gauge without making scrape failure fatal."""
    try:
        jobs = ingestion_queue(settings).list(5000)
        INGESTION_QUEUE_DEPTH.set(
            sum(1 for job in jobs if job.status in {"queued", "processing"})
        )
    except Exception:
        DATABASE_ERRORS.labels(backend=settings.metadata_backend).inc()
        logger.exception("metrics_queue_depth_failed")


def metrics_response(settings: Settings) -> Response:
    refresh_queue_depth(settings)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
