# CLAUDE.md

You are working on Agentic RAG: an enterprise-grade agentic RAG runtime with MCP tools, multi-agent orchestration, HITL approval, and RAG evals.

This is not a generic chatbot project. Follow the existing architecture, read relevant docs before design work, and keep changes small and production-minded.

## Working Principles

- Do not jump straight into implementation.
- First inspect relevant files, existing patterns, and related tests.
- For non-trivial changes, briefly explain:
  - what you found,
  - the likely root cause or design gap,
  - the proposed fix,
  - which files you plan to touch.
- If the user says “implement”, “fix it”, “go ahead”, or clearly asks for a change, proceed after a short plan.
- Do not ask the user to run commands if you can safely run them yourself.
- Prefer small, scoped changes over broad rewrites.
- Follow existing project patterns unless there is a clear reason not to.
- Do not add dependencies or change public contracts without asking first.

## Repository Inspection

Use the repo as the source of truth.

Prefer:

```bash
rg --files
rg "pattern" path/
````

Avoid:

* broad shell commands,
* unnecessary command chaining,
* `cd ... && ...`,
* pipes unless truly needed,
* reading many files at once,
* asking for approval because of avoidable shell syntax.

Run commands from the repository root/workdir instead of prefixing each command with `cd`.

When a shell command would trigger approval due to syntax, rewrite it as a simpler atomic command.

## Architecture Rules

Keep the documented flat `src/` architecture.

Layer responsibilities:

* `api/`: FastAPI routers and HTTP entrypoints only
* `schemas/`: Pydantic request/response DTOs
* `agents/`: LangGraph state, nodes, graph, tools, checkpoints
* `rag/`: chunking, embeddings, retrieval, reranking
* `mcp_server/`: MCP entrypoint and guarded tools
* `storage/`: Qdrant/Postgres adapters
* `core/`: config, logging, exceptions, shared infrastructure

Dependency direction:

```text
api / mcp_server -> agents -> rag -> storage -> core
```

Rules:

* Routers must stay thin.
* Routers must not call Qdrant, LLMs, databases, or MCP tools directly.
* Put runtime/business logic in the correct layer.
* Do not replace the documented architecture without asking.

## Read Relevant Docs First

Before design or implementation work, read only the docs relevant to the task.

Common references:

* `docs/architecture.md`
* `docs/local_notes/VIZYON 1.md`
* `docs/mcp/sql_tool_design.md`
* `docs/agents/langgraph_guide.md`
* `docs/agents/langchain_features.md`
* `docs/observability/tracing.md`

Use `docs/` as the cumulative knowledge layer.

If a design decision is worked out in depth, update the relevant docs with the decision and reasoning.

## Area-Specific Guidance

Before changing common areas:

* Exceptions: inspect existing `core` exceptions and API exception handling.
* Logging: inspect logging setup and nearby logger usage. Do not use `print`.
* Config: inspect settings first. Update `.env.example` and docs if config changes.
* Endpoints: inspect routers, schemas, dependencies, and endpoint tests.
* RAG: inspect chunking, embedding, retrieval, reranking, and Qdrant patterns.
* MCP tools: inspect safety guards and tests before adding or changing tools.
* Agents: inspect existing LangGraph docs and graph/node patterns first.
* Evals: keep datasets, rubrics, and large prompts outside hardcoded Python strings.

## Safety Rules

MCP SQL tools must remain read-only by default.

Keep both SQL safety layers:

1. read-only database role
2. explicit read-only SQL guard

Never:

* allow destructive SQL without HITL approval,
* weaken SQL guards, tool safety, approval flows, or tests,
* use private company data as sample RAG/eval data,
* commit secrets or private data,
* remove or loosen tests to hide failures,
* edit `uv.lock` manually,
* hardcode large prompts/rubrics in Python.

Risky or destructive actions require HITL approval.

## Code Quality

* Use type hints on public code.
* Prefer async patterns for API/service code.
* Use framework-idiomatic FastAPI, MCP, LangGraph, and Pydantic patterns.
* Keep comments, docstrings, prompts, and rubrics in English.
* Mock LLM, Qdrant, MCP, Phoenix/LangSmith, databases, and network calls in unit tests.
* Do not add dependencies unless the user explicitly approves.
* Do not manually edit generated lockfiles.

## Checks

Run relevant checks after changes when possible.

Default test command:

```bash
uv run ruff format
uv run pytest
```

For app startup checks when needed:

```bash
uv run uvicorn src.app:app --host 0.0.0.0 --port 8089 --reload
```

If a check cannot be run, explain why and mention what should be run manually.

## Approval Boundaries

Ask before:

* adding dependencies,
* changing public API contracts,
* adding a new database, worker, queue, top-level runtime, or frontend framework,
* performing large dependency/version migrations,
* replacing the documented architecture,
* making broad rewrites outside the requested scope.

Do not ask before:

* reading files,
* searching the repository,
* running safe local checks,
* making small scoped changes that the user clearly requested.
