"""Auditor node — self-reflection: is the draft faithful to the sources?

Compares ``state["draft_answer"]`` against ``state["retrieved_docs"]`` with the
chat model and records a structured verdict. It also bumps ``revision_count`` so
the loop has a brake. It does NOT route — the conditional edge in graph.py reads
the verdict and decides revise (back) vs. finish (END).

The verdict uses STRUCTURED OUTPUT (``with_structured_output``): the model is
forced to return the ``AuditVerdict`` schema, so the routing decision reads a
real ``bool`` instead of parsing free text (which would be fragile).
"""

import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.agents.llm import get_chat_model
from src.agents.knowledge_base.state import AgentState


log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "auditor_system.md"


class AuditVerdict(BaseModel):
    """The Auditor's structured judgement of a draft answer."""

    faithful: bool = Field(
        description="True only if every claim in the draft is supported by the "
        "evidence and the draft answers the question."
    )
    reason: str = Field(
        description="Brief justification. If not faithful, state exactly what is "
        "unsupported or wrong so the next draft can fix it."
    )


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


# TODO: evaluate whether the citation-honesty check (point 4 in auditor_system.md)
# is worth duplicating _format_evidence here. LLMs are unreliable at cross-referencing
# [N] numbers; factual grounding (points 1-3) is the real value. If dropped, the
# auditor can receive raw sources in a simpler format and this function goes away.
def _format_evidence(sources: list[dict], retrieved_docs: list[dict]) -> str:
    entries: list[str] = []

    for s in sources:
        n = len(entries) + 1
        name = s.get("source_name") or "unknown"
        path = " > ".join(s.get("heading_path") or [])
        header = f"[{n}] {name} > {path}" if path else f"[{n}] {name}"
        entries.append(f"{header}\n{s.get('text', '')}")

    for doc in retrieved_docs:
        if doc.get("tool") == "rag_search":
            continue
        n = len(entries) + 1
        entries.append(
            f"[{n}] from {doc.get('tool', 'unknown')}:\n{doc.get('content', '')}"
        )

    if not entries:
        return "(no evidence was retrieved)"
    return "\n\n".join(entries)


async def auditor(state: AgentState) -> dict:
    """Judge the current draft and bump the loop counter.

    Returns the slice this node owns:
      - ``audit_verdict``: {"faithful": bool, "reason": str} (overwrite)
      - ``revision_count``: incremented by hand — one node owns it, so the
        default overwrite reducer is enough (see state.py)
    """
    human = "\n".join(
        [
            f"Question: {state['question']}",
            "",
            "Evidence:",
            _format_evidence(state.get("sources", []), state.get("retrieved_docs", [])),
            "",
            "Draft answer to audit:",
            state.get("draft_answer", ""),
        ]
    )

    revision = state.get("revision_count", 0) + 1
    log.info("Auditor reviewing draft (revision=%d)", revision)

    judge = get_chat_model().with_structured_output(AuditVerdict)
    verdict: AuditVerdict = await judge.ainvoke(
        [SystemMessage(content=_load_prompt()), HumanMessage(content=human)]
    )

    log.info(
        "Audit verdict (revision=%d): faithful=%s — %s",
        revision,
        verdict.faithful,
        verdict.reason[:120],
    )
    return {
        "audit_verdict": verdict.model_dump(),
        "revision_count": revision,
    }
