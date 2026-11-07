#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter_ns
from typing import Any

from app.models.schemas import SourceCitation
from app.rag.evaluation import evaluate_rankings, load_eval_dataset
from app.rag.hybrid import rerank_hybrid

_MAX_FIXTURE_CANDIDATES = 100


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic local retrieval quality evaluation")
    parser.add_argument("--dataset", type=Path, default=Path("eval/retrieval-quality-v1.json"))
    parser.add_argument("--output", type=Path, default=Path("retrieval-quality-report.json"))
    parser.add_argument("--dense-weight", type=float, default=0.65)
    parser.add_argument("--hybrid-candidate-multiplier", type=int, default=4)
    parser.add_argument("--min-recall", type=float, default=0.80)
    parser.add_argument("--min-mrr", type=float, default=0.80)
    parser.add_argument("--min-ndcg", type=float, default=0.80)
    parser.add_argument("--min-citation-hit-rate", type=float, default=0.80)
    parser.add_argument("--require-hybrid-not-worse", action="store_true")
    return parser


def _validate_threshold(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")


def _load_fixture_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to load retrieval fixture candidates: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("retrieval fixture must be a JSON object")
    return payload


def _citations_for_case(raw_case: dict[str, Any], tenant_id: str) -> list[SourceCitation]:
    raw_candidates = raw_case.get("candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        raise ValueError(f"case {raw_case.get('id', '<unknown>')} must define deterministic candidates")
    if len(raw_candidates) > _MAX_FIXTURE_CANDIDATES:
        raise ValueError(
            f"case {raw_case.get('id', '<unknown>')} exceeds {_MAX_FIXTURE_CANDIDATES} deterministic candidates"
        )

    citations: list[SourceCitation] = []
    for index, raw in enumerate(raw_candidates):
        if not isinstance(raw, dict):
            raise ValueError(f"candidate {index} must be an object")
        document_id = raw.get("document_id")
        text = raw.get("text")
        score = raw.get("dense_score")
        candidate_tenant = raw.get("tenant_id", tenant_id)
        if not isinstance(document_id, str) or not document_id:
            raise ValueError(f"candidate {index} has invalid document_id")
        if not isinstance(text, str) or not text:
            raise ValueError(f"candidate {index} has invalid text")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise ValueError(f"candidate {index} has invalid dense_score")
        citations.append(
            SourceCitation(
                document_id=document_id,
                document_name=raw.get("document_name", f"{document_id}.md"),
                tenant_id=candidate_tenant,
                chunk_id=raw.get("chunk_id", f"{document_id}-{index}"),
                chunk_index=index,
                score=float(score),
                text=text,
                source_uri=None,
            )
        )
    return citations


def _dense_production_candidates(
    dense_ranked: list[SourceCitation], *, top_k: int
) -> list[SourceCitation]:
    """Emulate production dense mode, which requests exactly top_k chunk hits."""
    return dense_ranked[:top_k]


def _rerank_production_candidates(
    question: str,
    dense_ranked: list[SourceCitation],
    *,
    top_k: int,
    dense_weight: float,
    candidate_multiplier: int,
) -> list[SourceCitation]:
    """Emulate production's bounded dense-candidate generation and adaptive fill."""
    candidate_limit = max(
        top_k,
        min(_MAX_FIXTURE_CANDIDATES, top_k * candidate_multiplier),
    )
    while True:
        candidates = dense_ranked[:candidate_limit]
        reranked = rerank_hybrid(
            question,
            candidates,
            top_k,
            dense_weight=dense_weight,
            document_level_cutoff=True,
        )
        if (
            len(reranked) >= top_k
            or len(candidates) < candidate_limit
            or candidate_limit >= _MAX_FIXTURE_CANDIDATES
        ):
            return reranked
        candidate_limit = min(
            _MAX_FIXTURE_CANDIDATES,
            max(candidate_limit + 1, candidate_limit * 2),
        )


def _metrics_meet_thresholds(metrics: dict[str, float | int | None], args: argparse.Namespace) -> list[str]:
    failures: list[str] = []
    thresholds = {
        "recall_at_k": args.min_recall,
        "mrr": args.min_mrr,
        "ndcg_at_k": args.min_ndcg,
        "citation_hit_rate": args.min_citation_hit_rate,
    }
    for metric, threshold in thresholds.items():
        value = metrics[metric]
        if not isinstance(value, (int, float)) or float(value) < threshold:
            failures.append(f"{metric}={value!r} is below threshold {threshold:.3f}")
    return failures


def main() -> int:
    args = _parser().parse_args()
    for name in ("min_recall", "min_mrr", "min_ndcg", "min_citation_hit_rate"):
        _validate_threshold(name, getattr(args, name))
    if not 0.0 <= args.dense_weight <= 1.0:
        raise ValueError("dense_weight must be between 0 and 1")
    if not 1 <= args.hybrid_candidate_multiplier <= 20:
        raise ValueError("hybrid_candidate_multiplier must be between 1 and 20")

    cases = load_eval_dataset(args.dataset)
    payload = _load_fixture_payload(args.dataset)
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("retrieval fixture cases must be a list")
    raw_by_id = {raw.get("id"): raw for raw in raw_cases if isinstance(raw, dict)}

    dense_rankings: dict[str, list[SourceCitation]] = {}
    hybrid_rankings: dict[str, list[SourceCitation]] = {}
    answers: dict[str, str] = {}
    dense_sort_ns = 0
    hybrid_rerank_ns = 0
    for case in cases:
        raw_case = raw_by_id.get(case.case_id)
        if not isinstance(raw_case, dict):
            raise ValueError(f"fixture candidates missing for case {case.case_id}")
        candidates = _citations_for_case(raw_case, case.tenant_id)

        started = perf_counter_ns()
        dense_ranked = sorted(candidates, key=lambda citation: citation.score, reverse=True)
        dense_sort_ns += perf_counter_ns() - started
        dense_rankings[case.case_id] = _dense_production_candidates(
            dense_ranked,
            top_k=case.top_k,
        )

        started = perf_counter_ns()
        hybrid_rankings[case.case_id] = _rerank_production_candidates(
            case.question,
            dense_ranked,
            top_k=case.top_k,
            dense_weight=args.dense_weight,
            candidate_multiplier=args.hybrid_candidate_multiplier,
        )
        hybrid_rerank_ns += perf_counter_ns() - started

        if case.answer_must_contain:
            answer = raw_case.get("answer")
            if not isinstance(answer, str):
                raise ValueError(f"fixture answer missing for case {case.case_id}")
            answers[case.case_id] = answer

    dense = evaluate_rankings(cases, dense_rankings, answers=answers).as_dict()
    hybrid = evaluate_rankings(cases, hybrid_rankings, answers=answers).as_dict()
    case_count = len(cases)
    report = {
        "dataset_version": payload.get("version"),
        "case_count": case_count,
        "dense_weight": args.dense_weight,
        "hybrid_candidate_multiplier": args.hybrid_candidate_multiplier,
        "dense": dense,
        "hybrid": hybrid,
        "thresholds": {
            "recall_at_k": args.min_recall,
            "mrr_at_k": args.min_mrr,
            "ndcg_at_k": args.min_ndcg,
            "citation_hit_rate": args.min_citation_hit_rate,
        },
        "timing": {
            "scope": "offline_fixture_ranking_only",
            "gated": False,
            "dense_sort_ms_total": dense_sort_ns / 1_000_000,
            "hybrid_rerank_ms_total": hybrid_rerank_ns / 1_000_000,
            "hybrid_rerank_ms_per_case": (hybrid_rerank_ns / case_count) / 1_000_000,
        },
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    failures = _metrics_meet_thresholds(hybrid, args)
    if args.require_hybrid_not_worse:
        for metric in ("recall_at_k", "mrr", "ndcg_at_k", "citation_hit_rate"):
            hybrid_value = float(hybrid[metric])
            dense_value = float(dense[metric])
            if hybrid_value + 1e-12 < dense_value:
                failures.append(f"hybrid {metric}={hybrid_value:.3f} is worse than dense {dense_value:.3f}")

    print(json.dumps(report, indent=2, sort_keys=True))
    if failures:
        for failure in failures:
            print(f"QUALITY GATE FAILED: {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
