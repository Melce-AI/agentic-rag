"""Shared state for the multi-agent graph — the single source of truth.

Nodes never call each other directly; each one reads this state and returns
only the slice it changed. The reducer attached to a field decides how that
returned slice merges with the existing value: overwrite (last writer wins) or
accumulate. Picking the right reducer per field is the core of state design.

This is the graph's INTERNAL state, not the public API contract. The HTTP layer
returns its own DTOs (schemas/chat.py) so the API does not break when this
internal shape changes (anti-corruption layer / DTO separation).
"""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # Input — set once at START, never overwritten.
    question: str

    # Reasoning + tool-call history. `add_messages` ACCUMULATES (smart append:
    # appends new messages, updates same-id ones, handles Human/AI/Tool types).
    # Without it, each node's return would wipe prior messages and the
    # Auditor -> Researcher loop would lose its memory every turn.
    messages: Annotated[list[AnyMessage], add_messages]

    # Sources the Researcher fetched. OVERWRITE (no reducer): on each revision
    # the Researcher re-retrieves with a refined query, and the Analyst should
    # see the latest best set — not a growing pile of stale docs. (Switch to a
    # list-extend reducer here if you later want sources to accumulate.)
    retrieved_docs: list[dict]

    # Analyst's current draft answer — last writer wins (new draft replaces old).
    draft_answer: str

    # Auditor's judgement, e.g. {"faithful": bool, "reason": str} — last wins.
    audit_verdict: dict

    # Loop counter / infinite-loop brake. Incremented by hand in the auditor
    # node (return {"revision_count": state["revision_count"] + 1}); the default
    # overwrite reducer is enough because a single node owns this field.
    revision_count: int

    # Filled when the graph routes to END.
    final_answer: str

    # Citable sources extracted from rag_search results (source_name + heading_path),
    # for the Finalizer to append as citations. OVERWRITE — refreshed each revision,
    # mirroring retrieved_docs (not accumulated).
    sources: list[dict]
