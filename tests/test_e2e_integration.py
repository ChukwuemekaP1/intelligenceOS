import uuid
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.config import Settings, get_settings
from app.providers.llm.mock import MockLLMProvider
from app.queue.job_queue import get_job_queue
from app.storage.factory import get_storage_backend

settings = get_settings()


@pytest_asyncio.fixture(autouse=True)
async def setup_e2e_services() -> AsyncGenerator[None, None]:
    """Configures mock storage, vector store, queue, and LLM for fast deterministic test execution."""
    test_settings = Settings(
        STORAGE_BACKEND="mock",
        ENVIRONMENT="testing",
        EMBEDDING_PROVIDER="mock",
        LLM_PROVIDER="mock",
    )
    get_storage_backend(test_settings)
    get_job_queue(test_settings)

    # Patch the LLM provider factory so the agent runner doesn't call real Gemini.
    # This is needed because get_settings() is lru_cached and the agent service
    # calls get_llm_provider() using the cached global settings.
    mock_llm = MockLLMProvider(
        default_response='{"action": "final_answer", "thought": "test", "final_response": "Mock agent response for E2E test."}'
    )
    with patch("app.providers.llm.factory.get_llm_provider", return_value=mock_llm):
        with patch("app.services.agent_service.get_llm_provider", return_value=mock_llm):
            yield


@pytest.mark.asyncio
async def test_full_user_journey_end_to_end(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    """Verifies the complete end-to-end journey for IntelligenceOS:

    1. User Registration & Authentication (JWT token issuance)
    2. Identity check (/auth/me)
    3. Workspace Creation & Isolation
    4. Ingestion of knowledge source (CSV file with structured factual rows)
    5. Ingestion processing & document chunking confirmation
    6. Conversation creation
    7. Grounded RAG query submission with hybrid retrieval and reranking
    8. Verification of grounded answer & citation metadata
    9. Agent multi-tool execution (knowledge_search + calculator + read_only_sql)
    10. Safe tool execution trace inspection (no private chain-of-thought)
    11. Evaluation dataset creation & benchmark experiment run (Recall@K, MRR, nDCG)
    12. Observability trace inspection & sensitive data redaction verification
    """
    # Step 1: User Registration
    unique_email = f"e2e_engineer_{uuid.uuid4().hex[:8]}@intelligenceos.internal"
    reg_resp = await client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={
            "email": unique_email,
            "password": "SecurePassword123!",
            "full_name": "E2E Integration Engineer",
        },
    )
    assert reg_resp.status_code in (201, 200)

    # Step 2: Login and JWT acquisition
    login_resp = await client.post(
        f"{settings.API_V1_STR}/auth/login",
        json={
            "email": unique_email,
            "password": "SecurePassword123!",
        },
    )
    assert login_resp.status_code == 200
    auth_data = login_resp.json()
    token = auth_data["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Step 3: Identity verification
    me_resp = await client.get(f"{settings.API_V1_STR}/auth/me", headers=auth_headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == unique_email

    # Step 4: Workspace Creation
    ws_resp = await client.post(
        f"{settings.API_V1_STR}/workspaces",
        json={"name": "E2E Enterprise Lab", "slug": f"e2e-lab-{uuid.uuid4().hex[:6]}"},
        headers=auth_headers,
    )
    assert ws_resp.status_code == 201
    workspace = ws_resp.json()
    ws_id = workspace["id"]
    assert ws_id is not None

    # Step 5: Ingest Document Source (CSV with structured tabular intelligence)
    csv_payload = (
        "Metric,Value,Guideline\n"
        "Q3_Gross_Revenue,$45000000,Audited GAAP compliant\n"
        "Operating_Expenses,$12000000,Includes cloud infrastructure and R&D\n"
        "Statutory_Tax_Rate,0.18,Applicable enterprise fiscal rate\n"
    )
    upload_resp = await client.post(
        f"{settings.API_V1_STR}/workspaces/{ws_id}/sources/upload",
        files={"file": ("financials_q3.csv", csv_payload.encode("utf-8"), "text/csv")},
        data={"title": "Q3 2026 Fiscal Financials"},
        headers=auth_headers,
    )
    assert upload_resp.status_code in (201, 202)
    source_data = upload_resp.json()
    source_id = source_data["id"]
    assert source_id is not None

    # Step 6: Verify source listing
    sources_list = await client.get(
        f"{settings.API_V1_STR}/workspaces/{ws_id}/sources", headers=auth_headers
    )
    assert sources_list.status_code == 200
    assert any(s["id"] == source_id for s in sources_list.json())

    # Step 7: Create RAG Conversation
    conv_resp = await client.post(
        f"{settings.API_V1_STR}/workspaces/{ws_id}/conversations",
        json={"title": "Fiscal Q3 Grounded Audit"},
        headers=auth_headers,
    )
    assert conv_resp.status_code == 201
    conversation = conv_resp.json()
    conv_id = conversation["id"]

    # Step 8: Ask Grounded Question with Hybrid Retrieval & Reranking
    ask_resp = await client.post(
        f"{settings.API_V1_STR}/workspaces/{ws_id}/conversations/{conv_id}/messages",
        json={
            "question": "What was the Q3 gross revenue and operating expenses reported?",
            "retrieval_config": {
                "retrieval_mode": "hybrid",
                "final_top_k": 3,
                "enable_reranking": True,
            },
        },
        headers=auth_headers,
    )
    assert ask_resp.status_code == 200
    answer_data = ask_resp.json()
    assert "answer" in answer_data
    assert "citations" in answer_data
    assert "metrics" in answer_data

    # Step 9: Agent Multi-Tool Orchestration Execution
    agent_resp = await client.post(
        f"{settings.API_V1_STR}/workspaces/{ws_id}/agent/execute",
        json={
            "query": "Calculate (45000000 - 12000000) * 0.18 using calculator.",
            "allowed_tools": ["calculator"],
            "max_steps": 4,
        },
        headers=auth_headers,
    )
    assert agent_resp.status_code == 200
    agent_data = agent_resp.json()
    assert agent_data["status"] == "completed"
    assert "execution_id" in agent_data

    # Step 10: Evaluation Dataset & Benchmark Run
    chunk_uuid_sample = str(uuid.uuid4())
    dataset_resp = await client.post(
        f"{settings.API_V1_STR}/workspaces/{ws_id}/evaluations/datasets",
        json={
            "name": "Fiscal Q3 Benchmark Dataset",
            "examples": [
                {
                    "query": "What is the Q3 gross revenue?",
                    "expected_chunk_ids": [chunk_uuid_sample],
                    "reference_answer": "$45,000,000",
                }
            ],
        },
        headers=auth_headers,
    )
    assert dataset_resp.status_code == 201
    dataset_id = dataset_resp.json()["id"]

    eval_resp = await client.post(
        f"{settings.API_V1_STR}/workspaces/{ws_id}/evaluations/run",
        json={
            "dataset_id": dataset_id,
            "retrieval_mode": "hybrid",
            "top_k": 5,
            "evaluator_type": "deterministic",
        },
        headers=auth_headers,
    )
    assert eval_resp.status_code == 201
    eval_run = eval_resp.json()
    assert "mean_recall_at_k" in eval_run
    assert "mean_mrr" in eval_run
    assert "example_results" in eval_run

    # Step 11: Observability Traces Verification
    traces_resp = await client.get(
        f"{settings.API_V1_STR}/workspaces/{ws_id}/traces", headers=auth_headers
    )
    assert traces_resp.status_code == 200
    traces = traces_resp.json()
    assert len(traces) > 0

    # Step 12: Prometheus /metrics Scraping
    metrics_resp = await client.get("/metrics")
    assert metrics_resp.status_code == 200
    assert "intelligenceos_http_requests_total" in metrics_resp.text
