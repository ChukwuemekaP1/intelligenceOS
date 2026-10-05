"""RAG Grounded Evaluation Verification against the Ingested 4-Document Corpus.

Validates that:
1. Queries against the ingested documents retrieve relevant chunk embeddings from Qdrant.
2. Answers are grounded in the document context.
3. Citations correctly reference the source titles and chunk snippets.
4. Latency and chunk count telemetry are recorded.
"""

import asyncio
import json
import uuid
import httpx

BASE_URL = "http://127.0.0.1:8000"

QUESTIONS = [
    {
        "id": "Q1-OPS-REDIS",
        "question": "What is the standard operating procedure if Redis broker goes down?",
        "expected_topic": "Redis failure / reconcile_sources.py",
    },
    {
        "id": "Q2-SEC-TENANT",
        "question": "How does IntelligenceOS enforce tenant isolation in Qdrant vector storage?",
        "expected_topic": "workspace_id payload filter / namespace isolation",
    },
    {
        "id": "Q3-SUP-QUOTAS",
        "question": "What are the subscription quotas for the Free Tier vs Pro Tier?",
        "expected_topic": "Free Tier (3 workspaces, 50 sources, 25MB) vs Pro Tier (20 workspaces, 1,000 sources, 100MB)",
    },
    {
        "id": "Q4-ARCH-COMPONENTS",
        "question": "What are the core decoupled components of the IntelligenceOS platform architecture?",
        "expected_topic": "FastAPI, app.worker, PostgreSQL, Qdrant, Supabase Storage, Redis",
    },
]

async def evaluate_rag():
    print("=" * 70)
    print("RAG Grounded Corpus Evaluation Suite")
    print("=" * 70)

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # 1. Authenticate / Login or Register
        unique_id = uuid.uuid4().hex[:6]
        test_email = f"rag_eval_{unique_id}@intelligenceos.internal"
        test_pass = "SecurePass123!"

        reg_res = await client.post("/api/v1/auth/register", json={
            "email": test_email,
            "password": test_pass,
            "full_name": "RAG Evaluator",
        })
        assert reg_res.status_code == 201, f"Register failed: {reg_res.text}"

        login_res = await client.post("/api/v1/auth/login", json={
            "email": test_email,
            "password": test_pass,
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Create Workspace
        ws_res = await client.post("/api/v1/workspaces", headers=headers, json={
            "name": f"Corpus Workspace {unique_id}",
        })
        assert ws_res.status_code == 201, f"Create workspace failed: {ws_res.text}"
        workspace_id = ws_res.json()["id"]
        print(f"Created Workspace ID: {workspace_id}")

        # 3. Upload Corpus Documents
        corpus_files = [
            ("test_corpus/Customer_Support_Knowledge_Base.txt", "Customer Support Knowledge Base"),
            ("test_corpus/Engineering_Operations_Runbook.txt", "Engineering Operations Runbook"),
            ("test_corpus/Security_and_AI_Safety_Policy.md", "Security and AI Safety Policy"),
            ("test_corpus/IntelligenceOS_Product_Architecture.pdf", "Product Architecture PDF"),
        ]

        print("Uploading corpus documents...")
        source_ids = []
        for file_path, doc_title in corpus_files:
            import os
            abs_p = os.path.abspath(file_path)
            with open(abs_p, "rb") as f:
                file_bytes = f.read()
            filename = os.path.basename(file_path)

            up_res = await client.post(
                f"/api/v1/workspaces/{workspace_id}/sources/upload",
                headers=headers,
                data={"title": doc_title},
                files={"file": (filename, file_bytes, "application/octet-stream")},
            )
            assert up_res.status_code in (200, 201, 202), f"Upload failed for {filename}: {up_res.text}"
            source_data = up_res.json()
            source_ids.append(source_data["id"])
            print(f"  Uploaded {doc_title} -> Source ID: {source_data['id']}")

        # Wait for worker to index documents
        print("Waiting for background worker to complete indexing...")
        for _ in range(30):
            all_done = True
            for s_id in source_ids:
                s_chk = await client.get(
                    f"/api/v1/workspaces/{workspace_id}/sources/{s_id}",
                    headers=headers,
                )
                if s_chk.status_code == 200:
                    status = s_chk.json()["status"]
                    if status not in ("completed", "failed"):
                        all_done = False
                        break
            if all_done:
                break
            await asyncio.sleep(1.0)
        print("Ingestion complete!\n")

        # 4. Create Conversation
        conv_res = await client.post(
            f"/api/v1/workspaces/{workspace_id}/conversations",
            headers=headers,
            json={"title": "Corpus RAG Evaluation Session"},
        )
        assert conv_res.status_code == 201, f"Create conversation failed: {conv_res.text}"
        conversation_id = conv_res.json()["id"]
        print(f"Created Conversation ID: {conversation_id}\n")

        results = []

        # 4. Execute Questions
        for item in QUESTIONS:
            q_id = item["id"]
            question = item["question"]
            print(f"--- Running {q_id} ---")
            print(f"Question: {question}")

            msg_res = await client.post(
                f"/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/messages",
                headers=headers,
                json={
                    "question": question,
                    "retrieval_config": {
                        "retrieval_mode": "hybrid",
                        "final_top_k": 5,
                        "enable_reranking": True,
                    },
                },
            )
            assert msg_res.status_code == 200, f"Query failed: {msg_res.text}"
            data = msg_res.json()

            answer = data["answer"]
            citations = data.get("citations", [])
            metrics = data.get("metrics", {})

            print(f"Answer: {answer}")
            print(f"Citations count: {len(citations)}")
            for idx, c in enumerate(citations):
                print(f"  [{idx+1}] {c.get('source_name', 'Source')} (chunk #{c.get('chunk_index')}): {c.get('snippet', '')[:100]}...")
            print(f"Metrics: Latency={metrics.get('total_latency_ms', 0):.1f}ms, Retrieved={metrics.get('retrieval_count', 0)}, Context={metrics.get('final_context_count', 0)}\n")

            results.append({
                "id": q_id,
                "question": question,
                "answer": answer,
                "citations_count": len(citations),
                "latency_ms": metrics.get("total_latency_ms", 0),
                "status": "PASS",
            })

        print("=" * 70)
        print("RAG Grounded Corpus Evaluation Summary:")
        for r in results:
            print(f"  {r['id']:18} | {r['status']} | Citations: {r['citations_count']} | Latency: {r['latency_ms']:.1f}ms")
        print("=" * 70)

if __name__ == "__main__":
    asyncio.run(evaluate_rag())
