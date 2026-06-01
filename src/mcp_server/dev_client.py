"""Minimal MCP client (learning / no-Node alternative to the Inspector).

This connects to our own MCP server over stdio exactly like an agent would:
it launches `server.py` as a subprocess, performs the MCP handshake, lists the
available tools, and calls them. Pure Python — no Node.js required.

Run it:
    uv run python -m src.mcp_server.dev_client
"""

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    # How to launch the server process. Using sys.executable guarantees we use
    # the same (uv-managed) interpreter that has `mcp` installed.
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.mcp_server.server"],
    )

    # 1) Open the stdio transport (spawns the server subprocess).
    async with stdio_client(server_params) as (read, write):
        # 2) Open a session and do the MCP handshake.
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 3) Discover tools — this is what the LLM is shown.
            print("=== TOOLS ON THE SERVER ===")
            tools = await session.list_tools()
            for tool in tools.tools:
                print(f"  • {tool.name}: {tool.description.splitlines()[0]}")

            # 4) Call list_log_files.
            print("\n=== call list_log_files() ===")
            res = await session.call_tool("list_log_files", {})
            print(res.content[0].text)

            # 5) Call read_logs with arguments.
            print("=== call read_logs(lines=5) ===")
            res = await session.call_tool("read_logs", {"lines": 5})
            print(res.content[0].text)

            # 6) Trigger the security guard on purpose.
            print("=== call read_logs(filename='../pyproject.toml') -> guard ===")
            res = await session.call_tool("read_logs", {"filename": "../pyproject.toml"})
            print("isError =", res.isError)
            print(res.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
