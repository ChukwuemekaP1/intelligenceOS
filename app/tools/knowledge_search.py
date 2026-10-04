"""Knowledge search tool integrating with Phase 3 multi-tenant retrieval."""

from typing import Any

from pydantic import BaseModel, Field

from app.rag.retrieval.service import RetrievalService
from app.tools.base import BaseTool, ToolExecutionContext, ToolResult
from app.vectorstore.base import VectorStore


class KnowledgeSearchInput(BaseModel):
    """Input payload for workspace document search."""

    query: str = Field(
        ...,
        description="Semantic search query to look up relevant workspace documents.",
        max_length=500,
    )
    top_k: int = Field(
        default=4,
        ge=1,
        le=10,
        description="Maximum number of relevant knowledge chunks to retrieve.",
    )


class KnowledgeSearchTool(BaseTool):
    """Retrieves grounded document chunks strictly isolated by workspace context."""

    name = "knowledge_search"
    description = (
        "Searches the current workspace's ingested documents, PDFs, manuals, and knowledge base. "
        "Returns relevant textual passages with source references and page numbers. "
        "Use this whenever answering questions that require workspace knowledge."
    )
    input_schema = KnowledgeSearchInput
    required_permissions = []

    def __init__(
        self,
        retrieval_service: RetrievalService | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._vector_store = vector_store

    async def execute(
        self, input_data: KnowledgeSearchInput, context: ToolExecutionContext
    ) -> ToolResult:
        if not context.session:
            return ToolResult(
                success=False,
                error="Database session is required for knowledge search.",
                text_summary="Knowledge search error: no database session.",
            )

        # Enforce workspace isolation directly from authenticated context
        workspace_id = context.workspace_id

        # Initialize retrieval service with bound session and vector store
        service = self._retrieval_service or RetrievalService(
            session=context.session,
            vector_store=self._vector_store,
        )

        try:
            candidates = await service.retrieve(
                workspace_id=workspace_id,
                query=input_data.query,
                top_k=input_data.top_k,
            )

            if not candidates:
                return ToolResult(
                    success=True,
                    data={"query": input_data.query, "chunks_found": 0, "results": []},
                    text_summary=(
                        f"No relevant documents found in workspace for query: '{input_data.query}'."
                    ),
                )

            structured_results: list[dict[str, Any]] = []
            summary_lines: list[str] = [
                f"Retrieved {len(candidates)} relevant chunks for query '{input_data.query}':"
            ]

            for idx, cand in enumerate(candidates, start=1):
                page_str = f"Page {cand.page_number}" if cand.page_number else "Page N/A"
                source_str = cand.source_name or "Unknown Document"
                snippet = cand.content.strip().replace("\n", " ")
                if len(snippet) > 350:
                    snippet = snippet[:347] + "..."

                structured_results.append(
                    {
                        "doc_index": idx,
                        "chunk_id": str(cand.id),
                        "source_name": source_str,
                        "page_number": cand.page_number,
                        "chunk_index": cand.chunk_index,
                        "score": round(cand.score, 4),
                        "content": cand.content,
                    }
                )

                summary_lines.append(
                    f"[{idx}] Source: {source_str} ({page_str}, Chunk {cand.chunk_index})\n"
                    f"Content: {snippet}"
                )

            return ToolResult(
                success=True,
                data={
                    "query": input_data.query,
                    "chunks_found": len(candidates),
                    "results": structured_results,
                },
                text_summary="\n\n".join(summary_lines),
            )

        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Knowledge retrieval failed: {exc}",
                text_summary=f"Knowledge search error: {exc}",
            )
