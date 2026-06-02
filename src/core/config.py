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
    langchain_api_key: Optional[SecretStr] = None
    langchain_tracing_v2: bool = True
    langchain_project: str = "AGENTIC-RAG"

    # OpenTelemetry Settings
    otel_enabled: bool = True
    otel_service_name: str = "agentic-rag"
    otel_exporter_otlp_endpoint: str = "http://localhost:6006"

    # Core API Server Settings
    core_api_port: int = 8089

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
