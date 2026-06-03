"""Agentic RAG MCP server — entrypoint and tool registration.

Standalone process; agents connect as clients (see docs/architecture.md).
Tools live in src/mcp_server/tools/ and are registered here.

Run the interactive Inspector:
    uv run mcp dev src/mcp_server/server.py

Run over stdio (how an agent client launches it):
    uv run python -m src.mcp_server.server
"""

import logging

from mcp.server.fastmcp import FastMCP

from src.mcp_server.tools import rag_search, read_logs

logger = logging.getLogger(__name__)

mcp = FastMCP("agentic-rag-mcp")

rag_search.register(mcp)
read_logs.register(mcp)


if __name__ == "__main__":
    # stdio is the default transport: the agent client launches this file as a
    # subprocess and talks to it over stdin/stdout. We will switch to HTTP later
    # when the server runs as its own Docker container.
    mcp.run(transport="stdio")
