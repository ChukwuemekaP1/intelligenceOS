"""LangGraph agent orchestration workflow definition with bounded execution."""

import json
import logging
import re
import time
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agent.prompts import (
    AGENT_SYSTEM_PROMPT,
    BUDGET_EXCEEDED_PROMPT,
    build_agent_turn_prompt,
)
from app.agent.state import AgentState, AgentStepRecord
from app.models.agent_execution import ExecutionStatus
from app.providers.llm.base import LLMProvider
from app.schemas.llm import CompletionRequest
from app.tools.base import ToolExecutionContext
from app.tools.registry import ToolRegistry

logger = logging.getLogger("app.agent.graph")


def _clean_json_output(raw_text: str) -> str:
    """Extracts valid JSON payload from potential markdown fences."""
    text = raw_text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def create_agent_graph(
    llm_provider: LLMProvider,
    tool_registry: ToolRegistry,
    context: ToolExecutionContext,
) -> Any:
    """Builds and compiles the bounded LangGraph agent StateGraph."""
    graph_builder = StateGraph(AgentState)

    # 1. Reasoning Node: LLM determines next action or generates final response
    async def reasoning_node(state: AgentState) -> dict[str, Any]:
        step_count = state["step_count"]
        max_steps = state["max_steps"]

        # Check if execution budget was reached
        if step_count >= max_steps:
            logger.info(
                f"Agent step budget reached ({step_count}/{max_steps}). Forcing final synthesis."
            )
            completion_req = CompletionRequest(
                prompt=f"### USER QUERY:\n{state['query']}\n\n{BUDGET_EXCEEDED_PROMPT}",
                system_instruction=AGENT_SYSTEM_PROMPT,
                temperature=0.0,
                max_tokens=1000,
            )
            comp_resp = await llm_provider.generate_text(completion_req)
            cleaned = _clean_json_output(comp_resp.text)
            try:
                parsed = json.loads(cleaned)
                final_text = parsed.get("final_response", comp_resp.text)
            except Exception:
                final_text = comp_resp.text or "Execution budget reached without final answer."

            return {
                "current_thought": "Step budget reached; synthesizing available evidence.",
                "current_action": "final_answer",
                "final_response": final_text,
                "status": ExecutionStatus.BUDGET_EXCEEDED.value,
            }

        # Build turn prompt with authorized tools descriptors and execution history
        authorized_descriptors = tool_registry.get_descriptors(state["allowed_tools"])
        turn_prompt = build_agent_turn_prompt(
            query=state["query"],
            authorized_tools=authorized_descriptors,
            steps=state["steps"],
            history=state.get("history"),
        )

        completion_req = CompletionRequest(
            prompt=turn_prompt,
            system_instruction=AGENT_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=1500,
        )

        comp_resp = await llm_provider.generate_text(completion_req)
        cleaned = _clean_json_output(comp_resp.text)

        thought = ""
        action = "final_answer"
        tool_name = None
        tool_input = None
        final_response = None

        try:
            decision = json.loads(cleaned)
            thought = decision.get("thought", "")
            action = decision.get("action", "final_answer")

            if action == "call_tool":
                tool_name = decision.get("tool_name")
                tool_input = decision.get("tool_input")
            else:
                final_response = decision.get("final_response", comp_resp.text)

        except Exception as parse_err:
            logger.warning(
                f"Failed to parse LLM JSON decision: {parse_err}. "
                "Treating raw text as final answer."
            )
            thought = "Direct response generated."
            action = "final_answer"
            final_response = comp_resp.text

        return {
            "step_count": step_count + 1,
            "current_thought": thought,
            "current_action": action,
            "current_tool_name": tool_name,
            "current_tool_input": tool_input,
            "final_response": final_response,
            "status": (
                ExecutionStatus.COMPLETED.value
                if action == "final_answer"
                else ExecutionStatus.RUNNING.value
            ),
        }

    # 2. Tool Execution Node: Executes selected tool with strict authorization and isolation
    async def tool_execution_node(state: AgentState) -> dict[str, Any]:
        tool_name = state.get("current_tool_name")
        tool_input = state.get("current_tool_input")
        thought = state.get("current_thought", "")
        step_idx = len(state["steps"]) + 1

        if not tool_name:
            # Fallback if no tool was specified
            step_record: AgentStepRecord = {
                "step_index": step_idx,
                "thought": thought,
                "action": "call_tool",
                "tool_name": None,
                "tool_input": None,
                "tool_result": None,
                "error": "No tool specified by reasoning node.",
                "duration_ms": 0.0,
            }
            return {
                "steps": [*state["steps"], step_record],
                "current_tool_name": None,
                "current_tool_input": None,
                "current_tool_result": None,
            }

        start_time = time.perf_counter()
        tool_res = await tool_registry.execute_tool(
            tool_name=tool_name,
            raw_input=tool_input,
            context=context,
            allowed_tools=state["allowed_tools"],
        )
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        step_record = {
            "step_index": step_idx,
            "thought": thought,
            "action": "call_tool",
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_result": tool_res.data if tool_res.success else None,
            "error": tool_res.error if not tool_res.success else None,
            "duration_ms": round(duration_ms, 2),
        }

        # Formatted representation for next reasoning turn
        formatted_result = tool_res.text_summary if tool_res.success else tool_res.error

        return {
            "steps": [*state["steps"], step_record],
            "current_tool_name": None,
            "current_tool_input": None,
            "current_tool_result": formatted_result,
        }

    # 3. Conditional Edge: Determines whether to execute tool or terminate
    def router_edge(state: AgentState) -> str:
        if state.get("current_action") == "final_answer" or state.get("final_response") is not None:
            return END

        if state["step_count"] >= state["max_steps"]:
            # Route back to reasoning_node to force budget exceeded summary
            return "reasoning"

        return "tool_execution"

    # Assemble Graph
    graph_builder.add_node("reasoning", reasoning_node)
    graph_builder.add_node("tool_execution", tool_execution_node)

    graph_builder.add_edge(START, "reasoning")
    graph_builder.add_conditional_edges(
        "reasoning",
        router_edge,
        {
            "tool_execution": "tool_execution",
            "reasoning": "reasoning",
            END: END,
        },
    )
    graph_builder.add_edge("tool_execution", "reasoning")

    return graph_builder.compile()
