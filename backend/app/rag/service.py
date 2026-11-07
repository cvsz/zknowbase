import time
from collections.abc import AsyncIterator

from app.core.config import Settings
from app.models.schemas import QueryResponse, SourceCitation
from app.observability import (
    EMBEDDING_DURATION,
    LLM_DURATION,
    QUERY_DURATION,
    SEARCH_DURATION,
    timed,
    tracer,
)
from app.rag.hybrid import rerank_hybrid
from app.rag.providers import AIProviders
from app.rag.vector_store import VectorStore

SYSTEM_PROMPT = """You are the zknowbase grounded-answer engine.
Answer only from the supplied organizational context. If the context is insufficient, say so explicitly.
Do not invent policies, dates, requirements, or approvals. Cite sources inline using [S1], [S2], ... markers.
Prefer concise, operationally useful answers."""

_HYBRID_CANDIDATE_CEILING = 100


class RAGService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.providers = AIProviders(settings)
        self.vectors = VectorStore(settings)

    async def search(
        self,
        tenant_id: str,
        query: str,
        top_k: int,
        filters: dict | None = None,
    ) -> list[SourceCitation]:
        with tracer("zknowbase.rag").start_as_current_span("rag.search") as span, timed(SEARCH_DURATION):
            span.set_attribute("tenant.id", tenant_id)
            span.set_attribute("rag.top_k", top_k)
            with timed(
                EMBEDDING_DURATION,
                {"provider": self.settings.embedding_provider},
            ):
                query_vector = (await self.providers.embed([query]))[0]
            if self.settings.retrieval_mode == "dense":
                return await self.vectors.search(tenant_id, query_vector, top_k, filters)

            candidate_limit = max(
                top_k,
                min(
                    _HYBRID_CANDIDATE_CEILING,
                    top_k * self.settings.hybrid_candidate_multiplier,
                ),
            )
            while True:
                candidates = await self.vectors.search(
                    tenant_id, query_vector, candidate_limit, filters
                )
                reranked = rerank_hybrid(
                    query,
                    candidates,
                    top_k,
                    dense_weight=self.settings.hybrid_dense_weight,
                    document_level_cutoff=True,
                )
                if (
                    len(reranked) >= top_k
                    or len(candidates) < candidate_limit
                    or candidate_limit >= _HYBRID_CANDIDATE_CEILING
                ):
                    return reranked
                candidate_limit = min(
                    _HYBRID_CANDIDATE_CEILING,
                    max(candidate_limit + 1, candidate_limit * 2),
                )

    @staticmethod
    def _prompt(question: str, sources: list[SourceCitation]) -> str:
        context = "\n\n".join(
            f"[S{i}] document={s.document_name} chunk={s.chunk_index}\n{s.text}"
            for i, s in enumerate(sources, start=1)
        )
        return f"Context:\n{context or '(no relevant context found)'}\n\nQuestion: {question}\nAnswer:"

    async def answer(
        self,
        tenant_id: str,
        question: str,
        top_k: int,
        filters: dict | None = None,
    ) -> QueryResponse:
        with tracer("zknowbase.rag").start_as_current_span("rag.answer") as span, timed(QUERY_DURATION):
            span.set_attribute("tenant.id", tenant_id)
            sources = await self.search(tenant_id, question, top_k, filters)
            with timed(LLM_DURATION, {"provider": self.settings.llm_provider}):
                answer = await self.providers.complete(
                    SYSTEM_PROMPT, self._prompt(question, sources)
                )
            span.set_attribute("rag.source_count", len(sources))
            return QueryResponse(answer=answer, sources=sources)

    async def answer_stream(
        self,
        tenant_id: str,
        question: str,
        top_k: int,
        filters: dict | None = None,
    ) -> tuple[list[SourceCitation], AsyncIterator[str]]:
        sources = await self.search(tenant_id, question, top_k, filters)
        upstream = self.providers.stream(SYSTEM_PROMPT, self._prompt(question, sources))

        async def measured_stream() -> AsyncIterator[str]:
            started = time.perf_counter()
            with tracer("zknowbase.rag").start_as_current_span("rag.answer_stream") as span:
                span.set_attribute("tenant.id", tenant_id)
                span.set_attribute("rag.source_count", len(sources))
                try:
                    async for token in upstream:
                        yield token
                finally:
                    elapsed = time.perf_counter() - started
                    LLM_DURATION.labels(provider=self.settings.llm_provider).observe(elapsed)
                    QUERY_DURATION.observe(elapsed)

        return sources, measured_stream()
