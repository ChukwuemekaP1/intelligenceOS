"""Controlled read-only SQL tool with validation, timeouts, and table scope protection."""

import asyncio
import re
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.config import get_settings
from app.tools.base import BaseTool, ToolExecutionContext, ToolResult

PROHIBITED_KEYWORDS: set[str] = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "REPLACE",
    "GRANT",
    "REVOKE",
    "PRAGMA",
    "ATTACH",
    "DETACH",
    "VACUUM",
    "REINDEX",
    "COPY",
    "MERGE",
    "EXEC",
    "EXECUTE",
    "CALL",
    "LOCK",
    "SET",
    "TRANSACTION",
    "BEGIN",
    "COMMIT",
    "ROLLBACK",
}

DISALLOWED_TABLES_PATTERNS: list[re.Pattern] = [
    re.compile(r"\busers\b", re.IGNORECASE),
    re.compile(r"\bmemberships\b", re.IGNORECASE),
    re.compile(r"\balembic_version\b", re.IGNORECASE),
    re.compile(r"\bpg_catalog\b", re.IGNORECASE),
    re.compile(r"\binformation_schema\b", re.IGNORECASE),
    re.compile(r"\bsqlite_master\b", re.IGNORECASE),
    re.compile(r"\bsqlite_temp_master\b", re.IGNORECASE),
]


class ReadOnlySQLInput(BaseModel):
    """Input payload for read-only SQL queries."""

    query: str = Field(
        ...,
        description=(
            "The read-only SQL query to execute (SELECT or WITH ... SELECT only). "
            "Mutations, DDL, and access to internal security tables are prohibited."
        ),
        max_length=1000,
    )


class ReadOnlySQLTool(BaseTool):
    """Executes safe, bounded, read-only SQL queries against approved application tables."""

    name = "read_only_sql"
    description = (
        "Executes structured read-only SQL queries (SELECT queries only). "
        "Allows querying structured database entities like sources and documents metadata. "
        "Enforces row limits, statement timeouts, and strict mutation blocking."
    )
    input_schema = ReadOnlySQLInput
    required_permissions = []

    def validate_query(self, sql: str) -> tuple[bool, str | None]:
        """Validates query against mutations, multiple statements, and blacklisted tables."""
        clean_sql = sql.strip().rstrip(";")
        tokens = [t.upper() for t in re.findall(r"\b[A-Za-z_]+\b", clean_sql)]

        if not tokens:
            return False, "Empty SQL query."

        # 1. Enforce query starts with SELECT or WITH
        first_token = tokens[0]
        if first_token not in ("SELECT", "WITH"):
            return (
                False,
                f"Prohibited SQL statement type '{first_token}'. "
                "Only SELECT or WITH queries are permitted.",
            )

        # 2. Reject multiple statements / semicolon injections
        if ";" in clean_sql:
            return False, "Multiple semicolon-separated SQL statements are prohibited."

        # 3. Check for prohibited mutation keywords
        prohibited_found = set(tokens).intersection(PROHIBITED_KEYWORDS)
        if prohibited_found:
            kw_list = ", ".join(sorted(prohibited_found))
            return (
                False,
                f"Prohibited mutation/DDL keyword(s) detected: {kw_list}.",
            )

        # 4. Reject access to protected internal tables
        for pattern in DISALLOWED_TABLES_PATTERNS:
            if pattern.search(clean_sql):
                return (
                    False,
                    "Access to internal security, user, or migration tables is prohibited.",
                )

        return True, None

    async def execute(
        self, input_data: ReadOnlySQLInput, context: ToolExecutionContext
    ) -> ToolResult:
        if not context.session:
            return ToolResult(
                success=False,
                error="Database session is required for SQL execution.",
                text_summary="SQL error: no active session.",
            )

        sql = input_data.query.strip().rstrip(";")
        is_valid, validation_error = self.validate_query(sql)
        if not is_valid:
            return ToolResult(
                success=False,
                error=f"SQL Validation Error: {validation_error}",
                text_summary=f"SQL rejected: {validation_error}",
            )

        settings = get_settings()
        row_limit = settings.AGENT_SQL_ROW_LIMIT
        timeout = settings.AGENT_SQL_TIMEOUT_SECONDS

        # Enforce or inject LIMIT clause if not present
        if not re.search(r"\bLIMIT\s+\d+\b", sql, re.IGNORECASE):
            sql = f"{sql} LIMIT {row_limit}"

        try:
            # Execute with query timeout
            async def _run_query() -> Any:
                stmt = text(sql).execution_options(read_only=True)
                return await context.session.execute(stmt)

            result = await asyncio.wait_for(_run_query(), timeout=timeout)
            columns = list(result.keys())
            rows_data = result.fetchmany(row_limit)

            formatted_rows: list[dict[str, Any]] = []
            for row in rows_data:
                row_dict: dict[str, Any] = {}
                for col_name, val in zip(columns, row, strict=False):
                    # Format UUIDs and dates cleanly
                    row_dict[col_name] = str(val) if val is not None else None
                formatted_rows.append(row_dict)

            summary_lines: list[str] = [
                f"Query executed successfully ({len(formatted_rows)} rows returned):",
                f"Columns: {', '.join(columns)}",
            ]
            for r in formatted_rows[:5]:
                summary_lines.append(str(r))
            if len(formatted_rows) > 5:
                summary_lines.append(f"... and {len(formatted_rows) - 5} more rows.")

            return ToolResult(
                success=True,
                data={
                    "query": sql,
                    "columns": columns,
                    "row_count": len(formatted_rows),
                    "rows": formatted_rows,
                },
                text_summary="\n".join(summary_lines),
            )

        except TimeoutError:
            return ToolResult(
                success=False,
                error=f"SQL execution timed out after {timeout} seconds.",
                text_summary="SQL query timed out.",
            )
        except Exception as exc:
            # Mask internal connection details
            err_msg = str(exc).split("\n")[0]
            return ToolResult(
                success=False,
                error=f"SQL execution failed: {err_msg}",
                text_summary=f"SQL execution failed: {err_msg}",
            )
