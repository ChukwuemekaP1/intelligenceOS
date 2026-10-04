"""Context construction component for Grounded RAG.

Formats retrieved candidate chunks into predictable, injection-resistant context blocks
while enforcing strict token and character bounds.
"""

from pydantic import BaseModel, Field

from app.schemas.rag import RetrievedChunk


class BuiltContext(BaseModel):
    """Result of context construction."""

    formatted_context: str = Field(
        description="Structured context string formatted for LLM consumption"
    )
    included_chunks: list[RetrievedChunk] = Field(
        default_factory=list, description="Ordered candidate chunks that fit within budget"
    )
    total_characters: int = Field(description="Total character length of the built context")
    token_count_estimate: int = Field(description="Approximate token count of context")
    truncated: bool = Field(description="True if some candidate chunks were excluded due to budget")


class ContextBuilder:
    """Constructs structured, traceable context payloads from retrieved chunks."""

    def __init__(self, max_context_chars: int = 16000) -> None:
        self.max_context_chars = max_context_chars

    def build_context(
        self,
        candidates: list[RetrievedChunk],
        max_context_chars: int | None = None,
    ) -> BuiltContext:
        budget = max_context_chars or self.max_context_chars

        if not candidates:
            empty_msg = (
                "<context>\n  No relevant documents found in workspace knowledge base.\n</context>"
            )
            return BuiltContext(
                formatted_context=empty_msg,
                included_chunks=[],
                total_characters=0,
                token_count_estimate=0,
                truncated=False,
            )

        included_chunks: list[RetrievedChunk] = []
        seen_ids: set = set()
        accumulated_chars = 0
        truncated = False
        doc_blocks: list[str] = []

        for idx, chunk in enumerate(candidates, start=1):
            if chunk.id in seen_ids:
                continue
            seen_ids.add(chunk.id)

            p_val = chunk.page_number
            page_info = f"page='{p_val}'" if p_val is not None else "page='N/A'"
            source_info = f"source_name='{chunk.source_name}' source_type='{chunk.source_type}'"
            version_info = f"version='{chunk.version_number or 1}'"
            ids_info = (
                f"source_id='{chunk.source_id}' doc_id='{chunk.document_id}' chunk_id='{chunk.id}'"
            )

            # Sanitize content against delimiter hijacking
            sanitized_content = (
                chunk.content.replace("[UNTRUSTED_DOCUMENT_CONTENT_END]", "")
                .replace("[UNTRUSTED_DOCUMENT_CONTENT_START]", "")
                .strip()
            )

            doc_block = (
                f"  <document index='{idx}' {source_info} {page_info} {version_info} {ids_info}>\n"
                f"    [UNTRUSTED_DOCUMENT_CONTENT_START]\n"
                f"    {sanitized_content}\n"
                f"    [UNTRUSTED_DOCUMENT_CONTENT_END]\n"
                f"  </document>"
            )

            block_len = len(doc_block)
            if accumulated_chars + block_len > budget and included_chunks:
                truncated = True
                break

            doc_blocks.append(doc_block)
            included_chunks.append(chunk)
            accumulated_chars += block_len

        formatted_context = "<context>\n" + "\n".join(doc_blocks) + "\n</context>"

        return BuiltContext(
            formatted_context=formatted_context,
            included_chunks=included_chunks,
            total_characters=len(formatted_context),
            token_count_estimate=max(len(formatted_context) // 4, 1),
            truncated=truncated,
        )
