"""Finalizer node — promotes the accepted draft to the public final_answer field.

Single responsibility: copy draft_answer → final_answer when the Auditor has
approved the draft (or the revision budget is spent). Neither the Analyst nor
the Auditor owns this step — they write their own slices; the Finalizer seals
the graph's output.
"""

import logging

from src.agents.state import AgentState

log = logging.getLogger(__name__)


async def finalizer(state: AgentState) -> dict:
    # TODO: add citation formatting here — append source references from
    # retrieved_docs to the answer before sealing it. No LLM needed; deterministic
    # string formatting is enough (e.g. "[Source: doc.pdf, p.3]").
    log.info("Finalizer: promoting draft to final_answer")
    return {"final_answer": state["draft_answer"]}
