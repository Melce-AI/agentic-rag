"""Auditor node test — the structured-output judge is mocked.

The fake model's ``with_structured_output`` returns a judge that yields a fixed
AuditVerdict, so we verify the node's wiring: it returns the verdict as a dict
and increments revision_count. No live LLM (AGENTS.md).
"""

import asyncio

from src.agents.nodes import auditor as auditor_mod
from src.agents.nodes.auditor import AuditVerdict


def _state(**overrides) -> dict:
    state = {
        "question": "What is the top product by revenue?",
        "messages": [],
        "retrieved_docs": [{"tool": "sql_query", "content": "Wireless Mouse | 174.93"}],
        "draft_answer": "The top product is the Wireless Mouse.",
        "audit_verdict": {},
        "revision_count": 0,
        "final_answer": "",
    }
    state.update(overrides)
    return state


def _patch(monkeypatch, verdict: AuditVerdict) -> dict:
    captured = {}

    class FakeJudge:
        async def ainvoke(self, messages):
            captured["messages"] = messages
            return verdict

    class FakeModel:
        def with_structured_output(self, schema):
            captured["schema"] = schema
            return FakeJudge()

    monkeypatch.setattr(auditor_mod, "get_chat_model", lambda: FakeModel())
    return captured


def test_auditor_faithful_verdict_and_counter(monkeypatch):
    captured = _patch(
        monkeypatch, AuditVerdict(faithful=True, reason="Fully grounded.")
    )

    out = asyncio.run(auditor_mod.auditor(_state(revision_count=0)))

    assert out["audit_verdict"] == {"faithful": True, "reason": "Fully grounded."}
    assert out["revision_count"] == 1
    # The model was constrained to the structured schema.
    assert captured["schema"] is AuditVerdict
    # The draft and evidence were handed to the judge.
    human = captured["messages"][-1].content
    assert "Wireless Mouse" in human


def test_auditor_unfaithful_increments_existing_counter(monkeypatch):
    _patch(
        monkeypatch, AuditVerdict(faithful=False, reason="Revenue figure unsupported.")
    )

    out = asyncio.run(auditor_mod.auditor(_state(revision_count=2)))

    assert out["audit_verdict"]["faithful"] is False
    assert out["revision_count"] == 3
