"""Exceptions for embedding provider implementations."""


class EmbeddingProviderError(Exception):
    """Base exception for all embedding provider failures."""

    pass


class EmbeddingAuthenticationError(EmbeddingProviderError):
    """Raised when provider credentials are invalid or absent."""

    pass


class EmbeddingRateLimitError(EmbeddingProviderError):
    """Raised when rate limits or quotas are exceeded."""

    pass


class EmbeddingInvalidRequestError(EmbeddingProviderError):
    """Raised when request payload or parameters are invalid."""

    pass


class EmbeddingServiceUnavailableError(EmbeddingProviderError):
    """Raised when downstream provider service is unreachable or timing out."""

    pass
