"""Base tool abstractions, execution context, and result structures."""

import uuid
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class ToolExecutionContext(BaseModel):
    """Execution context injected into tools for security, DB sessions, and tenancy."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    workspace_id: uuid.UUID
    user_id: uuid.UUID | None = None
    user: User | None = None
    session: AsyncSession | None = None
    extra: dict[str, Any] = {}


class ToolResult(BaseModel):
    """Standardized result returned by any tool execution."""

    success: bool
    data: Any = None
    error: str | None = None
    text_summary: str

    def to_untrusted_block(self, tool_name: str) -> str:
        """Encapsulates tool output in untrusted data boundaries for prompt injection defense."""
        status_label = "SUCCESS" if self.success else "ERROR"
        content = self.text_summary if self.success else (self.error or "Unknown tool error")
        return (
            f'[UNTRUSTED_TOOL_RESULT_START tool="{tool_name}" status="{status_label}"]\n'
            f"{content}\n"
            f'[UNTRUSTED_TOOL_RESULT_END tool="{tool_name}"]'
        )


class BaseTool(ABC):
    """Abstract base class for all tools registered in the agent runtime."""

    name: str
    description: str
    input_schema: type[BaseModel]
    required_permissions: list[str] = []

    @abstractmethod
    async def execute(self, input_data: BaseModel, context: ToolExecutionContext) -> ToolResult:
        """Executes the tool logic with strict tenancy and security controls."""
        pass

    def get_json_schema(self) -> dict[str, Any]:
        """Returns the JSON schema describing the tool parameters for the agent."""
        return self.input_schema.model_json_schema()

    def to_descriptor(self) -> dict[str, Any]:
        """Provides a complete descriptor of the tool for prompts or catalog introspection."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.get_json_schema(),
            "required_permissions": self.required_permissions,
        }
