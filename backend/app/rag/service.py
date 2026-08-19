from collections.abc import AsyncIterator

from app.core.config import Settings
from app.models.schemas import QueryResponse, SourceCitation
from app.rag.hybrid import rerank_hybrid
from app.rag.providers import AIProviders
from app.rag.vector_store import VectorStore

SYSTEM_PROMPT = """You are the zknowbase grounded-answer engine.
Answer only from the supplied organizational context. If the context is insufficient, say so explicitly.
Do not invent policies, dates, requirements, or approvals. Cite sources inline using [S1], [S2], ... markers.
Prefer concise, operationally useful answers."""


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
        query_vector = (await self.providers.embed([query]))[0]
        if self.settings.retrieval_mode == "dense":
            return await self.vectors.search(tenant_id, query_vector, top_k, filters)
        candidate_limit = max(top_k, min(100, top_k * self.settings.hybrid_candidate_multiplier))
        candidates = await self.vectors.search(tenant_id, query_vector, candidate_limit, filters)
        return rerank_hybrid(
            query,
            candidates,
            top_k,
            dense_weight=self.settings.hybrid_dense_weight,
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
        sources = await self.search(tenant_id, question, top_k, filters)
        answer = await self.providers.complete(SYSTEM_PROMPT, self._prompt(question, sources))
        return QueryResponse(answer=answer, sources=sources)

    async def answer_stream(
        self,
        tenant_id: str,
        question: str,
        top_k: int,
        filters: dict | None = None,
    ) -> tuple[list[SourceCitation], AsyncIterator[str]]:
        sources = await self.search(tenant_id, question, top_k, filters)
        return sources, self.providers.stream(SYSTEM_PROMPT, self._prompt(question, sources))
