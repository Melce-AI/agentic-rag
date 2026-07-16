"""DEPRECATED HTTP endpoint for the legacy single-agent SQL loop.

Superseded by ``/chat`` (the LangGraph operator + HITL). Kept and marked
``deprecated=True`` so it still runs from Swagger for reference, but new clients
should use ``/chat``. The implementation lives in ``src/agents/legacy/``.

POST /agent/ask takes a natural-language question; the agent (an LLM) decides
which MCP tools to call, runs read-only SQL, and returns a final answer plus the
tool-call trail it followed.
"""

from fastapi import APIRouter, Depends, Request
from opentelemetry import trace

from src.agents.legacy.sql_agent import run_agent
from src.auth.claims import AuthClaims
from src.auth.dependencies import current_user
from src.schemas.response import SuccessResponse
from src.schemas.agent import AgentAnswer, AgentAskRequest

router = APIRouter(prefix="/agent", tags=["Agent"])


@router.post("/ask", response_model=SuccessResponse[AgentAnswer], deprecated=True)
async def agent_ask(
    payload: AgentAskRequest,
    request: Request,
    user: AuthClaims = Depends(current_user),
):
    span = trace.get_current_span()
    span.set_attribute("openinference.span.kind", "AGENT")
    span.set_attribute("input.value", payload.question)
    result = await run_agent(payload.question)
    span.set_attribute("output.value", result["answer"])
    return SuccessResponse(data=result, request_id=request.state.request_id)
