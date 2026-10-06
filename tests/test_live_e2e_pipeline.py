"""Live end-to-end acceptance test for IntelligenceOS ingestion and RAG pipeline.

Tests against REAL live infrastructure:
- PostgreSQL (live)
- Redis Cloud (live)
- Supabase Storage (live)
- Qdrant Cloud (live)
- Gemini Embeddings (live)
- Gemini LLM (live)
"""

import asyncio
import io
import uuid
from pypdf import PdfWriter

from app.core.config import get_settings
from app.database.session import async_session_factory
from app.models.source import ProcessingStatus, Source
from app.models.user import User
from app.models.workspace import Workspace
from app.queue.job_queue import get_job_queue
from app.rag.pipeline import RAGPipeline
from app.rag.prompts import INSUFFICIENT_EVIDENCE_PHRASE
from app.services.conversation_service import ConversationService
from app.services.ingestion_service import IngestionService
from app.vectorstore.factory import get_vector_store
from app.worker import process_next_job


def make_test_pdf(text: str) -> bytes:
    """Generates a valid single-page PDF with text using reportlab or minimal PDF bytes."""
    # A standard valid minimal PDF containing text
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length " + str(len(text) + 40).encode("ascii") + b">>\nstream\n"
        b"BT /F1 12 Tf 100 700 Td (" + text.encode("ascii", "replace") + b") Tj ET\nendstream\nendobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\n0000000266 00000 n\n0000000360 00000 n\n"
        b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n441\n%%EOF\n"
    )
    return pdf_content


async def run_live_tests():
    settings = get_settings()
    print("=" * 60)
    print("STARTING LIVE END-TO-END ACCEPTANCE TESTS")
    print(f"Environment: {settings.ENVIRONMENT}")
    print(f"Redis URL: {settings.REDIS_URL.split('@')[-1]}")
    print(f"Qdrant URL: {settings.QDRANT_URL}")
    print(f"Embedding Model: {settings.GEMINI_EMBEDDING_MODEL}")
    print(f"LLM Model: {settings.GEMINI_MODEL}")
    print("=" * 60)

    queue = get_job_queue(settings)
    # Drain any stale jobs left over in Redis
    print("[SETUP] Draining any stale jobs from Redis queue...")
    drained_count = 0
    while True:
        stale_job = await queue.dequeue(timeout=1)
        if not stale_job:
            break
        drained_count += 1
    print(f"[SETUP] Drained {drained_count} stale job(s) from Redis.")

    vstore = get_vector_store(settings)
    await vstore.ensure_collection()

    async with async_session_factory() as session:
        # Create a dedicated test workspace
        workspace_id = uuid.uuid4()
        workspace = Workspace(
            id=workspace_id,
            name=f"E2E Test Workspace {uuid.uuid4().hex[:6]}",
        )
        session.add(workspace)
        await session.commit()
        print(f"\n[SETUP] Created test workspace: {workspace_id}")

    # =========================================================================
    # Test 1: Real PDF Ingestion
    # =========================================================================
    print("\n--- TEST 1: Real PDF Ingestion ---")
    pdf_text = "IntelligenceOS is an enterprise AI platform that uses Redis for background queues and Qdrant for vector retrieval."
    pdf_bytes = make_test_pdf(pdf_text)

    async with async_session_factory() as session:
        source_pdf = await IngestionService.create_file_source(
            session=session,
            workspace_id=workspace_id,
            filename="intelligenceos_architecture.pdf",
            content=pdf_bytes,
            content_type="application/pdf",
        )
        pdf_source_id = source_pdf.id
        print(f"[TEST 1] Source created in DB: id={pdf_source_id}, status={source_pdf.status}")

    # Worker processes the job from Redis
    print("[TEST 1] Running worker process_next_job()...")
    processed = await process_next_job()
    assert processed is True, "Worker should have dequeued and processed the PDF job"

    # Verify source status in DB
    async with async_session_factory() as session:
        source = await IngestionService.get_source(session, pdf_source_id, workspace_id)
        assert source is not None
        print(f"[TEST 1] Post-processing Source status: {source.status}")
        assert source.status == ProcessingStatus.COMPLETED.value, f"Expected COMPLETED, got {source.status}, error={source.metadata_.get('error')}"

    # Verify vectors exist in Qdrant
    point_count = await vstore.count_points(workspace_id)
    print(f"[TEST 1] Qdrant points in workspace: {point_count}")
    assert point_count > 0, "Vectors must exist in Qdrant after PDF ingestion"
    print("[TEST 1] SUCCESS: PDF ingested, chunks embedded, Qdrant vectors created, status COMPLETED.")

    # =========================================================================
    # Test 2: Real URL Ingestion
    # =========================================================================
    print("\n--- TEST 2: Real URL Ingestion ---")
    test_url = "https://example.com"

    async with async_session_factory() as session:
        source_url = await IngestionService.create_url_source(
            session=session,
            workspace_id=workspace_id,
            url=test_url,
            title="Example Domain Test",
        )
        url_source_id = source_url.id
        print(f"[TEST 2] URL Source created in DB: id={url_source_id}, status={source_url.status}")

    # Worker processes the URL job from Redis
    print("[TEST 2] Running worker process_next_job()...")
    processed_url = await process_next_job()
    assert processed_url is True, "Worker should have dequeued and processed the URL job"

    # Verify source status in DB
    async with async_session_factory() as session:
        source = await IngestionService.get_source(session, url_source_id, workspace_id)
        assert source is not None
        print(f"[TEST 2] Post-processing URL Source status: {source.status}")
        assert source.status == ProcessingStatus.COMPLETED.value, f"Expected COMPLETED, got {source.status}, error={source.metadata_.get('error')}"

    # Verify points count increased
    new_point_count = await vstore.count_points(workspace_id)
    print(f"[TEST 2] Qdrant points in workspace after URL: {new_point_count}")
    assert new_point_count > point_count, "URL ingestion must create new points in Qdrant"
    print("[TEST 2] SUCCESS: URL fetched, parsed, embedded, Qdrant vectors created, status COMPLETED.")

    # =========================================================================
    # Test 3: RAG Retrieval and Generation
    # =========================================================================
    print("\n--- TEST 3: RAG Retrieval and Generation ---")
    async with async_session_factory() as session:
        conv = await ConversationService.create_conversation(session, workspace_id)
        print(f"[TEST 3] Created conversation: {conv.id}")

        rag = RAGPipeline(session=session)

        # 3a. Answerable question based on PDF content
        question = "What does IntelligenceOS use Redis for?"
        print(f"[TEST 3a] Asking: '{question}'")
        result = await rag.execute(workspace_id=workspace_id, query=question)

        print(f"[TEST 3a] Answer: {result.answer}")
        print(f"[TEST 3a] Chunks included: {len(result.included_chunks)}")
        print(f"[TEST 3a] Citations: {[c.model_dump() for c in result.citations]}")
        print(f"[TEST 3a] Retrieval mode: {result.retrieval_mode_used}")
        print(f"[TEST 3a] Insufficient knowledge: {result.insufficient_knowledge}")

        assert result.insufficient_knowledge is False, "Should have retrieved knowledge"
        assert len(result.included_chunks) > 0, "Should include retrieved chunks"
        assert "redis" in result.answer.lower(), "Answer should mention Redis"
        assert len(result.answer) > 20, "Answer should be a natural sentence"

        # 3b. Question on knowledge NOT present in the workspace
        unrelated_question = "What is the capital of Mars and the chemical composition of lunar cheese?"
        print(f"\n[TEST 3b] Asking unrelated: '{unrelated_question}'")
        unrelated_result = await rag.execute(workspace_id=workspace_id, query=unrelated_question)

        print(f"[TEST 3b] Answer: {unrelated_result.answer}")
        print(f"[TEST 3b] Insufficient knowledge: {unrelated_result.insufficient_knowledge}")
        assert INSUFFICIENT_EVIDENCE_PHRASE.lower() in unrelated_result.answer.lower() or unrelated_result.insufficient_knowledge is True, (
            "Pipeline must return insufficient evidence response for unrelated queries"
        )
        print("[TEST 3] SUCCESS: RAG retrieves context, generates grounded natural answer with citations, and rejects unsupported queries.")

    # =========================================================================
    # Test 4: Failure Handling & Worker Survival
    # =========================================================================
    print("\n--- TEST 4: Failure Handling & Worker Survival ---")
    # 4a. Corrupted / empty PDF
    corrupt_pdf_bytes = b"This is completely corrupt not a real pdf"
    async with async_session_factory() as session:
        bad_source = await IngestionService.create_file_source(
            session=session,
            workspace_id=workspace_id,
            filename="corrupt.pdf",
            content=corrupt_pdf_bytes,
            content_type="application/pdf",
        )
        bad_source_id = bad_source.id
        print(f"[TEST 4a] Created corrupt PDF source: id={bad_source_id}")

    # Process bad PDF
    print("[TEST 4a] Running worker process_next_job() on corrupt PDF...")
    processed_bad = await process_next_job()
    assert processed_bad is True

    # Verify status is FAILED, NOT stuck in PROCESSING
    async with async_session_factory() as session:
        bad_source_db = await IngestionService.get_source(session, bad_source_id, workspace_id)
        assert bad_source_db is not None
        print(f"[TEST 4a] Corrupt PDF Source status: {bad_source_db.status}, error={bad_source_db.metadata_.get('error')}")
        assert bad_source_db.status == ProcessingStatus.FAILED.value, f"Expected FAILED, got {bad_source_db.status}"
        assert bad_source_db.metadata_.get("error") is not None, "Error details must be saved in metadata"

    # 4b. Worker survival: Worker must be able to process another valid job right after failure!
    print("\n[TEST 4b] Testing worker survival with subsequent valid job...")
    valid_pdf_2 = make_test_pdf("Worker survival test document successfully processed after failure.")
    async with async_session_factory() as session:
        survive_source = await IngestionService.create_file_source(
            session=session,
            workspace_id=workspace_id,
            filename="survival_test.pdf",
            content=valid_pdf_2,
            content_type="application/pdf",
        )
        survive_id = survive_source.id

    processed_survive = await process_next_job()
    assert processed_survive is True

    async with async_session_factory() as session:
        survive_source_db = await IngestionService.get_source(session, survive_id, workspace_id)
        assert survive_source_db is not None
        print(f"[TEST 4b] Subsequent Source status: {survive_source_db.status}")
        assert survive_source_db.status == ProcessingStatus.COMPLETED.value
    print("[TEST 4] SUCCESS: Failed jobs transition to FAILED cleanly and worker survives to process subsequent jobs.")

    print("\n" + "=" * 60)
    print("ALL LIVE ACCEPTANCE TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_live_tests())
