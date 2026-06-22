# Agentic RAG: Enterprise-Grade Agentic Knowledge Runtime

[![Python](https://img.shields.io/badge/Python-3.13+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-FF6B35?style=flat-square)](https://langchain-ai.github.io/langgraph/)
[![Qdrant](https://img.shields.io/badge/Qdrant-Hybrid_Search-DC143C?style=flat-square)](https://qdrant.tech)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-Traced-7B2FBE?style=flat-square&logo=opentelemetry)](https://opentelemetry.io)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue?style=flat-square)](https://opensource.org/licenses/Apache-2.0)

> An autonomous knowledge system that connects enterprise documents, SQL databases, and logs through a secure MCP process boundary. Every LLM response is validated against source material in a self-reflection loop, and the system requires human approval before any destructive database operation.


## Vision & Mission

Most RAG systems are wrappers. They fail in three ways that matter in production:

- **No verification.** If the model confabulates, the answer ships.
- **No security boundary.** Credentials live in agent code; every tool call is an injection vector.
- **No measurement.** "It seems to work" is not an engineering standard.

This project is designed against each failure mode: a cyclical Auditor loop that mathematically checks every response, an MCP process boundary that keeps credentials out of agent code, and a CI/CD faithfulness gate that blocks regressions before they reach production.

---

## Architecture & System Design

### System Topology

```mermaid
flowchart LR
    User([User])
    UI["Streamlit UI\nSSE · HITL · Citations\n(planned)"]:::planned
    API["FastAPI\n/agent · /documents · /search"]

    subgraph lg [LangGraph — stateful, cyclical]
        R[Researcher]
        An[Analyst]
        Au[Auditor]
    end

    subgraph mcp [MCP Server — stdio subprocess]
        TS[rag_search]
        LL[list_log_files]
        RL[read_logs]
        LT[list_tables]
        DT[describe_table]
        SQ["sql_query (guarded)"]
    end

    Qdrant[(Qdrant Hybrid Vector)]
    PG[(PostgreSQL)]
    Phoenix[Arize Phoenix]
    Redis[(Redis — planned)]:::planned

    User -. planned .-> UI
    UI -. planned .-> API
    User --> API --> R
    R --> An --> Au
    Au -->|not faithful| R
    Au -->|faithful / budget spent| END([END])

    R --> TS & LL & RL & LT & DT & SQ

    TS --> Qdrant
    SQ --> PG

    API -.->|OTEL| Phoenix

    Au -. planned .-> Redis
    Redis -. planned .-> R

    classDef planned stroke-dasharray: 5 5
```

### Architecture Decisions

| # | Decision | Why |
|---|---|---|
| 1 | **MCP as internal process boundary** | Credentials cannot live in agent code. The process boundary enforces Principle of Least Privilege — a compromised agent cannot reach raw DB handles or `os.environ` on the data layer. A service layer in the same process doesn't provide this guarantee. |
| 2 | **Cyclical LangGraph over linear chains** | Recovery requires a graph. A linear chain ships a hallucinated answer. The `Auditor → Researcher` loop re-retrieves with an enriched query on every faithfulness failure; linear chains cannot express this control flow. |
| 3 | **HITL via `interrupt()` + Redis checkpoint** | Destructive SQL (`DELETE`, `UPDATE`) suspends the graph, surfaces a diff to the user, and resumes cleanly from the last checkpoint on approval. The agent never discards intermediate state regardless of the human decision. |
| 4 | **Hybrid search + cross-encoder reranking** | Dense-only misses exact terms; BM25-only misses paraphrase. RRF fuses both into a Top-20 candidate set; a BGE cross-encoder then scores each query-chunk pair directly, not just embedding similarity, for Top-5. |
| 5 | **Docling with lightweight fallback** | ML-powered layout analysis (table detection, heading structure) when docling is installed; pypdf/python-docx fallback otherwise. The parser is resolved once at process startup — no runtime branching overhead. |
| 6 | **CI/CD faithfulness gate** | Quality regressions should fail the build, not reach production. A Ragas faithfulness score < 0.85 on any PR blocks merge to `main` — the same guarantee a failing unit test provides for code correctness. |

---

## Tech Stack & Services

### Services (Docker Compose)

| Service | Image | Role |
|---|---|---|
| `api` | `infra/api/Dockerfile` | FastAPI — routers, middleware, SSE streaming |
| `frontend` | `infra/frontend/Dockerfile` | Streamlit — trace viewer, HITL approval, citations |
| `qdrant` | `qdrant/qdrant` | Hybrid vector DB (dense + sparse) |
| `postgres` | `postgres:16` | Structured operational data |
| `redis` | `redis:7-alpine` | LangGraph state checkpointer |
| `phoenix` | `infra/phoenix/docker-compose.yml` | OTEL trace collector + dashboard |

> **MCP Server** runs as a stdio subprocess (launched by the agent process), not a separate Docker service.

### Source Layout

```text
src/
├── api/          routers/       — thin HTTP entrypoint, no business logic
├── rag/          chunking · embeddings · ingest · retriever · reranker · parsers
├── agents/       graph · state · nodes (researcher/analyst/auditor) · prompts/
├── mcp_server/   server · tools/ (rag_search · read_logs · sql · list_tables · describe_table)
├── evals/        datasets/ · ragas_runner.py
├── adapters/     vector_store/qdrant.py · sql/postgres.py
├── observability/ logging · tracing
├── schemas/      Pydantic DTOs
└── core/         config · exceptions · context (request-ID)
```

Dependency direction (enforced): `api / mcp → agents → rag → adapters → core`

### Technology Choices

| Layer | Technology | Rationale |
|---|---|---|
| API | FastAPI | Async-native, SSE support, OTEL hooks |
| Orchestration | LangGraph | Cyclical graphs, `interrupt()` for HITL, Redis checkpointer built-in |
| Vector DB | Qdrant | Native hybrid search (dense + sparse); payload filtering for multi-tenancy |
| Embeddings | FastEmbed | Fully local, no external API dependency |
| Reranking | BGE-Reranker | Cross-encoder pair scoring; runs entirely offline |
| Document Parsing | Docling + pypdf/python-docx | ML layout analysis (CPU) with lightweight fallback |
| MCP | `mcp[cli]` / FastMCP | Process-boundary isolation; stdio transport |
| State | Redis | First-class LangGraph checkpointer backend |
| Tracing | Arize Phoenix + OTEL | LLM-native spans; OpenInference semantic conventions |
| Logging | Structured JSON + queue handler | Non-blocking async I/O; request-ID correlation across every log line |
| Evaluation | Ragas / DeepEval | Faithfulness scoring; direct CI integration |
| Packaging | `uv` | Deterministic lockfile, fast resolution |

---

## Engineering Goals

**"How does the agent access data without holding credentials?"**
The MCP process owns all connection handles. Agent-layer compromise does not imply data-layer compromise.

**"How do you know the model isn't hallucinating?"**
The Auditor runs an entailment check on every response using structured output (`with_structured_output`). Failure triggers a retry with the critique embedded in the next query — not a user-facing answer.

**"What if the model tries to delete production data?"**
Two independent layers stop it: the `ensure_read_only()` guard in the MCP tool layer, and the `sentinel_ro` least-privilege Postgres role the adapter connects with. The graph also suspends for explicit human approval before any destructive operation.

**"How do you prevent a prompt change from silently degrading quality?"**
Ragas faithfulness < 0.85 on any PR fails the GitHub Actions check and blocks the merge.

**"What if the agent crashes mid-conversation?"**
LangGraph checkpoints to Redis after each node. The next request resumes from the last committed state.

**"How do you trace a specific request across logs and spans?"**
A UUID is generated at the API gateway, injected into `request_id_var` (a Python `contextvars.ContextVar`), and propagated automatically into every structured log line and OTEL span attribute for the lifetime of that request.

---

## Current Status

| Step | Scope | Status |
|---|---|---|
| **1** | Advanced RAG — heading-aware chunking, hybrid search (dense + BM25 + RRF), BGE cross-encoder reranking | ✅ Done |
| **2** | MCP Server — `rag_search`, `read_logs`, guarded `sql_query`, `list_tables`, `describe_table` | ✅ Done |
| **3** | Multi-Agent — LangGraph Researcher · Analyst · Auditor with self-reflection loop + revision budget | ✅ Done |
| **4** | UI/UX — SSE trace stream, source citations, HITL approval | ⬜ Planned |
| **5** | CI/CD Evals — Ragas faithfulness gate on GitHub Actions | ⬜ Planned |

**Infrastructure & cross-cutting concerns complete:**

- Multi-stage Docker build with CPU-only PyTorch wheels for lean images
- Modular docker-compose with isolated Phoenix observability stack
- OpenTelemetry → Arize Phoenix tracing with request-ID on every span
- Structured JSON logging with non-blocking queue handler, stdout/stderr split, and per-request correlation
- Docling document parsing (PDF layout analysis, table detection) with automatic lightweight fallback
- Qdrant collection with dense + sparse (BM25) vector configuration
- Read-only SQL enforcement: guard layer + `sentinel_ro` DB role

---

## Getting Started

**Prerequisites:** Docker Desktop, `uv`

```bash
# 1. Clone and configure environment
git clone https://github.com/Melce-AI/agentic-rag.git
cd agentic-rag
cp .env.example .env          # fill in OPENAI_API_KEY and review other defaults
```

```bash
# 2. Create the external Qdrant volume (first time only)
docker volume create qdrant_data
```

```bash
# 3. Start all services (API · Frontend · Qdrant · Postgres · Redis · Phoenix)
docker compose up --build
```

| Service | URL |
|---|---|
| API + OpenAPI docs | http://localhost:8089/docs |
| Streamlit UI | http://localhost:8501 |
| Arize Phoenix (traces) | http://localhost:6006 |
| Qdrant dashboard | http://localhost:6333/dashboard |

```bash
# Run linter + formatter + tests
uv sync && uv run ruff check . && uv run ruff format && uv run pytest

# MCP Inspector — inspect tools interactively (development)
uv run mcp dev src/mcp_server/server.py
```

---

## License

Apache 2.0
