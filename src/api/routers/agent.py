"""HTTP endpoint for the SQL agent so it can be driven from Swagger UI.

POST /agent/ask takes a natural-language question; the agent (an LLM) decides
which MCP tools to call, runs read-only SQL, and returns a final answer plus the
tool-call trail it followed.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from src.agents.sql_agent import run_agent
from src.schemas.response import SuccessResponse

router = APIRouter(prefix="/agent", tags=["Agent"])


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


@router.post("/ask", response_model=SuccessResponse[AgentAnswer])
async def agent_ask(payload: AgentAskRequest, request: Request):
    result = await run_agent(payload.question)
    return SuccessResponse(data=result, request_id=request.state.request_id)
