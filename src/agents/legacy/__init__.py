"""Deprecated agent implementations, kept for reference only.

``sql_agent.py`` is the original hand-written single-agent ReAct loop (manual
tool-calling over the MCP tools, HF/Ollama backends). It has been superseded by
the LangGraph operator (``src/agents/graph.py``) + the multi-agent
``knowledge_base`` pipeline. Nothing new should depend on this package; it stays
as a reference for the manual tool-calling / tracing patterns.
"""
