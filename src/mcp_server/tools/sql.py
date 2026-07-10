"""MCP tools: read-only SQL access to the sample Postgres database.

Discovery-first (list_tables -> describe_table -> sql_query). Every query passes
through TWO independent safety layers: the ensure_read_only() guard here, and the
least-privilege ``sentinel_ro`` DB role the adapter connects with. Writes are
refused at both. See docs/mcp/sql_tool_design.md.
"""

import json
import logging

from mcp.server.fastmcp import FastMCP

from src.adapters.sql.postgres import postgres_manager, postgres_write_manager
from src.core.config import get_settings
from src.core.exceptions import SqlGuardError, SqlStoreError
from src.mcp_server.guards import ensure_read_only, ensure_write_safe

logger = logging.getLogger(__name__)


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_tables() -> list[str]:
        """List the tables available in the SQL database.

        Use this first to discover what you can query, then describe_table() to
        see a table's columns before writing a query with sql_query().
        """
        return await postgres_manager.list_tables()

    @mcp.tool()
    async def describe_table(table_name: str) -> str:
        """Show the columns of one table: name, data type, and nullability.

        Args:
            table_name: A table name returned by list_tables().
        """
        columns = await postgres_manager.describe_table(table_name)
        if not columns:
            return f"Table '{table_name}' not found. Try list_tables() first."

        lines = [
            f"  - {col['column_name']}: {col['data_type']} (nullable={col['is_nullable']})"
            for col in columns
        ]
        return f"Columns of '{table_name}':\n" + "\n".join(lines)

    @mcp.tool()
    async def sql_query(sql: str) -> str:
        """Run a READ-ONLY SQL query and return the matching rows as JSON.

        Only a single SELECT (or WITH ... SELECT) statement is permitted. Any
        write or DDL statement (INSERT/UPDATE/DELETE/DROP/ALTER/...) is refused.
        Results are capped to a fixed number of rows, so add your own LIMIT/WHERE
        to narrow them. Call list_tables()/describe_table() first to learn schema.

        Args:
            sql: A single read-only SQL statement.
        """
        try:
            safe_sql = ensure_read_only(sql)
        except SqlGuardError as exc:
            # A deliberate refusal — report it clearly so the model can correct.
            return f"Query refused: {exc.message}"

        try:
            rows = await postgres_manager.run_select(safe_sql)
        except SqlStoreError as exc:
            return f"Query failed: {exc.message} ({exc.details})"

        if not rows:
            return "Query returned no rows."

        return json.dumps(rows, default=str, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def sql_execute(sql: str) -> str:
        """Run a single WHERE-qualified UPDATE or DELETE on an operational table.

        DESTRUCTIVE: this modifies data. It is the write half of the two-tier
        SQL design and is gated by human approval in the agent graph before it
        ever runs. Requirements enforced here by an independent guard, then by
        the write-only DB role:
          - exactly one UPDATE or DELETE statement (no SELECT/INSERT/DDL),
          - a WHERE clause (an unqualified whole-table write is refused),
          - a target table in the configured writable set.

        Args:
            sql: A single UPDATE or DELETE statement with a WHERE clause.
        """
        try:
            safe_sql = ensure_write_safe(sql, get_settings().postgres_writable_tables)
        except SqlGuardError as exc:
            # A deliberate refusal — report it clearly so the model can correct.
            return f"Write refused: {exc.message}"

        try:
            affected = await postgres_write_manager.run_write(safe_sql)
        except SqlStoreError as exc:
            return f"Write failed: {exc.message} ({exc.details})"

        return f"Write applied: {affected} row(s) affected."
