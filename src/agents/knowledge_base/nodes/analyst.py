"""Analyst node — turns the retrieved context into a draft answer.

Reads ``state["sources"]`` (individual RAG chunks) and ``state["retrieved_docs"]``
(non-RAG tool results) and calls the chat model to produce a grounded draft.
It does NOT fetch data (that is the Researcher) and does NOT decide if the draft
is good enough (the Auditor).

Evidence is numbered so that [N] in the draft maps exactly to sources[N-1] and
therefore to citations[N-1] in the API response.
"""

import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.llm import get_chat_model
from src.agents.knowledge_base.state import AgentState

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "analyst_system.md"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _format_evidence(sources: list[dict], retrieved_docs: list[dict]) -> str:
    """Build the numbered evidence block the LLM will cite.

    The [N] numbers are the backbone of the citation system:
      - Analyst prompt instructs the model to write inline citations as [1], [2], etc.
      - The draft answer ends up with "some claim [1]" style references.
      - The API maps sources[N-1] positionally to the Citation objects returned to
        the client — so the order here must stay stable and match sources[].
    Without this numbering there is no way to link a sentence in the answer back to
    a specific source document. RAG chunks come first, non-RAG tool results follow.
    """
    entries: list[str] = []

    for s in sources:
        n = len(entries) + 1
        name = s.get("source_name") or "unknown"
        path = " > ".join(s.get("heading_path") or [])
        header = f"[{n}] {name} > {path}" if path else f"[{n}] {name}"
        entries.append(f"{header}\n{s.get('text', '')}")

    for doc in retrieved_docs:
        if doc.get("tool") == "rag_search":
            continue  # already covered via sources above
        n = len(entries) + 1
        entries.append(
            f"[{n}] from {doc.get('tool', 'unknown')}:\n{doc.get('content', '')}"
        )

    if not entries:
        return "(no evidence was retrieved)"
    return "\n\n".join(entries)


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
        _format_evidence(state.get("sources", []), state.get("retrieved_docs", [])),
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

    revision = state.get("revision_count", 0)
    log.info("Analyst generating draft (revision=%d)", revision)

    response = await get_chat_model().ainvoke(
        [SystemMessage(content=_load_prompt()), HumanMessage(content="\n".join(parts))]
    )

    log.debug("Draft answer: %d chars", len(response.content))
    return {"draft_answer": response.content, "messages": [response]}
