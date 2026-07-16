"""Multi-agent RAG pipeline (Researcher → Analyst → Auditor → Finalizer).

Exposed to the top-level operator as the ``knowledge_base_qa`` tool (see
``tool.py``); ``graph.py`` builds the subgraph and ``state.py`` holds its state.
"""
