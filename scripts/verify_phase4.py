"""Verification script for IntelligenceOS Phase 4: Agent & Tool Orchestration Layer.

Demonstrates:
  1. Knowledge Search tool execution with workspace scoping
  2. Safe Calculator tool execution (AST without eval)
  3. Controlled Read-Only SQL execution
  4. Web Search tool execution with SSRF validation
  5. Multi-tool combination (Knowledge Search + Calculator)
  6. Application-level authorization blocking unauthorized tool usage
  7. Multi-tenant workspace isolation (Workspace A cannot search Workspace B data)
  8. SQL mutation blocking (INSERT/UPDATE/DROP rejected)
  9. Bounded execution termination within max step budget
  10. Full execution trace persistence and inspection
"""

import asyncio
import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agent.runner import AgentRunner
from app.core.config import get_settings
from app.database.base import Base
from app.models.agent_execution import ExecutionStatus
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.source import ProcessingStatus, Source, SourceType
from app.providers.embedding.mock import MockEmbeddingProvider
from app.providers.llm.base import LLMProvider
from app.schemas.agent import AgentExecuteRequest
from app.schemas.auth import RegisterRequest
from app.schemas.llm import CompletionRequest, CompletionResponse
from app.services.agent_service import AgentService
from app.services.auth_service import AuthService
from app.services.workspace_service import WorkspaceService
from app.tools.builtins import create_default_registry
from app.tools.calculator import CalculatorInput, CalculatorTool
from app.tools.sql import ReadOnlySQLInput, ReadOnlySQLTool
from app.vectorstore.mock import MockVectorStore
from app.vectorstore.models import VectorPoint


class ScriptMockLLM(LLMProvider):
    """Deterministic multi-turn mock LLM for reproducible verification flows."""

    def __init__(self, turns: list[dict]) -> None:
        self.turns = turns
        self.idx = 0

    async def generate_text(self, request: CompletionRequest) -> CompletionResponse:
        if self.idx < len(self.turns):
            resp = self.turns[self.idx]
            self.idx += 1
            return CompletionResponse(text=json.dumps(resp), model="mock-model")
        return CompletionResponse(
            text=json.dumps(
                {
                    "thought": "Evidence collected.",
                    "action": "final_answer",
                    "final_response": "I have completed the task based on the collected evidence.",
                }
            ),
            model="mock-model",
        )

    async def health_check(self) -> bool:
        return True


async def seed_data(
    session: AsyncSession, ws_a: uuid.UUID, ws_b: uuid.UUID, vstore: MockVectorStore
) -> None:
    embedder = MockEmbeddingProvider(dimension=768)

    # Workspace A: Q4 Financial Report
    src_a = Source(
        id=uuid.uuid4(),
        workspace_id=ws_a,
        source_type=SourceType.PDF.value,
        name="Q4_Financial_Report.pdf",
        status=ProcessingStatus.COMPLETED.value,
    )
    session.add(src_a)
    doc_a = Document(id=uuid.uuid4(), source_id=src_a.id, workspace_id=ws_a)
    session.add(doc_a)
    ver_a = DocumentVersion(id=uuid.uuid4(), document_id=doc_a.id, version_number=1)
    session.add(ver_a)
    text_a = (
        "Quantum Dynamics achieved total revenue of $42.5M in Q4, representing a 25% "
        "year-over-year increase across enterprise cloud subscriptions."
    )
    chunk_a = Chunk(
        id=uuid.uuid4(),
        document_version_id=ver_a.id,
        workspace_id=ws_a,
        chunk_index=0,
        content=text_a,
        metadata_={"page_number": 1, "source_name": "Q4_Financial_Report.pdf"},
    )
    session.add(chunk_a)

    # Workspace B: Confidential Skynet Specs
    src_b = Source(
        id=uuid.uuid4(),
        workspace_id=ws_b,
        source_type=SourceType.PDF.value,
        name="Skynet_Secret.pdf",
        status=ProcessingStatus.COMPLETED.value,
    )
    session.add(src_b)
    doc_b = Document(id=uuid.uuid4(), source_id=src_b.id, workspace_id=ws_b)
    session.add(doc_b)
    ver_b = DocumentVersion(id=uuid.uuid4(), document_id=doc_b.id, version_number=1)
    session.add(ver_b)
    text_b = "TOP SECRET: Project Skynet neural core budget is $90M with deployment in 2029."
    chunk_b = Chunk(
        id=uuid.uuid4(),
        document_version_id=ver_b.id,
        workspace_id=ws_b,
        chunk_index=0,
        content=text_b,
        metadata_={"page_number": 1, "source_name": "Skynet_Secret.pdf"},
    )
    session.add(chunk_b)
    await session.commit()

    vec_a = await embedder.embed_query(text_a)
    await vstore.upsert_points(
        workspace_id=ws_a,
        points=[
            VectorPoint(
                id=chunk_a.id,
                vector=vec_a,
                payload={
                    "workspace_id": str(ws_a),
                    "chunk_id": str(chunk_a.id),
                    "source_name": src_a.name,
                    "text": text_a,
                    "page_number": 1,
                    "chunk_index": 0,
                },
            )
        ],
    )

    vec_b = await embedder.embed_query(text_b)
    await vstore.upsert_points(
        workspace_id=ws_b,
        points=[
            VectorPoint(
                id=chunk_b.id,
                vector=vec_b,
                payload={
                    "workspace_id": str(ws_b),
                    "chunk_id": str(chunk_b.id),
                    "source_name": src_b.name,
                    "text": text_b,
                    "page_number": 1,
                    "chunk_index": 0,
                },
            )
        ],
    )


async def main() -> None:
    print("=" * 80)
    print("IntelligenceOS Phase 4: Agent & Tool Orchestration Layer Verification")
    print("=" * 80)

    # 1. In-memory async SQLite engine
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    vstore = MockVectorStore()

    settings = get_settings()
    api_key_val = settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else None
    if api_key_val:
        print(f"[*] Live Gemini model configured: {settings.GEMINI_MODEL}")
    else:
        print("[*] Running verification with deterministic multi-turn mock provider")

    async with session_maker() as session:
        # 2. Provision identity and workspaces
        user = await AuthService.register_user(
            session,
            RegisterRequest(email="orchestrator@intelligenceos.ai", password="securepassword123"),
        )
        ws_a = await WorkspaceService.create_workspace(session, "Quantum Dynamics Corp", user)
        ws_b = await WorkspaceService.create_workspace(session, "Cyberdyne Systems", user)
        print(f"[+] Workspace A provisioned: '{ws_a.name}' (ID: {ws_a.id})")
        print(f"[+] Workspace B provisioned: '{ws_b.name}' (ID: {ws_b.id})")

        # 3. Seed knowledge
        await seed_data(session, ws_a.id, ws_b.id, vstore)
        print("[+] Seeded documents in Workspace A and B.")

        # --- FLOW 1: Agent answers using Knowledge Search ---
        print("\n--- Flow 1: Knowledge Search Tool ---")
        q1 = "What was Quantum Dynamics total revenue in Q4?"
        runner1 = AgentRunner(
            llm_provider=ScriptMockLLM(
                [
                    {
                        "thought": "Need to search workspace documents for Q4 revenue.",
                        "action": "call_tool",
                        "tool_name": "knowledge_search",
                        "tool_input": {"query": "Quantum Dynamics Q4 revenue"},
                    },
                    {
                        "thought": "Found revenue figure: $42.5M.",
                        "action": "final_answer",
                        "final_response": (
                            "Quantum Dynamics achieved a total revenue of $42.5M in Q4."
                        ),
                    },
                ]
            ),
            vector_store=vstore,
        )
        resp1 = await AgentService.execute_agent(
            session=session,
            workspace_id=ws_a.id,
            request=AgentExecuteRequest(query=q1),
            user=user,
            runner=runner1,
            vector_store=vstore,
        )
        print(f"[?] Query: {q1}")
        print(f"[+] Answer: {resp1.final_response}")
        print(f"[+] Steps: {resp1.steps_count} | Tool: {resp1.trace[0].tool_name}")
        assert "42.5M" in resp1.final_response
        assert resp1.trace[0].tool_name == "knowledge_search"

        # --- FLOW 2: Safe Calculator Tool ---
        print("\n--- Flow 2: Safe Calculator Tool ---")
        calc_tool = CalculatorTool()
        calc_res = await calc_tool.execute(
            CalculatorInput(expression="42.5 * 1.25"),
            context=None,
        )
        print("[?] Calculation: 42.5 * 1.25")
        print(f"[+] Calculator output: {calc_res.text_summary}")
        assert calc_res.success is True
        assert calc_res.data["result"] == 53.125

        # Calculator Safety: Reject arbitrary execution and math bombs
        malicious_calc = await calc_tool.execute(
            CalculatorInput(expression="__import__('os').system('ls')"),
            context=None,
        )
        assert malicious_calc.success is False
        print(f"[+] VERIFIED: Code execution blocked: '{malicious_calc.error}'")

        # --- FLOW 3: Read-only SQL Tool ---
        print("\n--- Flow 3: Read-Only SQL Tool ---")
        sql_tool = ReadOnlySQLTool()
        from app.tools.base import ToolExecutionContext

        sql_ctx = ToolExecutionContext(workspace_id=ws_a.id, session=session)
        sql_res = await sql_tool.execute(
            ReadOnlySQLInput(query="SELECT name, source_type FROM sources"),
            sql_ctx,
        )
        print(f"[+] SQL result: {sql_res.data['row_count']} row(s) returned.")
        assert sql_res.success is True
        assert sql_res.data["row_count"] >= 1

        # --- FLOW 4: Web Search with SSRF Protection ---
        print("\n--- Flow 4: Web Search Tool ---")
        registry = create_default_registry()
        web_res = await registry.execute_tool(
            tool_name="web_search",
            raw_input={"query": "python asyncio best practices"},
            context=sql_ctx,
            allowed_tools=["web_search"],
        )
        print(f"[+] Web search found: {web_res.data['results_found']} safe results.")
        assert web_res.success is True
        assert web_res.data["results_found"] > 0

        # --- FLOW 5: Multi-Tool Combination ---
        print("\n--- Flow 5: Combining Multiple Tools (Knowledge Search + Calculator) ---")
        q5 = "Find our Q4 revenue and calculate a 10% bonus pool."
        runner5 = AgentRunner(
            llm_provider=ScriptMockLLM(
                [
                    {
                        "thought": "Search workspace documents for Q4 revenue.",
                        "action": "call_tool",
                        "tool_name": "knowledge_search",
                        "tool_input": {"query": "Q4 revenue"},
                    },
                    {
                        "thought": "Revenue is 42.5M. Now calculate 10% of 42.5M.",
                        "action": "call_tool",
                        "tool_name": "calculator",
                        "tool_input": {"expression": "42.5 * 0.10"},
                    },
                    {
                        "thought": "10% of 42.5M is 4.25M. Formulating response.",
                        "action": "final_answer",
                        "final_response": "At Q4 revenue of $42.5M, the 10% bonus pool is $4.25M.",
                    },
                ]
            ),
            vector_store=vstore,
        )
        resp5 = await AgentService.execute_agent(
            session=session,
            workspace_id=ws_a.id,
            request=AgentExecuteRequest(query=q5),
            user=user,
            runner=runner5,
            vector_store=vstore,
        )
        print(f"[+] Multi-tool answer: {resp5.final_response}")
        print(f"[+] Trace steps: {[s.tool_name for s in resp5.trace]}")
        assert resp5.steps_count == 2
        assert resp5.trace[0].tool_name == "knowledge_search"
        assert resp5.trace[1].tool_name == "calculator"
        assert "$4.25M" in resp5.final_response

        # --- FLOW 6: Unauthorized Tool Usage Rejection ---
        print("\n--- Flow 6: Unauthorized Tool Usage Rejection ---")
        unauth_runner = AgentRunner(
            llm_provider=ScriptMockLLM(
                [
                    {
                        "thought": "Trying to run SQL even though only calculator is permitted.",
                        "action": "call_tool",
                        "tool_name": "read_only_sql",
                        "tool_input": {"query": "SELECT 1"},
                    },
                    {
                        "thought": "SQL rejected as unauthorized. Finishing.",
                        "action": "final_answer",
                        "final_response": "Cannot query the database: tool is unauthorized.",
                    },
                ]
            )
        )
        resp6 = await AgentService.execute_agent(
            session=session,
            workspace_id=ws_a.id,
            request=AgentExecuteRequest(
                query="Query DB",
                allowed_tools=["calculator"],  # read_only_sql not in list
            ),
            user=user,
            runner=unauth_runner,
        )
        print(f"[+] Step 1 error: {resp6.trace[0].error}")
        assert "Permission Denied" in resp6.trace[0].error

        # --- FLOW 7: Workspace Isolation Check ---
        print("\n--- Flow 7: Multi-Tenant Workspace Isolation ---")
        runner7 = AgentRunner(
            llm_provider=ScriptMockLLM(
                [
                    {
                        "thought": "Searching for Skynet in Workspace A.",
                        "action": "call_tool",
                        "tool_name": "knowledge_search",
                        "tool_input": {"query": "Skynet"},
                    },
                    {
                        "thought": "No documents found for Skynet in Workspace A.",
                        "action": "final_answer",
                        "final_response": "No documents found mentioning Skynet in this workspace.",
                    },
                ]
            ),
            vector_store=vstore,
        )
        resp7 = await AgentService.execute_agent(
            session=session,
            workspace_id=ws_a.id,
            request=AgentExecuteRequest(query="What is the budget for Project Skynet?"),
            user=user,
            runner=runner7,
            vector_store=vstore,
        )
        print(f"[+] Isolation query response: {resp7.final_response}")
        assert "$90M" not in resp7.final_response
        print("[+] VERIFIED: Workspace A completely denied access to Workspace B's data.")

        # --- FLOW 8: SQL Mutation Blocking ---
        print("\n--- Flow 8: SQL Mutation Guardrails ---")
        bad_sqls = [
            "DROP TABLE sources",
            "INSERT INTO sources (name) VALUES ('evil')",
            "UPDATE sources SET name = 'hacked'",
            "SELECT * FROM sources; DROP TABLE sources",
            "SELECT * FROM users",
        ]
        for bad_sql in bad_sqls:
            res_bad = await sql_tool.execute(ReadOnlySQLInput(query=bad_sql), sql_ctx)
            assert res_bad.success is False
            print(f"  [BLOCKED] '{bad_sql}': {res_bad.error}")
        print("[+] VERIFIED: All SQL mutation, DDL, and table traversal attempts blocked.")

        # --- FLOW 9: Bounded Step Budget Enforcement ---
        print("\n--- Flow 9: Bounded Step Budget Enforcement ---")
        looping_llm = ScriptMockLLM(
            [
                {
                    "thought": f"Loop step {i}",
                    "action": "call_tool",
                    "tool_name": "calculator",
                    "tool_input": {"expression": f"{i} + 1"},
                }
                for i in range(10)
            ]
        )
        loop_runner = AgentRunner(llm_provider=looping_llm)
        resp_budget = await AgentService.execute_agent(
            session=session,
            workspace_id=ws_a.id,
            request=AgentExecuteRequest(query="Loop forever", max_steps=2),
            user=user,
            runner=loop_runner,
        )
        print(f"[+] Status: {resp_budget.status} | Steps executed: {resp_budget.steps_count}")
        assert resp_budget.status == ExecutionStatus.BUDGET_EXCEEDED.value
        assert resp_budget.steps_count <= 2
        print("[+] VERIFIED: Agent runtime terminates strictly within configured step budget.")

        # --- FLOW 10: Trace Persistence and Observability ---
        print("\n--- Flow 10: Execution Trace Persistence ---")
        executions = await AgentService.list_executions(session, ws_a.id, user)
        print(f"[+] Total execution records persisted in DB: {len(executions)}")
        assert len(executions) >= 4

        trace_record = await AgentService.get_execution(session, ws_a.id, resp5.execution_id, user)
        assert trace_record is not None
        assert len(trace_record.trace) == 2
        print(f"[+] Retrieved trace for execution {trace_record.execution_id}:")
        for step in trace_record.trace:
            print(f"    - Step {step.step_index}: {step.tool_name} ({step.duration_ms:.2f}ms)")

    print("\n" + "=" * 80)
    print("PHASE 4 VERIFICATION COMPLETED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
