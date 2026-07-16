"""Neutral result types for the agents layer.

These are the operator service's return types (``service.py``), deliberately
separate from the HTTP DTOs in ``schemas/chat.py``: the service knows nothing
about HTTP, and the router maps these to Pydantic DTOs (anti-corruption layer).
Keep them dependency-free dataclasses — no FastAPI/Pydantic, no graph internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PendingWrite:
    """A destructive tool call paused for human approval.

    ``sql`` is the exact statement that will run if approved — "approved ==
    executed" is inherent to the interrupt-on-tool-call gate.
    """

    thread_id: str
    tool: str
    sql: str
    description: str


@dataclass
class TurnResult:
    """The outcome of a turn: either an answer, or a pending write to approve."""

    thread_id: str
    answer: str = ""
    citations: list[dict] = field(default_factory=list)
    pending: PendingWrite | None = None

    @property
    def is_pending(self) -> bool:
        return self.pending is not None
