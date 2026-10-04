class LLMProviderError(Exception):
    """Base exception for all LLM provider failures."""

    def __init__(
        self, message: str, provider: str = "unknown", original_error: Exception | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.original_error = original_error

    def __str__(self) -> str:
        return f"[{self.provider}] {self.message}"


class LLMAuthenticationError(LLMProviderError):
    """Raised when authentication with the LLM provider fails (invalid/missing key)."""

    pass


class LLMRateLimitError(LLMProviderError):
    """Raised when the LLM provider rate limit or quota is exceeded."""

    pass


class LLMInvalidRequestError(LLMProviderError):
    """Raised when an invalid request/parameter is sent to the LLM provider."""

    pass


class LLMServiceUnavailableError(LLMProviderError):
    """Raised when the LLM provider service is temporarily unavailable or timed out."""

    pass
