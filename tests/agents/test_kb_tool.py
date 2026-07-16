"""knowledge_base_qa tool test — the RAG subgraph is mocked.

Verifies OUR wiring: the tool forwards mcp_tools/tenant from the injected config
into the subgraph, returns the grounded answer as content, and surfaces the
subgraph's sources on the artifact (so the API can still render citations).
No live LLM/MCP — the compiled subgraph is replaced with a fake.
"""

import asyncio

from src.agents.knowledge_base import tool as rag_tool


class _FakeGraph:
    def __init__(self, result):
        self._result = result
        self.seen_config = None

    async def ainvoke(self, state, config=None):
        self.seen_config = config
        return self._result


def _call(question, config):
    # response_format="content_and_artifact" → the raw coroutine returns (str, dict).
    return asyncio.run(rag_tool.knowledge_base_qa.coroutine(question, config))


def test_kb_returns_answer_and_sources(monkeypatch):
    sources = [
        {
            "document_id": "d1",
            "source_name": "policy.pdf",
            "heading_path": ["Refunds"],
            "text": "You have 14 days.",
        }
    ]
    fake = _FakeGraph({"final_answer": "You have 14 days.", "sources": sources})
    monkeypatch.setattr(rag_tool, "get_rag_graph", lambda: fake)

    config = {"configurable": {"mcp_tools": ["tool"], "tenant_id": "acme"}}
    content, artifact = _call("refund window?", config)

    assert "You have 14 days." in content
    assert artifact["sources"] == sources
    # A compact, citable Sources tail is appended for the model.
    assert "Sources:" in content
    assert "policy.pdf" in content


def test_kb_forwards_tenant_and_tools(monkeypatch):
    fake = _FakeGraph({"final_answer": "ok", "sources": []})
    monkeypatch.setattr(rag_tool, "get_rag_graph", lambda: fake)

    config = {"configurable": {"mcp_tools": ["t1"], "tenant_id": "acme"}}
    _call("q", config)

    forwarded = fake.seen_config["configurable"]
    assert forwarded["tenant_id"] == "acme"
    assert forwarded["mcp_tools"] == ["t1"]


def test_kb_no_sources_has_no_sources_tail(monkeypatch):
    fake = _FakeGraph({"final_answer": "no docs matched", "sources": []})
    monkeypatch.setattr(rag_tool, "get_rag_graph", lambda: fake)

    content, artifact = _call("q", {"configurable": {}})

    assert artifact["sources"] == []
    assert "Sources:" not in content
