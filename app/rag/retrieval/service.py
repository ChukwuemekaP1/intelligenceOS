"""Retrieval factory and service orchestration."""

import uuid
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.providers.embedding.base import EmbeddingProvider
from app.providers.embedding.factory import get_embedding_provider
from app.rag.retrieval.base import BaseRetriever
from app.rag.retrieval.hybrid import HybridRetriever
from app.rag.retrieval.lexical import LexicalRetriever
from app.rag.retrieval.semantic import SemanticRetriever
from app.schemas.rag import RetrievedChunk
from app.vectorstore.base import VectorStore
from app.vectorstore.factory import get_vector_store


class RetrievalService:
    """Unified retrieval service wrapping underlying vector and lexical search strategies."""

    def __init__(
        self,
        session: AsyncSession,
        vector_store: VectorStore | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.vector_store = vector_store or get_vector_store(self.settings)
        self.embedding_provider = embedding_provider or get_embedding_provider(self.settings)

    def build_retriever(
        self,
        mode: Literal["semantic", "hybrid"] | None = None,
    ) -> BaseRetriever:
        """Instantiates the requested retriever strategy."""
        selected_mode = mode or self.settings.RAG_RETRIEVAL_MODE

        semantic = SemanticRetriever(
            vector_store=self.vector_store,
            embedding_provider=self.embedding_provider,
            session=self.session,
        )

        if selected_mode == "semantic":
            return semantic

        lexical = LexicalRetriever(session=self.session)
        return HybridRetriever(
            semantic_retriever=semantic,
            lexical_retriever=lexical,
        )

    async def retrieve(
        self,
        workspace_id: uuid.UUID,
        query: str,
        top_k: int = 20,
        similarity_threshold: float | None = None,
        mode: Literal["semantic", "hybrid"] | None = None,
        source_ids: list[uuid.UUID] | None = None,
    ) -> list[RetrievedChunk]:
        """Executes retrieval with strict workspace filtering and optional source scope."""
        retriever = self.build_retriever(mode=mode)
        return await retriever.retrieve(
            workspace_id=workspace_id,
            query=query,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            source_ids=source_ids,
        )
