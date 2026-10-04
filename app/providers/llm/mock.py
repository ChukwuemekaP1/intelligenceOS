from typing import Any

from app.providers.llm.base import LLMProvider
from app.schemas.llm import CompletionRequest, CompletionResponse


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for local development and automated testing."""

    def __init__(
        self,
        default_response: str = "This is a mock LLM completion response.",
        model: str = "mock-model",
        error_to_raise: Exception | None = None,
        is_healthy: bool = True,
    ) -> None:
        self.default_response = default_response
        self.model = model
        self.error_to_raise = error_to_raise
        self.is_healthy = is_healthy
        self.call_history: list[dict[str, Any]] = []

    async def generate_text(self, request: CompletionRequest) -> CompletionResponse:
        self.call_history.append(
            {
                "prompt": request.prompt,
                "system_instruction": request.system_instruction,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            }
        )

        if self.error_to_raise:
            raise self.error_to_raise

        return CompletionResponse(
            text=f"{self.default_response} Echo: {request.prompt[:30]}",
            model=self.model,
            usage={
                "prompt_tokens": len(request.prompt.split()),
                "completion_tokens": 10,
                "total_tokens": len(request.prompt.split()) + 10,
            },
        )

    async def health_check(self) -> bool:
        return self.is_healthy
