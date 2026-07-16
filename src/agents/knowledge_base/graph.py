"""The multi-agent RAG subgraph — Researcher → Analyst → Auditor (loop) → Finalizer.

This is the reusable knowledge-base pipeline (Vision Step 3). It is no longer the
top-level graph: the operator (``src/agents/graph.py``) reaches it through the
``knowledge_base_qa`` tool (``src/agents/knowledge_base/tool.py``), so document Q&A keeps its
self-reflection / faithfulness loop.

    Researcher -> Analyst -> Auditor
                               |- not faithful & budget left -> Researcher (cycle)
                               |- faithful OR budget spent    -> Finalizer -> END

Two brakes stop the loop from running forever:
  - agent_max_revisions (business): route_after_audit gives up after N loops.
  - recursion_limit (infrastructure): LangGraph's hard cap, passed at invoke as
    config={"recursion_limit": settings.agent_recursion_limit}.
"""

import logging

from langgraph.graph import END, START, StateGraph

from src.agents.knowledge_base.nodes.analyst import analyst
from src.agents.knowledge_base.nodes.auditor import auditor
from src.agents.knowledge_base.nodes.finalizer import finalizer
from src.agents.knowledge_base.nodes.researcher import researcher
from src.agents.knowledge_base.state import AgentState
from src.core.config import get_settings

log = logging.getLogger(__name__)


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
