"""Auditor node — self-reflection: is the draft faithful to the sources?

Compares ``state["draft_answer"]`` against ``state["retrieved_docs"]`` with the
chat model and records a verdict. It also bumps ``revision_count`` so the loop
has a brake. It does NOT route — the conditional edge in graph.py reads the
verdict and decides revise (back to Researcher) vs. finish (END).

    async def auditor(state: AgentState) -> dict:
        ...  # returns {"audit_verdict": {...}, "revision_count": n + 1, ...}

TODO (next step): implement together with the conditional edge in graph.py.
"""
