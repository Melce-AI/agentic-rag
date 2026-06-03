"""Agentic RAG MCP server — entrypoint and tool registration.

Standalone process; agents connect as clients (see docs/architecture.md).
Tools live in src/mcp_server/tools/ and are registered here.

Run the interactive Inspector:
    uv run mcp dev src/mcp_server/server.py

Run over stdio (how an agent client launches it):
    uv run python -m src.mcp_server.server
"""

import json
import logging

from mcp.server.fastmcp import FastMCP

from src.mcp_server.tools import rag_search, read_logs, sql

logger = logging.getLogger(__name__)

mcp = FastMCP("agentic-rag-mcp")

# TODO (distributed tracing): this MCP server runs as a separate process and does
# NOT call setup_tracing(), so the @traced spans inside the tools/adapters (e.g.
# postgres.run_select, qdrant.hybrid_search) are not exported to Phoenix. The
# agent currently captures tool calls with a client-side TOOL span instead, so we
# still see "agent -> tool -> result". To get end-to-end (distributed) traces:
#   1. call setup_tracing() here on startup,
#   2. propagate the trace context from the agent (client) into the tool calls
#      so the server spans nest under the agent's AGENT span (one trace, two
#      processes) instead of appearing as disconnected roots.

rag_search.register(mcp)
read_logs.register(mcp)
sql.register(mcp)


if __name__ == "__main__":
    # stdio is the default transport: the agent client launches this file as a
    # subprocess and talks to it over stdin/stdout. We will switch to HTTP later
    # when the server runs as its own Docker container.
    mcp.run(transport="stdio")
