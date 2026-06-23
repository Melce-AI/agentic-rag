from fastapi import APIRouter, Depends, Request

from src.auth.claims import AuthClaims
from src.auth.dependencies import current_user
from src.schemas.chat import ChatAnswer, ChatRequest, Citation
from src.schemas.response import SuccessResponse


router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("", response_model=SuccessResponse[ChatAnswer])
async def chat(
    payload: ChatRequest,
    request: Request,
    user: AuthClaims = Depends(current_user),
):
    """Chat with the multi-agent graph."""
    graph = request.app.state.graph
    mcp_tools = request.app.state.mcp_tools

    # Invoke the graph with configurable MCP tools and thread ID
    result = await graph.ainvoke(
        {
            "question": payload.question,
            "messages": [],
            "retrieved_docs": [],
            "draft_answer": "",
            "audit_verdict": {},
            "revision_count": 0,
            "final_answer": "",
            "sources": [],
        },
        config={
            "configurable": {
                "mcp_tools": mcp_tools,
                "thread_id": payload.thread_id
                or f"chat-{user.user_id}-{payload.tenant_id}",
            }
        },
    )

    # Map sources to Citation objects
    citations = [
        Citation(
            document_id=s.get("document_id", ""),
            source_name=s.get("source_name", ""),
            heading_path=s.get("heading_path", []),
            snippet=s.get("text", "")[:500],  # first 500 chars
        )
        for s in result.get("sources", [])
    ]

    answer = ChatAnswer(answer=result["final_answer"], citations=citations)
    return SuccessResponse(data=answer, request_id=request.state.request_id)
