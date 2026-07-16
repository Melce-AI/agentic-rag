"""Chat endpoints for the operator agent (Design B — HITL write operations).

Thin router (CLAUDE.md): it parses the request, calls the graph-orchestration
service (src/agents/service.py), and maps neutral results to HTTP DTOs. All
graph knowledge — invoke/resume, interrupt parsing, Command building — lives in
the service.

Endpoints:
  POST /chat                      one turn; returns an answer OR a pending write
  POST /chat/stream               SSE trace; emits approval_required when paused
  POST /chat/approve/{thread_id}  resume an approved write (auth'd, audit-logged)
  POST /chat/reject/{thread_id}   resume a rejected write (auth'd, audit-logged)
"""

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from opentelemetry import trace

from src.agents.models import TurnResult
from src.agents.service import (
    build_config,
    peek_pending,
    read_result,
    resume_turn,
    run_turn,
)
from src.auth.claims import AuthClaims
from src.auth.dependencies import current_user
from src.core.exceptions import AgentGraphError, AppException, ResourceNotFoundError
from src.schemas.chat import (
    ApproveRequest,
    ChatAnswer,
    ChatRequest,
    ChatResult,
    Citation,
    PendingApproval,
    RejectRequest,
    TraceEvent,
)
from src.schemas.response import SuccessResponse

log = logging.getLogger(__name__)


router = APIRouter(prefix="/chat", tags=["Chat"])


def _thread_id(request_thread_id: str | None, user: AuthClaims, tenant_id: str) -> str:
    """Stable per-user/tenant thread id unless the client pins one."""
    return request_thread_id or f"chat-{user.user_id}-{tenant_id}"


def _to_dto(result: TurnResult) -> ChatAnswer | PendingApproval:
    """Map a neutral TurnResult to the public /chat response union."""
    if result.is_pending:
        p = result.pending
        return PendingApproval(
            thread_id=p.thread_id, tool=p.tool, sql=p.sql, description=p.description
        )
    citations = [
        Citation(
            document_id=s.get("document_id", ""),
            source_name=s.get("source_name", ""),
            heading_path=s.get("heading_path", []),
            snippet=s.get("text", "")[:500],
        )
        for s in result.citations
    ]
    return ChatAnswer(answer=result.answer, citations=citations)


@router.post("", response_model=SuccessResponse[ChatResult])
async def chat(
    payload: ChatRequest,
    request: Request,
    user: AuthClaims = Depends(current_user),
):
    """Run one operator turn. Returns an answer, or a write awaiting approval."""
    span = trace.get_current_span()
    span.set_attribute("openinference.span.kind", "AGENT")
    span.set_attribute("input.value", payload.question)

    thread_id = _thread_id(payload.thread_id, user, payload.tenant_id)
    result = await run_turn(
        request.app.state.graph,
        request.app.state.mcp_tools,
        payload.question,
        payload.tenant_id,
        thread_id,
    )
    return SuccessResponse(data=_to_dto(result), request_id=request.state.request_id)


@router.post("/approve/{thread_id}", response_model=SuccessResponse[ChatResult])
async def approve(
    thread_id: str,
    request: Request,
    payload: ApproveRequest = ApproveRequest(),
    user: AuthClaims = Depends(current_user),
):
    """Approve the pending write on a thread and resume the operator.

    The already-decided SQL runs exactly as shown ("approved == executed"). The
    approval is audit-logged with the approver and the SQL.
    """
    graph = request.app.state.graph
    pending = await peek_pending(graph, {"configurable": {"thread_id": thread_id}})
    if pending is None:
        raise ResourceNotFoundError(
            "pending approval", details={"thread_id": thread_id}
        )

    log.warning(
        "WRITE APPROVED — approver=%s email=%s thread=%s sql=%r",
        user.user_id,
        user.email,
        thread_id,
        pending.sql,
    )
    result = await resume_turn(
        graph,
        request.app.state.mcp_tools,
        thread_id,
        approve=True,
        tenant_id=payload.tenant_id or "default",
    )
    return SuccessResponse(data=_to_dto(result), request_id=request.state.request_id)


@router.post("/reject/{thread_id}", response_model=SuccessResponse[ChatResult])
async def reject(
    thread_id: str,
    request: Request,
    payload: RejectRequest = RejectRequest(),
    user: AuthClaims = Depends(current_user),
):
    """Reject the pending write on a thread and resume the operator.

    The write is skipped; the model is told it was rejected. Audit-logged.
    """
    graph = request.app.state.graph
    pending = await peek_pending(graph, {"configurable": {"thread_id": thread_id}})
    if pending is None:
        raise ResourceNotFoundError(
            "pending approval", details={"thread_id": thread_id}
        )

    log.warning(
        "WRITE REJECTED — approver=%s email=%s thread=%s sql=%r reason=%r",
        user.user_id,
        user.email,
        thread_id,
        pending.sql,
        payload.reason,
    )
    result = await resume_turn(
        graph,
        request.app.state.mcp_tools,
        thread_id,
        approve=False,
        tenant_id=payload.tenant_id or "default",
        reject_message=payload.reason,
    )
    return SuccessResponse(data=_to_dto(result), request_id=request.state.request_id)


@router.post("/stream")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    user: AuthClaims = Depends(current_user),
):
    """Chat with real-time SSE via graph.astream_events().

    Event types emitted:
      node_start        — a RAG subgraph node began (researcher/analyst/...)
      node_end          — a RAG subgraph node finished (auditor carries verdict)
      token             — one LLM output token
      tool_call         — a tool was invoked (name + input args)
      tool_result       — a tool returned (truncated output)
      approval_required — operator paused on a destructive write; carries the SQL
      final             — operator finished; carries the answer + citations
      error             — unhandled exception; stream closes after this
    """
    span = trace.get_current_span()
    span.set_attribute("openinference.span.kind", "AGENT")
    span.set_attribute("input.value", payload.question)
    graph = request.app.state.graph
    mcp_tools = request.app.state.mcp_tools
    thread_id = _thread_id(payload.thread_id, user, payload.tenant_id)

    from langchain_core.messages import HumanMessage

    initial_input = {"messages": [HumanMessage(content=payload.question)]}
    config = build_config(mcp_tools, payload.tenant_id, thread_id)

    async def event_generator():
        # RAG subgraph nodes still surface (nested under knowledge_base_qa), so
        # the trace stays rich even though the top-level graph is the operator.
        RAG_NODES = {"researcher", "analyst", "auditor", "finalizer"}

        def sse(event: TraceEvent) -> str:
            return f"data: {event.model_dump_json()}\n\n"

        try:
            async for raw in graph.astream_events(initial_input, config, version="v2"):
                kind: str = raw["event"]
                name: str = raw["name"]
                data: dict = raw["data"]
                node: str | None = raw.get("metadata", {}).get("langgraph_node")

                if kind == "on_chain_start" and name in RAG_NODES:
                    yield sse(
                        TraceEvent(
                            type="node_start", node=name, data={"status": "running"}
                        )
                    )

                elif kind == "on_chain_end" and name in RAG_NODES:
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

            # The stream has drained: the operator either paused on a write or
            # finished. Read the terminal state and emit the right closing event.
            result = await read_result(graph, config)
            if result.is_pending:
                p = result.pending
                yield sse(
                    TraceEvent(
                        type="approval_required",
                        node=None,
                        data={
                            "thread_id": p.thread_id,
                            "tool": p.tool,
                            "sql": p.sql,
                            "description": p.description,
                        },
                    )
                )
            else:
                citations = [
                    Citation(
                        document_id=s.get("document_id", ""),
                        source_name=s.get("source_name", ""),
                        heading_path=s.get("heading_path", []),
                        snippet=s.get("text", "")[:500],
                    )
                    for s in result.citations
                ]
                yield sse(
                    TraceEvent(
                        type="final",
                        node=None,
                        data={
                            "answer": result.answer,
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
