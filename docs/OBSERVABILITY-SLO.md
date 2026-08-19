# Local Observability and Initial SLOs

zknowbase observability remains local-first and does not require a hosted telemetry service. The backend exposes Prometheus metrics at `/metrics`; optional OTLP traces can be sent to the local OpenTelemetry Collector by setting `ZKB_OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`. The `observability` Compose profile adds OpenTelemetry Collector, Prometheus, and Grafana.

## Telemetry safety boundary

Telemetry must never include API keys, bearer tokens, passwords, session cookies/secrets, OIDC tokens, cloud-provider credentials, or raw document body text. Request traces use bounded route templates rather than unbounded resource identifiers. Tenant IDs and opaque document/job IDs may appear only where required for operational attribution and must not be treated as an authorization mechanism.

Exporter failure is fail-open for retrieval availability: inability to initialize or reach the trace collector is logged but does not disable query/search/ingestion. Authentication, authorization, tenant isolation, upload validation, and configuration errors remain fail-closed independently of observability.

## Metrics

The initial operational surface includes:

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

Queue depth refresh is bounded to 5,000 recent jobs per scrape and metrics failure does not make the API unavailable.

## Initial SLO objectives

These are starting operational objectives, not contractual guarantees. Calibrate them using representative local hardware, corpus size, model choice, and workload before production enforcement.

| SLI | Initial objective | Measurement |
| --- | --- | --- |
| API availability | 99.5% successful non-5xx requests over 30 days | `zkb_http_requests_total` |
| Search latency | 95% of `/search` operations below 2 seconds over 1 hour | `zkb_search_duration_seconds` |
| Query latency | 95% of non-streaming RAG queries below 15 seconds over 1 hour | `zkb_query_duration_seconds` |
| Ingestion success | 99% of jobs eventually complete without terminal failure over 24 hours | `zkb_ingestion_jobs_total`, `zkb_ingestion_failures_total` |
| Queue health | queued+processing backlog below 100 for 95% of samples over 1 hour | `zkb_ingestion_queue_depth` |
| Qdrant reliability | less than 1% Qdrant operation error rate over 1 hour | `zkb_qdrant_errors_total`, operation counts/HTTP evidence |

Streaming query latency measures the complete stream lifetime. Provider and Qdrant histograms should be used to distinguish model latency, embedding latency, and vector-store latency before changing SLO targets.

## Local startup

Set the normal required zknowbase secrets, then enable trace export and start the optional profile:

```bash
export ZKB_OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
docker compose --profile observability up --build
```

Prometheus is exposed on port `9090`; Grafana is exposed on port `3001` with an anonymous Viewer role intended for a trusted local/operator network only. Do not publish either endpoint directly to an untrusted network. The provisioned `zknowbase Local SLO Overview` dashboard covers API rate/latency, retrieval/provider latency, ingestion backlog/failures, authentication denials, and Qdrant errors.

## Operational review

For release evidence, retain a representative dashboard capture or exported metrics report, document workload parameters, and record whether initial SLOs were met. A telemetry outage must be investigated separately from core service availability; do not weaken authorization or isolation controls to restore telemetry.
