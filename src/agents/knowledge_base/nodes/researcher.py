"""Researcher node — finds the context needed to answer the question.

Pattern: an agent *inside* a node (a subgraph). Rather than hand-writing the
tool-calling loop, we embed LangChain's prebuilt agent (``create_agent``) and
run it as this single node. The prebuilt agent owns the inner loop — think, call
a tool, read the result, repeat until done — and returns the full message trail.
Our job is only to feed it the question and map its output back into AgentState.

It gathers evidence via the MCP tools and does NOT write the final answer; that
is the Analyst's job (single responsibility).
"""

import logging
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from src.agents.llm import get_chat_model
from src.agents.knowledge_base.state import AgentState

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "researcher_system.md"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


async def researcher(state: AgentState, config: RunnableConfig) -> dict:
    """Run the research agent on the question and return the evidence it found.

    Receives pre-fetched MCP tools via ``config["configurable"]["mcp_tools"]``
    (loaded once at startup in app.py lifespan, bound to a persistent session).
    No subprocess is spawned per call; tests inject a list of fake tools.

    Returns only the slice of AgentState this node owns:
      - ``retrieved_docs``: the tool results, for the Analyst to ground its answer
      - ``messages``: the agent's reasoning/tool trail (accumulated via the
        ``add_messages`` reducer in state.py)
    """
    # Scope the Researcher to document retrieval only (plan, decision 7): it must
    # hold rag_search and nothing else — never sql_execute. SQL and log tools live
    # on the top-level operator; document retrieval is this subgraph's whole job.
    tools = [t for t in config["configurable"]["mcp_tools"] if t.name == "rag_search"]
    tenant_id = config["configurable"]["tenant_id"]
    revision = state.get("revision_count", 0)
    log.info("Researcher starting (revision=%d): %s", revision, state["question"][:120])

    # Inject the authenticated tenant into the system prompt so rag_search is
    # always scoped to the caller's data. tenant_id is a security boundary from
    # the request — it must come from here, never be chosen by the model.
    prompt = _load_prompt() + (
        f'\n\nThe current tenant is "{tenant_id}". Always pass exactly this '
        "value as the tenant_id argument when calling rag_search."
    )

    # On a revision loop, fold in the Auditor's critique so the Researcher issues
    # a BETTER query this time, not just so the Analyst redrafts (plan, decision
    # 6 — mirror how analyst.py uses the same critique). Only on revisions.
    verdict = state.get("audit_verdict") or {}
    if revision > 0 and verdict.get("reason"):
        prompt += (
            "\n\nYour previous evidence was judged insufficient. Critique to "
            f"address by retrieving better/more targeted evidence:\n{verdict['reason']}"
        )

    agent = create_agent(get_chat_model(), tools, system_prompt=prompt)

    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=state["question"])]}
    )
    messages = result["messages"]

    # Pull the fetched evidence out of the ToolMessages so the Analyst can use it
    # as a distinct field. Overwrite each revision (see state.py reducer note).
    retrieved_docs = [
        {"tool": m.name, "content": m.content}
        for m in messages
        if isinstance(m, ToolMessage)
    ]

    # Extract citable sources from rag_search results. The MCP adapter keeps the
    # tool's structured output (MCPSearchResult fields) on the ToolMessage's
    # `.artifact` (response_format="content_and_artifact"), so we read it directly
    # — no parsing of the human-readable content string. Only rag_search yields
    # citable sources; sql_query / read_logs do not.
    sources: list[dict] = []
    for m in messages:
        if not isinstance(m, ToolMessage) or m.name != "rag_search":
            continue
        artifact = getattr(m, "artifact", None) or {}
        structured = artifact.get("structured_content") or {}
        for item in structured.get("result", []):
            sources.append(
                {
                    "document_id": item.get("document_id", ""),
                    "source_name": item.get("source_name", ""),
                    "heading_path": item.get("heading_path", []),
                    "text": item.get("text", ""),
                }
            )

    log.info("Researcher done: retrieved %d doc(s)", len(retrieved_docs))
    return {"retrieved_docs": retrieved_docs, "sources": sources, "messages": messages}
