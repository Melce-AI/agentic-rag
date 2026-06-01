import logging
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import (
    Distance, VectorParams, SparseVectorParams, PointStruct, 
    SparseVector, PayloadSchemaType, Prefetch, FusionQuery, Fusion,
    Filter, FieldCondition, MatchValue
)
from src.core.config import get_settings
from src.core.exceptions import (
    VectorStoreInitializationError, 
    VectorStoreOperationError
)

logger = logging.getLogger(__name__)
settings = get_settings()

class QdrantManager:
    """
    Production-grade Qdrant manager (v2).
    Handles lifecycle, configuration validation, and indexing.
    """

    def __init__(self):
        self.client = AsyncQdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            api_key=settings.QDRANT_API_KEY,
            grpc_port=settings.QDRANT_GRPC_PORT,
            prefer_grpc=False
        )
        self.collection_name = settings.QDRANT_COLLECTION_NAME
        self.dense_vector_name = "dense-text"
        self.sparse_vector_name = "sparse-text"

    async def init_collection(self):
        """
        Bootstrap the collection: create if missing, or validate if exists.
        Then ensures payload indexes are up to date.
        """
        try:
            exists = await self.client.collection_exists(self.collection_name)
            
            if not exists:
                logger.info(f"Creating collection '{self.collection_name}' with Hybrid Search config...")
                await self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config={
                        self.dense_vector_name: VectorParams(
                            size=settings.QDRANT_VECTOR_SIZE,
                            distance=Distance.COSINE,
                        )
                    },
                    sparse_vectors_config={
                        self.sparse_vector_name: SparseVectorParams()
                    }
                )
                logger.info(f"Collection '{self.collection_name}' created.")
            else:
                logger.info(f"Validating existing collection '{self.collection_name}'...")
                info = await self.client.get_collection(self.collection_name)
                params = info.config.params
                
                # Validation Logic
                if not params.vectors or self.dense_vector_name not in params.vectors:
                    raise ValueError(f"Missing dense vector config for '{self.dense_vector_name}'")
                
                dense_cfg = params.vectors[self.dense_vector_name]
                if dense_cfg.size != settings.QDRANT_VECTOR_SIZE:
                    raise ValueError(f"Vector size mismatch: expected {settings.QDRANT_VECTOR_SIZE}, got {dense_cfg.size}")

                if not params.sparse_vectors or self.sparse_vector_name not in params.sparse_vectors:
                    raise ValueError(f"Missing sparse vector config for '{self.sparse_vector_name}'")
                
                logger.info(f"Collection '{self.collection_name}' validated.")

            # Always ensure payload indexes for performance
            await self._ensure_payload_indexes()
                
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant: {str(e)}")
            raise VectorStoreInitializationError(details={"error": str(e)})

    async def _ensure_payload_indexes(self):
        """
        Proactively creates indexes on frequently filtered fields.
        """
        indexed_fields = {
            "tenant_id": PayloadSchemaType.KEYWORD,
            "document_id": PayloadSchemaType.KEYWORD,
            "created_at": PayloadSchemaType.DATETIME,
        }
        
        for field, schema_type in indexed_fields.items():
            try:
                await self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=schema_type
                )
            except Exception as e:
                # Often occurs if index already exists, which is fine
                logger.debug(f"Payload index for '{field}' skip/fail: {str(e)}")

    async def upsert_document(self, doc_id: str, dense_vector: list[float], sparse_indices: list[int], sparse_values: list[float], payload: dict):
        """
        Standardized document insertion for Hybrid Search.
        """
        await self.upsert_chunks(
            [
                {
                    "id": doc_id,
                    "dense_vector": dense_vector,
                    "sparse_indices": sparse_indices,
                    "sparse_values": sparse_values,
                    "payload": payload,
                }
            ]
        )

    async def upsert_chunks(self, records: list[dict]):
        """
        Batch chunk insertion for hybrid dense+sparse search.
        """
        try:
            await self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=record["id"],
                        vector={
                            self.dense_vector_name: record["dense_vector"],
                            self.sparse_vector_name: SparseVector(
                                indices=record["sparse_indices"],
                                values=record["sparse_values"]
                            )
                        },
                        payload=record["payload"]
                    )
                    for record in records
                ]
            )
        except Exception as e:
            raise VectorStoreOperationError(operation="upsert", details={"error": str(e)})

    async def query_hybrid(
        self,
        *,
        dense_vector: list[float],
        sparse_indices: list[int],
        sparse_values: list[float],
        tenant_id: str,
        limit: int = 20,
    ):
        """
        Runs Qdrant hybrid retrieval with RRF over dense and sparse named vectors.
        """
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="tenant_id",
                    match=MatchValue(value=tenant_id),
                )
            ]
        )

        try:
            response = await self.client.query_points(
                collection_name=self.collection_name,
                prefetch=[
                    Prefetch(
                        query=dense_vector,
                        using=self.dense_vector_name,
                        limit=limit,
                    ),
                    Prefetch(
                        query=SparseVector(indices=sparse_indices, values=sparse_values),
                        using=self.sparse_vector_name,
                        limit=limit,
                    ),
                ],
                query=FusionQuery(fusion=Fusion.RRF),
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            return response.points
        except Exception as e:
            raise VectorStoreOperationError(operation="hybrid_search", details={"error": str(e)})

    async def hybrid_search(
        self,
        *,
        dense_vector: list[float],
        sparse_indices: list[int],
        sparse_values: list[float],
        tenant_id: str,
        limit: int = 20,
    ):
        return await self.query_hybrid(
            dense_vector=dense_vector,
            sparse_indices=sparse_indices,
            sparse_values=sparse_values,
            tenant_id=tenant_id,
            limit=limit,
        )

    async def delete_by_document_id(self, *, document_id: str, tenant_id: str):
        """
        Deletes all chunks for a document inside one tenant boundary.
        """
        try:
            await self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="tenant_id",
                            match=MatchValue(value=tenant_id),
                        ),
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=document_id),
                        ),
                    ]
                ),
            )
        except Exception as e:
            raise VectorStoreOperationError(operation="delete_by_document_id", details={"error": str(e)})

    async def health_check(self) -> dict:
        """
        Checks connection and collection health.
        """
        try:
            # Check basic connection
            # We use a simple lightweight check
            collections = await self.client.get_collections()
            
            # Check target collection
            exists = await self.client.collection_exists(self.collection_name)
            
            return {
                "status": "healthy" if exists else "degraded",
                "connection": "ok",
                "collection_found": exists,
                "collection_name": self.collection_name,
                "total_collections": len(collections.collections)
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    async def close(self):
        """Closes the client connection."""
        await self.client.close()

# Singleton instance for easy access across the app
qdrant_manager = QdrantManager()
