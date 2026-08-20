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

The loader rejects malformed versions, duplicate case IDs, invalid tenant IDs, empty expected-document sets, excessive case counts, invalid `top_k`, and oversized fields. Evaluation also fails closed if any candidate citation crosses the case tenant boundary.

## Metrics

The gate computes document-level metrics after de-duplicating repeated chunks from the same document:

- **Recall@K**: fraction of expected documents present in the first K unique retrieved documents;
- **MRR**: reciprocal rank of the first expected document;
- **nDCG@K**: binary-relevance discounted cumulative gain normalized against the ideal ranking;
- **citation hit rate**: fraction of cases with at least one expected source in the first K results;
- **grounded answer rate**: deterministic required-term coverage for cases that provide an answer rubric.

The committed fixture compares dense ordering with the same candidates re-ranked by the local BM25+dense fusion implementation. It does not replace real Qdrant lifecycle tests; it supplies a stable ranking-regression gate that can run offline and reproduce exactly.

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

The command exits non-zero when a hybrid metric falls below its threshold or when `--require-hybrid-not-worse` detects a regression relative to dense ordering. CI uploads the JSON report as evidence.

## Tuning guidance

The default hybrid dense weight remains `0.65`. Operators should calibrate it against their own corpus, language mix, embedding model, chunking settings, and latency budget. Lower dense weight increases lexical influence and can improve exact-term queries, but can over-promote keyword overlap; higher dense weight preserves semantic similarity but can miss exact policy/product identifiers.

Production tuning should record both quality and latency. Do not raise or lower committed thresholds solely to make CI green: update the dataset or thresholds only with reviewed evidence explaining the workload change and expected retrieval behavior.

## Security boundary

Evaluation fixtures contain synthetic/non-secret text only. They must not contain production documents, API keys, session data, or provider credentials. Tenant IDs in the fixture are test identities; evaluation rejects a ranking that returns a citation for a different tenant so quality tooling cannot normalize away a tenant-isolation defect.
