import datetime as dt
import hashlib
import uuid

from src.core.config import get_settings
from src.core.exceptions import (
    AppException,
    DocumentDeleteError,
    DocumentListError,
    RagConfigurationError,
    RagIngestError,
    RagValidationError,
)
from src.rag.chunking import HeadingAwareChunker, TableChunker
from src.rag.embeddings import EmbeddingProvider, FastEmbedProvider
from src.rag.models import Chunk, ContentKind, Document
from src.adapters.vector_store.qdrant import QdrantManager, qdrant_manager


class DocumentIngestService:
    def __init__(
        self,
        vector_store: QdrantManager = qdrant_manager,
        embedding_provider: EmbeddingProvider | None = None,
        chunker: HeadingAwareChunker | None = None,
    ) -> None:
        settings = get_settings()
        self.vector_store = vector_store
        self.embedding_provider = embedding_provider or FastEmbedProvider()
        try:
            self.chunker = chunker or HeadingAwareChunker(
                max_tokens=settings.RAG_CHUNK_MAX_TOKENS,
                overlap_tokens=settings.RAG_CHUNK_OVERLAP_TOKENS,
            )
            self.table_chunker = TableChunker(max_tokens=settings.RAG_CHUNK_MAX_TOKENS)
        except ValueError as exc:
            raise RagConfigurationError(
                "Invalid RAG chunking configuration",
                details={
                    "max_tokens": settings.RAG_CHUNK_MAX_TOKENS,
                    "overlap_tokens": settings.RAG_CHUNK_OVERLAP_TOKENS,
                    "error": str(exc),
                },
            ) from exc

    def _chunker_for(self, content_kind: ContentKind):
        """Picks the chunking strategy required by the loaded content."""
        if content_kind is ContentKind.TABULAR:
            return self.table_chunker
        return self.chunker

    async def ingest_document(
        self,
        *,
        source_name: str,
        content: str,
        tenant_id: str,
        content_kind: ContentKind = ContentKind.TEXT,
    ) -> dict:
        if not source_name.strip():
            raise RagValidationError("source_name must not be empty")
        if not content.strip():
            raise RagValidationError("content must not be empty")

        try:
            chunks = self._chunker_for(content_kind).split(content)
            if not chunks:
                raise RagValidationError("document did not produce any chunks")

            content_hash = self._sha256(content)
            document_id = self._stable_uuid(f"{tenant_id}:{source_name}:{content_hash}")
            document = Document(
                document_id=document_id,
                tenant_id=tenant_id,
                source_name=source_name,
                content_hash=content_hash,
            )
            embeddings = self.embedding_provider.embed_documents([chunk.text for chunk in chunks])
            created_at = dt.datetime.now(dt.timezone.utc).isoformat()

            records = []
            for chunk, embedding in zip(chunks, embeddings):
                chunk_id = self._stable_uuid(f"{document_id}:{content_hash}:{chunk.chunk_index}")
                stored_chunk = Chunk(
                    chunk_id=chunk_id,
                    document_id=document.document_id,
                    tenant_id=document.tenant_id,
                    text=chunk.text,
                    heading_path=chunk.heading_path,
                    chunk_index=chunk.chunk_index,
                    chunk_token_count=chunk.chunk_token_count,
                    section_title=chunk.section_title,
                    section_index=chunk.section_index,
                    source_name=document.source_name,
                    created_at=created_at,
                    content_hash=document.content_hash,
                )
                records.append(
                    {
                        "id": stored_chunk.chunk_id,
                        "dense_vector": embedding.dense,
                        "sparse_indices": embedding.sparse.indices,
                        "sparse_values": embedding.sparse.values,
                        "payload": {
                            "tenant_id": stored_chunk.tenant_id,
                            "document_id": stored_chunk.document_id,
                            "chunk_id": stored_chunk.chunk_id,
                            "source_name": stored_chunk.source_name,
                            "heading_path": stored_chunk.heading_path,
                            "chunk_index": stored_chunk.chunk_index,
                            "chunk_token_count": stored_chunk.chunk_token_count,
                            "section_title": stored_chunk.section_title,
                            "section_index": stored_chunk.section_index,
                            "text": stored_chunk.text,
                            "created_at": stored_chunk.created_at,
                            "content_hash": stored_chunk.content_hash,
                        },
                    }
                )

            await self.vector_store.upsert_chunks(records)
            return {
                "document_id": document.document_id,
                "chunk_count": len(records),
                "status": "ingested",
            }
        except AppException:
            raise
        except Exception as exc:
            raise RagIngestError(
                details={"source_name": source_name, "tenant_id": tenant_id, "error": str(exc)}
            ) from exc

    async def list_documents(self, *, tenant_id: str, limit: int = 100) -> dict:
        if not tenant_id.strip():
            raise RagValidationError("tenant_id must not be empty")
        if limit < 1:
            raise RagValidationError("limit must be greater than 0")

        try:
            documents = await self.vector_store.list_documents_by_tenant(tenant_id=tenant_id)
            limited_documents = documents[:limit]
            return {
                "documents": limited_documents,
                "count": len(limited_documents),
            }
        except AppException:
            raise
        except Exception as exc:
            raise DocumentListError(details={"tenant_id": tenant_id, "error": str(exc)}) from exc

    async def delete_document(self, *, document_id: str, tenant_id: str) -> dict:
        if not document_id.strip():
            raise RagValidationError("document_id must not be empty")
        if not tenant_id.strip():
            raise RagValidationError("tenant_id must not be empty")

        try:
            await self.vector_store.delete_by_document_id(
                document_id=document_id,
                tenant_id=tenant_id,
            )
            return {
                "document_id": document_id,
                "tenant_id": tenant_id,
                "status": "deleted",
            }
        except AppException:
            raise
        except Exception as exc:
            raise DocumentDeleteError(
                details={"document_id": document_id, "tenant_id": tenant_id, "error": str(exc)}
            ) from exc

    @staticmethod
    def _sha256(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _stable_uuid(value: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, value))
