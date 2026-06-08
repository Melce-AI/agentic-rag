"""Auditor node — self-reflection: is the draft faithful to the sources?

Compares ``state["draft_answer"]`` against ``state["retrieved_docs"]`` with the
chat model and records a structured verdict. It also bumps ``revision_count`` so
the loop has a brake. It does NOT route — the conditional edge in graph.py reads
the verdict and decides revise (back) vs. finish (END).

The verdict uses STRUCTURED OUTPUT (``with_structured_output``): the model is
forced to return the ``AuditVerdict`` schema, so the routing decision reads a
real ``bool`` instead of parsing free text (which would be fragile).
"""

from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.agents.llm import get_chat_model
from src.agents.state import AgentState

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


def _format_evidence(docs: list[dict]) -> str:
    if not docs:
        return "(no evidence was retrieved)"
    return "\n\n".join(
        f"[{i + 1}] from {doc.get('tool', 'unknown')}:\n{doc.get('content', '')}"
        for i, doc in enumerate(docs)
    )


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
            _format_evidence(state.get("retrieved_docs", [])),
            "",
            "Draft answer to audit:",
            state.get("draft_answer", ""),
        ]
    )

    judge = get_chat_model().with_structured_output(AuditVerdict)
    verdict: AuditVerdict = await judge.ainvoke(
        [SystemMessage(content=_load_prompt()), HumanMessage(content=human)]
    )

    return {
        "audit_verdict": verdict.model_dump(),
        "revision_count": state.get("revision_count", 0) + 1,
    }
