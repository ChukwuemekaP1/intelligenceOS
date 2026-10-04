"""Pass-through reranker that preserves initial candidate ordering."""

from app.rag.reranking.base import BaseReranker
from app.schemas.rag import RetrievedChunk


class PassThroughReranker(BaseReranker):
    """Bypasses reranking by taking the top_k candidates in their current order."""

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        return candidates[:top_k]
