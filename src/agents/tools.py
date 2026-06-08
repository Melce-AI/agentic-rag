"""MCP -> LangChain tool bridge.

The agents expect LangChain tools (``BaseTool``), but the real tools live in the
Sentinel MCP server (src/mcp_server/). ``langchain-mcp-adapters`` connects to
that server and converts each MCP tool (``rag_search``, ``sql_query``,
``list_tables``, ``read_logs`` ...) into a LangChain tool automatically.

Why go through MCP at all instead of importing the retriever / Postgres adapter
directly? Because the security lives in the MCP layer: the read-only ``sentinel_ro``
role and the ``ensure_read_only()`` guard (docs/mcp/sql_tool_design.md). Nodes
must never touch a DB directly (AGENTS.md) — they go through this bridge so every
tool call stays inside that guard.

Transport note: we launch the MCP server as a stdio subprocess, mirroring
``sql_agent.py``. ``env`` is forwarded so settings like ``POSTGRES_HOST`` reach
the server (MCP sanitizes the env otherwise). With stdio, each tool invocation
opens a fresh session; when the MCP server later runs as its own Docker service
we will switch this connection to streamable-http (server.py already flags this).
"""

import os
import sys
from functools import lru_cache

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient


def _connections() -> dict:
    """How to reach each MCP server. One entry per server; we have one."""
    return {
        "sentinel": {
            "transport": "stdio",
            "command": sys.executable,
            "args": ["-m", "src.mcp_server.server"],
            # Forward the full env so POSTGRES_HOST/QDRANT_HOST/etc. reach the
            # server subprocess (MCP strips the env by default).
            "env": dict(os.environ),
        }
    }


@lru_cache
def get_mcp_client() -> MultiServerMCPClient:
    """Shared client. Construction is cheap (just stores the config); the actual
    connection is opened lazily when tools are fetched or invoked."""
    return MultiServerMCPClient(_connections())


async def get_tools() -> list[BaseTool]:
    """Return the MCP tools as LangChain tools.

    Call this once when building the graph and bind the result to the model
    (``model.bind_tools(tools)``) / hand it to a ``ToolNode``. The names match
    the MCP tools: ``rag_search``, ``sql_query``, ``list_tables``,
    ``describe_table``, ``list_log_files``, ``read_logs``.
    """
    return await get_mcp_client().get_tools()
