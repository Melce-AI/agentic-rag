"""Tests for the /chat/stream SSE endpoint.

Verifies that the endpoint correctly translates graph.astream_events() output
into SSE events. The graph is replaced with a fake async generator so no LLM
or MCP calls are made.
"""

import asyncio
import json
from types import SimpleNamespace

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
    """Drain a StreamingResponse body and parse each SSE line into a dict."""
    events = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunk = chunk.decode()
        for line in chunk.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:") :].strip()))
    return events


# ---------------------------------------------------------------------------
# Fake graph factories
# ---------------------------------------------------------------------------


def _graph_with_events(*raw_events):
    """Return a fake graph whose astream_events yields the given dicts."""

    async def astream_events(state, config, version="v2"):
        for ev in raw_events:
            yield ev

    return SimpleNamespace(astream_events=astream_events)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_node_start_and_end_events():
    graph = _graph_with_events(
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
        {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {"output": {"final_answer": "ok", "sources": []}},
            "metadata": {},
        },
    )

    async def run():
        resp = await chat_module.chat_stream(_payload(), _make_request(graph), _user())
        return await _collect(resp)

    events = asyncio.run(run())
    types = [e["type"] for e in events]
    assert "node_start" in types
    assert "node_end" in types
    start = next(e for e in events if e["type"] == "node_start")
    assert start["node"] == "researcher"
    assert start["data"]["status"] == "running"


def test_token_event_forwarded():
    chunk = SimpleNamespace(content="Hello")
    graph = _graph_with_events(
        {
            "event": "on_chat_model_stream",
            "name": "ChatOpenAI",
            "data": {"chunk": chunk},
            "metadata": {"langgraph_node": "analyst"},
        },
        {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {"output": {"final_answer": "Hello", "sources": []}},
            "metadata": {},
        },
    )

    async def run():
        resp = await chat_module.chat_stream(_payload(), _make_request(graph), _user())
        return await _collect(resp)

    events = asyncio.run(run())
    token_events = [e for e in events if e["type"] == "token"]
    assert token_events, "expected at least one token event"
    assert token_events[0]["data"]["content"] == "Hello"
    assert token_events[0]["node"] == "analyst"


def test_tool_call_and_result_events():
    graph = _graph_with_events(
        {
            "event": "on_tool_start",
            "name": "rag_search",
            "data": {"input": {"query": "q"}},
            "metadata": {"langgraph_node": "researcher"},
        },
        {
            "event": "on_tool_end",
            "name": "rag_search",
            "data": {"output": "chunk text"},
            "metadata": {"langgraph_node": "researcher"},
        },
        {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {"output": {"final_answer": "done", "sources": []}},
            "metadata": {},
        },
    )

    async def run():
        resp = await chat_module.chat_stream(_payload(), _make_request(graph), _user())
        return await _collect(resp)

    events = asyncio.run(run())
    types = [e["type"] for e in events]
    assert "tool_call" in types
    assert "tool_result" in types
    call = next(e for e in events if e["type"] == "tool_call")
    assert call["data"]["tool"] == "rag_search"
    assert call["data"]["input"] == {"query": "q"}


def test_final_event_carries_answer_and_citations():
    sources = [
        {
            "document_id": "d1",
            "source_name": "policy.pdf",
            "heading_path": ["Sec 1"],
            "text": "MFA is required.",
        }
    ]
    graph = _graph_with_events(
        {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {"output": {"final_answer": "Use MFA.", "sources": sources}},
            "metadata": {},
        },
    )

    async def run():
        resp = await chat_module.chat_stream(_payload(), _make_request(graph), _user())
        return await _collect(resp)

    events = asyncio.run(run())
    final = next((e for e in events if e["type"] == "final"), None)
    assert final is not None
    assert final["data"]["answer"] == "Use MFA."
    assert len(final["data"]["citations"]) == 1
    assert final["data"]["citations"][0]["source_name"] == "policy.pdf"


def test_auditor_node_end_includes_verdict():
    verdict = {"faithful": True, "reason": "all good"}
    graph = _graph_with_events(
        {
            "event": "on_chain_end",
            "name": "auditor",
            "data": {"output": {"audit_verdict": verdict}},
            "metadata": {"langgraph_node": "auditor"},
        },
        {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {"output": {"final_answer": "ok", "sources": []}},
            "metadata": {},
        },
    )

    async def run():
        resp = await chat_module.chat_stream(_payload(), _make_request(graph), _user())
        return await _collect(resp)

    events = asyncio.run(run())
    node_end = next(
        (e for e in events if e["type"] == "node_end" and e["node"] == "auditor"), None
    )
    assert node_end is not None
    assert node_end["data"]["verdict"] == verdict


def test_unexpected_error_emits_structured_error_event():
    async def bad_astream_events(state, config, version="v2"):
        raise RuntimeError("boom")
        yield  # make it a generator

    graph = SimpleNamespace(astream_events=bad_astream_events)

    async def run():
        resp = await chat_module.chat_stream(_payload(), _make_request(graph), _user())
        return await _collect(resp)

    events = asyncio.run(run())
    assert events, "expected at least one event (the error)"
    err = events[0]
    assert err["type"] == "error"
    # Unexpected errors must not leak internal exception messages.
    assert "code" in err["data"] and "message" in err["data"]
    assert err["data"]["code"] == "AGT_GRAPH_500"
    assert err["data"]["details"] == "RuntimeError"


def test_app_exception_emits_structured_error_event():
    from src.core.exceptions import RagRetrievalError

    async def bad_astream_events(state, config, version="v2"):
        raise RagRetrievalError()
        yield

    graph = SimpleNamespace(astream_events=bad_astream_events)

    async def run():
        resp = await chat_module.chat_stream(_payload(), _make_request(graph), _user())
        return await _collect(resp)

    events = asyncio.run(run())
    err = events[0]
    assert err["type"] == "error"
    assert err["data"]["code"] == "RAG_SEARCH_500"
    assert "retrieval" in err["data"]["message"].lower()


def test_empty_token_not_emitted():
    chunk = SimpleNamespace(content="")
    graph = _graph_with_events(
        {
            "event": "on_chat_model_stream",
            "name": "ChatOpenAI",
            "data": {"chunk": chunk},
            "metadata": {"langgraph_node": "analyst"},
        },
        {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {"output": {"final_answer": "", "sources": []}},
            "metadata": {},
        },
    )

    async def run():
        resp = await chat_module.chat_stream(_payload(), _make_request(graph), _user())
        return await _collect(resp)

    events = asyncio.run(run())
    assert not any(e["type"] == "token" for e in events)
