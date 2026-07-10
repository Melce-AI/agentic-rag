import pathlib
from functools import lru_cache
from typing import Optional

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # General Application Settings
    project_name: str = "Agentic RAG API"
    version: str = "1.0.0"
    environment: str = "dev"
    log_level: str = "INFO"

    # LLM and Tracing Settings
    openai_api_key: Optional[SecretStr] = None
    anthropic_api_key: Optional[SecretStr] = None
    langchain_api_key: Optional[SecretStr] = None
    langchain_tracing_v2: bool = True
    langchain_project: str = "AGENTIC-RAG"

    # OpenTelemetry Settings
    otel_enabled: bool = True
    otel_service_name: str = "agentic-rag"
    otel_exporter_otlp_endpoint: str = "http://localhost:6006"

    # Core API Server Settings
    core_api_port: int = 8089

    # LLM that powers the SQL agent loop.
    # provider: "huggingface" (free serverless Inference API, just needs a token)
    #           or "ollama" (fully local, needs Ollama installed + a model pulled).
    llm_provider: str = "huggingface"

    # Hugging Face Inference API
    # Must be a model the HF router serves WITH tool-calling (many small models
    # reject tools/tool_choice). Qwen2.5-Instruct and Llama-3.3-70B work.
    hf_model: str = "Qwen/Qwen2.5-72B-Instruct"
    hf_token: Optional[SecretStr] = None  # read from HF_TOKEN env

    # Local Ollama
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    # Safety bound on the agent's tool-calling loop (avoid runaway calls).
    agent_max_steps: int = 6

    # --- LangGraph agent chat model (Researcher / Analyst / Auditor) ---
    # Provider-agnostic: `init_chat_model` picks the backend from this single
    # "provider:model" string, so swapping providers is a one-env-var change
    # (AGENT_MODEL), never a code change. API keys are read from the standard
    # env vars (ANTHROPIC_API_KEY / OPENAI_API_KEY) automatically.
    #   free/local : "ollama:llama3.1:8b"
    #   anthropic  : "anthropic:claude-opus-4-8"   (needs ANTHROPIC_API_KEY)
    #   openai     : "openai:gpt-4o"               (needs OPENAI_API_KEY)
    #   openrouter : "openai:openai/gpt-4o-mini"   (set AGENT_BASE_URL + OPENAI_API_KEY)
    agent_model: str = "ollama:llama3.1:8b"
    agent_temperature: float = 0.0

    # Optional OpenAI-compatible gateway base URL (e.g. OpenRouter:
    # "https://openrouter.ai/api/v1"). When set, get_chat_model() forwards it
    # plus OPENAI_API_KEY to the openai provider, so any OpenAI-wire-compatible
    # backend works without a code change.
    agent_base_url: Optional[str] = None

    # Loop brakes for the multi-agent graph (two layers, both needed):
    #   business brake — max Auditor -> Researcher revision loops before the
    #   graph gives up and returns the current draft (route_after_audit).
    agent_max_revisions: int = 2
    #   infrastructure brake — LangGraph's hard cap on total node steps per run,
    #   passed at invoke time as config={"recursion_limit": ...}.
    agent_recursion_limit: int = 25

    # Redis — LangGraph checkpoint store
    redis_url: str = "redis://redis:6379"

    # Vector Database (Qdrant) Settings
    qdrant_host: str = "qdrant-db"
    qdrant_port: int = 6333
    qdrant_grpc_port: int = 6334
    qdrant_api_key: Optional[SecretStr] = None
    qdrant_collection_name: str = "company_documents"
    qdrant_vector_size: int = 384
    # Upsert points in batches so a large document (e.g. a 20k-row CSV that
    # produces thousands of chunks) never exceeds Qdrant's request size limit.
    qdrant_upsert_batch_size: int = 128

    # Relational Database (Postgres) Settings — Sentinel MCP sql_query tool.
    # The tool connects with the read-only role, never the owner.
    postgres_host: str = "postgres-db"
    postgres_port: int = 5432
    postgres_db: str = "sentinel_db"
    postgres_ro_user: str = "sentinel_ro"
    postgres_ro_password: SecretStr = SecretStr("sentinel_ro")
    # Hard server-side cap on rows any single sql_query call may return.
    postgres_query_row_limit: int = 100

    # Read-WRITE role — the HITL-gated `sql_execute` tool connects with this.
    # A SECOND least-privilege role, distinct from sentinel_ro: it may run
    # UPDATE/DELETE, but only on `postgres_writable_tables`, and every write is
    # gated by human approval in the graph (executor node -> interrupt()).
    postgres_rw_user: str = "sentinel_rw"
    postgres_rw_password: SecretStr = SecretStr("sentinel_rw")
    # The only tables the write tier may mutate — single source of truth. The
    # write guard (ensure_write_safe) enforces it and the executor prompt lists
    # it. Keep in sync with the GRANTs in
    # infra/postgres/initdb/04_create_readwrite_role.sh.
    postgres_writable_tables: list[str] = ["orders", "customers", "order_items"]

    # Advanced RAG Settings
    rag_dense_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    rag_sparse_model: str = "Qdrant/bm25"
    rag_chunk_max_tokens: int = 350
    rag_chunk_overlap_tokens: int = 50
    rag_retrieval_candidates: int = 20
    rag_top_k: int = 5

    # Reranking: a cross-encoder re-scores the candidates before top_k is cut.
    rag_rerank_enabled: bool = True
    rag_rerank_model: str = "BAAI/bge-reranker-base"
    # JWT / Auth (RS256)
    jwt_private_key_path: str = "keys/jwt_private.pem"
    jwt_public_key_path: str = "keys/jwt_public.pem"
    jwt_issuer: str = "agentic-rag-auth"
    jwt_access_token_expire_minutes: int = 15

    auth_user_email: str = "ece@qkare.com"
    auth_user_password_hash: str = "8349bd0215f824bfba7c84e7c329743c:4e7966fc2c571782a56b1e582a15aff11eb4a3bb049a1489e6b58a3ddeb7c2c1"
    auth_user_roles: list[str] = ["admin"]

    # Environment Variables (.env) Reading Rules
    model_config = SettingsConfigDict(
        env_file=pathlib.Path(".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Reads settings only when called for the first time, then retrieves them
    quickly from memory (cache). Critical for performance.
    """
    return Settings()
