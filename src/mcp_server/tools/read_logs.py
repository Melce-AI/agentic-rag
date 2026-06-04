"""MCP tools: application log file access (read-only)."""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_LOG_DIR = _PROJECT_ROOT / "logs"
_MAX_LINES = 1000


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def list_log_files() -> list[str]:
        """List the available application log file names in the logs directory.

        Use this first to discover which log files exist before reading one.
        """
        if not _LOG_DIR.exists():
            return []
        return sorted(p.name for p in _LOG_DIR.glob("*.log*") if p.is_file())

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
        if "/" in filename or "\\" in filename or filename.startswith("."):
            raise ValueError(
                "filename must be a plain file name inside the logs directory"
            )

        lines = max(1, min(lines, _MAX_LINES))

        target = _LOG_DIR / filename
        if not target.exists():
            return f"Log file '{filename}' not found. Try list_log_files() first."

        with target.open("r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        if not all_lines:
            return f"Log file '{filename}' is empty."

        return "".join(all_lines[-lines:])
