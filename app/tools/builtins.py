"""Factory for initializing and registering default IntelligenceOS tools."""

from app.core.config import Settings, get_settings
from app.tools.calculator import CalculatorTool
from app.tools.knowledge_search import KnowledgeSearchTool
from app.tools.registry import ToolRegistry
from app.tools.sql import ReadOnlySQLTool
from app.tools.web_search.base import BaseWebSearchProvider
from app.tools.web_search.tool import WebSearchTool
from app.vectorstore.base import VectorStore


def _build_web_search_provider(settings: Settings) -> BaseWebSearchProvider | None:
    """Instantiates a real web search provider from config, or returns None if unavailable.

    Currently supported values for WEB_SEARCH_PROVIDER:
      - "mock"     → no real provider; tool will surface "Unavailable"
      - "brave"    → Brave Search API (requires BRAVE_SEARCH_API_KEY)
      - "serp"     → SerpAPI (requires SERP_API_KEY)
      - "tavily"   → Tavily AI Search (requires TAVILY_API_KEY)

    Additional providers can be added here without touching the tool itself.
    """
    provider_name = (settings.WEB_SEARCH_PROVIDER or "mock").strip().lower()

    if provider_name == "mock" or not provider_name:
        # Return None → WebSearchTool will mark itself as unavailable
        return None

    # Brave Search
    if provider_name == "brave":
        try:
            from app.tools.web_search.brave import BraveWebSearchProvider  # type: ignore[import]

            api_key = getattr(settings, "BRAVE_SEARCH_API_KEY", None)
            if api_key:
                return BraveWebSearchProvider(api_key=api_key.get_secret_value())
        except ImportError:
            pass

    # Tavily
    if provider_name == "tavily":
        try:
            from app.tools.web_search.tavily import TavilyWebSearchProvider  # type: ignore[import]

            api_key = getattr(settings, "TAVILY_API_KEY", None)
            if api_key:
                return TavilyWebSearchProvider(api_key=api_key.get_secret_value())
        except ImportError:
            pass

    # SerpAPI
    if provider_name == "serp":
        try:
            from app.tools.web_search.serp import SerpWebSearchProvider  # type: ignore[import]

            api_key = getattr(settings, "SERP_API_KEY", None)
            if api_key:
                return SerpWebSearchProvider(api_key=api_key.get_secret_value())
        except ImportError:
            pass

    # Unknown or misconfigured provider → unavailable
    return None


def create_default_registry(
    vector_store: VectorStore | None = None,
    web_search_provider: BaseWebSearchProvider | None = None,
    settings: Settings | None = None,
) -> ToolRegistry:
    """Creates a pre-configured ToolRegistry with all approved Phase 4 tools.

    Args:
        vector_store: Optional pre-constructed VectorStore (used by KnowledgeSearchTool).
        web_search_provider: Optional explicit provider override. When None, the provider
            is resolved from settings. When WEB_SEARCH_PROVIDER is "mock" or unconfigured,
            WebSearchTool will report itself as unavailable rather than returning fake results.
        settings: Optional settings override (defaults to get_settings()).
    """
    cfg = settings or get_settings()
    registry = ToolRegistry()

    # 1. Calculator — safe AST-based arithmetic, always available
    registry.register(CalculatorTool())

    # 2. Knowledge Search — calls real Qdrant retrieval via workspace isolation
    registry.register(KnowledgeSearchTool(vector_store=vector_store))

    # 3. Read-only SQL — mutation-blocked, row-limited, timeout-enforced
    registry.register(ReadOnlySQLTool())

    # 4. Web Search — real provider or honest "Unavailable" (never fake results)
    resolved_provider = web_search_provider or _build_web_search_provider(cfg)
    registry.register(WebSearchTool(provider=resolved_provider))

    return registry
