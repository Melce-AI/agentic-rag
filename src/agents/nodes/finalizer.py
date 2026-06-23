"""Finalizer node — promotes the accepted draft to the public final_answer field.

Single responsibility: copy draft_answer → final_answer when the Auditor has
approved the draft (or the revision budget is spent). Neither the Analyst nor
the Auditor owns this step — they write their own slices; the Finalizer seals
the graph's output.
"""

import logging

from src.agents.state import AgentState

log = logging.getLogger(__name__)


def _format_citations(sources: list[dict]) -> str:
    """Deduplicated, human-readable source list. Empty string if no sources."""
    labels: list[str] = []
    for s in sources:
        name = s.get("source_name") or "unknown"
        path = " > ".join(s.get("heading_path") or [])
        label = f"{name} > {path}" if path else name
        if label not in labels:  # dedup, preserve order
            labels.append(label)
    if not labels:
        return ""
    lines = "\n".join(f"- {label}" for label in labels)
    return f"Sources:\n{lines}"


async def finalizer(state: AgentState) -> dict:
    draft = state["draft_answer"]
    citations = _format_citations(state.get("sources", []))
    final = f"{draft}\n\n{citations}" if citations else draft
    log.info("Finalizer: sealing answer (%d unique source(s))", citations.count("- "))
    return {"final_answer": final}
