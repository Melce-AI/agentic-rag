import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from src.auth.claims import AuthClaims
from src.auth.dependencies import current_user
from src.schemas.chat import ChatAnswer, ChatRequest, Citation, TraceEvent
from src.schemas.response import SuccessResponse

log = logging.getLogger(__name__)


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


@router.post("/stream")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    user: AuthClaims = Depends(current_user),
):
    """Chat with SSE streaming of agent trace events."""
    graph = request.app.state.graph
    mcp_tools = request.app.state.mcp_tools

    async def event_generator():
        """Generate SSE events as the graph executes."""
        try:
            # Invoke the graph
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

            # Yield trace events (post-hoc simulation)
            events = [
                TraceEvent(
                    type="researcher",
                    node="researcher",
                    data={"status": "retrieving documents", "query": payload.question},
                ),
                TraceEvent(
                    type="analyst",
                    node="analyst",
                    data={"draft_answer": result.get("draft_answer", "")},
                ),
                TraceEvent(
                    type="auditor",
                    node="auditor",
                    data={"verdict": result.get("audit_verdict", {})},
                ),
            ]

            for event in events:
                event_json = event.model_dump_json()
                yield f"data: {event_json}\n\n"

            # Final event with answer and citations
            citations = [
                Citation(
                    document_id=s.get("document_id", ""),
                    source_name=s.get("source_name", ""),
                    heading_path=s.get("heading_path", []),
                    snippet=s.get("text", "")[:500],
                )
                for s in result.get("sources", [])
            ]

            final_event = TraceEvent(
                type="final",
                node="finalizer",
                data={
                    "answer": result["final_answer"],
                    "citations": [c.model_dump() for c in citations],
                },
            )
            final_json = final_event.model_dump_json()
            yield f"data: {final_json}\n\n"

            log.info(
                "Chat stream completed: %s (user=%s, thread=%s)",
                payload.question[:100],
                user.user_id,
                payload.thread_id or f"chat-{user.user_id}-{payload.tenant_id}",
            )
        except Exception as e:
            error_event = TraceEvent(
                type="error",
                node=None,
                data={"error": str(e)},
            )
            error_json = error_event.model_dump_json()
            yield f"data: {error_json}\n\n"
            log.error("Chat stream error: %s", e, exc_info=True)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
