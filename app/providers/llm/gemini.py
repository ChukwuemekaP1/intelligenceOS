import asyncio
import logging
from typing import Any

from app.providers.llm.base import LLMProvider
from app.providers.llm.exceptions import (
    LLMAuthenticationError,
    LLMInvalidRequestError,
    LLMProviderError,
    LLMRateLimitError,
    LLMServiceUnavailableError,
)
from app.schemas.llm import CompletionRequest, CompletionResponse

logger = logging.getLogger("app.providers.gemini")


class GeminiProvider(LLMProvider):
    """Google Gemini LLM provider implementation using the official google-genai SDK."""

    def __init__(self, api_key: str | None, model: str = "gemini-2.5-flash") -> None:
        if not api_key or api_key.strip() == "" or api_key == "your-gemini-api-key-here":
            raise LLMAuthenticationError(
                message="Gemini API key is missing or not configured.",
                provider="gemini",
            )
        self._api_key = api_key
        self._model = model
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from google import genai

                self._client = genai.Client(api_key=self._api_key)
            except Exception as exc:
                raise LLMProviderError(
                    message=f"Failed to initialize Gemini client: {exc}",
                    provider="gemini",
                    original_error=exc,
                ) from exc
        return self._client

    async def generate_text(self, request: CompletionRequest) -> CompletionResponse:
        client = self._get_client()
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            temperature=request.temperature,
            max_output_tokens=request.max_tokens,
            system_instruction=request.system_instruction,
        )

        max_retries = 3
        backoff_seconds = 1.5

        for attempt in range(max_retries):
            try:
                response = await client.aio.models.generate_content(
                    model=self._model,
                    contents=request.prompt,
                    config=config,
                )

                text_output = response.text or ""

                # Extract usage if present
                usage_dict = None
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    usage_dict = {
                        "prompt_tokens": getattr(response.usage_metadata, "prompt_token_count", 0),
                        "completion_tokens": getattr(
                            response.usage_metadata, "candidates_token_count", 0
                        ),
                        "total_tokens": getattr(response.usage_metadata, "total_token_count", 0),
                    }

                return CompletionResponse(
                    text=text_output,
                    model=self._model,
                    usage=usage_dict,
                )

            except Exception as exc:
                is_transient = False
                if isinstance(exc, errors.APIError):
                    code = getattr(exc, "code", None)
                    if code in (429, 500, 502, 503, 504):
                        is_transient = True

                if is_transient and attempt < max_retries - 1:
                    logger.warning(
                        "Gemini transient error on attempt %d: %s. Retrying in %.1fs...",
                        attempt + 1,
                        exc,
                        backoff_seconds,
                    )
                    await asyncio.sleep(backoff_seconds)
                    backoff_seconds *= 2.0
                    continue

                self._handle_exception(exc)

    async def health_check(self) -> bool:
        """Verifies Gemini client can be initialized and pinged."""
        try:
            client = self._get_client()
            # Lightweight verification
            return client is not None
        except Exception:
            return False

    def _handle_exception(self, exc: Exception) -> None:
        from google.genai import errors

        if isinstance(exc, errors.APIError):
            code = getattr(exc, "code", None)
            message = getattr(exc, "message", str(exc))

            if code in (401, 403):
                raise LLMAuthenticationError(
                    message=f"Gemini authentication failed: {message}",
                    provider="gemini",
                    original_error=exc,
                ) from exc
            if code == 429:
                raise LLMRateLimitError(
                    message=f"Gemini rate limit or quota exceeded: {message}",
                    provider="gemini",
                    original_error=exc,
                ) from exc
            if code == 400:
                raise LLMInvalidRequestError(
                    message=f"Invalid request to Gemini: {message}",
                    provider="gemini",
                    original_error=exc,
                ) from exc
            if code in (500, 502, 503, 504):
                raise LLMServiceUnavailableError(
                    message=f"Gemini service unavailable: {message}",
                    provider="gemini",
                    original_error=exc,
                ) from exc

        if isinstance(exc, (LLMProviderError,)):
            raise exc

        raise LLMProviderError(
            message=f"Gemini request failed: {exc}",
            provider="gemini",
            original_error=exc,
        ) from exc
