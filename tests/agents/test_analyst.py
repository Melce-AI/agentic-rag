"""Analyst node test — the chat model is mocked.

The fake model records the messages it receives and returns a fixed reply, so we
can assert both the output slice (draft_answer + appended message) and that the
node fed the evidence (and any critique) into the prompt. No live LLM (AGENTS.md).
"""

import asyncio

from langchain_core.messages import AIMessage

from src.agents.nodes import analyst as analyst_mod


def _state(**overrides) -> dict:
    state = {
        "question": "What is the top product by revenue?",
        "messages": [],
        "retrieved_docs": [{"tool": "sql_query", "content": "Wireless Mouse | 174.93"}],
        "draft_answer": "",
        "audit_verdict": {},
        "revision_count": 0,
        "final_answer": "",
    }
    state.update(overrides)
    return state


class FakeModel:
    def __init__(self):
        self.received = None

    async def ainvoke(self, messages):
        self.received = messages
        return AIMessage(content="The top product is the Wireless Mouse.")


def _patch(monkeypatch) -> FakeModel:
    model = FakeModel()
    monkeypatch.setattr(analyst_mod, "get_chat_model", lambda: model)
    return model


def test_analyst_drafts_from_evidence(monkeypatch):
    model = _patch(monkeypatch)

    out = asyncio.run(analyst_mod.analyst(_state()))

    assert out["draft_answer"] == "The top product is the Wireless Mouse."
    assert len(out["messages"]) == 1
    # The evidence was passed into the human prompt.
    human = model.received[-1].content
    assert "Wireless Mouse | 174.93" in human


def test_analyst_includes_auditor_critique_on_revision(monkeypatch):
    model = _patch(monkeypatch)

    out = asyncio.run(
        analyst_mod.analyst(
            _state(
                audit_verdict={
                    "faithful": False,
                    "reason": "Missing the revenue figure.",
                },
                revision_count=1,
            )
        )
    )

    human = model.received[-1].content
    assert "Missing the revenue figure." in human
    assert out["draft_answer"]
