"""MCP tool: hybrid RAG search over the Qdrant knowledge base."""

import logging

from mcp.server.fastmcp import FastMCP

from src.core.exceptions import RagRetrievalError
from src.mcp_server.schemas import MCPSearchResult
from src.rag.retriever import HybridRetriever

logger = logging.getLogger(__name__)


def register(mcp: FastMCP) -> None:
    retriever = HybridRetriever()

    @mcp.tool()
    async def rag_search(
        query: str, tenant_id: str, top_k: int = 5
    ) -> list[MCPSearchResult]:
        """Search the knowledge base using hybrid dense+sparse retrieval with reranking.

        Use this tool to retrieve relevant document chunks for a given question or topic.
        Results are ranked by relevance score (higher is better).

        Args:
            query: The search query or question to look up.
            tenant_id: The tenant whose knowledge base to search.
            top_k: Number of results to return (1–20, default 5).
        """
        top_k = max(1, min(top_k, 20))

        try:
            chunks = await retriever.search(
                query=query, tenant_id=tenant_id, top_k=top_k
            )
        except RagRetrievalError as exc:
            logger.error("rag_search failed: %s", exc)
            raise

        return [
            MCPSearchResult(
                document_id=chunk.document_id,
                source_name=chunk.source_name,
                heading_path=chunk.heading_path,
                text=chunk.text,
                score=chunk.score,
            )
            for chunk in chunks
        ]
