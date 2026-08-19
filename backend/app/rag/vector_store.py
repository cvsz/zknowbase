from uuid import uuid4

from qdrant_client import AsyncQdrantClient, models

from app.core.config import Settings
from app.models.schemas import SourceCitation


class VectorStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncQdrantClient(url=settings.qdrant_url)

    async def ensure_collection(self, vector_size: int) -> None:
        exists = await self.client.collection_exists(self.settings.qdrant_collection)
        if not exists:
            await self.client.create_collection(
                collection_name=self.settings.qdrant_collection,
                vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
            )

    async def upsert_chunks(self, document_id: str, document_name: str, source_uri: str | None,
                            chunks: list[str], vectors: list[list[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks/vectors length mismatch")
        if not vectors:
            return
        await self.ensure_collection(len(vectors[0]))
        points = []
        for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            chunk_id = str(uuid4())
            points.append(models.PointStruct(
                id=chunk_id,
                vector=vector,
                payload={"document_id": document_id, "document_name": document_name,
                         "source_uri": source_uri, "chunk_id": chunk_id,
                         "chunk_index": index, "text": chunk},
            ))
        await self.client.upsert(collection_name=self.settings.qdrant_collection, points=points, wait=True)

    async def search(self, vector: list[float], top_k: int, filters: dict | None = None) -> list[SourceCitation]:
        if not await self.client.collection_exists(self.settings.qdrant_collection):
            return []
        conditions = []
        for key, value in (filters or {}).items():
            if key not in {"document_id", "source_uri", "document_name"}:
                continue
            conditions.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))
        query_filter = models.Filter(must=conditions) if conditions else None
        response = await self.client.query_points(
            collection_name=self.settings.qdrant_collection,
            query=vector,
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )
        results = []
        for point in response.points:
            payload = point.payload or {}
            results.append(SourceCitation(
                document_id=str(payload.get("document_id", "")),
                document_name=str(payload.get("document_name", "unknown")),
                chunk_id=str(payload.get("chunk_id", point.id)),
                chunk_index=int(payload.get("chunk_index", 0)),
                score=float(point.score),
                text=str(payload.get("text", "")),
                source_uri=payload.get("source_uri"),
            ))
        return results

    async def delete_document(self, document_id: str) -> None:
        if not await self.client.collection_exists(self.settings.qdrant_collection):
            return
        await self.client.delete(
            collection_name=self.settings.qdrant_collection,
            points_selector=models.FilterSelector(filter=models.Filter(must=[
                models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))
            ])),
            wait=True,
        )

    async def healthy(self) -> bool:
        try:
            await self.client.get_collections()
            return True
        except Exception:
            return False
