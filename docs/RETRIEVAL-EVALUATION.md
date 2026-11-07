# Retrieval Quality Evaluation

zknowbase uses a deterministic, local-first retrieval quality gate to catch ranking regressions without a paid model API or a flaky LLM judge.

## Dataset contract

The committed baseline is `backend/eval/retrieval-quality-v1.json`. The top-level object is versioned and contains bounded cases. Each case defines:

- `id`: stable unique case identifier;
- `question`: retrieval query;
- `tenant_id`: authoritative tenant expected for every returned citation;
- `expected_document_ids`: one or more acceptable source documents;
- `top_k`: document-level cutoff used by the metrics;
- optional `answer_must_contain`: deterministic grounded-answer terms;
- deterministic `candidates` with document metadata, dense score, and chunk text for the offline comparison fixture.

The loader rejects malformed versions, duplicate case IDs, invalid tenant IDs, empty expected-document sets, excessive case counts, invalid `top_k`, and the structural/query fields for which explicit bounds are implemented. Candidate count is bounded separately; this document does not claim that every candidate text or metadata field has an independent length limit. Evaluation also fails closed if any candidate citation crosses the case tenant boundary.

## Metrics

The gate computes document-level metrics after de-duplicating repeated chunks from the same document:

- **Recall@K**: fraction of expected documents present in the first K unique retrieved documents;
- **MRR@K**: reciprocal rank of the first expected document within the first K unique retrieved documents; expected documents appearing only after K contribute zero;
- **nDCG@K**: binary-relevance discounted cumulative gain normalized against the ideal ranking;
- **citation hit rate**: fraction of cases with at least one expected source in the first K unique documents;
- **grounded answer rate**: fraction of rubric-bearing cases for which every required term is present; each case is a binary pass/fail, not a term-level coverage percentage.

The committed fixture compares production-shaped dense and hybrid retrieval semantics over deterministic synthetic candidates. Dense mode evaluates exactly the first `top_k` chunk hits, matching production's single Qdrant request even when repeated chunks underfill the later document-level metric view. Hybrid mode starts with the multiplier-bounded dense prefix used by production, reranks that prefix with local BM25+dense fusion, and expands the prefix geometrically only when duplicate chunks leave fewer than `top_k` unique documents. Expansion remains capped at 100 candidates and stops when enough unique documents are available or the fixture result set is exhausted. The fixture does not replace real Qdrant lifecycle tests; it supplies a stable ranking-regression gate that can run offline and reproduce ranking metrics deterministically.

## CI gate

Run from `backend/`:

```bash
PYTHONPATH=. python scripts/evaluate_retrieval.py \
  --dataset eval/retrieval-quality-v1.json \
  --output retrieval-quality-report.json \
  --min-recall 0.80 \
  --min-mrr 0.80 \
  --min-ndcg 0.80 \
  --min-citation-hit-rate 0.80 \
  --require-hybrid-not-worse
```

The command exits non-zero when a hybrid quality metric falls below its threshold or when `--require-hybrid-not-worse` detects a regression relative to the production-shaped dense baseline. CI uploads the JSON report as evidence. The CLI option remains `--min-mrr` for compatibility, but the metric it gates is semantically MRR@K. `--hybrid-candidate-multiplier` is constrained to the same production range of 1 through 20.

## Latency and quality trade-off

The evaluator records informational ranking-stage timings in the JSON report:

- `dense_sort_ms_total`: time spent ordering the synthetic candidates by their precomputed dense score;
- `hybrid_rerank_ms_total`: time spent applying local BM25+dense fusion across the production-shaped bounded candidate prefixes;
- `hybrid_rerank_ms_per_case`: average local hybrid re-ranking time per evaluation case.

These measurements intentionally cover only offline fixture ranking. They do **not** represent end-to-end production retrieval latency because they exclude embedding generation, Qdrant/network latency, request middleware, serialization, and workload concurrency. Timing values are environment-dependent and are therefore retained as evidence but are not CI pass/fail thresholds.

The trade-off is explicit: hybrid mode adds local tokenization/BM25 scoring, candidate fusion, and potentially additional bounded Qdrant fetches in exchange for the quality metrics recorded beside the timings. Lower dense weight increases lexical influence and can improve exact-term queries but can over-promote keyword overlap; higher dense weight preserves semantic similarity but can miss exact policy/product identifiers. The default dense weight remains `0.65` because the committed deterministic baseline must meet the configured Recall@K, MRR@K, nDCG@K, and citation-hit thresholds without regressing below dense ordering.

Production tuning should compare the quality report with representative end-to-end latency telemetry from the actual deployment before changing dense weight, candidate bounds, or thresholds. Do not change committed thresholds solely to make CI green; update the dataset or thresholds only with reviewed evidence explaining the workload change and expected retrieval behavior.

## Security boundary

Evaluation fixtures contain synthetic/non-secret text only. They must not contain production documents, API keys, session data, or provider credentials. Tenant IDs in the fixture are test identities; evaluation rejects a ranking that returns a citation for a different tenant so quality tooling cannot normalize away a tenant-isolation defect.
