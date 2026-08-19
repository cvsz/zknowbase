from app.models.schemas import SourceCitation
from app.rag.hybrid import bm25_scores, rerank_hybrid


def citation(chunk_id: str, text: str, score: float) -> SourceCitation:
    return SourceCitation(
        document_id="doc",
        document_name="policy.md",
        chunk_id=chunk_id,
        chunk_index=0,
        score=score,
        text=text,
        source_uri=None,
    )


def test_bm25_prefers_exact_lexical_match():
    scores = bm25_scores("parental leave", ["travel expense policy", "parental leave is sixteen weeks"])
    assert scores[1] > scores[0]


def test_hybrid_rerank_can_promote_lexical_match():
    dense_only = citation("dense", "travel and general benefits", 0.90)
    exact = citation("exact", "parental leave is sixteen weeks", 0.70)
    ranked = rerank_hybrid("parental leave", [dense_only, exact], 2, dense_weight=0.5)
    assert ranked[0].chunk_id == "exact"


def test_hybrid_rerank_respects_top_k_and_empty_inputs():
    candidates = [citation(str(index), f"policy {index}", 0.8 - index * 0.1) for index in range(3)]
    assert len(rerank_hybrid("policy", candidates, 2)) == 2
    assert rerank_hybrid("policy", [], 2) == []
    assert rerank_hybrid("policy", candidates, 0) == []
