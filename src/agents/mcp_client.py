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

Lifecycle: ``create_mcp_client()`` is called once in app.py lifespan.
``app.py`` opens a persistent ``client.session(MCP_SERVER_NAME)`` context,
fetches tools once with ``load_mcp_tools(session)``, and stores them in
``app.state.mcp_tools``. Nodes receive the pre-fetched list via
``config["configurable"]["mcp_tools"]`` — no subprocess is spawned per request.
"""

import os
import sys

from langchain_mcp_adapters.client import MultiServerMCPClient

MCP_SERVER_NAME = "sentinel"


def _connections() -> dict:
    return {
        MCP_SERVER_NAME: {
            "transport": "stdio",
            "command": sys.executable,
            "args": ["-m", "src.mcp_server.server"],
            # Forward the full env so POSTGRES_HOST/QDRANT_HOST/etc. reach the
            # server subprocess (MCP strips the env by default).
            "env": dict(os.environ),
        }
    }


def create_mcp_client() -> MultiServerMCPClient:
    """Return a configured client. Open a session with ``client.session(MCP_SERVER_NAME)``
    to establish the persistent stdio connection — call once in the app lifespan.
    """
    return MultiServerMCPClient(_connections())
