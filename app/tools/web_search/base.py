"""Web search provider interface and structured search result models."""

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class WebSearchResultItem(BaseModel):
    """Structured search result item."""

    title: str = Field(..., description="Title of the web page.")
    url: str = Field(..., description="URL of the web source.")
    snippet: str = Field(..., description="Summary snippet of the web content.")


class BaseWebSearchProvider(ABC):
    """Abstract interface isolating web search implementations."""

    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> list[WebSearchResultItem]:
        """Performs a web search and returns structured items."""
        pass
