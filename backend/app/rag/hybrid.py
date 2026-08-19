import math
import re
from collections import Counter

from app.models.schemas import SourceCitation

_TOKEN_RE = re.compile(r"[\w'-]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text)]


def bm25_scores(query: str, documents: list[str], *, k1: float = 1.5, b: float = 0.75) -> list[float]:
    """Compute dependency-free BM25 scores for a bounded candidate set."""
    if not documents:
        return []
    query_terms = set(tokenize(query))
    if not query_terms:
        return [0.0] * len(documents)

    tokenized = [tokenize(document) for document in documents]
    avgdl = sum(len(tokens) for tokens in tokenized) / len(tokenized) or 1.0
    document_frequency = Counter()
    for tokens in tokenized:
        document_frequency.update(set(tokens) & query_terms)

    total = len(documents)
    scores: list[float] = []
    for tokens in tokenized:
        frequencies = Counter(tokens)
        length = len(tokens)
        score = 0.0
        for term in query_terms:
            frequency = frequencies[term]
            if not frequency:
                continue
            df = document_frequency[term]
            idf = math.log(1.0 + (total - df + 0.5) / (df + 0.5))
            denominator = frequency + k1 * (1.0 - b + b * length / avgdl)
            score += idf * (frequency * (k1 + 1.0)) / denominator
        scores.append(score)
    return scores


def rerank_hybrid(query: str, candidates: list[SourceCitation], top_k: int, *, dense_weight: float = 0.65) -> list[SourceCitation]:
    """Fuse dense similarity with local BM25 over dense candidates.

    Candidate generation remains Qdrant-backed, so filters and collection boundaries
    stay authoritative. BM25 is computed locally and requires no paid/external service.
    """
    if not candidates or top_k <= 0:
        return []
    lexical = bm25_scores(query, [candidate.text for candidate in candidates])
    lexical_max = max(lexical, default=0.0)
    lexical_normalized = [score / lexical_max if lexical_max > 0 else 0.0 for score in lexical]
    lexical_weight = 1.0 - dense_weight
    ranked = sorted(
        zip(candidates, lexical_normalized, strict=True),
        key=lambda item: dense_weight * max(0.0, min(1.0, item[0].score)) + lexical_weight * item[1],
        reverse=True,
    )
    return [candidate for candidate, _ in ranked[:top_k]]
