"""Public API DTOs for the agent chat endpoint (Step 4/7).

These are the API contract — deliberately separate from the graph's internal
AgentState (agents/state.py). Internal state can change without breaking the
API (anti-corruption layer / DTO separation). The non-streaming answer is still
returned inside the shared SuccessResponse envelope; SSE events stream raw but
stay typed.
"""

from typing import Annotated, Literal, Union

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
    # Literal discriminator so the /chat response union resolves unambiguously.
    status: Literal["answer"] = "answer"
    answer: str
    citations: list[Citation]


class PendingApproval(BaseModel):
    """A destructive write the operator wants to run, awaiting human approval.

    Returned by /chat when the operator paused on ``sql_execute``. The client
    shows ``sql`` (the exact statement that will run — "approved == executed")
    and calls /chat/approve/{thread_id} or /chat/reject/{thread_id}.
    """

    status: Literal["pending_approval"] = "pending_approval"
    thread_id: str
    tool: str
    sql: str
    description: str


# The /chat endpoint returns one of these; ``status`` discriminates them.
ChatResult = Annotated[
    Union[ChatAnswer, PendingApproval], Field(discriminator="status")
]


class RejectRequest(BaseModel):
    """Optional body for /chat/reject — a reason relayed back to the model."""

    reason: str | None = None
    tenant_id: str | None = None  # so a continued turn can still retrieve docs


class ApproveRequest(BaseModel):
    """Optional body for /chat/approve."""

    tenant_id: str | None = None  # so a continued turn can still retrieve docs


class TraceEvent(BaseModel):
    """One SSE event in the streaming trace (Step 4)."""

    # "tool_call" | "tool_result" | "token" | "approval_required" | "final"
    type: str
    node: str | None  # which node emitted it
    data: dict
