from pydantic import BaseModel, Field


class CompletionRequest(BaseModel):
    prompt: str = Field(min_length=1, description="Prompt text to generate from")
    system_instruction: str | None = Field(default=None, description="Optional system instructions")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int | None = Field(default=None, gt=0, description="Max tokens to generate")


class CompletionResponse(BaseModel):
    text: str = Field(description="Generated text response")
    model: str = Field(description="Model used for generation")
    usage: dict[str, int] | None = Field(
        default=None, description="Token usage metrics if available"
    )
