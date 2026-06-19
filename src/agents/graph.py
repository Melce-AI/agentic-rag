"""StateGraph wiring for the multi-agent layer — the heart of Step 3.

Researcher -> Analyst -> Auditor, with a conditional edge from the Auditor that
either loops back to the Researcher (draft not faithful — re-retrieve with the
critique in hand) or routes to END (faithful, or the revision budget is spent).

    Researcher -> Analyst -> Auditor
                               |- not faithful & budget left -> Researcher (cycle)
                               |- faithful OR budget spent    -> END

Two brakes stop infinite loops:
  - agent_max_revisions (business): route_after_audit gives up after N loops.
  - recursion_limit (infrastructure): LangGraph's hard cap, passed at invoke as
    config={"recursion_limit": settings.agent_recursion_limit}.
"""

import logging

from langgraph.graph import END, START, StateGraph

from src.agents.nodes.analyst import analyst
from src.agents.nodes.auditor import auditor
from src.agents.nodes.researcher import researcher
from src.agents.state import AgentState
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


def build_graph(checkpointer=None):
    """Compile the Researcher -> Analyst -> Auditor (loop) graph.

    Pass a checkpointer (e.g. MemorySaver, later Redis) to persist state across
    steps and enable resume / human-in-the-loop; None compiles without it.
    """
    g = StateGraph(AgentState)

    g.add_node("researcher", researcher)
    g.add_node("analyst", analyst)
    g.add_node("auditor", auditor)

    g.add_edge(START, "researcher")
    g.add_edge("researcher", "analyst")
    g.add_edge("analyst", "auditor")

    # The conditional edge is where the cycle is born: the router's label picks
    # the next node, and "revise" points back to an earlier node (researcher).
    g.add_conditional_edges(
        "auditor",
        route_after_audit,
        {"revise": "researcher", "finish": END},
    )

    return g.compile(checkpointer=checkpointer)
