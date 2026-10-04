"""Tests for Phase 4 Tool Registry, Calculator Safety, SQL Guardrails, and Tenancy."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.source import ProcessingStatus, Source, SourceType
from app.tools.base import ToolExecutionContext
from app.tools.builtins import create_default_registry
from app.tools.calculator import CalculatorInput, CalculatorTool
from app.tools.knowledge_search import KnowledgeSearchInput, KnowledgeSearchTool
from app.tools.sql import ReadOnlySQLInput, ReadOnlySQLTool
from app.tools.web_search.base import WebSearchResultItem
from app.tools.web_search.mock import MockWebSearchProvider
from app.tools.web_search.tool import WebSearchInput, WebSearchTool
from app.vectorstore.mock import MockVectorStore
from app.vectorstore.models import VectorPoint


@pytest.mark.asyncio
async def test_tool_registration_and_descriptors():
    registry = create_default_registry()
    tools = registry.list_tools()
    assert len(tools) == 4

    names = {t.name for t in tools}
    assert names == {"calculator", "knowledge_search", "read_only_sql", "web_search"}

    descriptors = registry.get_descriptors()
    assert len(descriptors) == 4
    calc_desc = next(d for d in descriptors if d["name"] == "calculator")
    assert "expression" in calc_desc["parameters"]["properties"]


@pytest.mark.asyncio
async def test_calculator_valid_math():
    tool = CalculatorTool()
    ctx = ToolExecutionContext(workspace_id=uuid.uuid4())

    # Arithmetic & precedence
    res1 = await tool.execute(CalculatorInput(expression="15 * 4 + 10 / 2"), ctx)
    assert res1.success is True
    assert res1.data["result"] == 65

    # Functions
    res2 = await tool.execute(
        CalculatorInput(expression="sqrt(16) + abs(-10) + round(3.14159, 2)"), ctx
    )
    assert res2.success is True
    assert res2.data["result"] == 17.14


@pytest.mark.asyncio
async def test_calculator_safety_rejections():
    tool = CalculatorTool()
    ctx = ToolExecutionContext(workspace_id=uuid.uuid4())

    # Division by zero
    res_div_zero = await tool.execute(CalculatorInput(expression="10 / 0"), ctx)
    assert res_div_zero.success is False
    assert "Division by zero" in res_div_zero.error

    # Arbitrary code execution / imports
    res_exec = await tool.execute(CalculatorInput(expression="__import__('os').system('ls')"), ctx)
    assert res_exec.success is False
    assert "Forbidden variable or identifier" in res_exec.error or "Unsupported" in res_exec.error

    # Attribute access
    res_attr = await tool.execute(CalculatorInput(expression="'hello'.upper()"), ctx)
    assert res_attr.success is False

    # Power denial of service (DoS) cap
    res_pow = await tool.execute(CalculatorInput(expression="999999 ** 999999"), ctx)
    assert res_pow.success is False
    assert "safe computational limits" in res_pow.error


@pytest.mark.asyncio
async def test_read_only_sql_allowed_select(db_session: AsyncSession):
    tool = ReadOnlySQLTool()
    ws_id = uuid.uuid4()
    ctx = ToolExecutionContext(workspace_id=ws_id, session=db_session)

    # Seed a simple source row for structured query
    source = Source(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        source_type=SourceType.PDF.value,
        name="Quarterly_Report.pdf",
        status=ProcessingStatus.COMPLETED.value,
    )
    db_session.add(source)
    await db_session.commit()

    # Valid SELECT query
    res = await tool.execute(ReadOnlySQLInput(query="SELECT name, source_type FROM sources"), ctx)
    assert res.success is True
    assert res.data["row_count"] >= 1
    assert "Quarterly_Report.pdf" in [r["name"] for r in res.data["rows"]]


@pytest.mark.asyncio
async def test_read_only_sql_mutation_blocking(db_session: AsyncSession):
    tool = ReadOnlySQLTool()
    ctx = ToolExecutionContext(workspace_id=uuid.uuid4(), session=db_session)

    # INSERT
    res_ins = await tool.execute(
        ReadOnlySQLInput(query="INSERT INTO sources (id, name) VALUES ('123', 'fake')"), ctx
    )
    assert res_ins.success is False
    assert "Prohibited" in res_ins.error

    # DROP TABLE
    res_drop = await tool.execute(ReadOnlySQLInput(query="DROP TABLE sources"), ctx)
    assert res_drop.success is False
    assert "Prohibited" in res_drop.error

    # UPDATE
    res_upd = await tool.execute(ReadOnlySQLInput(query="UPDATE sources SET name = 'hacked'"), ctx)
    assert res_upd.success is False
    assert "Prohibited" in res_upd.error

    # Multiple statements / Semicolon injection
    res_multi = await tool.execute(
        ReadOnlySQLInput(query="SELECT * FROM sources; DROP TABLE sources"), ctx
    )
    assert res_multi.success is False
    assert "Multiple semicolon-separated" in res_multi.error


@pytest.mark.asyncio
async def test_read_only_sql_disallowed_tables(db_session: AsyncSession):
    tool = ReadOnlySQLTool()
    ctx = ToolExecutionContext(workspace_id=uuid.uuid4(), session=db_session)

    # Prohibited users and credentials tables
    res_users = await tool.execute(ReadOnlySQLInput(query="SELECT * FROM users"), ctx)
    assert res_users.success is False
    assert "Access to internal security, user, or migration tables is prohibited" in res_users.error


@pytest.mark.asyncio
async def test_web_search_with_ssrf_filtering():
    mock_provider = MockWebSearchProvider()
    mock_provider.set_results(
        "fastapi",
        [
            WebSearchResultItem(
                title="FastAPI Documentation",
                url="https://fastapi.tiangolo.com",
                snippet="Modern, high performance web framework for building APIs with Python.",
            ),
            # Malicious/internal URL that must be blocked by SSRF
            WebSearchResultItem(
                title="Internal Cloud Metadata",
                url="http://169.254.169.254/latest/meta-data/",
                snippet="Sensitive internal cloud metadata.",
            ),
            WebSearchResultItem(
                title="Local Server Loopback",
                url="http://127.0.0.1:8000/internal-admin",
                snippet="Private admin dashboard.",
            ),
        ],
    )

    tool = WebSearchTool(provider=mock_provider)
    ctx = ToolExecutionContext(workspace_id=uuid.uuid4())

    res = await tool.execute(WebSearchInput(query="fastapi"), ctx)
    assert res.success is True
    # The two internal SSRF URLs must have been purged
    assert res.data["results_found"] == 1
    assert res.data["results"][0]["url"] == "https://fastapi.tiangolo.com"


@pytest.mark.asyncio
async def test_knowledge_search_workspace_isolation(db_session: AsyncSession):
    vstore = MockVectorStore()
    tool = KnowledgeSearchTool(vector_store=vstore)

    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()

    # Seed doc in Workspace A
    src_a = Source(
        id=uuid.uuid4(),
        workspace_id=ws_a,
        source_type=SourceType.PDF.value,
        name="Alpha_Manual.pdf",
        status=ProcessingStatus.COMPLETED.value,
    )
    db_session.add(src_a)
    doc_a = Document(id=uuid.uuid4(), source_id=src_a.id, workspace_id=ws_a)
    db_session.add(doc_a)
    ver_a = DocumentVersion(id=uuid.uuid4(), document_id=doc_a.id, version_number=1)
    db_session.add(ver_a)
    chunk_a = Chunk(
        id=uuid.uuid4(),
        document_version_id=ver_a.id,
        workspace_id=ws_a,
        chunk_index=0,
        content="Alpha project uses quantum encryption algorithms.",
        metadata_={"page_number": 1, "source_name": "Alpha_Manual.pdf"},
    )
    db_session.add(chunk_a)

    # Seed doc in Workspace B
    src_b = Source(
        id=uuid.uuid4(),
        workspace_id=ws_b,
        source_type=SourceType.PDF.value,
        name="Beta_Secret.pdf",
        status=ProcessingStatus.COMPLETED.value,
    )
    db_session.add(src_b)
    doc_b = Document(id=uuid.uuid4(), source_id=src_b.id, workspace_id=ws_b)
    db_session.add(doc_b)
    ver_b = DocumentVersion(id=uuid.uuid4(), document_id=doc_b.id, version_number=1)
    db_session.add(ver_b)
    chunk_b = Chunk(
        id=uuid.uuid4(),
        document_version_id=ver_b.id,
        workspace_id=ws_b,
        chunk_index=0,
        content="Beta secret stealth aircraft codename BlackBird.",
        metadata_={"page_number": 1, "source_name": "Beta_Secret.pdf"},
    )
    db_session.add(chunk_b)
    await db_session.commit()

    # Index points in MockVectorStore
    vec = [0.1] * 768
    await vstore.upsert_points(
        workspace_id=ws_a,
        points=[
            VectorPoint(
                id=chunk_a.id,
                vector=vec,
                payload={
                    "workspace_id": str(ws_a),
                    "chunk_id": str(chunk_a.id),
                    "source_name": "Alpha_Manual.pdf",
                    "text": chunk_a.content,
                    "page_number": 1,
                    "chunk_index": 0,
                },
            )
        ],
    )
    await vstore.upsert_points(
        workspace_id=ws_b,
        points=[
            VectorPoint(
                id=chunk_b.id,
                vector=vec,
                payload={
                    "workspace_id": str(ws_b),
                    "chunk_id": str(chunk_b.id),
                    "source_name": "Beta_Secret.pdf",
                    "text": chunk_b.content,
                    "page_number": 1,
                    "chunk_index": 0,
                },
            )
        ],
    )

    # Search in Workspace A
    ctx_a = ToolExecutionContext(workspace_id=ws_a, session=db_session)
    res_a = await tool.execute(KnowledgeSearchInput(query="encryption"), ctx_a)
    assert res_a.success is True
    assert res_a.data["chunks_found"] == 1
    assert "Alpha_Manual.pdf" in res_a.text_summary
    assert "Beta_Secret.pdf" not in res_a.text_summary

    # Search in Workspace A for Workspace B's secret
    res_leak = await tool.execute(KnowledgeSearchInput(query="BlackBird"), ctx_a)
    assert "Beta_Secret.pdf" not in res_leak.text_summary
    assert all("BlackBird" not in r["content"] for r in res_leak.data["results"])


@pytest.mark.asyncio
async def test_tool_registry_authorization_enforcement():
    registry = create_default_registry()
    ctx = ToolExecutionContext(workspace_id=uuid.uuid4())

    # Attempting to execute read_only_sql when only calculator is allowed
    allowed = ["calculator"]
    res = await registry.execute_tool(
        tool_name="read_only_sql",
        raw_input={"query": "SELECT 1"},
        context=ctx,
        allowed_tools=allowed,
    )
    assert res.success is False
    assert "Permission Denied" in res.error
    assert "not authorized" in res.error


@pytest.mark.asyncio
async def test_tool_registry_input_validation():
    registry = create_default_registry()
    ctx = ToolExecutionContext(workspace_id=uuid.uuid4())

    # Passing malformed input (wrong data type or missing fields)
    res = await registry.execute_tool(
        tool_name="calculator",
        raw_input={"wrong_field": 123},
        context=ctx,
        allowed_tools=["calculator"],
    )
    assert res.success is False
    assert "Input validation error" in res.error
