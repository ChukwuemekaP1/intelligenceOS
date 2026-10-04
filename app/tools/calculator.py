"""Safe mathematical calculator tool using AST analysis without eval()."""

import ast
import math
from typing import Any

from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolExecutionContext, ToolResult

SAFE_MATH_NAMES: dict[str, Any] = {
    # Constants
    "pi": math.pi,
    "e": math.e,
    # Functions
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "pow": math.pow,
    "log": math.log,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "floor": math.floor,
    "ceil": math.ceil,
}


class CalculatorInput(BaseModel):
    """Input payload for mathematical expression evaluation."""

    expression: str = Field(
        ...,
        description="The mathematical expression to evaluate (e.g., '15 * 4 + sqrt(16)').",
        max_length=500,
    )


class SafeMathEvaluator(ast.NodeVisitor):
    """AST visitor that evaluates only strictly whitelisted arithmetic and math functions."""

    def visit(self, node: ast.AST) -> Any:
        method = "visit_" + node.__class__.__name__
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node: ast.AST) -> Any:
        raise ValueError(
            f"Unsupported or dangerous syntax in expression: {node.__class__.__name__}"
        )

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")

    # Backward compatibility for older AST representations
    def visit_Num(self, node: Any) -> Any:
        return node.n

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        val = self.visit(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +val
        if isinstance(node.op, ast.USub):
            return -val
        raise ValueError(f"Unsupported unary operator: {node.op.__class__.__name__}")

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        left = self.visit(node.left)
        right = self.visit(node.right)

        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ZeroDivisionError("Division by zero in mathematical expression.")
            return left / right
        if isinstance(node.op, ast.FloorDiv):
            if right == 0:
                raise ZeroDivisionError("Division by zero in mathematical expression.")
            return left // right
        if isinstance(node.op, ast.Mod):
            if right == 0:
                raise ZeroDivisionError("Modulo by zero in mathematical expression.")
            return left % right
        if isinstance(node.op, ast.Pow):
            # Guard against resource exhaustion (DoS) via massive exponents
            if abs(right) > 100 or (abs(left) > 1000 and right > 4):
                raise ValueError("Exponent or base exceeds safe computational limits.")
            return left**right

        raise ValueError(f"Unsupported binary operator: {node.op.__class__.__name__}")

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id in SAFE_MATH_NAMES:
            return SAFE_MATH_NAMES[node.id]
        raise ValueError(f"Forbidden variable or identifier: '{node.id}'")

    def visit_Call(self, node: ast.Call) -> Any:
        func = self.visit(node.func)
        if not callable(func):
            raise ValueError(f"Expression target '{node.func}' is not callable.")

        args = [self.visit(arg) for arg in node.args]
        return func(*args)


class CalculatorTool(BaseTool):
    """Safely evaluates mathematical expressions without arbitrary code execution."""

    name = "calculator"
    description = (
        "Calculates mathematical and arithmetic expressions safely. "
        "Supports operators (+, -, *, /, //, %, **) and math functions "
        "(sqrt, abs, round, min, max, log, sin, cos, tan, floor, ceil, pi, e). "
        "Input should be a mathematical string expression."
    )
    input_schema = CalculatorInput
    required_permissions = []

    async def execute(
        self, input_data: CalculatorInput, context: ToolExecutionContext
    ) -> ToolResult:
        expr = input_data.expression.strip()
        if not expr:
            return ToolResult(
                success=False,
                error="Empty mathematical expression provided.",
                text_summary="Calculator error: empty expression.",
            )

        try:
            tree = ast.parse(expr, mode="eval")
            evaluator = SafeMathEvaluator()
            result = evaluator.visit(tree)

            # Round float values cleanly if they are exact integers
            if isinstance(result, float) and result.is_integer():
                formatted_result = int(result)
            elif isinstance(result, float):
                formatted_result = round(result, 6)
            else:
                formatted_result = result

            return ToolResult(
                success=True,
                data={"expression": expr, "result": formatted_result},
                text_summary=f"{expr} = {formatted_result}",
            )
        except ZeroDivisionError as zde:
            return ToolResult(
                success=False,
                error=f"Math error: {zde}",
                text_summary=f"Calculator error: {zde}",
            )
        except (ValueError, SyntaxError) as err:
            return ToolResult(
                success=False,
                error=f"Calculation rejected: {err}",
                text_summary=f"Calculator error: {err}",
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"Calculation failed: {exc}",
                text_summary=f"Calculator error: {exc}",
            )
