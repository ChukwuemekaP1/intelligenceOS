from abc import ABC, abstractmethod

from app.schemas.llm import CompletionRequest, CompletionResponse


class LLMProvider(ABC):
    """Abstract interface for LLM provider implementations."""

    @abstractmethod
    async def generate_text(self, request: CompletionRequest) -> CompletionResponse:
        """Generates a text completion for the provided request.

        Raises:
            LLMAuthenticationError: When credentials are invalid or missing.
            LLMRateLimitError: When quota or rate limits are exceeded.
            LLMInvalidRequestError: When request parameters are malformed.
            LLMServiceUnavailableError: When downstream provider is down/timed out.
            LLMProviderError: On any other provider-specific error.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Checks if the provider is reachable and operational."""
        pass
