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
