"""Finalizer node — promotes the accepted draft to the public final_answer field.

Single responsibility: copy draft_answer → final_answer when the Auditor has
approved the draft (or the revision budget is spent). Neither the Analyst nor
the Auditor owns this step — they write their own slices; the Finalizer seals
the graph's output.
"""

import logging

from src.agents.knowledge_base.state import AgentState

log = logging.getLogger(__name__)


async def finalizer(state: AgentState) -> dict:
    # Citations are sent as a separate structured field by the router — do not
    # append a Sources block to the answer text.
    draft = state["draft_answer"]
    log.info("Finalizer: sealing answer (%d source(s))", len(state.get("sources", [])))
    return {"final_answer": draft}
