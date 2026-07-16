"""Tests for the /chat/stream SSE endpoint (operator + HITL).

Verifies that the endpoint translates graph.astream_events() output into SSE
events, and that after the stream drains it reads the terminal checkpoint state
to emit either `final` (answer) or `approval_required` (paused on a write). The
graph is faked so no LLM/MCP/checkpointer is touched.
"""

import asyncio
import json
from types import SimpleNamespace

from langchain_core.messages import AIMessage, ToolMessage

from src.api.routers import chat as chat_module
from src.auth.claims import AuthClaims
from src.schemas.chat import ChatRequest


def _make_request(graph):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(graph=graph, mcp_tools=[])),
        state=SimpleNamespace(request_id="req-1"),
    )


def _payload(question="What is the policy?", tenant_id="tenant-a"):
    return ChatRequest(question=question, tenant_id=tenant_id)


def _user():
    return AuthClaims(user_id="u1", email="test@test.com", roles=["admin"])


async def _collect(response) -> list[dict]:
    events = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunk = chunk.decode()
        for line in chunk.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:") :].strip()))
    return events


def _snapshot(messages=None, interrupts=()):
    return SimpleNamespace(
        values={"messages": messages or []}, interrupts=tuple(interrupts)
    )


def _graph(events, snapshot=None):
    """Fake graph: astream_events yields `events`, aget_state returns `snapshot`."""

    async def astream_events(state, config, version="v2"):
        for ev in events:
            yield ev

    async def aget_state(config):
        return snapshot if snapshot is not None else _snapshot()

    return SimpleNamespace(astream_events=astream_events, aget_state=aget_state)


def _run(graph):
    async def run():
        resp = await chat_module.chat_stream(_payload(), _make_request(graph), _user())
        return await _collect(resp)

    return asyncio.run(run())


# --- event translation -----------------------------------------------------


def test_node_start_and_end_events():
    graph = _graph(
        [
            {
                "event": "on_chain_start",
                "name": "researcher",
                "data": {},
                "metadata": {"langgraph_node": "researcher"},
            },
            {
                "event": "on_chain_end",
                "name": "researcher",
                "data": {"output": {}},
                "metadata": {"langgraph_node": "researcher"},
            },
        ]
    )
    events = _run(graph)
    types = [e["type"] for e in events]
    assert "node_start" in types
    assert "node_end" in types


def test_token_event_forwarded():
    chunk = SimpleNamespace(content="Hello")
    graph = _graph(
        [
            {
                "event": "on_chat_model_stream",
                "name": "ChatOpenAI",
                "data": {"chunk": chunk},
                "metadata": {"langgraph_node": "analyst"},
            }
        ]
    )
    events = _run(graph)
    token_events = [e for e in events if e["type"] == "token"]
    assert token_events
    assert token_events[0]["data"]["content"] == "Hello"


def test_tool_call_and_result_events():
    graph = _graph(
        [
            {
                "event": "on_tool_start",
                "name": "knowledge_base_qa",
                "data": {"input": {"question": "q"}},
                "metadata": {},
            },
            {
                "event": "on_tool_end",
                "name": "knowledge_base_qa",
                "data": {"output": "grounded"},
                "metadata": {},
            },
        ]
    )
    events = _run(graph)
    types = [e["type"] for e in events]
    assert "tool_call" in types
    assert "tool_result" in types
    call = next(e for e in events if e["type"] == "tool_call")
    assert call["data"]["tool"] == "knowledge_base_qa"


def test_auditor_node_end_includes_verdict():
    verdict = {"faithful": True, "reason": "all good"}
    graph = _graph(
        [
            {
                "event": "on_chain_end",
                "name": "auditor",
                "data": {"output": {"audit_verdict": verdict}},
                "metadata": {"langgraph_node": "auditor"},
            }
        ]
    )
    events = _run(graph)
    node_end = next(
        (e for e in events if e["type"] == "node_end" and e["node"] == "auditor"), None
    )
    assert node_end is not None
    assert node_end["data"]["verdict"] == verdict


# --- closing events: final / approval_required -----------------------------


def test_final_event_from_terminal_state():
    sources = [
        {
            "document_id": "d1",
            "source_name": "policy.pdf",
            "heading_path": ["Sec 1"],
            "text": "MFA is required.",
        }
    ]
    kb_msg = ToolMessage(
        content="ans",
        name="knowledge_base_qa",
        tool_call_id="c1",
        artifact={"sources": sources},
    )
    snapshot = _snapshot(messages=[kb_msg, AIMessage(content="Use MFA.")])
    graph = _graph([], snapshot=snapshot)

    events = _run(graph)
    final = next((e for e in events if e["type"] == "final"), None)
    assert final is not None
    assert final["data"]["answer"] == "Use MFA."
    assert len(final["data"]["citations"]) == 1
    assert final["data"]["citations"][0]["source_name"] == "policy.pdf"


def test_approval_required_event_when_paused():
    interrupt = SimpleNamespace(
        value={
            "action_requests": [
                {
                    "name": "sql_execute",
                    "args": {"sql": "UPDATE orders SET status='shipped' WHERE id=1"},
                    "description": "Tool execution requires approval",
                }
            ]
        }
    )
    snapshot = _snapshot(interrupts=[interrupt])
    graph = _graph([], snapshot=snapshot)

    events = _run(graph)
    approval = next((e for e in events if e["type"] == "approval_required"), None)
    assert approval is not None
    assert approval["data"]["tool"] == "sql_execute"
    assert approval["data"]["sql"] == "UPDATE orders SET status='shipped' WHERE id=1"
    assert not any(e["type"] == "final" for e in events)


# --- error handling --------------------------------------------------------


def test_unexpected_error_emits_structured_error_event():
    async def bad_astream_events(state, config, version="v2"):
        raise RuntimeError("boom")
        yield

    graph = SimpleNamespace(astream_events=bad_astream_events)
    events = _run(graph)
    assert events
    err = events[0]
    assert err["type"] == "error"
    assert err["data"]["code"] == "AGT_GRAPH_500"
    assert err["data"]["details"] == "RuntimeError"


def test_app_exception_emits_structured_error_event():
    from src.core.exceptions import RagRetrievalError

    async def bad_astream_events(state, config, version="v2"):
        raise RagRetrievalError()
        yield

    graph = SimpleNamespace(astream_events=bad_astream_events)
    events = _run(graph)
    err = events[0]
    assert err["type"] == "error"
    assert err["data"]["code"] == "RAG_SEARCH_500"


def test_empty_token_not_emitted():
    chunk = SimpleNamespace(content="")
    graph = _graph(
        [
            {
                "event": "on_chat_model_stream",
                "name": "ChatOpenAI",
                "data": {"chunk": chunk},
                "metadata": {"langgraph_node": "analyst"},
            }
        ]
    )
    events = _run(graph)
    assert not any(e["type"] == "token" for e in events)
