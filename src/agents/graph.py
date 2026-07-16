"""Graph wiring for the agent layer.

Two graphs live here, one nested inside the other (Design B — see
docs/agents/hitl_operator_plan.md):

1. ``build_rag_graph`` — the multi-agent RAG pipeline (Vision Step 3):
   Researcher -> Analyst -> Auditor, with a conditional edge from the Auditor
   that either loops back to the Researcher (draft not faithful — re-retrieve
   with the critique in hand) or routes to Finalizer -> END.

       Researcher -> Analyst -> Auditor
                                  |- not faithful & budget left -> Researcher (cycle)
                                  |- faithful OR budget spent    -> Finalizer -> END

   It is no longer the top-level graph: it is exposed to the operator as the
   ``knowledge_base_qa`` tool (src/agents/rag_tool.py), so document Q&A keeps its
   self-reflection / faithfulness loop.

2. ``build_graph`` — the top-level operator (Vision Step 4). A single ReAct agent
   (``create_agent``) that reads documents via ``knowledge_base_qa``, reads data
   via the SQL read tools + ``read_logs``, and performs a change via
   ``sql_execute`` — which is gated by ``HumanInTheLoopMiddleware`` so a human
   Approves/Rejects before the write runs.

       START -> operator (ReAct, interrupt_on sql_execute) -> END
                 tools: knowledge_base_qa, sql_query, list_tables,
                        describe_table, read_logs, list_log_files, sql_execute

Two brakes stop the RAG loop from running forever:
  - agent_max_revisions (business): route_after_audit gives up after N loops.
  - recursion_limit (infrastructure): LangGraph's hard cap, passed at invoke as
    config={"recursion_limit": settings.agent_recursion_limit}.
"""

import logging
from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph

from src.agents.nodes.analyst import analyst
from src.agents.nodes.auditor import auditor
from src.agents.nodes.finalizer import finalizer
from src.agents.nodes.researcher import researcher
from src.agents.llm import get_chat_model
from src.agents.rag_tool import knowledge_base_qa
from src.agents.state import AgentState
from src.core.config import get_settings

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


def route_after_audit(state: AgentState) -> str:
    """Decide where to go after the Auditor.

    Pure routing: it only reads state and returns a label — it never mutates
    state. (Mutation happens in nodes; routing happens in edges.)
    """
    verdict = state.get("audit_verdict") or {}
    revision_count = state.get("revision_count", 0)
    if verdict.get("faithful"):
        log.info("Routing: faithful → finish (revision=%d)", revision_count)
        return "finish"
    if revision_count >= get_settings().agent_max_revisions:
        log.warning(
            "Routing: revision budget exhausted (%d/%d) → finish",
            revision_count,
            get_settings().agent_max_revisions,
        )
        return "finish"
    log.info("Routing: not faithful → revise (revision=%d)", revision_count)
    return "revise"


def build_rag_graph(checkpointer=None):
    """Compile the Researcher -> Analyst -> Auditor (loop) RAG subgraph.

    Behaviour is unchanged from the original top-level pipeline; it is now a
    reusable subgraph invoked by the ``knowledge_base_qa`` tool. Pass a
    checkpointer to persist state across steps; None compiles without one (the
    subgraph runs to completion inside a single tool call, so it needs none).
    """
    g = StateGraph(AgentState)

    g.add_node("researcher", researcher)
    g.add_node("analyst", analyst)
    g.add_node("auditor", auditor)
    g.add_node("finalizer", finalizer)

    g.add_edge(START, "researcher")
    g.add_edge("researcher", "analyst")
    g.add_edge("analyst", "auditor")

    # The conditional edge is where the cycle is born: the router's label picks
    # the next node, and "revise" points back to an earlier node (researcher).
    g.add_conditional_edges(
        "auditor",
        route_after_audit,
        {"revise": "researcher", "finish": "finalizer"},
    )

    g.add_edge("finalizer", END)

    return g.compile(checkpointer=checkpointer)


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
