"""Researcher node test — the chat model and MCP tools are mocked.

We swap ``create_agent`` for a fake agent that returns a fixed message trail, so
the test verifies OUR wiring — that the node extracts the tool results into
``retrieved_docs`` and forwards the message trail — without a live LLM or MCP
server (AGENTS.md: mock LLM/MCP in tests).
"""

import asyncio

from langchain_core.messages import AIMessage, ToolMessage

from src.agents.nodes import researcher as researcher_mod


def _state(question: str) -> dict:
    return {
        "question": question,
        "messages": [],
        "retrieved_docs": [],
        "draft_answer": "",
        "audit_verdict": {},
        "revision_count": 0,
        "final_answer": "",
    }


def _patch(monkeypatch, fake_messages):
    async def fake_get_tools():
        return []

    class FakeAgent:
        async def ainvoke(self, inputs):
            return {"messages": fake_messages}

    monkeypatch.setattr(researcher_mod, "get_tools", fake_get_tools)
    monkeypatch.setattr(researcher_mod, "get_chat_model", lambda: object())
    monkeypatch.setattr(researcher_mod, "create_agent", lambda *a, **k: FakeAgent())


def test_researcher_extracts_tool_results(monkeypatch):
    _patch(
        monkeypatch,
        [
            AIMessage(content="", tool_calls=[]),
            ToolMessage(
                content="Wireless Mouse | 174.93",
                name="sql_query",
                tool_call_id="call_1",
            ),
            AIMessage(content="The top product is the Wireless Mouse."),
        ],
    )

    out = asyncio.run(researcher_mod.researcher(_state("top product?")))

    assert out["retrieved_docs"] == [
        {"tool": "sql_query", "content": "Wireless Mouse | 174.93"}
    ]
    # The full trail is forwarded; the add_messages reducer accumulates it.
    assert len(out["messages"]) == 3


def test_researcher_no_tool_calls_yields_empty_docs(monkeypatch):
    _patch(monkeypatch, [AIMessage(content="I cannot answer that.")])

    out = asyncio.run(researcher_mod.researcher(_state("???")))

    assert out["retrieved_docs"] == []
    assert len(out["messages"]) == 1
