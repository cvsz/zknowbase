# Local observability and SLOs

zknowbase observability is local-first and optional. Core retrieval, ingestion, authentication, and tenant enforcement do not require a SaaS telemetry backend.

## Signals

The backend exposes Prometheus metrics at `/metrics` when `ZKB_METRICS_ENABLED=true`. Metrics intentionally use bounded labels such as HTTP method, route template, status, provider, operation, and denial reason; API keys, cookies, raw bearer tokens, passwords, session secrets, document bodies, prompts, and model responses are not metric labels.

Key metrics include:

- `zkb_http_requests_total`
- `zkb_http_request_duration_seconds`
- `zkb_query_duration_seconds`
- `zkb_search_duration_seconds`
- `zkb_embedding_duration_seconds`
- `zkb_llm_duration_seconds`
- `zkb_qdrant_duration_seconds`
- `zkb_qdrant_errors_total`
- `zkb_ingestion_jobs_total`
- `zkb_ingestion_queue_depth`
- `zkb_ingestion_failures_total`
- `zkb_auth_failures_total`
- `zkb_authorization_denials_total`
- `zkb_database_errors_total`
- `zkb_upload_scan_duration_seconds`
- `zkb_upload_scan_failures_total`

OpenTelemetry traces are enabled only when `ZKB_OTEL_EXPORTER_OTLP_ENDPOINT` is configured. Exporter initialization and delivery are fail-open with respect to the knowledge service: collector failure is logged but must not make retrieval or ingestion unavailable.

## Local stack

Run the normal stack with the observability profile:

```bash
ZKB_OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318 \
ZKB_GRAFANA_ADMIN_PASSWORD='<strong local password>' \
docker compose --profile observability up --build
```

Prometheus is available on port `9090` and Grafana on port `3001`. The profile uses the repository-owned OpenTelemetry Collector, Prometheus scrape configuration, Grafana provisioning, and dashboard files under `ops/observability/`.

Do not expose Prometheus, Grafana, the Collector, or `/metrics` directly to an untrusted network without an operator-controlled reverse proxy/firewall and authentication policy.

## Initial SLO objectives

These are initial operational objectives, not universal guarantees. Calibrate them using production workload evidence before turning them into contractual SLOs.

| Objective | Initial target | Measurement |
| --- | --- | --- |
| API availability | >= 99.5% over 30 days | non-5xx requests / total requests, excluding planned maintenance |
| Query latency | p95 <= 5 s for local default models under validated reference load | `zkb_query_duration_seconds` |
| Search latency | p95 <= 1 s under validated reference corpus/load | `zkb_search_duration_seconds` |
| Ingestion success | >= 99% for accepted, supported inputs | completed jobs / terminal jobs; policy rejections are excluded |
| Queue health | queued+processing backlog returns below 100 within 15 minutes after a reference burst | `zkb_ingestion_queue_depth` |
| Qdrant operation errors | < 1% over 15 minutes | `zkb_qdrant_errors_total` relative to Qdrant operations |

The latency objectives include local provider/model performance and therefore must be re-baselined when model, hardware, corpus size, chunking, or concurrency settings materially change.

## Alerting guidance

Recommended local alerts:

- API 5xx ratio > 5% for 5 minutes.
- query p95 above the calibrated SLO for 10 minutes.
- ingestion failures > 5 in 10 minutes.
- queue depth continuously increasing for 15 minutes.
- Qdrant errors > 1% for 5 minutes.
- sustained authentication or authorization-denial spikes relative to the deployment baseline.

## Security and privacy

Telemetry must never contain credentials or raw knowledge content by default. Tenant identifiers and opaque resource/request IDs may be emitted only when needed for operational correlation and must not be used as unbounded metric labels. Traces should record operation metadata, timing, status, and request IDs—not prompt/document bodies or authorization headers.
