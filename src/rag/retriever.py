from dataclasses import replace
from typing import Any

from opentelemetry import trace
from starlette.concurrency import run_in_threadpool

from src.core.config import get_settings
from src.core.exceptions import AppException, RagRetrievalError, RagValidationError
from src.rag.embeddings import EmbeddingProvider, FastEmbedProvider
from src.rag.models import RetrievedChunk
from src.rag.reranker import FastEmbedReranker, Reranker
from src.adapters.vector_store.qdrant import QdrantManager, qdrant_manager
from src.observability.tracing import traced


class HybridRetriever:
    def __init__(
        self,
        vector_store: QdrantManager = qdrant_manager,
        embedding_provider: EmbeddingProvider | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self.settings = get_settings()
        self.vector_store = vector_store
        self.embedding_provider = embedding_provider or FastEmbedProvider()
        # Explicit reranker wins; otherwise use the configured one unless disabled.
        if reranker is not None:
            self.reranker: Reranker | None = reranker
        elif self.settings.rag_rerank_enabled:
            self.reranker = FastEmbedReranker()
        else:
            self.reranker = None

    @traced("rag.retrieve", span_kind="RETRIEVER")
    async def search(
        self,
        *,
        query: str,
        tenant_id: str,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        if not query.strip():
            raise RagValidationError("query must not be empty")

        limit = top_k or self.settings.rag_top_k
        span = trace.get_current_span()
        span.set_attribute("input.value", query)
        span.set_attribute("rag.tenant_id", tenant_id)
        span.set_attribute("rag.query", query[:200])
        span.set_attribute("rag.top_k", limit)
        span.set_attribute("rag.rerank_enabled", self.reranker is not None)

        try:
            embedding = await run_in_threadpool(self.embedding_provider.embed_query, query)
            raw_results = await self.vector_store.query_hybrid(
                dense_vector=embedding.dense,
                sparse_indices=embedding.sparse.indices,
                sparse_values=embedding.sparse.values,
                tenant_id=tenant_id,
                limit=self.settings.rag_retrieval_candidates,
            )
            candidates = [self._map_result(result) for result in raw_results]
            ranked = await run_in_threadpool(self._rerank, query, candidates)
            results = ranked[:limit]

            for i, r in enumerate(results):
                span.set_attribute(f"retrieval.documents.{i}.document.id", r.chunk_id)
                span.set_attribute(f"retrieval.documents.{i}.document.content", r.text[:500])
                span.set_attribute(f"retrieval.documents.{i}.document.score", r.score)
            span.set_attribute("rag.candidates", len(raw_results))
            span.set_attribute("rag.result_count", len(results))
            return results
        except AppException:
            raise
        except Exception as exc:
            raise RagRetrievalError(
                details={"tenant_id": tenant_id, "query": query, "error": str(exc)}
            ) from exc

    @traced("rag.rerank", span_kind="RERANKER")
    def _rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Re-score candidates with the cross-encoder, then order best-first.

        Without a reranker we fall back to the hybrid retrieval score. With one,
        each chunk's `score` becomes the rerank score and the original retrieval
        score is preserved under `metadata["retrieval_score"]` for observability.
        """
        span = trace.get_current_span()
        span.set_attribute("reranker.query", query[:200])
        span.set_attribute("reranker.top_k", len(candidates))
        if not candidates or self.reranker is None:
            return sorted(
                candidates,
                key=lambda item: (-item.score, item.document_id, item.chunk_id),
            )

        scores = self.reranker.rerank(query, [item.text for item in candidates])
        rescored = [
            replace(
                item,
                score=score,
                metadata={**item.metadata, "retrieval_score": item.score},
            )
            for item, score in zip(candidates, scores)
        ]
        return sorted(
            rescored,
            key=lambda item: (-item.score, item.document_id, item.chunk_id),
        )

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
