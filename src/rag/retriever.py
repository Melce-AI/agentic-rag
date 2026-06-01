from typing import Any

from src.core.config import get_settings
from src.core.exceptions import AppException, RagRetrievalError, RagValidationError
from src.rag.embeddings import EmbeddingProvider, FastEmbedProvider
from src.rag.models import RetrievedChunk
from src.storage.qdrant_client import QdrantManager, qdrant_manager


class HybridRetriever:
    def __init__(
        self,
        vector_store: QdrantManager = qdrant_manager,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.settings = get_settings()
        self.vector_store = vector_store
        self.embedding_provider = embedding_provider or FastEmbedProvider()

    async def search(
        self,
        *,
        query: str,
        tenant_id: str,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        if not query.strip():
            raise RagValidationError("query must not be empty")

        try:
            limit = top_k or self.settings.RAG_TOP_K
            embedding = self.embedding_provider.embed_query(query)
            raw_results = await self.vector_store.query_hybrid(
                dense_vector=embedding.dense,
                sparse_indices=embedding.sparse.indices,
                sparse_values=embedding.sparse.values,
                tenant_id=tenant_id,
                limit=self.settings.RAG_RETRIEVAL_CANDIDATES,
            )
            candidates = [self._map_result(result) for result in raw_results]
            return sorted(
                candidates,
                key=lambda item: (-item.score, item.document_id, item.chunk_id),
            )[:limit]
        except AppException:
            raise
        except Exception as exc:
            raise RagRetrievalError(
                details={"tenant_id": tenant_id, "query": query, "error": str(exc)}
            ) from exc

    @staticmethod
    def _map_result(result: Any) -> RetrievedChunk:
        if isinstance(result, dict):
            payload = result.get("payload", {})
            score = result.get("score", 0.0)
            result_id = result.get("id", "")
        else:
            payload = getattr(result, "payload", None) or {}
            score = getattr(result, "score", 0.0)
            result_id = getattr(result, "id", "")

        chunk_id = str(payload.get("chunk_id") or result_id)
        document_id = str(payload.get("document_id", ""))
        source_name = str(payload.get("source_name", ""))
        heading_path = payload.get("heading_path") or []
        text = str(payload.get("text", ""))

        metadata = {
            key: value
            for key, value in payload.items()
            if key not in {"chunk_id", "document_id", "source_name", "heading_path", "text"}
        }

        return RetrievedChunk(
            chunk_id=chunk_id,
            document_id=document_id,
            source_name=source_name,
            heading_path=list(heading_path),
            text=text,
            score=float(score),
            metadata=metadata,
        )
