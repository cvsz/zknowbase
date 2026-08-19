# Performance validation

zknowbase performance validation is local-first and separates repeatable component evidence from deployment-specific end-to-end model latency.

## CI Qdrant load evidence

Every CI run executes `backend/scripts/benchmark_qdrant.py` against the same pinned local Qdrant version used by Docker Compose. The bounded workload is:

- 512 tenant-scoped vector points
- 32-dimensional deterministic vectors
- 200 tenant-filtered searches
- concurrency 8
- top 10 results per search
- zero accepted search errors
- p95 search guardrail of 2.0 seconds on the GitHub-hosted runner

The job emits `performance-report.json` and publishes it as `qdrant-performance-<commit-sha>` for 30 days. The report records point/request counts, concurrency, elapsed time, requests per second, mean latency, p50/p95/p99 latency, errors, and the configured p95 guardrail.

The 2-second CI limit is a regression guardrail, not a contractual performance guarantee. It is intentionally broad enough to tolerate shared CI runner variability while detecting severe vector-store regressions.

## Reproduce locally

From `backend/` with a local Qdrant instance:

```bash
python -m pip install -r requirements.txt
PYTHONPATH=. python scripts/benchmark_qdrant.py \
  --qdrant-url http://127.0.0.1:6333 \
  --points 512 \
  --requests 200 \
  --concurrency 8 \
  --vector-size 32 \
  --max-p95-seconds 2.0 \
  --output performance-report.json
```

All benchmark cardinalities and concurrency values are bounded by the CLI. The benchmark creates and removes an ephemeral collection and does not require Ollama, a cloud model provider, or paid infrastructure.

## What this proves

This workload validates the Qdrant portion of tenant-filtered retrieval under concurrent local load and produces commit-addressable evidence. It does not by itself prove the complete `/query` SLO because full RAG latency also depends on embedding generation, selected Ollama model, CPU/GPU, corpus size, prompt size, and streaming behavior.

For a production deployment, retain an additional workload report from representative hardware covering API availability, `/search`, `/query`, ingestion throughput, queue backlog, and local model latency. Calibrate the initial SLOs in `OBSERVABILITY-SLO.md` against that deployment rather than tightening CI thresholds to mimic hardware that CI does not provide.
