"""``knowledge_base_qa`` — the multi-agent RAG pipeline exposed as a single tool.

Design B (docs/agents/hitl_operator_plan.md): the top-level operator agent does
not retrieve documents itself. Instead it calls this tool, which runs the full
Researcher -> Analyst -> Auditor -> Finalizer subgraph (``build_rag_graph``) so
document Q&A keeps its self-reflection / faithfulness loop and citations.

The tool reads the pre-fetched MCP tools and the authenticated ``tenant_id`` from
the injected ``RunnableConfig`` — the same values the operator was invoked with —
and forwards them to the subgraph, which scopes ``rag_search`` to that tenant.

It returns ``(answer, {"sources": [...]})`` via ``content_and_artifact``: the
answer text goes to the model as the ToolMessage content, and the structured
sources ride along on the ToolMessage's ``.artifact`` so the API can still render
citations (the service layer reads them back off the message trail).
"""

import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.core.config import get_settings

log = logging.getLogger(__name__)

# Compiled lazily and cached: the subgraph is stateless wiring (nodes read their
# tools/tenant from config at runtime), so one compiled instance is reusable.
# Lazy so graph.py -> rag_tool.py -> graph.py import stays acyclic.
_rag_graph = None


def get_rag_graph():
    """Return the compiled RAG subgraph, building it once on first use."""
    global _rag_graph
    if _rag_graph is None:
        from src.agents.knowledge_base.graph import build_rag_graph

        _rag_graph = build_rag_graph()
    return _rag_graph


def _initial_rag_state(question: str) -> dict:
    return {
        "question": question,
        "messages": [],
        "retrieved_docs": [],
        "draft_answer": "",
        "audit_verdict": {},
        "revision_count": 0,
        "final_answer": "",
        "sources": [],
    }


@tool(response_format="content_and_artifact")
async def knowledge_base_qa(question: str, config: RunnableConfig) -> tuple[str, dict]:
    """Answer a question from the company's documents (the knowledge base).

    Use this for any unstructured/knowledge question — policies, docs, how-tos,
    definitions. It runs a grounded multi-agent retrieval pipeline that cites its
    sources. Do NOT use it for structured/numeric data in the SQL database (use
    the SQL tools) or for changing data (use sql_execute).

    Args:
        question: The user's question, phrased in full.
    """
    cfg = config.get("configurable", {}) if config else {}
    mcp_tools = cfg.get("mcp_tools", [])
    tenant_id = cfg.get("tenant_id", "default")

    log.info("knowledge_base_qa invoked (tenant=%s): %s", tenant_id, question[:120])

    result = await get_rag_graph().ainvoke(
        _initial_rag_state(question),
        config={
            "configurable": {"mcp_tools": mcp_tools, "tenant_id": tenant_id},
            "recursion_limit": get_settings().agent_recursion_limit,
        },
    )

    answer = result.get("final_answer", "") or "No answer could be produced."
    sources = result.get("sources", [])

    # Give the model a compact, citable "Sources" tail so it can reference them
    # in its reply; the full structured list rides on the artifact for the API.
    if sources:
        lines = []
        for i, s in enumerate(sources, 1):
            name = s.get("source_name") or "unknown"
            path = " > ".join(s.get("heading_path") or [])
            lines.append(f"[{i}] {name} > {path}" if path else f"[{i}] {name}")
        answer = f"{answer}\n\nSources:\n" + "\n".join(lines)

    log.info("knowledge_base_qa done: %d source(s)", len(sources))
    return answer, {"sources": sources}
