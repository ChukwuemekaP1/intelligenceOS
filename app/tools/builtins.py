"""Factory for initializing and registering default IntelligenceOS tools."""

from app.tools.calculator import CalculatorTool
from app.tools.knowledge_search import KnowledgeSearchTool
from app.tools.registry import ToolRegistry
from app.tools.sql import ReadOnlySQLTool
from app.tools.web_search.base import BaseWebSearchProvider
from app.tools.web_search.tool import WebSearchTool
from app.vectorstore.base import VectorStore


def create_default_registry(
    vector_store: VectorStore | None = None,
    web_search_provider: BaseWebSearchProvider | None = None,
) -> ToolRegistry:
    """Creates a pre-configured ToolRegistry with all approved Phase 4 tools."""
    registry = ToolRegistry()

    # 1. Calculator
    registry.register(CalculatorTool())

    # 2. Knowledge Search
    registry.register(KnowledgeSearchTool(vector_store=vector_store))

    # 3. Read-only SQL
    registry.register(ReadOnlySQLTool())

    # 4. Web Search
    registry.register(WebSearchTool(provider=web_search_provider))

    return registry
