import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from opentelemetry import trace

from src.auth.claims import AuthClaims
from src.auth.dependencies import current_user
from src.core.exceptions import AppException, AgentGraphError
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
    span = trace.get_current_span()
    span.set_attribute("openinference.span.kind", "AGENT")
    span.set_attribute("input.value", payload.question)
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
                "tenant_id": payload.tenant_id,
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
    """Chat with real-time SSE via graph.astream_events().

    Event types emitted:
      node_start   — a graph node began executing
      node_end     — a graph node finished (auditor includes the verdict)
      token        — one LLM output token (streamed as the model writes)
      tool_call    — an MCP tool was invoked (name + input args)
      tool_result  — an MCP tool returned (truncated output)
      final        — graph finished; carries the full answer + citations
      error        — unhandled exception; stream closes after this
    """
    span = trace.get_current_span()
    span.set_attribute("openinference.span.kind", "AGENT")
    span.set_attribute("input.value", payload.question)
    graph = request.app.state.graph
    mcp_tools = request.app.state.mcp_tools
    thread_id = payload.thread_id or f"chat-{user.user_id}-{payload.tenant_id}"

    initial_state = {
        "question": payload.question,
        "messages": [],
        "retrieved_docs": [],
        "draft_answer": "",
        "audit_verdict": {},
        "revision_count": 0,
        "final_answer": "",
        "sources": [],
    }
    config = {
        "configurable": {
            "mcp_tools": mcp_tools,
            "tenant_id": payload.tenant_id,
            "thread_id": thread_id,
        }
    }

    async def event_generator():
        NODE_NAMES = {"researcher", "analyst", "auditor", "finalizer"}

        def sse(event: TraceEvent) -> str:
            return f"data: {event.model_dump_json()}\n\n"

        try:
            async for raw in graph.astream_events(initial_state, config, version="v2"):
                kind: str = raw["event"]
                name: str = raw["name"]
                data: dict = raw["data"]
                # langgraph_node tells us which node the event originated inside.
                node: str | None = raw.get("metadata", {}).get("langgraph_node")

                if kind == "on_chain_start" and name in NODE_NAMES:
                    yield sse(
                        TraceEvent(
                            type="node_start", node=name, data={"status": "running"}
                        )
                    )

                elif kind == "on_chain_end" and name in NODE_NAMES:
                    extra: dict = {}
                    if name == "auditor":
                        out = data.get("output") or {}
                        extra = {"verdict": out.get("audit_verdict", {})}
                    yield sse(
                        TraceEvent(
                            type="node_end", node=name, data={"status": "done", **extra}
                        )
                    )

                elif kind == "on_chat_model_stream":
                    chunk = data.get("chunk")
                    token = chunk.content if chunk else ""
                    if token:
                        yield sse(
                            TraceEvent(type="token", node=node, data={"content": token})
                        )

                elif kind == "on_tool_start":
                    yield sse(
                        TraceEvent(
                            type="tool_call",
                            node=node,
                            data={"tool": name, "input": data.get("input") or {}},
                        )
                    )

                elif kind == "on_tool_end":
                    out = data.get("output")
                    yield sse(
                        TraceEvent(
                            type="tool_result",
                            node=node,
                            data={
                                "tool": name,
                                "output": str(out)[:300] if out else "",
                            },
                        )
                    )

                elif kind == "on_chain_end" and name == "LangGraph" and node is None:
                    output = data.get("output") or {}
                    citations = [
                        Citation(
                            document_id=s.get("document_id", ""),
                            source_name=s.get("source_name", ""),
                            heading_path=s.get("heading_path", []),
                            snippet=s.get("text", "")[:500],
                        )
                        for s in output.get("sources", [])
                    ]
                    yield sse(
                        TraceEvent(
                            type="final",
                            node="finalizer",
                            data={
                                "answer": output.get("final_answer", ""),
                                "citations": [c.model_dump() for c in citations],
                            },
                        )
                    )

            log.info(
                "Chat stream completed: %s (user=%s, thread=%s)",
                payload.question[:100],
                user.user_id,
                thread_id,
            )

        except AppException as exc:
            yield sse(
                TraceEvent(
                    type="error",
                    node=None,
                    data={
                        "code": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                    },
                )
            )
            log.error(
                "Chat stream app error [%s]: %s", exc.code, exc.message, exc_info=True
            )
        except Exception as exc:
            err = AgentGraphError(details=type(exc).__name__)
            yield sse(
                TraceEvent(
                    type="error",
                    node=None,
                    data={
                        "code": err.code,
                        "message": err.message,
                        "details": err.details,
                    },
                )
            )
            log.error("Chat stream unexpected error: %s", exc, exc_info=True)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
