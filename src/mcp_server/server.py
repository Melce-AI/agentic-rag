"""Sentinel MCP server (Step 2 — learning scaffold).

This is the project's MCP entrypoint: a standalone process that exposes a small,
authorized set of tools an LLM agent may call. It is NOT a service that other
modules import — the agent connects to it as a client (see docs/architecture.md).

For now it ships read-only, safe tools over the local log files so you can learn
how an MCP server is defined, run, and inspected.

Run the interactive Inspector:
    uv run mcp dev src/mcp_server/server.py

Run over stdio (how an agent client launches it):
    uv run python -m src.mcp_server.server
"""

import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# server.py lives at src/mcp_server/server.py → parents[2] is the repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "logs"

# The server instance. The name is what clients see when they connect.
mcp = FastMCP("sentinel-mcp")

# Guardrail: never let a model pull an unbounded amount of log data in one call.
MAX_LINES = 1000


@mcp.tool()
def list_log_files() -> list[str]:
    """List the available application log file names in the logs directory.

    Use this first to discover which log files exist before reading one.
    """
    if not LOG_DIR.exists():
        return []
    return sorted(p.name for p in LOG_DIR.glob("*.log*") if p.is_file())


@mcp.tool()
def read_logs(filename: str = "agentic_rag.log", lines: int = 100) -> str:
    """Read the last N lines of an application log file (read-only).

    Args:
        filename: Log file name inside the logs directory. Defaults to the main
            application log. Must be a plain file name, not a path.
        lines: How many trailing lines to return (1..1000).

    Returns:
        The tail of the log file as text, or a clear message if it is empty or
        missing.
    """
    # Security guard: reject anything that tries to escape the logs directory.
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise ValueError("filename must be a plain file name inside the logs directory")

    lines = max(1, min(lines, MAX_LINES))

    target = LOG_DIR / filename
    if not target.exists():
        return f"Log file '{filename}' not found. Try list_log_files() first."

    with target.open("r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()

    if not all_lines:
        return f"Log file '{filename}' is empty."

    tail = all_lines[-lines:]
    return "".join(tail)


if __name__ == "__main__":
    # stdio is the default transport: the agent client launches this file as a
    # subprocess and talks to it over stdin/stdout. We will switch to HTTP later
    # when the server runs as its own Docker container.
    mcp.run(transport="stdio")
