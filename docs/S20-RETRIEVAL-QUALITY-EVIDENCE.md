# S20 Retrieval Quality Evaluation Evidence

This document records immutable repository evidence for the `S20 — Retrieval quality evaluation and regression gates` slice in `exec-planning.md`.

## Implementation provenance

Implementation PR: `#55 feat: add deterministic retrieval quality gates`

- PR head: `7043270fa83d65f83866a99b6c314e3df7472c94`
- Merge commit: `e1f7b5d7e28bdc911076867aaa111368afbe3155`
- Exact-head CI: run `32367426382` (CI #158), conclusion `success`
- Exact-head Security: run `32367426366` (Security #38), conclusion `success`

Follow-up correctness hardening is carried by this evidence PR itself: production hybrid retrieval applies a document-level top-K cutoff and adaptively expands its bounded dense-candidate prefix when duplicate chunks would otherwise underfill the requested unique-document result count. The offline evaluator emulates that hybrid candidate-generation policy, evaluates dense mode using production's exact `top_k` chunk cutoff, documents the reciprocal-rank metric explicitly as MRR@K, and emits informational ranking-stage timing evidence alongside quality metrics.

## Dataset and determinism

The committed dataset is `backend/eval/retrieval-quality-v1.json` and is consumed entirely offline. Each case carries a stable case identifier, retrieval question, authoritative tenant identity, expected document constraints, a bounded `top_k`, optional deterministic grounded-answer terms, and synthetic candidate data. The loader rejects malformed dataset versions, duplicate case IDs, invalid tenants, empty expected-document sets, invalid cutoffs, excessive case counts, and the structural/query fields that are explicitly bounded by the loader. Synthetic candidate payloads are test fixtures; this evidence does not claim that every candidate text or metadata field is length-bounded by the dataset loader.

No paid model API, hosted evaluation service, or nondeterministic LLM judge is required for this gate.

## Metrics and regression gate

The evaluator records document-level quality metrics from production-shaped dense and hybrid rankings:

- Recall@K
- MRR@K — reciprocal rank of the first expected document within the first K unique documents
- nDCG@K
- citation hit rate
- deterministic grounded-answer all-required-terms pass rate when a rubric is supplied

For the grounded-answer metric, a case scores `1` only when every required rubric term is present and `0` otherwise; `grounded_answer_rate` is the mean of those binary case results. It is not a term-level coverage percentage.

Dense evaluation sorts the synthetic candidates by dense score and passes exactly the first `top_k` chunk hits into document-level metrics, matching production dense mode's single Qdrant request. It does not scan beyond that production cutoff merely to fill unique-document metric slots.

Hybrid evaluation starts with the dense prefix bounded by `top_k * hybrid_candidate_multiplier` and the 100-candidate ceiling. BM25+dense fusion reranks only that prefix. If duplicate chunks leave fewer than `top_k` unique documents, both production and the evaluator expand the prefix geometrically, still capped at 100, until enough unique documents are available or the dense result set is exhausted. The evaluator restricts the multiplier to production's supported range of 1 through 20. Dedicated regression coverage verifies the dense cutoff and hybrid adaptive-fill behaviors.

The CI command fails non-zero when a configured hybrid quality metric is below threshold or when `--require-hybrid-not-worse` detects a hybrid regression relative to the production-shaped dense baseline. The repository validation target uses thresholds of `0.80` for Recall@K, MRR@K (CLI compatibility flag `--min-mrr`), nDCG@K, and citation hit rate and includes the result in `make validate`. The evaluator exposes `--hybrid-candidate-multiplier` so the committed gate can remain aligned with the production candidate-generation setting without introducing an external service.

## Latency and quality evidence

The evaluator records informational `dense_sort_ms_total`, `hybrid_rerank_ms_total`, and `hybrid_rerank_ms_per_case` values in its JSON artifact. These timings cover only the deterministic offline ranking stage over precomputed synthetic candidates and are not treated as stable CI thresholds. They deliberately exclude embeddings, Qdrant/network latency, HTTP middleware, serialization, and concurrency, so they must not be represented as end-to-end production latency.

This establishes the local ranking-stage trade-off without making the quality gate flaky: hybrid retrieval adds bounded local tokenization/BM25/fusion CPU work and may issue additional bounded Qdrant searches when duplicate chunks would underfill the unique-document result count, while its Recall@K, MRR@K, nDCG@K, and citation-hit results are recorded beside ranking-stage timing evidence. `docs/RETRIEVAL-EVALUATION.md` requires production tuning to pair this quality baseline with representative end-to-end latency telemetry from the deployment before changing dense weight, candidate bounds, or thresholds. The current documented hybrid dense weight remains `0.65` and the default candidate multiplier remains `4`.

## Tenant and security boundary

Tenant identity is authoritative in each evaluation case. Evaluation fails closed if any returned candidate/citation crosses the expected tenant boundary. Fixtures are synthetic and must not contain production documents, service keys, API keys, browser/session secrets, provider credentials, or other sensitive content.

The evaluator does not alter the production Qdrant authorization model and does not replace real Qdrant lifecycle or cross-tenant integration tests.

## S20 acceptance mapping

- Local evaluation dataset format with question/source constraints and optional answer rubric: implemented.
- Offline Recall@K, MRR@K, nDCG@K, citation-hit, and grounded-answer all-required-terms pass-rate metrics: implemented.
- Dense-only versus hybrid comparison under tenant-authoritative evaluation: implemented with production-shaped dense chunk cutoff and hybrid bounded/adaptive candidate generation.
- Deterministic local fixtures with no paid model API: implemented.
- Configurable non-LLM-judge CI thresholds: implemented and exact-head CI-proven.
- Retrieval latency/quality trade-offs and default tuning guidance: implemented through informational ranking-stage timing evidence plus explicit production telemetry/tuning guidance in `docs/RETRIEVAL-EVALUATION.md`.

S20 should only be reconciled to `[x]` in `exec-planning.md` after this evidence document and its correctness hardening pass the repository's exact-head CI and Security gates and merge under normal repository governance.
