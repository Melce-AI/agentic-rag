"""Operator graph tests (Design B) — the top-level agent's tool scoping + HITL gate.

The operator is a ``create_agent`` ReAct agent; here we verify OUR wiring without
a live LLM: which tools it is built with (SQL read/write + logs + the RAG tool,
never ``rag_search``) and that the write tool is gated by HumanInTheLoopMiddleware.
The RAG subgraph wiring is tested separately in test_rag_graph.py.
"""

from types import SimpleNamespace

from src.agents import graph as graph_mod
from src.agents.graph import WRITE_TOOL_NAME, _select_operator_tools, build_graph


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
