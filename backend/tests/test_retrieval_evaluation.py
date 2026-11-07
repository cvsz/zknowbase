import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.schemas import SourceCitation
from app.rag.evaluation import RetrievalEvalCase, evaluate_rankings, load_eval_dataset
from app.rag.hybrid import rerank_hybrid
from app.rag.service import RAGService
from scripts.evaluate_retrieval import _dense_production_candidates, _rerank_production_candidates


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


def test_dense_evaluator_matches_production_chunk_cutoff_before_document_metrics():
    first = _citation("doc-a", score=0.99)
    duplicate = first.model_copy(update={"chunk_id": "doc-a-1", "chunk_index": 1, "score": 0.98})
    outside_cutoff = _citation("doc-b", score=0.97)

    dense = _dense_production_candidates(
        [first, duplicate, outside_cutoff],
        top_k=2,
    )

    assert [citation.document_id for citation in dense] == ["doc-a", "doc-a"]


def test_hybrid_evaluator_expands_bounded_dense_prefix_for_unique_documents():
    first = _citation("doc-a", score=0.99).model_copy(update={"text": "policy policy"})
    duplicate = first.model_copy(update={"chunk_id": "doc-a-1", "chunk_index": 1, "score": 0.98})
    second = _citation("doc-b", score=0.97).model_copy(update={"text": "policy"})

    reranked = _rerank_production_candidates(
        "policy",
        [first, duplicate, second],
        top_k=2,
        dense_weight=1.0,
        candidate_multiplier=1,
    )

    assert [citation.document_id for citation in reranked] == ["doc-a", "doc-b"]


def test_hybrid_evaluator_ignores_candidates_outside_sufficient_production_prefix():
    first = _citation("doc-a", score=0.99).model_copy(update={"text": "policy"})
    second = _citation("doc-b", score=0.98).model_copy(update={"text": "policy"})
    outside_prefix = _citation("doc-c", score=0.97).model_copy(update={"text": "policy policy policy"})

    reranked = _rerank_production_candidates(
        "policy",
        [first, second, outside_prefix],
        top_k=2,
        dense_weight=0.0,
        candidate_multiplier=1,
    )

    assert [citation.document_id for citation in reranked] == ["doc-a", "doc-b"]


def test_hybrid_document_level_cutoff_skips_duplicate_chunks():
    first = _citation("doc-a", score=0.99).model_copy(update={"text": "policy policy"})
    duplicate = first.model_copy(update={"chunk_id": "doc-a-1", "chunk_index": 1, "score": 0.98})
    second = _citation("doc-b", score=0.97).model_copy(update={"text": "policy"})

    reranked = rerank_hybrid(
        "policy",
        [first, duplicate, second],
        2,
        dense_weight=1.0,
        document_level_cutoff=True,
    )

    assert [citation.document_id for citation in reranked] == ["doc-a", "doc-b"]


@pytest.mark.asyncio
async def test_hybrid_service_adaptively_overfetches_until_top_k_unique_documents():
    first = _citation("doc-a", score=0.99).model_copy(update={"text": "policy policy"})
    duplicate = first.model_copy(update={"chunk_id": "doc-a-1", "chunk_index": 1, "score": 0.98})
    second = _citation("doc-b", score=0.97).model_copy(update={"text": "policy"})

    service = RAGService.__new__(RAGService)
    service.settings = SimpleNamespace(
        embedding_provider="ollama",
        retrieval_mode="hybrid",
        hybrid_candidate_multiplier=1,
        hybrid_dense_weight=1.0,
    )
    service.providers = SimpleNamespace(embed=AsyncMock(return_value=[[0.1]]))
    service.vectors = SimpleNamespace(
        search=AsyncMock(side_effect=[[first, duplicate], [first, duplicate, second]])
    )

    result = await service.search("acme", "policy", 2)

    assert [citation.document_id for citation in result] == ["doc-a", "doc-b"]
    assert [call.args[2] for call in service.vectors.search.await_args_list] == [2, 4]


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
