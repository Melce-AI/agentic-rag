"""Tests for the rag_search MCP tool with the retriever mocked.

No live Qdrant/embeddings (AGENTS.md: mock Qdrant in tests). We replace
HybridRetriever with a fake so we test only the tool's own behavior: mapping
chunks to MCPSearchResult and clamping top_k. Driven through mcp.call_tool, like
a real client.
"""

import asyncio

import pytest
from mcp.server.fastmcp import FastMCP

from src.mcp_server.tools import rag_search
from src.rag.models import RetrievedChunk


class _FakeRetriever:
    def __init__(self, chunks):
        self._chunks = chunks
        self.calls = []

    async def search(self, *, query, tenant_id, top_k):
        self.calls.append({"query": query, "tenant_id": tenant_id, "top_k": top_k})
        return self._chunks


def _register_with(monkeypatch, chunks):
    fake = _FakeRetriever(chunks)
    # register() builds the retriever via HybridRetriever(); patch the factory so
    # the closure captures our fake instead of a real (Qdrant-backed) one.
    monkeypatch.setattr(rag_search, "HybridRetriever", lambda: fake)
    mcp = FastMCP("test")
    rag_search.register(mcp)
    return mcp, fake


def _result(call_tool_result):
    # FastMCP.call_tool returns (content_list, result_dict).
    _, structured = call_tool_result
    return structured["result"]


def test_rag_search_maps_chunks_to_results(monkeypatch):
    chunks = [
        RetrievedChunk(
            chunk_id="c1",
            document_id="d1",
            source_name="guide.md",
            heading_path=["Intro", "Setup"],
            text="hello world",
            score=0.91,
            metadata={"retrieval_score": 0.4},
        )
    ]
    mcp, _ = _register_with(monkeypatch, chunks)

    results = _result(
        asyncio.run(mcp.call_tool("rag_search", {"query": "hi", "tenant_id": "t1"}))
    )

    # chunk_id and metadata are intentionally dropped by MCPSearchResult.
    assert results == [
        {
            "document_id": "d1",
            "source_name": "guide.md",
            "heading_path": ["Intro", "Setup"],
            "text": "hello world",
            "score": 0.91,
        }
    ]


def test_rag_search_forwards_query_and_tenant(monkeypatch):
    mcp, fake = _register_with(monkeypatch, [])

    asyncio.run(mcp.call_tool("rag_search", {"query": "invoices", "tenant_id": "acme"}))

    assert fake.calls[0]["query"] == "invoices"
    assert fake.calls[0]["tenant_id"] == "acme"


@pytest.mark.parametrize("requested, expected", [(50, 20), (0, 1), (-5, 1), (5, 5)])
def test_rag_search_clamps_top_k(monkeypatch, requested, expected):
    mcp, fake = _register_with(monkeypatch, [])

    asyncio.run(
        mcp.call_tool(
            "rag_search", {"query": "q", "tenant_id": "t1", "top_k": requested}
        )
    )

    assert fake.calls[0]["top_k"] == expected


def test_rag_search_empty_results(monkeypatch):
    mcp, _ = _register_with(monkeypatch, [])

    results = _result(
        asyncio.run(mcp.call_tool("rag_search", {"query": "q", "tenant_id": "t1"}))
    )

    assert results == []
