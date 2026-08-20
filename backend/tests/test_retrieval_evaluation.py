import json

import pytest

from app.models.schemas import SourceCitation
from app.rag.evaluation import RetrievalEvalCase, evaluate_rankings, load_eval_dataset


def _citation(document_id: str, *, tenant_id: str = "acme", score: float = 0.9) -> SourceCitation:
    return SourceCitation(
        document_id=document_id,
        document_name=f"{document_id}.md",
        tenant_id=tenant_id,
        chunk_id=f"{document_id}-0",
        chunk_index=0,
        score=score,
        text=f"content for {document_id}",
        source_uri=None,
    )


def test_evaluate_rankings_computes_recall_mrr_ndcg_and_grounding():
    cases = [
        RetrievalEvalCase(
            case_id="case-a",
            question="question",
            tenant_id="acme",
            expected_document_ids=frozenset({"expected-a", "expected-b"}),
            top_k=2,
            answer_must_contain=("grounded phrase",),
        )
    ]
    rankings = {"case-a": [_citation("noise"), _citation("expected-a", score=0.8)]}
    result = evaluate_rankings(cases, rankings, answers={"case-a": "A grounded phrase is present."})

    assert result.recall_at_k == pytest.approx(0.5)
    assert result.mrr == pytest.approx(0.5)
    assert result.ndcg_at_k == pytest.approx((1 / 1.584962500721156) / (1 + 1 / 1.584962500721156))
    assert result.citation_hit_rate == pytest.approx(1.0)
    assert result.grounded_answer_rate == pytest.approx(1.0)


def test_evaluation_deduplicates_document_chunks_for_document_metrics():
    case = RetrievalEvalCase(
        case_id="case-a",
        question="question",
        tenant_id="acme",
        expected_document_ids=frozenset({"expected-a", "expected-b"}),
        top_k=2,
    )
    first = _citation("expected-a")
    duplicate = first.model_copy(update={"chunk_id": "expected-a-1", "chunk_index": 1, "score": 0.85})
    rankings = {"case-a": [first, duplicate, _citation("expected-b", score=0.8)]}

    result = evaluate_rankings([case], rankings)

    assert result.recall_at_k == pytest.approx(1.0)
    assert result.mrr == pytest.approx(1.0)
    assert result.ndcg_at_k == pytest.approx(1.0)


def test_evaluation_rejects_cross_tenant_citations():
    case = RetrievalEvalCase(
        case_id="case-a",
        question="question",
        tenant_id="acme",
        expected_document_ids=frozenset({"expected"}),
        top_k=1,
    )

    with pytest.raises(ValueError, match="crossed the authoritative tenant boundary"):
        evaluate_rankings([case], {"case-a": [_citation("expected", tenant_id="other")]})


def test_dataset_loader_fails_closed_on_duplicate_case_ids(tmp_path):
    dataset = tmp_path / "eval.json"
    case = {
        "id": "duplicate",
        "question": "What is the policy?",
        "tenant_id": "acme",
        "expected_document_ids": ["doc"],
        "top_k": 1,
    }
    dataset.write_text(json.dumps({"version": 1, "cases": [case, case]}), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate retrieval evaluation case id"):
        load_eval_dataset(dataset)


def test_committed_retrieval_dataset_is_valid():
    cases = load_eval_dataset(__import__("pathlib").Path("eval/retrieval-quality-v1.json"))
    assert len(cases) == 3
    assert all(case.tenant_id == "acme" for case in cases)
