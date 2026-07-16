"""Graph wiring tests — nodes mocked, the real StateGraph/edges exercised.

Two things are verified (langgraph_guide §11):
  1. route_after_audit is a pure decision function (faithful / budget logic).
  2. The compiled graph actually CYCLES: an unfaithful verdict loops back to the
     Researcher, and agent_max_revisions stops an always-unfaithful loop.

No live LLM/MCP — the three node functions are replaced with fakes (AGENTS.md).
"""

import asyncio
from types import SimpleNamespace

from src.agents import graph as graph_mod
from src.agents.graph import (
    WRITE_TOOL_NAME,
    _select_operator_tools,
    build_graph,
    build_rag_graph,
    route_after_audit,
)


class FakeSettings:
    agent_max_revisions = 2


def _init_state(question: str = "q") -> dict:
    return {
        "question": question,
        "messages": [],
        "retrieved_docs": [],
        "draft_answer": "",
        "audit_verdict": {},
        "revision_count": 0,
        "final_answer": "",
    }


# --- route_after_audit: pure decision logic ---


def test_route_finish_when_faithful(monkeypatch):
    monkeypatch.setattr(graph_mod, "get_settings", lambda: FakeSettings())
    state = {"audit_verdict": {"faithful": True}, "revision_count": 0}
    assert route_after_audit(state) == "finish"


def test_route_revise_when_unfaithful_under_budget(monkeypatch):
    monkeypatch.setattr(graph_mod, "get_settings", lambda: FakeSettings())
    state = {"audit_verdict": {"faithful": False}, "revision_count": 1}
    assert route_after_audit(state) == "revise"


def test_route_finish_when_budget_spent(monkeypatch):
    monkeypatch.setattr(graph_mod, "get_settings", lambda: FakeSettings())
    state = {"audit_verdict": {"faithful": False}, "revision_count": 2}
    assert route_after_audit(state) == "finish"


# --- compiled graph: the cycle really happens ---


def _patch_nodes(monkeypatch, auditor_fn):
    calls = {"researcher": 0, "analyst": 0, "auditor": 0, "finalizer": 0}

    async def fake_researcher(state):
        calls["researcher"] += 1
        return {"retrieved_docs": [{"tool": "t", "content": "c"}], "messages": []}

    async def fake_analyst(state):
        calls["analyst"] += 1
        return {"draft_answer": "draft", "messages": []}

    async def fake_finalizer(state):
        calls["finalizer"] += 1
        return {"final_answer": state["draft_answer"]}

    monkeypatch.setattr(graph_mod, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(graph_mod, "researcher", fake_researcher)
    monkeypatch.setattr(graph_mod, "analyst", fake_analyst)
    monkeypatch.setattr(graph_mod, "auditor", auditor_fn(calls))
    monkeypatch.setattr(graph_mod, "finalizer", fake_finalizer)
    return calls


def test_graph_loops_back_then_finishes(monkeypatch):
    def auditor_fn(calls):
        async def fake_auditor(state):
            calls["auditor"] += 1
            n = state.get("revision_count", 0) + 1
            return {
                "audit_verdict": {"faithful": n >= 2, "reason": "r"},
                "revision_count": n,
            }

        return fake_auditor

    calls = _patch_nodes(monkeypatch, auditor_fn)
    app = build_rag_graph()
    final = asyncio.run(app.ainvoke(_init_state()))

    assert calls["researcher"] == 2  # looped back to researcher once
    assert calls["finalizer"] == 1
    assert final["audit_verdict"]["faithful"] is True
    assert final["final_answer"] == "draft"


def test_graph_stops_at_revision_budget(monkeypatch):
    def auditor_fn(calls):
        async def fake_auditor(state):
            calls["auditor"] += 1
            n = state.get("revision_count", 0) + 1
            return {
                "audit_verdict": {"faithful": False, "reason": "r"},
                "revision_count": n,
            }

        return fake_auditor

    calls = _patch_nodes(monkeypatch, auditor_fn)
    app = build_rag_graph()
    final = asyncio.run(app.ainvoke(_init_state()))

    # max_revisions=2: auditor runs twice, then the budget brake ends the run.
    assert calls["auditor"] == 2
    assert calls["finalizer"] == 1
    assert final["final_answer"] == "draft"


# --- operator tool scoping (Design B) ---


def _fake_tool(name: str):
    return SimpleNamespace(name=name)


def test_operator_tool_scoping_excludes_rag_search():
    """The operator holds SQL read/write + logs, never rag_search (decision 4)."""
    mcp = [
        _fake_tool("rag_search"),
        _fake_tool("sql_query"),
        _fake_tool("list_tables"),
        _fake_tool("describe_table"),
        _fake_tool("read_logs"),
        _fake_tool("list_log_files"),
        _fake_tool("sql_execute"),
    ]
    selected = {t.name for t in _select_operator_tools(mcp)}

    assert "rag_search" not in selected
    assert WRITE_TOOL_NAME in selected
    assert {"sql_query", "list_tables", "describe_table", "read_logs"} <= selected


def test_build_graph_includes_kb_tool_and_write_gate(monkeypatch):
    """Operator is built with knowledge_base_qa + the write tool gated by HITL."""
    from langchain.agents.middleware import HumanInTheLoopMiddleware

    captured = {}

    def fake_create_agent(model, tools, **kwargs):
        captured["tools"] = tools
        captured["middleware"] = kwargs.get("middleware")
        return SimpleNamespace(name="operator")

    monkeypatch.setattr(graph_mod, "create_agent", fake_create_agent)
    monkeypatch.setattr(graph_mod, "get_chat_model", lambda: object())

    build_graph(mcp_tools=[_fake_tool("sql_execute"), _fake_tool("rag_search")])

    tool_names = [t.name for t in captured["tools"]]
    assert "knowledge_base_qa" in tool_names
    assert WRITE_TOOL_NAME in tool_names
    assert "rag_search" not in tool_names

    # The write tool is gated by HumanInTheLoopMiddleware(interrupt_on=...).
    mw = captured["middleware"]
    assert len(mw) == 1 and isinstance(mw[0], HumanInTheLoopMiddleware)
    assert WRITE_TOOL_NAME in mw[0].interrupt_on
