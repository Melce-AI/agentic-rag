"""Analyst node — turns the retrieved context into a draft answer.

Reads ``state["retrieved_docs"]`` and ``state["question"]`` and calls the chat
model (``get_chat_model()``) to produce a grounded draft. It does NOT fetch data
(that is the Researcher) and does NOT decide if it is good enough (the Auditor).

    async def analyst(state: AgentState) -> dict:
        ...  # returns {"draft_answer": "...", "messages": [...]}

TODO (next step): implement after the Researcher node works end to end.
"""
