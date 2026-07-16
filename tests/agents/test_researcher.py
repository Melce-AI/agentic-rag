"""Researcher node test — the chat model and MCP tools are mocked.

We swap ``create_agent`` for a fake agent that returns a fixed message trail, so
the test verifies OUR wiring — that the node extracts the tool results into
``retrieved_docs`` and forwards the message trail — without a live LLM or MCP
server (AGENTS.md: mock LLM/MCP in tests).
"""

import asyncio

from langchain_core.messages import AIMessage, ToolMessage

from src.agents.knowledge_base.nodes import researcher as researcher_mod


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


def _fake_config() -> dict:
    """Minimal config with empty tools — no subprocess is opened."""
    return {"configurable": {"mcp_tools": [], "tenant_id": "default"}}


def _patch(monkeypatch, fake_messages):
    class FakeAgent:
        async def ainvoke(self, inputs):
            return {"messages": fake_messages}

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

    out = asyncio.run(researcher_mod.researcher(_state("top product?"), _fake_config()))

    assert out["retrieved_docs"] == [
        {"tool": "sql_query", "content": "Wireless Mouse | 174.93"}
    ]
    # The full trail is forwarded; the add_messages reducer accumulates it.
    assert len(out["messages"]) == 3


def test_researcher_no_tool_calls_yields_empty_docs(monkeypatch):
    _patch(monkeypatch, [AIMessage(content="I cannot answer that.")])

    out = asyncio.run(researcher_mod.researcher(_state("???"), _fake_config()))

    assert out["retrieved_docs"] == []
    assert len(out["messages"]) == 1


def test_researcher_no_rag_search_yields_empty_sources(monkeypatch):
    """Only rag_search yields sources; sql_query does not."""
    _patch(
        monkeypatch,
        [
            AIMessage(content="", tool_calls=[]),
            ToolMessage(
                content="Wireless Mouse | 174.93",
                name="sql_query",
                tool_call_id="call_1",
            ),
        ],
    )

    out = asyncio.run(researcher_mod.researcher(_state("top?"), _fake_config()))

    assert out["sources"] == []


def _patch_capturing(monkeypatch):
    """Patch create_agent to capture the (tools, system_prompt) it was built with."""
    captured = {}

    class FakeAgent:
        async def ainvoke(self, inputs):
            return {"messages": [AIMessage(content="done")]}

    def fake_create_agent(model, tools, system_prompt="", **kwargs):
        captured["tools"] = tools
        captured["prompt"] = system_prompt
        return FakeAgent()

    monkeypatch.setattr(researcher_mod, "get_chat_model", lambda: object())
    monkeypatch.setattr(researcher_mod, "create_agent", fake_create_agent)
    return captured


def test_researcher_scoped_to_rag_search_only(monkeypatch):
    """The researcher must receive rag_search only — never SQL/write tools."""
    from types import SimpleNamespace

    captured = _patch_capturing(monkeypatch)
    config = {
        "configurable": {
            "mcp_tools": [
                SimpleNamespace(name="rag_search"),
                SimpleNamespace(name="sql_query"),
                SimpleNamespace(name="sql_execute"),
            ],
            "tenant_id": "default",
        }
    }

    asyncio.run(researcher_mod.researcher(_state("q"), config))

    tool_names = [t.name for t in captured["tools"]]
    assert tool_names == ["rag_search"]


def test_researcher_folds_critique_on_revision(monkeypatch):
    """On a revision, the auditor critique is folded into the researcher prompt."""
    captured = _patch_capturing(monkeypatch)
    state = _state("q")
    state["revision_count"] = 1
    state["audit_verdict"] = {"faithful": False, "reason": "missing the refund window"}

    asyncio.run(researcher_mod.researcher(state, _fake_config()))

    assert "missing the refund window" in captured["prompt"]


def test_researcher_no_critique_on_first_pass(monkeypatch):
    """On the first pass (revision 0), no critique is appended."""
    captured = _patch_capturing(monkeypatch)
    state = _state("q")  # revision_count = 0
    state["audit_verdict"] = {"faithful": False, "reason": "should not appear"}

    asyncio.run(researcher_mod.researcher(state, _fake_config()))

    assert "should not appear" not in captured["prompt"]
