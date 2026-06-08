"""Researcher node — finds the context needed to answer the question.

Reads ``state["question"]`` (and prior messages on a revision), calls the MCP
tools through the bridge in ``src/agents/tools.py`` (rag_search, sql_query) and
returns the sources it found. It does NOT write the answer — that is the
Analyst's job (single responsibility).

    async def researcher(state: AgentState) -> dict:
        ...  # returns {"retrieved_docs": [...], "messages": [...]}

TODO (next step): implement once tools.py (the MCP -> LangChain bridge) exists.
"""
