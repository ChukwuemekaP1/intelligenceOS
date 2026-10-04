from app.core.config import Settings, get_settings
from app.providers.llm.base import LLMProvider
from app.providers.llm.gemini import GeminiProvider
from app.providers.llm.mock import MockLLMProvider


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    """Factory that returns the configured LLM provider instance."""
    if settings is None:
        settings = get_settings()

    if settings.LLM_PROVIDER == "mock":
        return MockLLMProvider()

    api_key_val = settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else None
    return GeminiProvider(api_key=api_key_val, model=settings.GEMINI_MODEL)
