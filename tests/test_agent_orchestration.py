"""Integration and orchestration tests for LangGraph agent workflows, budgets, and APIs."""

import json
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runner import AgentRunner
from app.models.agent_execution import ExecutionStatus
from app.providers.llm.base import LLMProvider
from app.schemas.auth import RegisterRequest
from app.schemas.llm import CompletionRequest, CompletionResponse
from app.services.auth_service import AuthService
from app.services.workspace_service import WorkspaceService


class SequentialMockLLMProvider(LLMProvider):
    """Mock LLM returning a pre-programmed sequence of turn responses."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = responses
        self._index = 0

    async def generate_text(self, request: CompletionRequest) -> CompletionResponse:
        if self._index < len(self._responses):
            resp = self._responses[self._index]
            self._index += 1
            return CompletionResponse(text=json.dumps(resp), model="mock-model")
        # Fallback to final answer
        return CompletionResponse(
            text=json.dumps(
                {"thought": "Done", "action": "final_answer", "final_response": "Completed."}
            ),
            model="mock-model",
        )

    async def health_check(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_agent_single_tool_workflow(db_session: AsyncSession):
    ws_id = uuid.uuid4()
    mock_responses = [
        {
            "thought": "I need to calculate 25 * 4.",
            "action": "call_tool",
            "tool_name": "calculator",
            "tool_input": {"expression": "25 * 4"},
        },
        {
            "thought": "The result is 100. I can answer now.",
            "action": "final_answer",
            "final_response": "25 multiplied by 4 equals 100.",
        },
    ]
    llm = SequentialMockLLMProvider(mock_responses)
    runner = AgentRunner(llm_provider=llm)

    result = await runner.run(
        query="What is 25 * 4?",
        workspace_id=ws_id,
        session=db_session,
    )

    assert result.status == ExecutionStatus.COMPLETED.value
    assert result.final_response == "25 multiplied by 4 equals 100."
    assert result.steps_count == 1
    assert result.steps[0]["tool_name"] == "calculator"
    assert result.steps[0]["tool_result"]["result"] == 100


@pytest.mark.asyncio
async def test_agent_combining_multiple_tools(db_session: AsyncSession):
    ws_id = uuid.uuid4()
    mock_responses = [
        # Step 1: Web search
        {
            "thought": "Let me search for project specs.",
            "action": "call_tool",
            "tool_name": "web_search",
            "tool_input": {"query": "Apollo mission year"},
        },
        # Step 2: Calculator
        {
            "thought": "Apollo landed in 1969. Let me calculate the years elapsed to 2026.",
            "action": "call_tool",
            "tool_name": "calculator",
            "tool_input": {"expression": "2026 - 1969"},
        },
        # Step 3: Final Answer
        {
            "thought": "I now have all pieces of information.",
            "action": "final_answer",
            "final_response": "The Apollo 11 moon landing occurred in 1969, which is 57 years ago.",
        },
    ]
    llm = SequentialMockLLMProvider(mock_responses)
    runner = AgentRunner(llm_provider=llm)

    result = await runner.run(
        query="How many years ago was Apollo 11?",
        workspace_id=ws_id,
        session=db_session,
    )

    assert result.status == ExecutionStatus.COMPLETED.value
    assert result.steps_count == 2
    assert result.steps[0]["tool_name"] == "web_search"
    assert result.steps[1]["tool_name"] == "calculator"
    assert "57 years ago" in result.final_response


@pytest.mark.asyncio
async def test_agent_step_budget_enforcement(db_session: AsyncSession):
    ws_id = uuid.uuid4()
    # LLM that attempts an infinite tool calling loop
    endless_responses = [
        {
            "thought": f"Calling calculator again {i}.",
            "action": "call_tool",
            "tool_name": "calculator",
            "tool_input": {"expression": f"{i} + 1"},
        }
        for i in range(10)
    ]
    llm = SequentialMockLLMProvider(endless_responses)
    runner = AgentRunner(llm_provider=llm)

    # Set hard cap of max_steps=2
    result = await runner.run(
        query="Loop forever",
        workspace_id=ws_id,
        session=db_session,
        max_steps=2,
    )

    assert result.status == ExecutionStatus.BUDGET_EXCEEDED.value
    assert result.steps_count <= 2


@pytest.mark.asyncio
async def test_agent_unauthorized_tool_attempt(db_session: AsyncSession):
    ws_id = uuid.uuid4()
    # LLM tries to call read_only_sql, but only calculator is authorized
    mock_responses = [
        {
            "thought": "Attempting SQL injection/bypass.",
            "action": "call_tool",
            "tool_name": "read_only_sql",
            "tool_input": {"query": "SELECT 1"},
        },
        {
            "thought": "SQL was blocked. Concluding now.",
            "action": "final_answer",
            "final_response": "Unable to execute SQL as it is unauthorized.",
        },
    ]
    llm = SequentialMockLLMProvider(mock_responses)
    runner = AgentRunner(llm_provider=llm)

    result = await runner.run(
        query="Run SQL",
        workspace_id=ws_id,
        session=db_session,
        allowed_tools=["calculator"],  # read_only_sql NOT authorized
    )

    assert result.steps_count == 1
    assert result.steps[0]["tool_name"] == "read_only_sql"
    assert "Permission Denied" in result.steps[0]["error"]


@pytest.mark.asyncio
async def test_agent_api_execute_and_trace_endpoints(
    client: AsyncClient, db_session: AsyncSession, auth_headers: Any
):
    headers = await auth_headers("agent_lead@intelligenceos.ai", "securepassword123")
    user = await AuthService.get_user_by_email(db_session, "agent_lead@intelligenceos.ai")
    assert user is not None

    # Provision Workspace
    ws = await WorkspaceService.create_workspace(db_session, "Autonomous Agent Labs", user)

    # 1. Execute agent task
    exec_payload = {
        "query": "Calculate 12 * 12",
        "allowed_tools": ["calculator"],
        "max_steps": 4,
    }
    res = await client.post(
        f"/api/v1/workspaces/{ws.id}/agent/execute",
        json=exec_payload,
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert "execution_id" in data
    assert data["workspace_id"] == str(ws.id)
    assert data["query"] == "Calculate 12 * 12"
    execution_id = data["execution_id"]

    # 2. Retrieve execution trace
    res_trace = await client.get(
        f"/api/v1/workspaces/{ws.id}/agent/executions/{execution_id}",
        headers=headers,
    )
    assert res_trace.status_code == 200
    trace_data = res_trace.json()
    assert trace_data["execution_id"] == execution_id

    # 3. List executions in workspace
    res_list = await client.get(
        f"/api/v1/workspaces/{ws.id}/agent/executions",
        headers=headers,
    )
    assert res_list.status_code == 200
    summaries = res_list.json()
    assert len(summaries) >= 1
    assert any(s["execution_id"] == execution_id for s in summaries)

    # 4. List available tools
    res_tools = await client.get(
        f"/api/v1/workspaces/{ws.id}/agent/tools",
        headers=headers,
    )
    assert res_tools.status_code == 200
    tools = res_tools.json()
    assert len(tools) == 4


@pytest.mark.asyncio
async def test_agent_api_cross_workspace_forbidden(
    client: AsyncClient, db_session: AsyncSession, auth_headers: Any
):
    headers = await auth_headers("agent_insider@intelligenceos.ai", "securepassword123")

    # Create another user and workspace
    other_user = await AuthService.register_user(
        db_session,
        RegisterRequest(email="outsider@intelligenceos.ai", password="securepassword123"),
    )
    other_ws = await WorkspaceService.create_workspace(db_session, "Private Beta Corp", other_user)

    # User from headers tries to execute agent on other_ws
    res = await client.post(
        f"/api/v1/workspaces/{other_ws.id}/agent/execute",
        json={"query": "Sneak peek"},
        headers=headers,
    )
    assert res.status_code == 403
    assert "not a member of this workspace" in res.json()["detail"].lower()
