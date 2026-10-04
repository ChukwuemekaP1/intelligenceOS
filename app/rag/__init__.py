"""IntelligenceOS Grounded RAG Intelligence Layer."""

from app.rag.citations.generator import CitationGenerator
from app.rag.context.builder import BuiltContext, ContextBuilder
from app.rag.evaluation_hooks import CandidateEvalRecord, RAGEvaluationPayload
from app.rag.pipeline import RAGExecutionResult, RAGPipeline
from app.rag.prompts import (
    INSUFFICIENT_EVIDENCE_PHRASE,
    RAG_SYSTEM_INSTRUCTION,
    build_rag_user_prompt,
)
from app.rag.reranking.base import BaseReranker
from app.rag.reranking.factory import get_reranker
from app.rag.retrieval.base import BaseRetriever
from app.rag.retrieval.service import RetrievalService

__all__ = [
    "BaseRetriever",
    "RetrievalService",
    "BaseReranker",
    "get_reranker",
    "ContextBuilder",
    "BuiltContext",
    "CitationGenerator",
    "RAGPipeline",
    "RAGExecutionResult",
    "RAGEvaluationPayload",
    "CandidateEvalRecord",
    "RAG_SYSTEM_INSTRUCTION",
    "INSUFFICIENT_EVIDENCE_PHRASE",
    "build_rag_user_prompt",
]
