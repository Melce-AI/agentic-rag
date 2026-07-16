"""Tests for the /chat, /chat/approve, /chat/reject endpoints (operator + HITL).

The router is thin: it parses the request, calls the service, and maps the
neutral TurnResult to the response DTO. Here the graph is faked so we exercise
that mapping — answer vs. pending_approval, the 404 when nothing is pending, and
that approve/reject reach the graph with the right resume Command.
"""

import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage
from langgraph.types import Command

from src.api.routers import chat as chat_module
from src.auth.claims import AuthClaims
from src.core.exceptions import ResourceNotFoundError
from src.schemas.chat import ApproveRequest, ChatRequest, RejectRequest


def _interrupt(sql):
    return SimpleNamespace(
        value={"action_requests": [{"name": "sql_execute", "args": {"sql": sql}}]}
    )


def _snapshot(messages=None, interrupts=()):
    return SimpleNamespace(
        values={"messages": messages or []}, interrupts=tuple(interrupts)
    )


class _FakeGraph:
    def __init__(self, output=None, snapshot=None):
        self._output = output or {}
        self._snapshot = snapshot
        self.invoked_with = None

    async def ainvoke(self, payload, config=None):
        self.invoked_with = payload
        return self._output

    async def aget_state(self, config):
        return self._snapshot


def _request(graph):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(graph=graph, mcp_tools=[])),
        state=SimpleNamespace(request_id="req-1"),
    )


def _user():
    return AuthClaims(user_id="u1", email="ops@test.com", roles=["admin"])


# --- POST /chat ------------------------------------------------------------


def test_chat_returns_answer():
    graph = _FakeGraph(output={"messages": [AIMessage(content="hello")]})
    payload = ChatRequest(question="hi", tenant_id="acme")

    resp = asyncio.run(chat_module.chat(payload, _request(graph), _user()))

    assert resp.data.status == "answer"
    assert resp.data.answer == "hello"


def test_chat_returns_pending_approval():
    graph = _FakeGraph(
        output={"__interrupt__": [_interrupt("DELETE FROM orders WHERE id=1")]}
    )
    payload = ChatRequest(question="delete order 1", tenant_id="acme")

    resp = asyncio.run(chat_module.chat(payload, _request(graph), _user()))

    assert resp.data.status == "pending_approval"
    assert resp.data.sql == "DELETE FROM orders WHERE id=1"
    assert resp.data.tool == "sql_execute"


# --- POST /chat/approve/{thread_id} ---------------------------------------


def test_approve_resumes_and_returns_answer():
    graph = _FakeGraph(
        output={"messages": [AIMessage(content="done, 1 row")]},
        snapshot=_snapshot(interrupts=[_interrupt("UPDATE orders SET x=1 WHERE id=1")]),
    )

    resp = asyncio.run(
        chat_module.approve("t1", _request(graph), ApproveRequest(), _user())
    )

    assert resp.data.status == "answer"
    assert resp.data.answer == "done, 1 row"
    # Resumed with an approve decision.
    assert isinstance(graph.invoked_with, Command)
    assert graph.invoked_with.resume == {"decisions": [{"type": "approve"}]}


def test_approve_404_when_nothing_pending():
    graph = _FakeGraph(snapshot=_snapshot())  # no interrupts

    with pytest.raises(ResourceNotFoundError):
        asyncio.run(
            chat_module.approve("t1", _request(graph), ApproveRequest(), _user())
        )


# --- POST /chat/reject/{thread_id} ----------------------------------------


def test_reject_resumes_with_reason():
    graph = _FakeGraph(
        output={"messages": [AIMessage(content="ok, cancelled")]},
        snapshot=_snapshot(interrupts=[_interrupt("DELETE FROM orders WHERE id=1")]),
    )

    resp = asyncio.run(
        chat_module.reject(
            "t1", _request(graph), RejectRequest(reason="too risky"), _user()
        )
    )

    assert resp.data.status == "answer"
    assert graph.invoked_with.resume == {
        "decisions": [{"type": "reject", "message": "too risky"}]
    }


def test_reject_404_when_nothing_pending():
    graph = _FakeGraph(snapshot=_snapshot())

    with pytest.raises(ResourceNotFoundError):
        asyncio.run(chat_module.reject("t1", _request(graph), RejectRequest(), _user()))
