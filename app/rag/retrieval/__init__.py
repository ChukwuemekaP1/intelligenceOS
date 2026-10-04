"""Retrieval module for Phase 3 Grounded RAG."""

from app.rag.retrieval.base import BaseRetriever
from app.rag.retrieval.hybrid import HybridRetriever
from app.rag.retrieval.lexical import LexicalRetriever
from app.rag.retrieval.semantic import SemanticRetriever
from app.rag.retrieval.service import RetrievalService

__all__ = [
    "BaseRetriever",
    "SemanticRetriever",
    "LexicalRetriever",
    "HybridRetriever",
    "RetrievalService",
]
