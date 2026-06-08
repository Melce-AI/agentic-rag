"""StateGraph wiring for the multi-agent layer — the heart of Step 3.

This builds the cyclical graph: Researcher -> Analyst -> Auditor, with a
conditional edge from the Auditor that either loops back to the Researcher
(draft not faithful) or routes to END (faithful). A `revision_count` brake plus
LangGraph's `recursion_limit` stop infinite loops.

    Researcher -> Analyst -> Auditor
                               |- not faithful -> Researcher (cycle)
                               |- faithful      -> END

TODO (next step): implement build_graph(checkpointer=None) once the three nodes
(researcher/analyst/auditor) and the route_after_audit router are written.
See docs/agents/langgraph_guide.md §6.
"""
