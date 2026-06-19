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

from src.agents.llm import get_chat_model
from src.agents.state import AgentState
from src.agents.tools import get_tools

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "researcher_system.md"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


async def researcher(state: AgentState) -> dict:
    """Run the research agent on the question and return the evidence it found.

    Returns only the slice of AgentState this node owns:
      - ``retrieved_docs``: the tool results, for the Analyst to ground its answer
      - ``messages``: the agent's reasoning/tool trail (accumulated via the
        ``add_messages`` reducer in state.py)
    """
    # Build the inner ReAct agent: chat model + MCP tools + system prompt.
    # create_agent returns a compiled graph that drives the tool-calling loop.
    # TODO: cache this — today it re-fetches tools / relaunches the MCP
    # subprocess on every call, including each revision loop.
    revision = state.get("revision_count", 0)
    log.info("Researcher starting (revision=%d): %s", revision, state["question"][:120])

    tools = await get_tools()
    agent = create_agent(get_chat_model(), tools, system_prompt=_load_prompt())

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

    log.info("Researcher done: retrieved %d doc(s)", len(retrieved_docs))
    return {"retrieved_docs": retrieved_docs, "messages": messages}
