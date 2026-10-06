"""Google Gemini Embedding Provider implementation using google-genai SDK."""

import asyncio

from google import genai
from google.genai import errors

from app.core.logging import get_logger
from app.providers.embedding.base import EmbeddingProvider
from app.providers.embedding.exceptions import (
    EmbeddingAuthenticationError,
    EmbeddingInvalidRequestError,
    EmbeddingProviderError,
    EmbeddingRateLimitError,
    EmbeddingServiceUnavailableError,
)

logger = get_logger("app.providers.embedding.gemini")


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Generates embeddings using Google Gemini API (e.g. text-embedding-004)."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-embedding-001",
        dimension: int = 768,
    ) -> None:
        self.api_key = api_key
        # Automatically map deprecated text-embedding-004 to supported gemini-embedding-001
        if model in ("text-embedding-004", ""):
            model = "gemini-embedding-001"
        self.model = model
        self._dimension = dimension

        if not self.api_key:
            logger.warning("Gemini API key is not configured for embeddings.")
            self._client = None
        else:
            self._client = genai.Client(api_key=self.api_key)

    @property
    def dimension(self) -> int:
        return self._dimension

    def _map_gemini_error(self, exc: Exception) -> EmbeddingProviderError:
        """Translates downstream Google GenAI exceptions into domain embedding errors."""
        msg = str(exc)
        if isinstance(exc, errors.APIError):
            code = getattr(exc, "code", None)
            if code in (401, 403) or "API_KEY_INVALID" in msg or "PERMISSION_DENIED" in msg:
                return EmbeddingAuthenticationError(f"Gemini API authentication failed: {msg}")
            if code == 429 or "RESOURCE_EXHAUSTED" in msg:
                return EmbeddingRateLimitError(f"Gemini embedding quota exceeded: {msg}")
            if code in (400, 422) or "INVALID_ARGUMENT" in msg:
                return EmbeddingInvalidRequestError(f"Invalid embedding request: {msg}")
            if code in (500, 502, 503, 504) or "UNAVAILABLE" in msg:
                return EmbeddingServiceUnavailableError(f"Gemini service unavailable: {msg}")

        return EmbeddingProviderError(f"Unexpected error from Gemini embedding provider: {msg}")

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if not self._client:
            raise EmbeddingAuthenticationError("Gemini API key is not configured.")

        def _call_api() -> list[list[float]]:
            from google.genai import types

            config = None
            if self._dimension:
                config = types.EmbedContentConfig(output_dimensionality=self._dimension)

            response = self._client.models.embed_content(
                model=self.model,
                contents=texts,
                config=config,
            )
            embeddings = getattr(response, "embeddings", [])
            if not embeddings and hasattr(response, "embedding") and response.embedding:
                embeddings = [response.embedding]

            results: list[list[float]] = []
            for item in embeddings:
                values = getattr(item, "values", None)
                if values is not None:
                    results.append(list(values))
            return results

        try:
            return await asyncio.to_thread(_call_api)
        except Exception as exc:
            mapped_exc = self._map_gemini_error(exc)
            logger.error(f"Gemini embedding call failed: {mapped_exc}")
            raise mapped_exc from exc

    async def embed_query(self, text: str) -> list[float]:
        results = await self.embed_texts([text])
        if not results:
            raise EmbeddingProviderError("Failed to generate embedding for query.")
        return results[0]

    async def health_check(self) -> bool:
        if not self._client:
            return False
        try:
            await self.embed_query("health check")
            return True
        except Exception as exc:
            logger.warning(f"Gemini embedding health check failed: {exc}")
            return False
