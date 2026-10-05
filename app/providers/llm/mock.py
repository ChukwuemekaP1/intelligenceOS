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

        import re

        if self.default_response != "This is a mock LLM completion response.":
            response_text = self.default_response
        else:
            response_text = f"{self.default_response} Echo: {request.prompt[:30]}"
            if "Context Documents:" in request.prompt and "User Question:" in request.prompt:
                try:
                    q_part = request.prompt.split("User Question:")[1].split("Answer strictly")[0].strip()
                    ctx_part = request.prompt.split("Context Documents:")[1].split("User Question:")[0].strip()
                    if ctx_part and "No matching documents" not in ctx_part:
                        words = set(re.findall(r"\w+", q_part.lower())) - {
                            "what", "is", "the", "how", "to", "in", "and", "or", "a", "an", "of", "if", "does", "are"
                        }
                        matched_lines = []
                        for line in ctx_part.splitlines():
                            cleaned = line.strip()
                            if cleaned and not cleaned.startswith("[UNTRUSTED_") and not cleaned.startswith("--- Document"):
                                line_words = set(re.findall(r"\w+", cleaned.lower()))
                                if words & line_words:
                                    matched_lines.append(cleaned)

                        if matched_lines:
                            summary = " ".join(matched_lines[:3])
                            response_text = f"Based on the workspace knowledge base: {summary} [Doc 1]"
                        else:
                            first_meaningful = [
                                l.strip() for l in ctx_part.splitlines()
                                if l.strip() and not l.startswith("[") and not l.startswith("-")
                            ][:2]
                            if first_meaningful:
                                response_text = f"According to the indexed documentation: {' '.join(first_meaningful)} [Doc 1]"
                except Exception:
                    pass

        return CompletionResponse(
            text=response_text,
            model=self.model,
            usage={
                "prompt_tokens": len(request.prompt.split()),
                "completion_tokens": len(response_text.split()),
                "total_tokens": len(request.prompt.split()) + len(response_text.split()),
            },
        )

    async def health_check(self) -> bool:
        return self.is_healthy
