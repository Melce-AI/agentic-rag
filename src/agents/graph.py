"""The top-level operator graph (Vision Step 4) — the graph the app compiles.

A single ReAct agent (``create_agent``) that drives everything:
- answers document questions via ``knowledge_base_qa`` (the RAG subgraph as a
  tool — see ``src/agents/knowledge_base/``),
- reads data via the SQL read tools + ``read_logs``,
- performs a change via ``sql_execute``, gated by ``HumanInTheLoopMiddleware`` so
  a human Approves/Rejects before the write runs ("approved == executed").

    START -> operator (ReAct, interrupt_on sql_execute) -> END
              tools: knowledge_base_qa, sql_query, list_tables,
                     describe_table, read_logs, list_log_files, sql_execute

Design B — a single operator that can interleave read → understand → act, rather
than an up-front read/write router that would trap the flow. See
docs/agents/hitl_operator_plan.md.
"""

import logging
from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.tools import BaseTool

from src.agents.llm import get_chat_model
from src.agents.knowledge_base.tool import knowledge_base_qa

log = logging.getLogger(__name__)

_OPERATOR_PROMPT_PATH = Path(__file__).parent / "prompts" / "operator_system.md"

# The write tool the operator may call. It is gated by HumanInTheLoopMiddleware:
# the graph pauses at this exact tool-call boundary so a human approves the SQL
# before it runs ("approved == executed" is inherent — see the plan, decision 1).
WRITE_TOOL_NAME = "sql_execute"

# MCP tools the OPERATOR is allowed to hold. Deliberately excludes ``rag_search``:
# all document retrieval is delegated to ``knowledge_base_qa`` (the RAG subgraph),
# so retrieval is not duplicated across layers (plan, decision 4).
_OPERATOR_MCP_TOOLS = frozenset(
    {
        "sql_query",
        "list_tables",
        "describe_table",
        "read_logs",
        "list_log_files",
        WRITE_TOOL_NAME,
    }
)


def _load_operator_prompt() -> str:
    return _OPERATOR_PROMPT_PATH.read_text(encoding="utf-8")


def _select_operator_tools(mcp_tools: list[BaseTool]) -> list[BaseTool]:
    """Pick the MCP tools the operator holds, by name (plan, decision 7).

    Explicit per-agent construction, not fragile filtering downstream: the
    operator gets SQL read/write + logs; ``rag_search`` is intentionally left
    out (delegated to ``knowledge_base_qa``).
    """
    return [t for t in mcp_tools if t.name in _OPERATOR_MCP_TOOLS]


def build_graph(mcp_tools: list[BaseTool] | None = None, checkpointer=None):
    """Compile the top-level operator agent (Design B).

    A single ReAct agent (``create_agent``) whose tools are ``knowledge_base_qa``
    (the RAG subgraph as a tool) plus the SQL read/write and log MCP tools. The
    write tool (``sql_execute``) is gated by ``HumanInTheLoopMiddleware``: the
    graph interrupts at that tool call so a human Approves/Rejects before the
    write runs. ``interrupt_on`` requires a checkpointer — pass the Redis one.

    Args:
        mcp_tools: the pre-fetched MCP tools (from app.py lifespan). Empty/None
            is allowed so tests can build an operator with only the RAG tool.
        checkpointer: LangGraph checkpointer (Redis in production). Required for
            the HITL interrupt/resume flow to persist across HTTP requests.
    """
    operator_tools: list[BaseTool] = [knowledge_base_qa]
    operator_tools += _select_operator_tools(mcp_tools or [])

    tool_names = [t.name for t in operator_tools]
    log.info("Building operator agent with tools: %s", tool_names)
    if WRITE_TOOL_NAME not in tool_names:
        # Not fatal (the operator can still read), but the HITL write path is the
        # point of Step 4 — surface a missing write tool loudly.
        log.warning(
            "Operator built WITHOUT '%s' — HITL write path is unavailable.",
            WRITE_TOOL_NAME,
        )

    return create_agent(
        get_chat_model(),
        operator_tools,
        system_prompt=_load_operator_prompt(),
        middleware=[HumanInTheLoopMiddleware(interrupt_on={WRITE_TOOL_NAME: True})],
        checkpointer=checkpointer,
    )
