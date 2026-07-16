"""DTOs for the deprecated ``/agent/ask`` endpoint (legacy single-agent loop).

Superseded by ``schemas/chat.py`` + ``/chat``. Kept only for the deprecated
endpoint; do not use for new work.
"""

from pydantic import BaseModel, Field


class AgentAskRequest(BaseModel):
    question: str = Field(
        ..., min_length=1, examples=["En çok ciro yapan 3 ürün hangisi?"]
    )


class AgentStep(BaseModel):
    tool: str
    args: dict
    result: str


class AgentAnswer(BaseModel):
    answer: str
    steps: list[AgentStep]
