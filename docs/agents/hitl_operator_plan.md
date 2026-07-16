# HITL Write Operations — Operator-Agent Plan (Design B)

> Self-contained execution plan. A fresh session should be able to pick this up
> with no prior context. Read `docs/mcp/sql_tool_design.md`,
> `docs/local_notes/VIZYON 1.md` (Step 4), and `docs/architecture.md` first.

## Goal

Add HITL-gated destructive SQL (`UPDATE`/`DELETE`) to the runtime — Vision Step 4
("if the agent runs a critical SQL statement, a human Approve/Reject step"). The
write plumbing already exists (see "Reusable, already built"); what remains is the
**agent/graph layer** and the **API/UI** to drive approval.

## Architecture decision — Design B (LOCKED, do not re-litigate)

A **single top-level operator agent** (ReAct, `create_agent`) with:
- SQL **read** tools + `read_logs`,
- `sql_execute` (**write**) gated by `HumanInTheLoopMiddleware(interrupt_on={"sql_execute": True})`,
- `knowledge_base_qa` — a **tool** wrapping the existing RAG pipeline
  (researcher → analyst → auditor → finalizer) so document Q&A keeps its
  self-reflection/faithfulness loop.

```
START → operator agent (create_agent, ReAct, interrupt_on sql_execute) → END
          tools:
            - knowledge_base_qa   → RAG subgraph (researcher[ReAct] → analyst → auditor → finalizer)
            - sql_query / list_tables / describe_table   (read, sentinel_ro)
            - read_logs
            - sql_execute         (write, sentinel_rw, HITL-gated)
```

No `intent_router`, no read/write branches, no `planner`/`executor` nodes.

### Why B (so it isn't reopened)
- A router that classifies read-vs-write up front **traps** the flow: if it picks
  the read branch it can never write, and vice-versa. Real usage interleaves
  (explore → understand → maybe act; the user may not know upfront what to change).
- One ReAct operator can read repeatedly, understand intent, then act — naturally.
- The multi-agent RAG pipeline (Vision Step 3) is **preserved** as a callable tool,
  not thrown away.

## Locked design decisions

1. **Gate = `interrupt_on` (auto), NOT manual `interrupt()`.** The middleware calls
   `interrupt()` for us at the exact `sql_execute` tool-call boundary. This makes
   "approved == executed" **inherent** (the pause is at the decided tool call), so
   no planner/executor two-node split is needed.
2. **`interrupt_on` automates the PAUSE only — never the RESUME.** The human decision
   arrives later as a separate HTTP request (button click). So `/chat/approve` and
   `/chat/reject` endpoints are **required**; they call
   `graph.ainvoke(Command(resume=<middleware-format>), config={thread_id})`. The
   resume payload must match `HumanInTheLoopMiddleware`'s schema
   (accept / edit / reject), not a custom `{"decision": ...}`.
3. **Two-tier security stays (defense in depth):**
   - reads → `sentinel_ro` role + `ensure_read_only` guard (unchanged),
   - writes → `sentinel_rw` role + `ensure_write_safe` guard (single WHERE-qualified
     UPDATE/DELETE on a writable table only). Both already implemented.
4. **No redundant retrieval across layers.** The operator must **NOT** hold
   `rag_search` — it delegates all document retrieval to `knowledge_base_qa`. SQL
   tools live on the operator; `rag_search` lives only inside the RAG subgraph's
   researcher.
5. **`researcher` stays a ReAct agent** (`create_agent`) — its value is adaptive,
   multi-step retrieval (search → inspect → refine → search) within one call.
6. **Bonus (do it): feed the auditor's critique to the researcher.** Today the
   critique (`state["audit_verdict"]["reason"]`) only reaches the *analyst*
   (redraft). Also fold it into the researcher's prompt on a revision so the loop
   produces a *better query*, not just a better draft.
7. **Per-agent tool scoping (safety):** the RAG `researcher` must be built with
   **doc retrieval tools only** (`rag_search`) and must **never** receive
   `sql_execute`. Only the operator gets `sql_execute`, and it's gated. This is
   explicit per-agent construction, not fragile list-filtering.
8. **Memory:** Redis checkpointer + `thread_id` already give cross-turn memory
   (`create_agent` persists `messages`). Do not build a separate memory system.
9. **Preview / "diff":** with `interrupt_on` the approval surfaces the tool args
   (the SQL). For an affected-rows preview, prompt the operator to run a read
   (`sql_query SELECT ... WHERE ...`) BEFORE calling `sql_execute`; the preview
   shows in the trace and the approval shows the SQL. (Update README wording to
   "affected-rows preview", not "diff".)
10. **Layering (CLAUDE.md):** routers stay thin. Graph orchestration
    (invoke/resume, interrupt parsing, `Command`, AgentState shape) lives in
    `src/agents/service.py`. Routers parse the request and map to DTOs only.
11. **DRY / no hardcode:** writable tables come from `settings.postgres_writable_tables`
    (single source). Share helpers; don't duplicate.

## Reusable, already built (DO NOT rebuild — verify present)

Committed on the baseline; Design B reuses all of it unchanged:
- `src/core/config.py` — `postgres_rw_user/password`, `postgres_writable_tables`
  (`orders`, `customers`, `order_items`).  ⚠ has stale comments mentioning
  "executor node" — clean them up.
- `infra/postgres/initdb/04_create_readwrite_role.sh` — `sentinel_rw` role
  (SELECT/UPDATE/DELETE on the 3 tables only; no INSERT/TRUNCATE/DDL).
- `infra/postgres/docker-compose.yml` — `SENTINEL_RW_PASSWORD`.
- `.env.example` — `POSTGRES_RW_USER/PASSWORD`.
- `src/mcp_server/guards.py` — `ensure_write_safe` + shared `_clean_and_tokenize`
  (tests: `tests/mcp/test_sql_write_guard.py`).
- `src/adapters/sql/postgres.py` — role-parameterized `PostgresManager`,
  `run_write`, `postgres_write_manager` singleton.
- `src/mcp_server/tools/sql.py` — `sql_execute` MCP tool
  (tests: `tests/mcp/test_sql_tools.py`).

## Deleted / reverted to baseline (Design A/branch attempt — gone on purpose)

`intent_router`, `planner`, `executor` nodes + their prompts; `state.py`,
`graph.py`, `chat.py` reverted to the original RAG pipeline. Do not resurrect.

---

## Step-by-step (each step = one commit; run `uv run ruff check . && uv run ruff format && uv run pytest` per step)

### Step 0 — Verify baseline
- `git log --oneline`, `git status` (expect clean tree + write plumbing present,
  no intent_router/planner/executor).
- `uv run pytest` green (existing RAG tests + write-guard + sql_execute tests).
- Confirm the "Reusable, already built" files exist as described.

### Step 1 — RAG pipeline → reusable subgraph
- Rename current `build_graph()` → `build_rag_graph()` in `src/agents/graph.py`
  (researcher → analyst → auditor → finalizer). Behavior unchanged; it's no longer
  the top-level graph. Keep `AgentState` for the subgraph.
- Scope the RAG `researcher` to doc-retrieval tools only (`rag_search`); it must not
  receive `sql_execute`.
- Update `tests/agents/test_graph.py` for the rename.

### Step 2 — Bonus: critique → researcher (feedback-driven requery)
- In `src/agents/nodes/researcher.py`, fold `state["audit_verdict"]["reason"]` into
  the researcher prompt when `revision_count > 0` (mirror how `analyst.py` uses it),
  so a revision refines the retrieval query. Add a test.

### Step 3 — `knowledge_base_qa` tool
- New tool (e.g. `src/agents/rag_tool.py`) wrapping `build_rag_graph()`: input
  `question: str`, reads `mcp_tools` + `tenant_id` from the injected
  `RunnableConfig`, invokes the subgraph, returns the grounded answer.
- Surface citations: return `sources` too (via `response_format="content_and_artifact"`
  on the tool, or fold a compact "Sources:" block) so the API can still show them.
- Test with a mocked subgraph.

### Step 4 — Operator agent (new top-level graph)
- New `build_graph(mcp_tools, checkpointer)` builds the operator via `create_agent`:
  - tools = `knowledge_base_qa` + `sql_query`/`list_tables`/`describe_table` +
    `read_logs` + `sql_execute` (selected from `mcp_tools` by name; **no
    `rag_search`**).
  - `middleware=[HumanInTheLoopMiddleware(interrupt_on={"sql_execute": True})]`.
  - `checkpointer=<redis>`.
- Operator system prompt (new `.md` under `src/agents/prompts/`): answer document
  questions via `knowledge_base_qa`; use SQL read tools for data; for a change,
  first preview affected rows with a read, then call `sql_execute` (a human will
  approve). Never invent data.
- `app.py` lifespan already builds the graph after `load_mcp_tools` — pass
  `mcp_tools` into `build_graph`.
- Tests: operator routes a doc question to `knowledge_base_qa`; a write attempt
  triggers the interrupt; researcher/operator tool scoping (no `sql_execute` on
  researcher).

### Step 5 — `src/agents/service.py` (graph orchestration for the API)
- `run_turn(graph, mcp_tools, question, tenant_id, thread_id) -> TurnResult`
- `resume_turn(graph, mcp_tools, thread_id, decision) -> TurnResult`  (builds the
  middleware-format `Command(resume=...)`)
- `peek_pending(graph, config) -> PendingWrite | None` (checkpointed-interrupt
  lookup for the stream path)
- `TurnResult` / `PendingWrite` neutral dataclasses (no HTTP/DTO knowledge).
- Operator I/O is message-based (`{"messages": [HumanMessage(question)]}`), answer
  = last AI message. Verify the exact `interrupt_on` interrupt + resume shapes
  against the installed langchain/langgraph version before finalizing.

### Step 6 — API (thin router)
- `POST /chat` → `run_turn`; return answer or `pending_approval` (sql + preview +
  thread_id).
- `POST /chat/stream` → SSE trace; emit `approval_required` when paused.
- `POST /chat/approve/{thread_id}` / `POST /chat/reject/{thread_id}` → `resume_turn`;
  auth required; audit-log who approved/rejected.
- `PendingApproval` DTO in `schemas/chat.py`; `response_model=SuccessResponse[ChatAnswer | PendingApproval]`.
- Keep thin: only request parsing + DTO mapping; everything else in `service.py`.

### Step 7 — Streamlit approve/reject UI
- `streamlit/app.py`: on `approval_required`, show SQL + affected-rows preview +
  Approve / Reject buttons → call `/chat/approve|reject`. GIF-able.

### Step 8 — Docs + README
- `docs/mcp/sql_tool_design.md`: change the "Future" note → "Implemented".
- `docs/architecture.md`, `docs/backlog.md`, `README.md`: mark Step 4 done; describe
  the operator + RAG-as-tool + HITL design; use "affected-rows preview" wording.

## Gotchas / learnings (from the design session)

- `interrupt_on` **requires** a checkpointer (already wired to Redis).
- Pause is automatic; **resume is always external** → endpoints are mandatory.
- With `interrupt_on`, the pause is at the tool-call boundary, so the approved SQL
  is exactly what runs — no need for the manual two-node "propose then execute" trick.
- Nested `create_agent` (operator → `knowledge_base_qa` → researcher) is fine **only
  if tool sets don't overlap across layers** (operator: SQL/ops + delegate; researcher:
  doc retrieval). Overlap = redundant retrieval.
- The researcher must never be handed `sql_execute` (it's a separate `create_agent`;
  an ungated write there would bypass approval).
- `config.py` has stale "executor"/"planner" comments to remove.
- Verify the exact `HumanInTheLoopMiddleware` resume schema against the installed
  version; it drives the `/approve` `/reject` payload shape.
