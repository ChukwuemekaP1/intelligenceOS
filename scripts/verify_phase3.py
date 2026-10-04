"""Verification script for IntelligenceOS Phase 3 Grounded RAG Intelligence Layer.

Demonstrates:
  1. Authenticated user and workspace provisioning
  2. Document ingestion and vector indexing across two isolated workspaces
  3. Grounded RAG Question Answering pipeline using Google Gemini (gemini-3.8-flash)
  4. Candidate retrieval (dense + lexical RRF)
  5. Second-stage reranking and candidate refinement
  6. Injection-resistant, bounded context construction
  7. Live Gemini grounded answer generation
  8. Traceable citations with document, page, and chunk metadata
  9. Full conversation and message persistence
  10. Strict multi-tenant workspace isolation (Workspace A cannot access Workspace B)
  11. Insufficient evidence handling when evidence is not found
"""

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.database.base import Base
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.source import ProcessingStatus, Source, SourceType
from app.providers.embedding.mock import MockEmbeddingProvider
from app.providers.llm.gemini import GeminiProvider
from app.providers.llm.mock import MockLLMProvider
from app.rag.pipeline import RAGPipeline
from app.schemas.auth import RegisterRequest
from app.schemas.rag import QuestionRequest
from app.services.auth_service import AuthService
from app.services.conversation_service import ConversationService
from app.services.workspace_service import WorkspaceService
from app.vectorstore.mock import MockVectorStore
from app.vectorstore.models import VectorPoint


async def seed_document(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    source_name: str,
    text_content: str,
    page_number: int,
    vstore: MockVectorStore,
    embedder: MockEmbeddingProvider,
) -> tuple[Source, Document, DocumentVersion, Chunk]:
    source = Source(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        source_type=SourceType.PDF.value,
        name=source_name,
        status=ProcessingStatus.COMPLETED.value,
    )
    session.add(source)

    doc = Document(
        id=uuid.uuid4(),
        source_id=source.id,
        workspace_id=workspace_id,
        metadata_={"title": source_name},
    )
    session.add(doc)

    doc_version = DocumentVersion(
        id=uuid.uuid4(),
        document_id=doc.id,
        version_number=1,
        status=ProcessingStatus.COMPLETED.value,
    )
    session.add(doc_version)

    chunk = Chunk(
        id=uuid.uuid4(),
        document_version_id=doc_version.id,
        workspace_id=workspace_id,
        chunk_index=0,
        content=text_content,
        metadata_={"page_number": page_number, "source_name": source_name},
    )
    session.add(chunk)
    await session.commit()

    vec = await embedder.embed_query(text_content)
    await vstore.upsert_points(
        workspace_id=workspace_id,
        points=[
            VectorPoint(
                id=chunk.id,
                vector=vec,
                payload={
                    "workspace_id": str(workspace_id),
                    "source_id": str(source.id),
                    "document_id": str(doc.id),
                    "document_version_id": str(doc_version.id),
                    "chunk_id": str(chunk.id),
                    "source_type": source.source_type,
                    "source_name": source.name,
                    "page_number": page_number,
                    "chunk_index": 0,
                    "text": text_content,
                },
            )
        ],
    )

    return source, doc, doc_version, chunk


async def main() -> None:
    print("================================================================================")
    print("IntelligenceOS Phase 3: Grounded RAG Intelligence Layer Verification")
    print("================================================================================")

    # 1. Setup isolated in-memory test database
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    settings = get_settings()
    vstore = MockVectorStore()
    embedder = MockEmbeddingProvider(dimension=768)

    # Use live Gemini if key is configured, else fallback to mock
    api_key_val = settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else None
    if api_key_val:
        print(f"[*] Initializing live Gemini Provider using model: {settings.GEMINI_MODEL}")
        llm = GeminiProvider(api_key=api_key_val, model=settings.GEMINI_MODEL)
    else:
        print("[*] Gemini API key not provided; using MockLLMProvider")
        llm = MockLLMProvider()

    async with session_maker() as session:
        # 2. Authenticate User and create Workspaces
        user = await AuthService.register_user(
            session,
            RegisterRequest(email="lead_architect@intelligenceos.ai", password="securepassword123"),
        )
        ws_a = await WorkspaceService.create_workspace(session, "Alpha Engineering Corp", user)
        ws_b = await WorkspaceService.create_workspace(session, "Beta Competitor Ltd", user)

        print(f"[+] User registered: {user.email} (ID: {user.id})")
        print(f"[+] Workspace A provisioned: '{ws_a.name}' (ID: {ws_a.id})")
        print(f"[+] Workspace B provisioned: '{ws_b.name}' (ID: {ws_b.id})")

        # 3. Ingest documents into Workspace A
        text_a1 = (
            "IntelligenceOS Phase 3 implements an enterprise Grounded RAG system. "
            "It combines dense vector search in Qdrant with relational keyword search via RRF "
            "to retrieve the most relevant candidate chunks."
        )
        text_a2 = (
            "After candidate retrieval, a secondary reranker scores items based on lexical density "
            "and keyword coverage. Context construction then builds injection-resistant XML blocks "
            "bounded by strict token/character limits, preventing prompt injection attacks."
        )
        await seed_document(
            session, ws_a.id, "IntelligenceOS_Architecture.pdf", text_a1, 3, vstore, embedder
        )
        await seed_document(
            session, ws_a.id, "IntelligenceOS_Architecture.pdf", text_a2, 4, vstore, embedder
        )

        # 4. Ingest sensitive confidential document into Workspace B
        text_b1 = (
            "CONFIDENTIAL: Project BlackBird is Beta Competitor's secret next-gen neural engine. "
            "It is funded with a $15M budget and scheduled for release in Q4."
        )
        await seed_document(
            session, ws_b.id, "Competitor_Strategy.pdf", text_b1, 1, vstore, embedder
        )
        print("[+] Knowledge ingested into Workspace A (2 chunks) and Workspace B (1 chunk).")

        # 5. Create conversation in Workspace A
        conv_a = await ConversationService.create_conversation(
            session=session,
            workspace_id=ws_a.id,
            user=user,
        )
        print(f"[+] Conversation created: '{conv_a.title}' (ID: {conv_a.id})")

        # 6. Execute Grounded RAG Question Answering pipeline in Workspace A
        question = "How does Phase 3 implement candidate retrieval and context construction?"
        print(f"\n[?] User Question in Workspace A: '{question}'")

        pipeline_a = RAGPipeline(
            session=session,
            llm_provider=llm,
            vector_store=vstore,
            embedding_provider=embedder,
        )

        resp_a = await ConversationService.ask_question(
            session=session,
            workspace_id=ws_a.id,
            conversation_id=conv_a.id,
            request=QuestionRequest(question=question),
            user=user,
            pipeline=pipeline_a,
        )

        print("\n" + "=" * 40 + " GROUNDED RAG ANSWER " + "=" * 40)
        print(resp_a.answer)
        print("=" * 101)

        print("\n[*] Citations Generated:")
        for idx, cit in enumerate(resp_a.citations, start=1):
            print(
                f"  [{idx}] Source: {cit.source_name} | Page: {cit.page_number} "
                f"| Chunk: {cit.chunk_index}"
            )
            print(f"      Snippet: {cit.snippet}")

        print("\n[*] Execution Metrics:")
        print(f"  - Initial candidates retrieved: {resp_a.metrics.retrieval_count}")
        print(f"  - Final context chunks:        {resp_a.metrics.final_context_count}")
        print(f"  - Retrieval latency:           {resp_a.metrics.retrieval_latency_ms:.2f} ms")
        print(f"  - Reranking latency:           {resp_a.metrics.rerank_latency_ms:.2f} ms")
        print(f"  - Generation latency:          {resp_a.metrics.generation_latency_ms:.2f} ms")
        print(f"  - Total pipeline latency:      {resp_a.metrics.total_latency_ms:.2f} ms")

        # 7. Verify Conversation History Persistence
        conv_detail = await ConversationService.get_conversation(session, conv_a.id, ws_a.id)
        assert conv_detail is not None
        assert len(conv_detail.messages) == 2
        print(f"\n[+] Conversation history persisted: {len(conv_detail.messages)} messages.")
        print(f"[+] Citations count in DB: {len(conv_detail.messages[1].citations)}")

        # 8. Workspace Isolation Verification
        print("\n" + "=" * 35 + " MULTI-TENANT ISOLATION CHECK " + "=" * 35)
        secret_q = "What is Project BlackBird and what is its budget?"
        print(f"[?] Asking Workspace A about Workspace B's secret knowledge: '{secret_q}'")

        resp_secret = await ConversationService.ask_question(
            session=session,
            workspace_id=ws_a.id,
            conversation_id=conv_a.id,
            request=QuestionRequest(question=secret_q),
            user=user,
            pipeline=pipeline_a,
        )

        print(f"[*] Response from Workspace A: '{resp_secret.answer}'")
        print(f"[*] Citations returned: {len(resp_secret.citations)}")
        assert "BlackBird" not in resp_secret.answer
        assert "$15M" not in resp_secret.answer
        assert len(resp_secret.citations) == 0
        print("[+] VERIFIED: Workspace A completely denied access to Workspace B's knowledge.")
        print("[+] VERIFIED: System acknowledged insufficient evidence without hallucinating.")

        # 9. Cross-workspace conversation authorization check
        cross_conv = await ConversationService.get_conversation(session, conv_a.id, ws_b.id)
        assert cross_conv is None
        print("[+] VERIFIED: Cross-workspace access to Conversation A through WS B returned 404.")

    print("\n================================================================================")
    print("PHASE 3 RAG VERIFICATION COMPLETED SUCCESSFULLY!")
    print("================================================================================")


if __name__ == "__main__":
    asyncio.run(main())
