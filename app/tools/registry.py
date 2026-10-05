"""Tool registry with application-level authorization and safe execution boundaries."""

import logging
from typing import Any

from pydantic import ValidationError

from app.tools.base import BaseTool, ToolExecutionContext, ToolResult

logger = logging.getLogger("app.tools.registry")


class ToolRegistry:
    """Manages registered tools, enforces application authorization, and executes tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Registers a tool instance under its stable name."""
        if tool.name in self._tools:
            logger.warning(f"Overwriting registered tool '{tool.name}'.")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool '{tool.name}'.")

    def get(self, name: str) -> BaseTool | None:
        """Retrieves a registered tool by name."""
        return self._tools.get(name)

    def list_tools(self, allowed_names: list[str] | None = None) -> list[BaseTool]:
        """Lists registered tools, optionally filtered by authorized names."""
        if allowed_names is None:
            return list(self._tools.values())
        return [t for name, t in self._tools.items() if name in allowed_names]

    def get_descriptors(self, allowed_names: list[str] | None = None) -> list[dict[str, Any]]:
        """Returns JSON schema descriptors of authorized tools for LLM reasoning prompts."""
        return [t.to_descriptor() for t in self.list_tools(allowed_names)]

    def is_authorized(self, tool_name: str, allowed_tools: list[str]) -> bool:
        """Checks if a tool name is authorized by application policy."""
        return tool_name in allowed_tools

    async def execute_tool(
        self,
        tool_name: str,
        raw_input: Any,
        context: ToolExecutionContext,
        allowed_tools: list[str],
    ) -> ToolResult:
        """Validates authorization, validates input schema, and executes the tool safely."""
        # 1. Application-level authorization check
        if not self.is_authorized(tool_name, allowed_tools):
            logger.warning(
                f"Unauthorized tool invocation attempt: '{tool_name}' (allowed: {allowed_tools})"
            )
            return ToolResult(
                success=False,
                error=(
                    f"Permission Denied: Tool '{tool_name}' is not authorized "
                    "for this workspace or user session."
                ),
                text_summary=f"Tool '{tool_name}' is unauthorized.",
            )

        # 2. Tool existence check
        tool = self.get(tool_name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' does not exist in registry.",
                text_summary=f"Tool '{tool_name}' not found.",
            )

        # 3. Input schema validation
        try:
            if isinstance(raw_input, dict):
                validated_input = tool.input_schema.model_validate(raw_input)
            elif isinstance(raw_input, str):
                # Handle single-field string inputs if schema has a primary field
                fields = list(tool.input_schema.model_fields.keys())
                if len(fields) == 1:
                    validated_input = tool.input_schema.model_validate({fields[0]: raw_input})
                else:
                    return ToolResult(
                        success=False,
                        error=(
                            f"Invalid input: expected JSON object matching "
                            f"{tool.input_schema.__name__}, got string."
                        ),
                        text_summary="Invalid tool input format.",
                    )
            else:
                validated_input = tool.input_schema.model_validate(raw_input)
        except ValidationError as val_err:
            logger.warning(f"Tool input validation error for '{tool_name}': {val_err}")
            return ToolResult(
                success=False,
                error=f"Input validation error for tool '{tool_name}': {val_err.errors()}",
                text_summary=f"Validation failed for tool '{tool_name}'.",
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Unexpected input formatting error for tool '{tool_name}': {exc}",
                text_summary="Invalid tool input.",
            )

        # 4. Safe tool execution
        try:
            res = await tool.execute(validated_input, context)
            if not res.success:
                from app.observability.metrics import record_agent_tool_failure

                record_agent_tool_failure(tool_name, "tool_execution_error")
            return res
        except Exception as exc:
            logger.exception(f"Unhandled exception during tool '{tool_name}' execution: {exc}")
            from app.observability.metrics import record_agent_tool_failure

            record_agent_tool_failure(tool_name, type(exc).__name__)
            # Ensure internal secrets or DB credentials are never leaked
            err_details = f"{type(exc).__name__}: {str(exc)[:200]}"
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' encountered an execution error: {err_details}",
                text_summary=f"Error executing '{tool_name}'.",
            )
