#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
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

    cases = load_eval_dataset(args.dataset)
    payload = _load_fixture_payload(args.dataset)
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("retrieval fixture cases must be a list")
    raw_by_id = {raw.get("id"): raw for raw in raw_cases if isinstance(raw, dict)}

    dense_rankings: dict[str, list[SourceCitation]] = {}
    hybrid_rankings: dict[str, list[SourceCitation]] = {}
    answers: dict[str, str] = {}
    for case in cases:
        raw_case = raw_by_id.get(case.case_id)
        if not isinstance(raw_case, dict):
            raise ValueError(f"fixture candidates missing for case {case.case_id}")
        candidates = _citations_for_case(raw_case, case.tenant_id)
        dense_ranked = sorted(candidates, key=lambda citation: citation.score, reverse=True)
        dense_rankings[case.case_id] = dense_ranked
        hybrid_rankings[case.case_id] = rerank_hybrid(
            case.question,
            dense_ranked,
            case.top_k,
            dense_weight=args.dense_weight,
        )
        if case.answer_must_contain:
            answer = raw_case.get("answer")
            if not isinstance(answer, str):
                raise ValueError(f"fixture answer missing for case {case.case_id}")
            answers[case.case_id] = answer

    dense = evaluate_rankings(cases, dense_rankings, answers=answers).as_dict()
    hybrid = evaluate_rankings(cases, hybrid_rankings, answers=answers).as_dict()
    report = {
        "dataset_version": payload.get("version"),
        "case_count": len(cases),
        "dense_weight": args.dense_weight,
        "dense": dense,
        "hybrid": hybrid,
        "thresholds": {
            "recall_at_k": args.min_recall,
            "mrr": args.min_mrr,
            "ndcg_at_k": args.min_ndcg,
            "citation_hit_rate": args.min_citation_hit_rate,
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
