"""Graph-orchestration service tests (Design B, plan Step 5).

The operator graph is faked: we assert that run_turn/resume_turn/peek_pending/
read_result parse the message-based I/O, the HITL interrupt payload, and build
the correct resume Command — without a live LLM/MCP/checkpointer.
"""

import asyncio
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from src.agents import service


# --- fakes -----------------------------------------------------------------


def _interrupt(sql, description="approve?"):
    """Mimic a HumanInTheLoopMiddleware interrupt (HITLRequest on .value)."""
    return SimpleNamespace(
        value={
            "action_requests": [
                {
                    "name": "sql_execute",
                    "args": {"sql": sql},
                    "description": description,
                }
            ]
        }
    )


def _kb_tool_message(sources):
    return ToolMessage(
        content="grounded answer",
        name="knowledge_base_qa",
        tool_call_id="c1",
        artifact={"sources": sources},
    )


class _FakeGraph:
    """ainvoke returns a preset output; aget_state returns a preset snapshot."""

    def __init__(self, output=None, snapshot=None):
        self._output = output or {}
        self._snapshot = snapshot
        self.invoked_with = None

    async def ainvoke(self, payload, config=None):
        self.invoked_with = payload
        return self._output

    async def aget_state(self, config):
        return self._snapshot


def _snapshot(values=None, interrupts=()):
    return SimpleNamespace(values=values or {}, interrupts=tuple(interrupts))


# --- run_turn --------------------------------------------------------------


def test_run_turn_returns_answer_and_citations():
    sources = [
        {"document_id": "d1", "source_name": "p.pdf", "heading_path": [], "text": "x"}
    ]
    output = {
        "messages": [
            HumanMessage(content="q"),
            _kb_tool_message(sources),
            AIMessage(content="Final answer."),
        ]
    }
    graph = _FakeGraph(output=output)

    result = asyncio.run(service.run_turn(graph, [], "q", "acme", "t1"))

    assert not result.is_pending
    assert result.answer == "Final answer."
    assert result.citations == sources


def test_run_turn_returns_pending_on_interrupt():
    output = {"__interrupt__": [_interrupt("UPDATE orders SET status='x' WHERE id=1")]}
    graph = _FakeGraph(output=output)

    result = asyncio.run(service.run_turn(graph, [], "change it", "acme", "t1"))

    assert result.is_pending
    assert result.pending.tool == "sql_execute"
    assert result.pending.sql == "UPDATE orders SET status='x' WHERE id=1"
    assert result.pending.thread_id == "t1"


# --- resume_turn -----------------------------------------------------------


def test_resume_turn_approve_builds_approve_command():
    graph = _FakeGraph(output={"messages": [AIMessage(content="done")]})

    result = asyncio.run(service.resume_turn(graph, [], "t1", approve=True))

    assert isinstance(graph.invoked_with, Command)
    assert graph.invoked_with.resume == {"decisions": [{"type": "approve"}]}
    assert result.answer == "done"


def test_resume_turn_reject_builds_reject_command_with_message():
    graph = _FakeGraph(output={"messages": [AIMessage(content="ok, not doing it")]})

    asyncio.run(
        service.resume_turn(graph, [], "t1", approve=False, reject_message="too risky")
    )

    assert graph.invoked_with.resume == {
        "decisions": [{"type": "reject", "message": "too risky"}]
    }


def test_resume_turn_reject_without_message():
    graph = _FakeGraph(output={"messages": [AIMessage(content="ok")]})

    asyncio.run(service.resume_turn(graph, [], "t1", approve=False))

    assert graph.invoked_with.resume == {"decisions": [{"type": "reject"}]}


# --- peek_pending / read_result -------------------------------------------


def test_peek_pending_finds_checkpointed_write():
    snap = _snapshot(interrupts=[_interrupt("DELETE FROM orders WHERE id=9")])
    graph = _FakeGraph(snapshot=snap)

    pending = asyncio.run(
        service.peek_pending(graph, {"configurable": {"thread_id": "t1"}})
    )

    assert pending is not None
    assert pending.sql == "DELETE FROM orders WHERE id=9"


def test_peek_pending_none_when_no_interrupt():
    graph = _FakeGraph(snapshot=_snapshot())

    pending = asyncio.run(
        service.peek_pending(graph, {"configurable": {"thread_id": "t1"}})
    )

    assert pending is None


def test_read_result_pending():
    snap = _snapshot(interrupts=[_interrupt("UPDATE customers SET x=1 WHERE id=2")])
    graph = _FakeGraph(snapshot=snap)

    result = asyncio.run(
        service.read_result(graph, {"configurable": {"thread_id": "t1"}})
    )

    assert result.is_pending
    assert result.pending.sql == "UPDATE customers SET x=1 WHERE id=2"


def test_read_result_answer():
    snap = _snapshot(values={"messages": [AIMessage(content="the answer")]})
    graph = _FakeGraph(snapshot=snap)

    result = asyncio.run(
        service.read_result(graph, {"configurable": {"thread_id": "t1"}})
    )

    assert not result.is_pending
    assert result.answer == "the answer"
