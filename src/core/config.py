import pathlib
from functools import lru_cache
from typing import Optional

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # General Application Settings
    PROJECT_NAME: str = "Agentic RAG API"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = "dev"
    LOG_LEVEL: str = "INFO"

    # LLM and Tracing Settings
    OPENAI_API_KEY: Optional[SecretStr] = None
    LANGCHAIN_API_KEY: Optional[SecretStr] = None
    LANGCHAIN_TRACING_V2: bool = True
    LANGCHAIN_PROJECT: str = "AGENTIC-RAG"

    # Core API Server Settings
    CORE_API_PORT: int = 8089

    # Vector Database (Qdrant) Settings
    QDRANT_HOST: str = "qdrant-db"
    QDRANT_PORT: int = 6333
    QDRANT_GRPC_PORT: int = 6334
    QDRANT_API_KEY: Optional[SecretStr] = None
    QDRANT_COLLECTION_NAME: str = "company_documents"
    QDRANT_VECTOR_SIZE: int = 384
    # Upsert points in batches so a large document (e.g. a 20k-row CSV that
    # produces thousands of chunks) never exceeds Qdrant's request size limit.
    QDRANT_UPSERT_BATCH_SIZE: int = 128

    # Advanced RAG Settings
    RAG_DENSE_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    RAG_SPARSE_MODEL: str = "Qdrant/bm25"
    RAG_CHUNK_MAX_TOKENS: int = 350
    RAG_CHUNK_OVERLAP_TOKENS: int = 50
    RAG_RETRIEVAL_CANDIDATES: int = 20
    RAG_TOP_K: int = 5

    # Reranking: a cross-encoder re-scores the candidates before top_k is cut.
    RAG_RERANK_ENABLED: bool = True
    RAG_RERANK_MODEL: str = "BAAI/bge-reranker-base"

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
