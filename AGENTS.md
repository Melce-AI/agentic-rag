# AGENTS.md

You are working on **Agentic RAG**: an enterprise-grade agentic RAG runtime with
MCP tools, multi-agent orchestration, human-in-the-loop approval, and RAG evals.

Target vision: **Vision 1: Sentinel-MCP** in `docs/local_notes/VIZYON 1.md`.
Target architecture: `docs/architecture.md`.

You are not a generic chat bot; you know this project's vision, architecture, and
decisions. Read the relevant `docs/` pages before starting a task.

## Status (as of 2026-06)

Step 1 (Advanced RAG) is done; Step 2 (MCP) is underway.

- Done (Step 1): FastAPI skeleton, lifespan, request-id middleware, OpenAPI
  tags; centralized exception handling; structured JSON logging; Qdrant manager
  with dense + sparse vectors and payload indexes; heading-aware + table
  chunking; FastEmbed dense/sparse embeddings; hybrid retrieval with RRF;
  cross-encoder reranking; document ingest/upload/list/delete; pydantic
  settings; multi-stage Docker and multi docker-compose; OpenTelemetry tracing
  to Phoenix.
- Done (Step 2, partial): Sentinel MCP server with read-only tools — log tools
  (`list_log_files`, `read_logs`) and SQL tools (`list_tables`,
  `describe_table`, `sql_query`) over a sample Postgres DB. Two-layer SQL safety:
  read-only `sentinel_ro` DB role + `ensure_read_only()` guard. See
  `docs/mcp/sql_tool_design.md`.
- Partial: Streamlit UI is a placeholder.
- Missing: agents (LangGraph), `/chat` streaming + HITL, evals.
- Not yet in deps: `langgraph`, eval libs (`ragas`/`deepeval`) — add to
  `pyproject.toml` when Step 3/5 begins.

## Scope

- Main code: `src/`
- API routers: `src/api/routers/`
- Core: `src/core/`
- Schemas: `src/schemas/`
- Storage adapters: `src/storage/`
- Frontend prototype: `streamlit/`
- Tests: `tests/`
- Infra: `infra/`, `docker-compose.yml`
- Docs: `docs/`

## Stack

- Python 3.13+
- FastAPI, Uvicorn
- Pydantic / pydantic-settings
- pytest
- uv
- Qdrant
- Streamlit
- MCP (`mcp[cli]`), PostgreSQL (`psycopg`), Phoenix/OpenTelemetry
- Planned: LangGraph, Redis, RAGAS/DeepEval, Next.js

## Commands

Run from repo root:

```bash
uv sync
uv run pytest
uv run uvicorn src.app:app --host 0.0.0.0 --port 8089 --reload
docker compose up
```

Service compose files:

```bash
docker compose -f infra/api/docker-compose.yml up --build
docker compose -f infra/frontend/docker-compose.yml up --build
docker compose -f infra/qdrant-db/docker-compose.yml up
```

## Project Shape

Current:

```text
src/
+-- app.py
+-- api/
+-- core/
+-- schemas/
+-- storage/
streamlit/
tests/
infra/
docs/
```

Target:

```text
src/
+-- api/          # HTTP entrypoint, thin routers
+-- rag/          # chunking, embeddings, ingest, retrieval, reranking
+-- agents/       # LangGraph state, graph, nodes, checkpoints
+-- mcp_server/   # MCP entrypoint and guarded tools
+-- evals/        # eval datasets and runners
+-- storage/      # Qdrant/Postgres adapters
+-- schemas/      # Pydantic DTOs
+-- core/         # config, logging, exceptions
```

Dependency direction:

```text
api/mcp -> agents -> rag -> storage -> core
```

## Roadmap

- Advanced RAG: heading-aware chunking, hybrid search, Qdrant, reranking.
- MCP: custom server, authorized tools, read-only SQL by default.
- Agents: LangGraph Researcher, Analyst, Auditor with self-reflection loop.
- UI: streaming trace, tool-call visibility, citations, HITL approval.
- Evals: faithfulness, context precision, answer/context relevancy.

## Rules

- Search/read before adding files, schemas, config keys, prompts, tools, agents, or endpoints.
- Prefer project-aware tools before terminal commands for file work.
- Keep routers thin; put logic in `rag/`, `agents/`, `storage/`, or `mcp_server/`.
- Use type hints on public code.
- Prefer async patterns for API/service code.
- Keep comments, docstrings, prompts, and rubrics in English.
- Keep large prompts/rubrics in config or data files, not hardcoded in Python.
- Mock LLM, Qdrant, MCP, Phoenix/LangSmith, and network calls in tests.
- Update `.env.example` and docs when adding required config.
- Preserve centralized logging, request IDs, and global exception handling.

## Boundaries

Ask first before:

- Adding dependencies.
- Changing public API contracts.
- Adding a new database, worker, queue, top-level runtime, or frontend framework.
- Large dependency/version migrations.
- Replacing the documented flat `src/` architecture.

Never:

- Commit secrets or private data.
- Edit `uv.lock` manually.
- Remove/loosen tests to hide failures.
- Use private company data as sample RAG/eval data.
- Hardcode large prompts in Python.
- Let destructive SQL run without human approval.
- Let routers call Qdrant, LLMs, databases, or MCP tools directly.

## Knowledge Layer (docs/)

Keep knowledge **cumulative** under `docs/` instead of rediscovering it each task.
When a topic is worked out in depth, write the decision (with its "why") into the
appropriate page so future sessions build on synthesized knowledge.

- `docs/architecture.md` — target architecture and decision rationale (canonical)
- `docs/local_notes/VIZYON 1.md` — product vision and 5-step roadmap
- `docs/agents/langgraph_guide.md` — LangGraph multi-agent layer: StateGraph,
  conditional edges, state/nodes/tools/checkpointer, plus the `schemas/` and
  `core/` additions Step 3 requires (teaching guide)
- `docs/agents/langchain_features.md` — LangChain feature guide: ecosystem,
  skills (Deep Agents `SKILL.md` + progressive disclosure via `SkillsMiddleware`),
  chat models, messages, tools, `create_agent`, middleware (deep dive: hooks,
  built-ins, HITL), structured output, streaming, observability — with industry
  standards and how each maps to this project (teaching guide)
- `docs/team_notes/` — FastAPI architecture, API design, dockerization, logging
- `docs/qdrant/` — Qdrant deep dive, hybrid search setup, metrics
- `docs/api/`, `docs/docker/` — standards and baseline analyses
- `docs/observability/tracing.md` — OTel concepts, OTLP, OpenInference span kinds, `@traced` decorator, attribute conventions

## Commits

Use conventional commits:

```text
feat(rag): add heading-aware chunker
feat(mcp): expose read-only sql tool
feat(agents): add auditor reflection loop
feat(api): stream chat trace events
test(evals): cover faithfulness threshold
docs(architecture): update sentinel mcp workflow
```
