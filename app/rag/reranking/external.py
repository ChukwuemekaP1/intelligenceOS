"""External HTTP API reranker (e.g. Cohere or custom reranker service)."""

import httpx

from app.core.logging import get_logger
from app.rag.reranking.base import BaseReranker
from app.schemas.rag import RetrievedChunk

logger = get_logger("app.rag.reranking.external")


class ExternalReranker(BaseReranker):
    """Calls an external HTTP reranking endpoint, configured strictly via environment variables."""

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        model: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint or "https://api.cohere.com/v1/rerank"
        self.model = model or "rerank-english-v3.0"
        self.timeout = timeout

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int = 5,
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []

        if not self.api_key:
            logger.warning("External reranker API key not configured; falling back to passthrough.")
            return candidates[:top_k]

        payload = {
            "model": self.model,
            "query": query,
            "documents": [c.content for c in candidates],
            "top_n": top_k,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self.endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            results = data.get("results", [])
            reranked: list[RetrievedChunk] = []
            for item in results:
                idx = item.get("index")
                rel_score = float(item.get("relevance_score", 0.0))
                if idx is not None and 0 <= idx < len(candidates):
                    cand = candidates[idx]
                    reranked.append(cand.model_copy(update={"score": round(rel_score, 4)}))

            return reranked if reranked else candidates[:top_k]

        except Exception as exc:
            logger.warning(
                f"External reranker call failed ({exc}); safely falling back to candidate order."
            )
            return candidates[:top_k]
