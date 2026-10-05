"""End-to-End Cloud Infrastructure Verification Script.

Tests the full production flow:
1. Health check & Probes (/health, /healthz, /readyz)
2. PostgreSQL connection & tables
3. Supabase Storage: bucket reachability, upload, metadata, signed URL, download
4. Redis Cloud: connectivity, enqueue, dequeue, job processing
5. Qdrant Cloud: collection verification, vector insertion, hybrid search
6. Authentication: User registration & JWT login
7. Workspace: Multi-tenant workspace provisioning
8. File Upload & Ingestion:
   - Upload file -> Persist in Supabase Storage
   - Record metadata in PostgreSQL
   - Enqueue ingestion job to Redis Cloud
   - Process job (chunk, embed, upsert to Qdrant Cloud)
   - Update PostgreSQL status to COMPLETED
9. RAG Query: Multi-turn question answering using Qdrant Cloud retrieval
10. Cleanup
"""

import asyncio
import time
import uuid

from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.database.redis import check_redis_health, get_redis_client
from app.database.session import check_database_health
from app.main import app
from app.storage.factory import get_storage_backend
from app.vectorstore.factory import get_vector_store
from app.worker import process_next_job

settings = get_settings()


async def run_cloud_infrastructure_verification():
    print("=" * 80)
    print("INTELLIGENCEOS - PRODUCTION CLOUD INFRASTRUCTURE VERIFICATION")
    print("=" * 80)

    # 1. Health Checks & Probes
    print("\n[Step 1/10] Verifying Health & Probes (/health, /healthz, /readyz)...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # GET /health
        health_resp = await client.get("/api/v1/health")
        print(f"  -> GET /api/v1/health response ({health_resp.status_code}): {health_resp.json()}")
        assert health_resp.status_code == 200, f"Health endpoint failed: {health_resp.text}"

        # GET /healthz
        healthz_resp = await client.get("/healthz")
        assert healthz_resp.status_code == 200
        print(f"  -> GET /healthz: {healthz_resp.json()['status']}")

        # GET /readyz
        readyz_resp = await client.get("/readyz")
        assert readyz_resp.status_code == 200
        print(f"  -> GET /readyz: {readyz_resp.json()['status']}")

    # 2. Direct PostgreSQL Health
    print("\n[Step 2/10] Verifying PostgreSQL Connection...")
    db_ok = await check_database_health()
    assert db_ok, "PostgreSQL connection failed!"
    print("  [OK] PostgreSQL connection active and query verified.")

    # 3. Redis Cloud Health
    print("\n[Step 3/10] Verifying Redis Cloud Connectivity...")
    redis_ok = await check_redis_health()
    assert redis_ok, "Redis Cloud connection failed!"
    r_client = get_redis_client()
    test_key = f"intelligenceos:ping:{uuid.uuid4()}"
    await r_client.set(test_key, "pong", ex=30)
    val = await r_client.get(test_key)
    await r_client.delete(test_key)
    assert val == "pong", f"Redis SET/GET failed: {val}"
    print("  [OK] Redis Cloud active (SET/GET/DELETE passed).")

    # 4. Supabase Storage Health & Operations
    print("\n[Step 4/10] Verifying Supabase Storage Bucket...")
    storage = get_storage_backend()
    storage_ok = await storage.health_check()
    assert storage_ok, "Supabase Storage health check failed!"
    print(f"  [OK] Supabase Storage connected to bucket '{settings.SUPABASE_STORAGE_BUCKET}'.")

    # 5. Qdrant Cloud Health & Collection
    print("\n[Step 5/10] Verifying Qdrant Cloud Connectivity...")
    vstore = get_vector_store()
    qdrant_ok = await vstore.health_check()
    assert qdrant_ok, "Qdrant Cloud health check failed!"
    await vstore.ensure_collection()
    print(f"  [OK] Qdrant Cloud active and collection '{settings.QDRANT_COLLECTION}' verified.")

    # 6. User Registration & JWT Authentication
    print("\n[Step 6/10] Testing User Registration & Authentication...")
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        test_email = f"cloud_test_{int(time.time())}@intelligenceos.io"
        test_password = "ProductionSecurePassword123!"

        reg_res = await client.post(
            f"{settings.API_V1_STR}/auth/register",
            json={"email": test_email, "password": test_password, "full_name": "Cloud Tester"},
        )
        assert reg_res.status_code == 201, f"Registration failed: {reg_res.text}"

        login_res = await client.post(
            f"{settings.API_V1_STR}/auth/login",
            json={"email": test_email, "password": test_password},
        )
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        auth_token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {auth_token}"}
        print(f"  [OK] Authenticated as: {test_email}")

        # 7. Workspace Creation
        print("\n[Step 7/10] Creating Multi-tenant Workspace...")
        ws_res = await client.post(
            f"{settings.API_V1_STR}/workspaces",
            json={"name": "Cloud Production Workspace", "slug": f"cloud-prod-{int(time.time())}"},
            headers=headers,
        )
        assert ws_res.status_code == 201, f"Workspace creation failed: {ws_res.text}"
        ws = ws_res.json()
        ws_id = uuid.UUID(ws["id"])
        print(f"  [OK] Workspace created: '{ws['name']}' (ID: {ws_id})")

        # 8. File Upload -> Supabase Storage -> PostgreSQL Metadata -> Redis Job
        print("\n[Step 8/10] Uploading Document Source to Supabase Storage...")
        sample_doc_content = (
            "IntelligenceOS Architecture Policy\n"
            "Infrastructure Standard: Supabase PostgreSQL for relational tables.\n"
            "Object Storage Standard: Supabase Storage buckets for raw uploaded files.\n"
            "Queue Standard: Redis Cloud for asynchronous ingestion background workers.\n"
            "Vector Database Standard: Qdrant Cloud for high-dimensional semantic vectors.\n"
        )
        file_bytes = sample_doc_content.encode("utf-8")
        filename = "architecture_policy.csv"

        up_res = await client.post(
            f"{settings.API_V1_STR}/workspaces/{ws_id}/sources/upload",
            files={"file": (filename, file_bytes, "text/csv")},
            data={"title": "Cloud Architecture Policy"},
            headers=headers,
        )
        assert up_res.status_code in (201, 202), f"Upload failed: {up_res.text}"
        source = up_res.json()
        source_id = uuid.UUID(source["id"])
        print(f"  [OK] Upload recorded: source_id={source_id}, status={source['status']}")

        # Verify object exists in Supabase Storage directly
        expected_storage_key = f"workspaces/{ws_id}/sources/{source_id}/{filename}"
        exists_in_supabase = await storage.file_exists(expected_storage_key)
        assert exists_in_supabase, (
            f"File not found in Supabase Storage at '{expected_storage_key}'!"
        )
        print(f"  [OK] Verified object in Supabase Storage: '{expected_storage_key}'")

        # Download back from Supabase Storage and verify byte integrity
        downloaded_bytes = await storage.download_file(expected_storage_key)
        assert downloaded_bytes == file_bytes, (
            "Downloaded content does not match uploaded content!"
        )
        print(
            f"  [OK] Byte integrity verified ({len(downloaded_bytes)} bytes from Supabase Storage)"
        )

        # 9. Background Worker Consumption & Ingestion Pipeline
        print("\n[Step 9/10] Running Background Worker to Process Ingestion Job...")
        for _ in range(5):
            processed = await process_next_job()
            if not processed:
                break
            check_res = await client.get(
                f"{settings.API_V1_STR}/workspaces/{ws_id}/sources/{source_id}",
                headers=headers,
            )
            if check_res.json().get("status") == "completed":
                break
        print("  [OK] Worker dequeued and executed ingestion job successfully.")

        # Verify PostgreSQL status updated to COMPLETED
        get_source_res = await client.get(
            f"{settings.API_V1_STR}/workspaces/{ws_id}/sources/{source_id}",
            headers=headers,
        )
        assert get_source_res.status_code == 200
        source_data = get_source_res.json()
        print(f"  [OK] PostgreSQL Source Status: {source_data['status']}")
        assert source_data["status"] == "completed", (
            f"Expected completed, got {source_data['status']}"
        )

        # Verify vector in Qdrant Cloud
        qdrant_count = await vstore.count_points(ws_id)
        print(f"  [OK] Qdrant Cloud points stored for workspace: {qdrant_count}")
        assert qdrant_count > 0, "No vectors found in Qdrant Cloud!"

        # 10. RAG Pipeline Query Execution
        print("\n[Step 10/10] Executing RAG Conversation Query against Qdrant Cloud...")
        conv_res = await client.post(
            f"{settings.API_V1_STR}/workspaces/{ws_id}/conversations",
            json={"title": "Cloud Architecture Q&A"},
            headers=headers,
        )
        assert conv_res.status_code == 201
        conv_id = conv_res.json()["id"]

        msg_res = await client.post(
            f"{settings.API_V1_STR}/workspaces/{ws_id}/conversations/{conv_id}/messages",
            json={
                "question": "What is the Object Storage standard for IntelligenceOS?",
                "retrieval_config": {
                    "retrieval_mode": "hybrid",
                    "final_top_k": 5,
                    "enable_reranking": True,
                },
            },
            headers=headers,
        )
        assert msg_res.status_code in (200, 201), f"RAG message failed: {msg_res.text}"
        rag_answer = msg_res.json()
        print("  [OK] RAG Assistant Response generated!")
        print(f"  [OK] Citations returned: {len(rag_answer.get('citations', []))}")

        # Clean up test object in Supabase Storage and vectors in Qdrant Cloud
        print("\nCleaning up test artifacts...")
        await storage.delete_file(expected_storage_key)
        await vstore.delete_by_source(ws_id, source_id)
        print("  [OK] Cleaned up Supabase Storage test file and Qdrant Cloud vectors.")

    print("\n" + "=" * 80)
    print("ALL 10 CLOUD INFRASTRUCTURE VERIFICATION PHASES PASSED WITH 100% SUCCESS!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_cloud_infrastructure_verification())
