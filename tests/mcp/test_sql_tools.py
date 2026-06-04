"""Tests for the MCP SQL tools with the Postgres adapter mocked.

No live database (AGENTS.md: mock the DB in tests). The tools live in
src/mcp_server/tools/sql.py and are registered into a FastMCP instance, so we
drive them through mcp.call_tool exactly as a client would. The guard is
exercised for real; only the adapter call is faked.
"""

import asyncio

from mcp.server.fastmcp import FastMCP

from src.mcp_server.tools import sql


def _build_mcp() -> FastMCP:
    mcp = FastMCP("test")
    sql.register(mcp)
    return mcp


def _text(call_tool_result) -> str:
    # FastMCP.call_tool returns (content_list, result_dict).
    content, _ = call_tool_result
    return content[0].text


def _fake_select(rows):
    async def _run(query, params=None):
        return rows

    return _run


def test_sql_query_refuses_write_before_touching_db(monkeypatch):
    hit_db = False

    async def _run(query, params=None):
        nonlocal hit_db
        hit_db = True
        return []

    monkeypatch.setattr(sql.postgres_manager, "run_select", _run)
    mcp = _build_mcp()

    out = _text(asyncio.run(mcp.call_tool("sql_query", {"sql": "DELETE FROM orders"})))

    assert "refused" in out.lower()
    assert hit_db is False  # guard blocked it before any DB call


def test_sql_query_returns_json_rows(monkeypatch):
    monkeypatch.setattr(
        sql.postgres_manager,
        "run_select",
        _fake_select([{"name": "Wireless Mouse", "revenue": 174.93}]),
    )
    mcp = _build_mcp()

    out = _text(asyncio.run(mcp.call_tool("sql_query", {"sql": "SELECT name FROM products"})))

    assert "Wireless Mouse" in out
    assert "174.93" in out


def test_sql_query_empty_result(monkeypatch):
    monkeypatch.setattr(sql.postgres_manager, "run_select", _fake_select([]))
    mcp = _build_mcp()

    out = _text(asyncio.run(mcp.call_tool("sql_query", {"sql": "SELECT 1 WHERE false"})))

    assert "no rows" in out.lower()


def test_describe_table_not_found(monkeypatch):
    async def _describe(table_name):
        return []

    monkeypatch.setattr(sql.postgres_manager, "describe_table", _describe)
    mcp = _build_mcp()

    out = _text(asyncio.run(mcp.call_tool("describe_table", {"table_name": "nope"})))

    assert "not found" in out.lower()
