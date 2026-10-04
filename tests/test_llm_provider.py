from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.providers.llm import (
    GeminiProvider,
    LLMAuthenticationError,
    LLMInvalidRequestError,
    LLMRateLimitError,
    LLMServiceUnavailableError,
    MockLLMProvider,
    get_llm_provider,
)
from app.schemas.llm import CompletionRequest


@pytest.mark.asyncio
async def test_mock_llm_provider_generation() -> None:
    mock_provider = MockLLMProvider(default_response="Mocked reply.")
    req = CompletionRequest(prompt="Hello IntelligenceOS")
    resp = await mock_provider.generate_text(req)

    assert "Mocked reply." in resp.text
    assert resp.model == "mock-model"
    assert len(mock_provider.call_history) == 1
    assert mock_provider.call_history[0]["prompt"] == "Hello IntelligenceOS"


@pytest.mark.asyncio
async def test_mock_llm_provider_health_check() -> None:
    provider = MockLLMProvider(is_healthy=True)
    assert await provider.health_check() is True

    provider.is_healthy = False
    assert await provider.health_check() is False


@pytest.mark.asyncio
async def test_mock_llm_provider_error_raising() -> None:
    provider = MockLLMProvider(error_to_raise=LLMRateLimitError("Quota limit hit", provider="mock"))
    req = CompletionRequest(prompt="Should fail")
    with pytest.raises(LLMRateLimitError) as exc_info:
        await provider.generate_text(req)
    assert "Quota limit hit" in str(exc_info.value)


def test_gemini_provider_missing_key() -> None:
    with pytest.raises(LLMAuthenticationError):
        GeminiProvider(api_key=None)

    with pytest.raises(LLMAuthenticationError):
        GeminiProvider(api_key="")

    with pytest.raises(LLMAuthenticationError):
        GeminiProvider(api_key="your-gemini-api-key-here")


@pytest.mark.asyncio
async def test_gemini_provider_successful_generation() -> None:
    provider = GeminiProvider(api_key="valid-test-key", model="gemini-2.5-flash")

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Generated text from Gemini."
    mock_response.usage_metadata.prompt_token_count = 5
    mock_response.usage_metadata.candidates_token_count = 8
    mock_response.usage_metadata.total_token_count = 13

    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
    provider._client = mock_client

    req = CompletionRequest(prompt="Tell me about AI", temperature=0.5)
    resp = await provider.generate_text(req)

    assert resp.text == "Generated text from Gemini."
    assert resp.model == "gemini-2.5-flash"
    assert resp.usage["total_tokens"] == 13


@pytest.mark.asyncio
async def test_gemini_provider_error_normalization() -> None:
    provider = GeminiProvider(api_key="valid-test-key")
    provider._client = MagicMock()

    class MockAPIError(Exception):
        def __init__(self, code: int, message: str) -> None:
            self.code = code
            self.message = message

    # Mock errors.APIError in google.genai
    with patch("google.genai.errors.APIError", MockAPIError):
        # 401 Authentication Error
        provider._client.aio.models.generate_content = AsyncMock(
            side_effect=MockAPIError(401, "API_KEY_INVALID")
        )
        with pytest.raises(LLMAuthenticationError) as exc:
            await provider.generate_text(CompletionRequest(prompt="test"))
        assert "API_KEY_INVALID" in str(exc.value)

        # 429 Rate Limit
        provider._client.aio.models.generate_content = AsyncMock(
            side_effect=MockAPIError(429, "Resource has been exhausted")
        )
        with pytest.raises(LLMRateLimitError) as exc:
            await provider.generate_text(CompletionRequest(prompt="test"))
        assert "exhausted" in str(exc.value)

        # 400 Invalid Request
        provider._client.aio.models.generate_content = AsyncMock(
            side_effect=MockAPIError(400, "Invalid argument")
        )
        with pytest.raises(LLMInvalidRequestError) as exc:
            await provider.generate_text(CompletionRequest(prompt="test"))
        assert "Invalid argument" in str(exc.value)

        # 503 Service Unavailable
        provider._client.aio.models.generate_content = AsyncMock(
            side_effect=MockAPIError(503, "Service unavailable")
        )
        with pytest.raises(LLMServiceUnavailableError) as exc:
            await provider.generate_text(CompletionRequest(prompt="test"))
        assert "Service unavailable" in str(exc.value)


def test_llm_factory() -> None:
    mock_settings = Settings(
        SECRET_KEY="dev-secret-key-32-characters-minimum-for-intelligence-os",
        LLM_PROVIDER="mock",
    )
    provider = get_llm_provider(mock_settings)
    assert isinstance(provider, MockLLMProvider)

    gemini_settings = Settings(
        SECRET_KEY="dev-secret-key-32-characters-minimum-for-intelligence-os",
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY=SecretStr("my-valid-api-key"),
    )
    gemini_prov = get_llm_provider(gemini_settings)
    assert isinstance(gemini_prov, GeminiProvider)
