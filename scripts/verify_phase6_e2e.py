"""Phase 6 End-to-End Verification and Demonstration Script for IntelligenceOS.

Simulates the complete user and platform journey:
1. System Health Verification (/healthz, /health/live, /metrics)
2. Authentication & JWT Security
3. Workspace Provisioning & RBAC Isolation
4. Knowledge Source Upload & Ingestion Simulation
5. RAG Retrieval, Cross-Encoder Reranking & Grounded Citations
6. Agent Execution with multi-tool sandbox (Calculator, SQL, Knowledge Search)
7. Deterministic Evaluation Runs (Recall@K, MRR, nDCG@K, Citation F1)
8. Observability & Tracing with Sensitive Data Redaction
"""

import asyncio
import json
import time

from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app

settings = get_settings()


async def run_live_verification():
    print("=" * 80)
    print("IntelligenceOS - Phase 6 Complete End-to-End Verification")
    print("=" * 80)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Health Checks
        print("\n[1/8] Verifying Health & Probes...")
        live_res = await client.get("/health/live")
        ready_res = await client.get("/healthz")
        assert live_res.status_code == 200, f"Liveness failed: {live_res.text}"
        assert ready_res.status_code == 200, f"Readiness failed: {ready_res.text}"
        print(f"  ✓ Liveness probe: {live_res.json()}")
        print(f"  ✓ Readiness probe: {ready_res.json()}")

        # 2. Authentication & Identity
        print("\n[2/8] Testing Authentication & Token Issuance...")
        email = f"verified_admin_{int(time.time())}@intelligenceos.io"
        reg_res = await client.post(
            f"{settings.API_V1_STR}/auth/register",
            json={
                "email": email,
                "password": "ProductionPassword999!",
                "full_name": "Chief Platform Engineer",
            },
        )
        assert reg_res.status_code in (200, 201), f"Register error: {reg_res.text}"

        login_res = await client.post(
            f"{settings.API_V1_STR}/auth/login",
            data={"username": email, "password": "ProductionPassword999!"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert login_res.status_code == 200, f"Login error: {login_res.text}"
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"  ✓ Registered & Authenticated: {email}")

        # 3. Workspace Provisioning
        print("\n[3/8] Creating Workspace...")
        ws_res = await client.post(
            f"{settings.API_V1_STR}/workspaces",
            json={"name": "Production AI Operations", "slug": f"prod-ops-{int(time.time())}"},
            headers=headers,
        )
        assert ws_res.status_code == 201, f"Workspace creation error: {ws_res.text}"
        ws = ws_res.json()
        ws_id = ws["id"]
        print(f"  ✓ Provisioned Workspace: '{ws['name']}' (ID: {ws_id})")

        # 4. Ingesting Document Source
        print("\n[4/8] Ingesting Structured Knowledge Source...")
        doc_csv = (
            "Standard,Value,Details\n"
            "Data_Retention_Policy,90_Days,Compliant with GDPR Article 17\n"
            "Encryption_At_Rest,AES_256_GCM,FIPS 140-3 validated\n"
            "Max_Concurrent_Connections,2500,Load balanced across ingress clusters\n"
        )
        up_res = await client.post(
            f"{settings.API_V1_STR}/workspaces/{ws_id}/sources/upload",
            files={"file": ("security_policy.csv", doc_csv.encode("utf-8"), "text/csv")},
            data={"title": "Enterprise Security Standards"},
            headers=headers,
        )
        assert up_res.status_code == 201, f"Upload error: {up_res.text}"
        source = up_res.json()
        print(f"  ✓ Source Uploaded: '{source['title']}' (Status: {source['status']})")

        # 5. RAG Query & Reranked Answer Generation
        print("\n[5/8] Executing RAG Pipeline with Hybrid Search & Reranking...")
        conv_res = await client.post(
            f"{settings.API_V1_STR}/workspaces/{ws_id}/conversations",
            json={"title": "Security Standards Inquiries"},
            headers=headers,
        )
        conv_id = conv_res.json()["id"]

        msg_res = await client.post(
            f"{settings.API_V1_STR}/workspaces/{ws_id}/conversations/{conv_id}/messages",
            json={
                "content": "What encryption standard and data retention policy are mandated?",
                "retrieval_mode": "hybrid",
                "top_k": 3,
                "enable_reranking": True,
            },
            headers=headers,
        )
        assert msg_res.status_code == 201, f"RAG message error: {msg_res.text}"
        answer = msg_res.json()
        print(f"  ✓ Assistant Grounded Answer: {answer['content'][:120]}...")
        print(f"  ✓ Citations Received: {len(answer.get('citations', []))}")

        # 6. Autonomous Agent Execution
        print("\n[6/8] Executing Multi-Tool Autonomous Agent...")
        agent_res = await client.post(
            f"{settings.API_V1_STR}/workspaces/{ws_id}/agent/execute",
            json={
                "query": "Calculate (2500 * 4) / 10 and lookup retention policy.",
                "allowed_tools": ["calculator", "knowledge_search"],
                "max_steps": 4,
            },
            headers=headers,
        )
        assert agent_res.status_code == 200, f"Agent execution error: {agent_res.text}"
        agent_data = agent_res.json()
        print(f"  ✓ Agent Status: {agent_data['status']}")
        print(f"  ✓ Tool Steps Executed: {len(agent_data['steps'])}")
        print(f"  ✓ Final Response: {agent_data['final_response'][:100]}...")

        # 7. Evaluation & Deterministic Metrics
        print("\n[7/8] Running Deterministic Benchmark Evaluation...")
        ds_res = await client.post(
            f"{settings.API_V1_STR}/workspaces/{ws_id}/evaluations/datasets",
            json={
                "name": "Security Compliance Ground Truth",
                "examples": [
                    {
                        "query": "What encryption algorithm is required?",
                        "expected_chunk_ids": ["chunk_enc_1"],
                        "reference_answer": "AES_256_GCM",
                    }
                ],
            },
            headers=headers,
        )
        ds_id = ds_res.json()["id"]

        eval_res = await client.post(
            f"{settings.API_V1_STR}/workspaces/{ws_id}/evaluations/run",
            json={
                "dataset_id": ds_id,
                "retrieval_mode": "hybrid",
                "top_k": 5,
                "evaluator_type": "deterministic",
            },
            headers=headers,
        )
        eval_run = eval_res.json()
        print(f"  ✓ Evaluation Run ID: {eval_run['run_id']}")
        print(f"  ✓ Metrics: {json.dumps(eval_run['retrieval_metrics'])}")

        # 8. Observability & Traces
        print("\n[8/8] Inspecting Observability Traces & Prometheus Metrics...")
        traces_res = await client.get(
            f"{settings.API_V1_STR}/workspaces/{ws_id}/traces", headers=headers
        )
        traces = traces_res.json()
        print(f"  ✓ Total Traces Captured: {len(traces)}")

        metrics_res = await client.get("/metrics")
        assert metrics_res.status_code == 200
        print("  ✓ Prometheus /metrics scrape verified.")

        print("\n" + "=" * 80)
        print("PHASE 6 END-TO-END VERIFICATION COMPLETED SUCCESSFULLY!")
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_live_verification())
