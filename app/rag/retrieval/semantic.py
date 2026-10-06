"""Semantic dense vector retriever implementation."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.source import Source
from app.providers.embedding.base import EmbeddingProvider
from app.rag.retrieval.base import BaseRetriever
from app.schemas.rag import RetrievedChunk
from app.vectorstore.base import VectorStore

logger = get_logger("app.rag.retrieval.semantic")


class SemanticRetriever(BaseRetriever):
    """Dense vector retriever using embedding provider and vector store."""

    def __init__(
        self,
        vector_store: VectorStore,
        embedding_provider: EmbeddingProvider,
        session: AsyncSession | None = None,
    ) -> None:
        self.vector_store = vector_store
        self.embedding_provider = embedding_provider
        self.session = session

    async def retrieve(
        self,
        workspace_id: uuid.UUID,
        query: str,
        top_k: int = 20,
        similarity_threshold: float | None = None,
        source_ids: list[uuid.UUID] | None = None,
    ) -> list[RetrievedChunk]:
        if not query.strip():
            return []

        # 1. Generate query embedding vector
        try:
            query_vector = await self.embedding_provider.embed_query(query)
        except Exception as exc:
            logger.error(
                f"Failed to generate embedding for query in workspace {workspace_id}: {exc}"
            )
            raise

        # 2. Query vector store with mandatory workspace filter and optional source filter
        search_results = await self.vector_store.search(
            workspace_id=workspace_id,
            query_vector=query_vector,
            limit=top_k,
            score_threshold=similarity_threshold,
            source_ids=source_ids,
        )

        if not search_results:
            return []

        # 3. Resolve source names from PostgreSQL if session available
        source_names: dict[uuid.UUID, str] = {}
        if self.session is not None:
            source_ids = set()
            for r in search_results:
                s_id_raw = r.payload.get("source_id")
                if s_id_raw:
                    try:
                        source_ids.add(uuid.UUID(str(s_id_raw)))
                    except ValueError:
                        pass
            if source_ids:
                stmt = select(Source.id, Source.name).where(
                    Source.id.in_(source_ids),
                    Source.workspace_id == workspace_id,
                )
                res = await self.session.execute(stmt)
                for s_id, s_name in res.fetchall():
                    source_names[s_id] = s_name

        # 4. Map to canonical RetrievedChunk models
        candidates: list[RetrievedChunk] = []
        for r in search_results:
            payload = r.payload or {}
            chunk_id = r.id
            if "chunk_id" in payload:
                try:
                    chunk_id = uuid.UUID(str(payload["chunk_id"]))
                except ValueError:
                    chunk_id = r.id

            s_id = uuid.UUID(str(payload.get("source_id", uuid.uuid4())))
            doc_id = uuid.UUID(str(payload.get("document_id", uuid.uuid4())))
            ver_id = uuid.UUID(str(payload.get("document_version_id", uuid.uuid4())))
            s_name = (
                source_names.get(s_id)
                or payload.get("source_name")
                or payload.get("title")
                or payload.get("name")
                or "Unknown Source"
            )

            raw_page = payload.get("page_number")
            page_num = int(raw_page) if raw_page is not None else None

            candidates.append(
                RetrievedChunk(
                    id=chunk_id,
                    chunk_index=int(payload.get("chunk_index", 0)),
                    workspace_id=workspace_id,
                    source_id=s_id,
                    source_name=s_name,
                    source_type=str(payload.get("source_type", "document")),
                    document_id=doc_id,
                    document_version_id=ver_id,
                    version_number=payload.get("version_number", 1),
                    page_number=page_num,
                    content=str(payload.get("text", "")),
                    score=r.score,
                    metadata=payload,
                )
            )

        return candidates
