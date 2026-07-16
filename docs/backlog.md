# Backlog & Open Items

Living list of known gaps and technical debt, grouped by the Vision 1 roadmap
step they belong to. Checked items are done; unchecked are pending. Keep this in
sync as work lands — it is the single place to see "what's left".

See also: `README.md` (high-level status), `docs/architecture.md` (phase
mapping), `AGENTS.md` (roadmap).

## Roadmap status

- [x] **Step 1 — Advanced RAG** (chunking, hybrid search, reranking, parsing)
- [x] **Step 2 — MCP Server** (read-only SQL tools, log tools, safety guards)
- [x] **Step 3 — Multi-agent orchestration** — graph, nodes, routing, Redis
      checkpointer, tenant-scoped retrieval done. The RAG pipeline is now the
      reusable `knowledge_base_qa` subgraph (`build_rag_graph`).
- [x] **Step 4 — Operator + HITL** — top-level ReAct operator (`build_graph`)
      over `knowledge_base_qa` + SQL read/write + logs; SSE streaming, citations,
      and human approval for destructive `sql_execute` via
      `HumanInTheLoopMiddleware` + `/chat/approve|reject` + Streamlit UI.
- [ ] **Step 5 — Evals (Ragas faithfulness CI gate)** — not started.

## Open items (by priority)

### High
- [x] **Real SSE streaming.** Replaced post-hoc simulation with
      `graph.astream_events(version="v2")`. Emits `node_start`, `node_end`,
      `token`, `tool_call`, `tool_result`, and `final` events live as the graph
      executes. Also fixed missing `tenant_id` in stream config. (Step 4)
- [x] **HITL approval flow.** The operator holds `sql_execute` behind
      `HumanInTheLoopMiddleware(interrupt_on={"sql_execute": True})`, so a
      destructive write pauses at the tool-call boundary. `/chat/approve/{thread_id}`
      and `/chat/reject/{thread_id}` resume via `Command(resume=...)`; the
      Streamlit console shows the SQL + affected-rows preview and Approve/Reject.
      (Step 4)
- [ ] **Evals pipeline.** Add Ragas (faithfulness, context precision), a golden
      Q&A dataset, and a CI gate that blocks merge below threshold. (Step 5)

### Medium
- [ ] **Reranking latency decision.** CPU cross-encoder reranking adds ~11s per
      search (warm). Currently disabled via `RAG_RERANK_ENABLED=false` for speed.
      Decide: keep off / re-enable with fewer candidates (`RAG_RETRIEVAL_CANDIDATES`
      20→8) / accept cost. Document the decision in `.env.example`.
- [ ] **Model warm-up at startup.** First search is ~9s (cold load of embedding/
      rerank models). Warm them in the app lifespan so the first request is fast.
- [ ] **Citation quality.** Low-score, irrelevant chunks still appear as citations.
      Add a score threshold or cite only sources the Analyst actually used.
- [ ] **MCP server tracing.** The MCP server runs as a separate process and does
      not call `setup_tracing()`, so inner Qdrant/rerank spans never reach Phoenix.
      Propagate trace context from the agent to the tool process.

### Security / ops
- [ ] **Rotate secrets.** Real OpenRouter and Hugging Face keys are in the local
      `.env`. Rotate before any non-local deployment. (`.env` is gitignored.)
- [ ] **Auth Phase 2–3.** Refresh tokens, user registration, role-based authz.
      Phase 1 (login + RS256 validation + endpoint protection) is done.

## Done (recent)
- [x] HITL write operations (Design B): operator agent + RAG-as-tool +
      `HumanInTheLoopMiddleware` gate + approve/reject endpoints + Streamlit UI.
- [x] OpenRouter / OpenAI-compatible LLM gateway support.
- [x] Tenant-scoped retrieval (rag_search now bound to the request tenant).
- [x] Streamlit operator console (two-pane: knowledge base + cited Q&A).
- [x] Phoenix tracing via OpenInference (named span tree for the agent graph).
