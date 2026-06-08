"""Public API DTOs for the agent chat endpoint (Step 4/7).

These are the API contract — deliberately separate from the graph's internal
AgentState (agents/state.py). Internal state can change without breaking the
API (anti-corruption layer / DTO separation). The non-streaming answer is still
returned inside the shared SuccessResponse envelope; SSE events stream raw but
stay typed.
"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)  # naming kept consistent with search.py
    thread_id: str | None = None  # set to continue an existing conversation


class Citation(BaseModel):
    """Source backing a sentence in the answer (Step 4: citations first-class)."""

    document_id: str
    source_name: str
    heading_path: list[str]
    snippet: str


class ChatAnswer(BaseModel):
    answer: str
    citations: list[Citation]


class TraceEvent(BaseModel):
    """One SSE event in the streaming trace (Step 4)."""

    # "tool_call" | "tool_result" | "token" | "approval_required" | "final"
    type: str
    node: str | None  # which node emitted it
    data: dict
