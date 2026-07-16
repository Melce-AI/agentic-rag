"""Graph orchestration for the API (Design B, plan Step 5).

Routers stay thin (CLAUDE.md): everything about *how* to drive the operator
graph — invoke, resume, interrupt parsing, ``Command`` building, message-based
I/O, checkpointed-interrupt lookup — lives here. Routers only parse the request
and map these neutral results to HTTP DTOs.

The operator is a ``create_agent`` ReAct agent, so its I/O is message-based:
input is ``{"messages": [HumanMessage(question)]}`` and the answer is the last
AI message. Destructive writes pause via ``HumanInTheLoopMiddleware``; the pause
surfaces as an ``__interrupt__`` on the invoke result (and on the checkpointed
state), and is resumed later by a separate HTTP request (Approve/Reject).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.types import Command

from src.core.config import get_settings

log = logging.getLogger(__name__)

# Resume decision shapes for HumanInTheLoopMiddleware (verified against
# langchain 1.3.x — see docs/agents/hitl_operator_plan.md). The middleware
# interrupt payload is a HITLRequest; the resume payload is a HITLResponse:
# {"decisions": [<decision>]}, one decision per interrupted tool call.
_APPROVE_DECISION = {"type": "approve"}


def _reject_decision(message: str | None) -> dict:
    decision: dict = {"type": "reject"}
    if message:
        decision["message"] = message
    return decision


@dataclass
class PendingWrite:
    """A destructive tool call paused for human approval.

    Neutral (no HTTP/DTO knowledge): the router maps this to a PendingApproval
    DTO. ``sql`` is the exact statement that will run if approved — "approved ==
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


def build_config(mcp_tools: list[BaseTool], tenant_id: str, thread_id: str) -> dict:
    """Build the invoke config: runtime tools/tenant + the checkpoint thread.

    ``mcp_tools`` and ``tenant_id`` are runtime values (not persisted in the
    checkpoint), so they must be passed on every invoke/resume — the operator's
    tools (e.g. ``knowledge_base_qa``) read them from this config.
    """
    return {
        "configurable": {
            "mcp_tools": mcp_tools,
            "tenant_id": tenant_id,
            "thread_id": thread_id,
        },
        "recursion_limit": get_settings().agent_recursion_limit,
    }


def _parse_pending(interrupts: list, thread_id: str) -> PendingWrite | None:
    """Turn a HumanInTheLoopMiddleware interrupt into a PendingWrite.

    The interrupt value is a HITLRequest: {"action_requests": [{"name", "args",
    "description"}], ...}. Only the write tool is gated, so we take the first
    action request and read its SQL out of the tool args.
    """
    if not interrupts:
        return None
    value = getattr(interrupts[0], "value", interrupts[0])
    requests = (value or {}).get("action_requests") or []
    if not requests:
        return None
    action = requests[0]
    args = action.get("args") or {}
    return PendingWrite(
        thread_id=thread_id,
        tool=action.get("name", ""),
        sql=args.get("sql", ""),
        description=action.get("description", ""),
    )


def _extract_answer(messages: list) -> str:
    """The operator's answer is the last AI message with textual content."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            content = msg.content
            if isinstance(content, list):
                # Some providers return content blocks; join text parts.
                content = "".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            if content:
                return content
    return ""


def _extract_citations(messages: list) -> list[dict]:
    """Pull citations off any knowledge_base_qa tool results in the trail.

    The RAG tool surfaces its sources on the ToolMessage ``.artifact`` (via
    ``response_format="content_and_artifact"``), so the API can render citations
    even though retrieval happened one layer down, inside the tool.
    """
    citations: list[dict] = []
    for msg in messages:
        if not isinstance(msg, ToolMessage) or msg.name != "knowledge_base_qa":
            continue
        artifact = getattr(msg, "artifact", None) or {}
        citations.extend(artifact.get("sources", []))
    return citations


def _result_from_output(output: dict, thread_id: str) -> TurnResult:
    """Map a graph invoke/resume output to a neutral TurnResult.

    If the operator paused on the write tool, ``__interrupt__`` is present and we
    return a pending result; otherwise we extract the answer and citations.
    """
    pending = _parse_pending(output.get("__interrupt__") or [], thread_id)
    if pending is not None:
        return TurnResult(thread_id=thread_id, pending=pending)

    messages = output.get("messages", [])
    return TurnResult(
        thread_id=thread_id,
        answer=_extract_answer(messages),
        citations=_extract_citations(messages),
    )


async def run_turn(
    graph,
    mcp_tools: list[BaseTool],
    question: str,
    tenant_id: str,
    thread_id: str,
) -> TurnResult:
    """Run one operator turn for a new question.

    Returns a TurnResult that is either an answer (+ citations) or a pending
    write awaiting Approve/Reject.
    """
    log.info(
        "run_turn (thread=%s, tenant=%s): %s", thread_id, tenant_id, question[:120]
    )
    output = await graph.ainvoke(
        {"messages": [HumanMessage(content=question)]},
        config=build_config(mcp_tools, tenant_id, thread_id),
    )
    return _result_from_output(output, thread_id)


async def resume_turn(
    graph,
    mcp_tools: list[BaseTool],
    thread_id: str,
    approve: bool,
    tenant_id: str = "default",
    reject_message: str | None = None,
) -> TurnResult:
    """Resume a paused turn with a human Approve/Reject decision.

    The pause was created by ``interrupt_on`` (automatic); the resume is always
    external (this call). On approve, the already-decided SQL runs exactly as
    shown; on reject, the tool is skipped and the model is told it was rejected.
    The operator may then continue and could even pause again on a new write.
    """
    decision = _APPROVE_DECISION if approve else _reject_decision(reject_message)
    log.info("resume_turn (thread=%s): decision=%s", thread_id, decision["type"])
    output = await graph.ainvoke(
        Command(resume={"decisions": [decision]}),
        config=build_config(mcp_tools, tenant_id, thread_id),
    )
    return _result_from_output(output, thread_id)


async def peek_pending(graph, config: dict) -> PendingWrite | None:
    """Look up a checkpointed pending write for a thread, without resuming.

    Used by the streaming path: after the stream ends we ask the checkpoint
    whether the operator is paused on the write tool, and if so emit an
    approval-required event.
    """
    snapshot = await graph.aget_state(config)
    interrupts = list(getattr(snapshot, "interrupts", ()) or ())
    thread_id = config.get("configurable", {}).get("thread_id", "")
    return _parse_pending(interrupts, thread_id)


async def read_result(graph, config: dict) -> TurnResult:
    """Build a TurnResult from a thread's checkpointed state (no invoke).

    The streaming path drives the graph with ``astream_events`` and then reads
    the terminal state here: either a pending write (paused) or the finished
    answer + citations. Mirrors ``_result_from_output`` but sourced from the
    checkpoint snapshot instead of an invoke return value.
    """
    snapshot = await graph.aget_state(config)
    thread_id = config.get("configurable", {}).get("thread_id", "")
    interrupts = list(getattr(snapshot, "interrupts", ()) or ())
    pending = _parse_pending(interrupts, thread_id)
    if pending is not None:
        return TurnResult(thread_id=thread_id, pending=pending)

    messages = (snapshot.values or {}).get("messages", [])
    return TurnResult(
        thread_id=thread_id,
        answer=_extract_answer(messages),
        citations=_extract_citations(messages),
    )
