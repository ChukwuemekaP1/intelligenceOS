"""Mock web search provider for deterministic and safe agent execution."""

from app.tools.web_search.base import BaseWebSearchProvider, WebSearchResultItem


class MockWebSearchProvider(BaseWebSearchProvider):
    """Simulated web search provider with deterministic responses."""

    def __init__(
        self, predefined_results: dict[str, list[WebSearchResultItem]] | None = None
    ) -> None:
        self._predefined = predefined_results or {}

    def set_results(self, query: str, results: list[WebSearchResultItem]) -> None:
        """Seeds predefined results for a specific query."""
        self._predefined[query.strip().lower()] = results

    async def search(self, query: str, max_results: int = 5) -> list[WebSearchResultItem]:
        q_norm = query.strip().lower()

        # 1. Exact or partial match in predefined results
        for key, items in self._predefined.items():
            if key in q_norm or q_norm in key:
                return items[:max_results]

        # 2. Heuristic simulated results based on query terms
        return [
            WebSearchResultItem(
                title=f"Web Overview: {query.capitalize()}",
                url=f"https://en.wikipedia.org/wiki/{query.replace(' ', '_')}",
                snippet=f"Overview and documentation regarding {query}.",
            ),
            WebSearchResultItem(
                title=f"Latest Updates and News on {query.capitalize()}",
                url=f"https://news.example.com/search?q={query.replace(' ', '+')}",
                snippet=f"Recent developments and updates concerning {query}.",
            ),
            WebSearchResultItem(
                title=f"{query.capitalize()} - Official Guide & Documentation",
                url=f"https://docs.example.org/{query.replace(' ', '-').lower()}",
                snippet=f"Authoritative specifications and guides for {query}.",
            ),
        ][:max_results]
