"""Analyst node — turns the retrieved context into a draft answer.

Reads ``state["retrieved_docs"]`` and ``state["question"]`` and calls the chat
model to produce a grounded draft. It does NOT fetch data (that is the
Researcher) and does NOT decide if the draft is good enough (the Auditor).

Unlike the Researcher, this node has NO tools — it is a single LLM call. It uses
the distilled ``retrieved_docs`` field, not the raw message trail, so the answer
is grounded in evidence rather than the Researcher's internal reasoning steps.
"""

from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.llm import get_chat_model
from src.agents.state import AgentState

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "analyst_system.md"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _format_evidence(docs: list[dict]) -> str:
    if not docs:
        return "(no evidence was retrieved)"
    return "\n\n".join(
        f"[{i + 1}] from {doc.get('tool', 'unknown')}:\n{doc.get('content', '')}"
        for i, doc in enumerate(docs)
    )


async def analyst(state: AgentState) -> dict:
    """Produce a draft answer grounded in the retrieved evidence.

    Returns the slice this node owns:
      - ``draft_answer``: the grounded draft (overwrite — last draft wins)
      - ``messages``: the model's reply, appended via the add_messages reducer
    """
    parts = [
        f"Question: {state['question']}",
        "",
        "Evidence:",
        _format_evidence(state.get("retrieved_docs", [])),
    ]

    # On a revision loop, fold in the Auditor's critique so the new draft fixes
    # what was flagged (see the Auditor -> Researcher/Analyst cycle in graph.py).
    verdict = state.get("audit_verdict") or {}
    if verdict.get("reason"):
        parts += [
            "",
            "Critique of your previous draft (address every point):",
            verdict["reason"],
        ]

    response = await get_chat_model().ainvoke(
        [SystemMessage(content=_load_prompt()), HumanMessage(content="\n".join(parts))]
    )

    return {"draft_answer": response.content, "messages": [response]}
