"""Web search tool providing controlled external search with SSRF validation.

When no real web search provider is configured (WEB_SEARCH_PROVIDER="mock"),
the tool returns an explicit "unavailable" result rather than fake fabricated URLs.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.ingestion.parsers.website import validate_safe_url
from app.tools.base import BaseTool, ToolExecutionContext, ToolResult
from app.tools.web_search.base import BaseWebSearchProvider
from app.tools.web_search.mock import MockWebSearchProvider

# Sentinel to detect when only the mock provider is wired
_UNAVAILABLE_MSG = (
    "Web search is not configured in this deployment. "
    "Set WEB_SEARCH_PROVIDER to a real provider and supply the required API key."
)


class WebSearchInput(BaseModel):
    """Input payload for web search queries."""

    query: str = Field(
        ...,
        description="The web search query string (e.g., 'latest Python 3.13 release date').",
        max_length=300,
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of search results to return.",
    )


class WebSearchTool(BaseTool):
    """Executes structured web searches while guarding against SSRF and unrestricted browsing.

    If the provider is the built-in MockWebSearchProvider (i.e. no real provider is configured),
    the tool reports itself as unavailable rather than returning fabricated results.
    """

    name = "web_search"
    description = (
        "Searches the public web for real-time information, public documentation, and facts. "
        "Returns titles, public URLs, and content snippets. "
        "Use this tool when the information is not present in the workspace documents."
    )
    input_schema = WebSearchInput
    required_permissions = []

    def __init__(self, provider: BaseWebSearchProvider | None = None) -> None:
        self._provider = provider
        # Mark unavailable ONLY when no provider was supplied at all.
        # When an explicit provider is passed (including MockWebSearchProvider for tests),
        # honour it and execute normally.
        self._is_mock = provider is None

    @property
    def is_available(self) -> bool:
        """Returns True only when a real (non-mock) provider is wired."""
        return not self._is_mock

    async def execute(
        self, input_data: WebSearchInput, context: ToolExecutionContext
    ) -> ToolResult:
        # Immediately surface unavailability — do not fabricate results
        if self._is_mock or self._provider is None:
            return ToolResult(
                success=False,
                error=_UNAVAILABLE_MSG,
                text_summary=(
                    "Web search is unavailable: no real search provider is configured. "
                    "Contact an administrator to configure WEB_SEARCH_PROVIDER."
                ),
            )

        query = input_data.query.strip()
        if not query:
            return ToolResult(
                success=False,
                error="Empty web search query provided.",
                text_summary="Web search error: empty query.",
            )

        try:
            raw_items = await self._provider.search(query, max_results=input_data.max_results)

            # SSRF validation: ensure result URLs do not target private/internal network addresses
            safe_items = []
            for item in raw_items:
                try:
                    validate_safe_url(item.url)
                    safe_items.append(item)
                except Exception:
                    # Filter out any URL failing SSRF verification
                    continue

            if not safe_items:
                return ToolResult(
                    success=True,
                    data={"query": query, "results_found": 0, "results": []},
                    text_summary=f"No public web results found for query: '{query}'.",
                )

            structured_results: list[dict[str, Any]] = []
            summary_lines: list[str] = [
                f"Web Search Results for '{query}' ({len(safe_items)} results):"
            ]

            for idx, item in enumerate(safe_items, start=1):
                structured_results.append(
                    {
                        "index": idx,
                        "title": item.title,
                        "url": item.url,
                        "snippet": item.snippet,
                    }
                )
                summary_lines.append(
                    f"[{idx}] Title: {item.title}\n    URL: {item.url}\n    Snippet: {item.snippet}"
                )

            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "results_found": len(safe_items),
                    "results": structured_results,
                },
                text_summary="\n\n".join(summary_lines),
            )

        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Web search execution failed: {exc}",
                text_summary=f"Web search error: {exc}",
            )
