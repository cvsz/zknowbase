from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models.schemas import SourceCitation

_MAX_CASES = 1000
_MAX_CANDIDATES_PER_CASE = 100
_MAX_EXPECTED_DOCUMENTS = 50
_MAX_QUESTION_CHARS = 20_000
_MAX_ANSWER_TERM_CHARS = 200
_TENANT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")


@dataclass(frozen=True)
class RetrievalEvalCase:
    case_id: str
    question: str
    tenant_id: str
    expected_document_ids: frozenset[str]
    top_k: int
    answer_must_contain: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalEvalResult:
    recall_at_k: float
    mrr: float
    ndcg_at_k: float
    citation_hit_rate: float
    grounded_answer_rate: float | None
    evaluated_cases: int

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "recall_at_k": self.recall_at_k,
            "mrr": self.mrr,
            "ndcg_at_k": self.ndcg_at_k,
            "citation_hit_rate": self.citation_hit_rate,
            "grounded_answer_rate": self.grounded_answer_rate,
            "evaluated_cases": self.evaluated_cases,
        }


def _require_non_empty_string(value: Any, field: str, *, max_chars: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    value = value.strip()
    if len(value) > max_chars:
        raise ValueError(f"{field} exceeds {max_chars} characters")
    return value


def load_eval_dataset(path: Path) -> list[RetrievalEvalCase]:
    """Load a bounded, deterministic retrieval evaluation dataset from JSON."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to load retrieval evaluation dataset: {exc}") from exc

    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("retrieval evaluation dataset must be a version 1 object")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("retrieval evaluation dataset must contain at least one case")
    if len(raw_cases) > _MAX_CASES:
        raise ValueError(f"retrieval evaluation dataset exceeds {_MAX_CASES} cases")

    cases: list[RetrievalEvalCase] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_cases):
        if not isinstance(raw, dict):
            raise ValueError(f"cases[{index}] must be an object")
        case_id = _require_non_empty_string(raw.get("id"), f"cases[{index}].id", max_chars=120)
        if case_id in seen_ids:
            raise ValueError(f"duplicate retrieval evaluation case id: {case_id}")
        seen_ids.add(case_id)

        question = _require_non_empty_string(
            raw.get("question"), f"cases[{index}].question", max_chars=_MAX_QUESTION_CHARS
        )
        tenant_id = _require_non_empty_string(raw.get("tenant_id"), f"cases[{index}].tenant_id", max_chars=63)
        if _TENANT_RE.fullmatch(tenant_id) is None:
            raise ValueError(f"cases[{index}].tenant_id is invalid")

        expected = raw.get("expected_document_ids")
        if not isinstance(expected, list) or not expected or len(expected) > _MAX_EXPECTED_DOCUMENTS:
            raise ValueError(
                f"cases[{index}].expected_document_ids must contain 1-{_MAX_EXPECTED_DOCUMENTS} values"
            )
        expected_ids = frozenset(
            _require_non_empty_string(value, f"cases[{index}].expected_document_ids", max_chars=200)
            for value in expected
        )

        top_k = raw.get("top_k", 5)
        if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 50:
            raise ValueError(f"cases[{index}].top_k must be an integer between 1 and 50")

        answer_terms = raw.get("answer_must_contain", [])
        if not isinstance(answer_terms, list) or len(answer_terms) > 20:
            raise ValueError(f"cases[{index}].answer_must_contain must be a list with at most 20 values")
        normalized_terms = tuple(
            _require_non_empty_string(value, f"cases[{index}].answer_must_contain", max_chars=_MAX_ANSWER_TERM_CHARS)
            .casefold()
            for value in answer_terms
        )

        cases.append(
            RetrievalEvalCase(
                case_id=case_id,
                question=question,
                tenant_id=tenant_id,
                expected_document_ids=expected_ids,
                top_k=top_k,
                answer_must_contain=normalized_terms,
            )
        )
    return cases


def _unique_document_ids(citations: list[SourceCitation], top_k: int) -> list[str]:
    document_ids: list[str] = []
    seen: set[str] = set()
    for citation in citations:
        if citation.document_id in seen:
            continue
        seen.add(citation.document_id)
        document_ids.append(citation.document_id)
        if len(document_ids) >= top_k:
            break
    return document_ids


def _dcg(relevance: list[int]) -> float:
    return sum(value / math.log2(index + 2) for index, value in enumerate(relevance))


def evaluate_rankings(
    cases: list[RetrievalEvalCase],
    rankings: dict[str, list[SourceCitation]],
    *,
    answers: dict[str, str] | None = None,
) -> RetrievalEvalResult:
    if not cases:
        raise ValueError("at least one retrieval evaluation case is required")

    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []
    citation_hits = 0
    grounded_results: list[float] = []

    for case in cases:
        citations = rankings.get(case.case_id)
        if citations is None:
            raise ValueError(f"missing ranking for evaluation case {case.case_id}")
        if len(citations) > _MAX_CANDIDATES_PER_CASE:
            raise ValueError(
                f"ranking for {case.case_id} exceeds {_MAX_CANDIDATES_PER_CASE} candidates"
            )
        if any(citation.tenant_id != case.tenant_id for citation in citations):
            raise ValueError(f"ranking for {case.case_id} crossed the authoritative tenant boundary")

        ranked_ids = _unique_document_ids(citations, case.top_k)
        relevant = [1 if document_id in case.expected_document_ids else 0 for document_id in ranked_ids]
        retrieved_expected = set(ranked_ids) & case.expected_document_ids
        recalls.append(len(retrieved_expected) / len(case.expected_document_ids))

        first_relevant_rank = next((index + 1 for index, value in enumerate(relevant) if value), None)
        reciprocal_ranks.append(0.0 if first_relevant_rank is None else 1.0 / first_relevant_rank)

        ideal_relevant = [1] * min(case.top_k, len(case.expected_document_ids))
        ideal_dcg = _dcg(ideal_relevant)
        ndcgs.append(0.0 if ideal_dcg == 0 else _dcg(relevant) / ideal_dcg)
        citation_hits += int(bool(retrieved_expected))

        if case.answer_must_contain:
            if answers is None or case.case_id not in answers:
                raise ValueError(f"missing grounded answer for evaluation case {case.case_id}")
            normalized_answer = answers[case.case_id].casefold()
            grounded_results.append(
                1.0 if all(term in normalized_answer for term in case.answer_must_contain) else 0.0
            )

    count = len(cases)
    return RetrievalEvalResult(
        recall_at_k=sum(recalls) / count,
        mrr=sum(reciprocal_ranks) / count,
        ndcg_at_k=sum(ndcgs) / count,
        citation_hit_rate=citation_hits / count,
        grounded_answer_rate=(sum(grounded_results) / len(grounded_results)) if grounded_results else None,
        evaluated_cases=count,
    )
