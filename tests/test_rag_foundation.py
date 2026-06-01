import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.api.routers import documents as documents_router
from src.api.routers import search as search_router
from src.app import app
from src.core.exceptions import RagEmbeddingError
from src.rag.chunking import HeadingAwareChunker
from src.rag.embeddings import FastEmbedProvider
from src.rag.ingest import DocumentIngestService
from src.rag.models import EmbeddedText, RetrievedChunk, SparseEmbedding
from src.rag.retriever import HybridRetriever


class FakeEmbeddingProvider:
    def embed_documents(self, texts: list[str]) -> list[EmbeddedText]:
        return [
            EmbeddedText(
                dense=[float(index), 0.1, 0.2],
                sparse=SparseEmbedding(indices=[index + 1], values=[1.0]),
            )
            for index, _ in enumerate(texts)
        ]

    def embed_query(self, text: str) -> EmbeddedText:
        _ = text
        return EmbeddedText(
            dense=[0.5, 0.1, 0.2],
            sparse=SparseEmbedding(indices=[7], values=[1.0]),
        )


class FakeVectorStore:
    def __init__(self) -> None:
        self.upserted_records = []
        self.search_calls = []

    async def upsert_chunks(self, records: list[dict]) -> None:
        self.upserted_records = records

    async def query_hybrid(self, **kwargs):
        self.search_calls.append(kwargs)
        return [
            {
                "score": 0.8,
                "payload": {
                    "chunk_id": "chunk-1",
                    "document_id": "doc-1",
                    "source_name": "policy.md",
                    "heading_path": ["Policy", "Access"],
                    "text": "Access policy text",
                    "tenant_id": "default",
                    "chunk_index": 0,
                },
            }
        ]


class FakeReranker:
    """Deterministic stub so retriever tests never load a real cross-encoder.

    With no preset scores it preserves the input order (descending scores).
    """

    def __init__(self, scores: list[float] | None = None) -> None:
        self.scores = scores
        self.calls: list[tuple[str, list[str]]] = []

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        self.calls.append((query, list(documents)))
        if self.scores is not None:
            return self.scores[: len(documents)]
        return [float(len(documents) - index) for index in range(len(documents))]


class FailingEmbeddingProvider:
    def embed_documents(self, texts: list[str]) -> list[EmbeddedText]:
        _ = texts
        raise RuntimeError("embedding backend unavailable")


def test_fastembed_provider_rejects_blank_document_text_before_model_load() -> None:
    provider = FastEmbedProvider()

    try:
        provider.embed_documents(["valid text", "   "])
    except RagEmbeddingError as exc:
        assert exc.code == "RAG_EMBED_500"
        assert exc.details["index"] == 1
    else:
        raise AssertionError("expected blank embedding input to fail")

    def embed_query(self, text: str) -> EmbeddedText:
        _ = text
        raise RuntimeError("embedding backend unavailable")


def test_heading_aware_chunking_preserves_heading_path() -> None:
    chunker = HeadingAwareChunker(max_chars=120, overlap_chars=10)

    chunks = chunker.split("# Policy\nIntro\n## Access\nUsers need MFA.\n## Audit\nLogs stay on.")

    assert [chunk.heading_path for chunk in chunks] == [
        ["Policy"],
        ["Policy", "Access"],
        ["Policy", "Audit"],
    ]
    assert chunks[1].text.startswith("Access")


def test_plain_text_chunks_predictably_without_headings() -> None:
    chunker = HeadingAwareChunker(max_chars=100, overlap_chars=10)

    chunks = chunker.split(("alpha " * 40).strip())

    assert len(chunks) > 1
    assert all(chunk.heading_path == [] for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_ingest_service_creates_stable_ids_and_upserts_chunks() -> None:
    vector_store = FakeVectorStore()
    service = DocumentIngestService(
        vector_store=vector_store,
        embedding_provider=FakeEmbeddingProvider(),
        chunker=HeadingAwareChunker(max_chars=120, overlap_chars=10),
    )

    first = asyncio.run(
        service.ingest_document(
            source_name="policy.md",
            content="# Policy\nAccess rules apply.",
            tenant_id="default",
        )
    )
    second = asyncio.run(
        service.ingest_document(
            source_name="policy.md",
            content="# Policy\nAccess rules apply.",
            tenant_id="default",
        )
    )

    assert first["document_id"] == second["document_id"]
    assert first["chunk_count"] == 1
    record = vector_store.upserted_records[0]
    assert record["id"] == record["payload"]["chunk_id"]
    assert record["payload"]["heading_path"] == ["Policy"]
    assert record["payload"]["source_name"] == "policy.md"
    assert record["payload"]["content_hash"]
    assert record["dense_vector"] == [0.0, 0.1, 0.2]
    assert record["sparse_indices"] == [1]


def test_ingest_service_wraps_unexpected_errors() -> None:
    service = DocumentIngestService(
        vector_store=FakeVectorStore(),
        embedding_provider=FailingEmbeddingProvider(),
        chunker=HeadingAwareChunker(max_chars=120, overlap_chars=10),
    )

    try:
        asyncio.run(
            service.ingest_document(
                source_name="policy.md",
                content="# Policy\nAccess rules apply.",
                tenant_id="default",
            )
        )
    except Exception as exc:
        assert exc.code == "RAG_INGEST_500"
        assert exc.status_code == 500
    else:
        raise AssertionError("expected RAG ingest error")


def test_retriever_calls_hybrid_search_and_maps_results() -> None:
    vector_store = FakeVectorStore()
    retriever = HybridRetriever(
        vector_store=vector_store,
        embedding_provider=FakeEmbeddingProvider(),
        reranker=FakeReranker(),
    )

    results = asyncio.run(retriever.search(query="access policy", tenant_id="default", top_k=1))

    assert vector_store.search_calls[0]["dense_vector"] == [0.5, 0.1, 0.2]
    assert vector_store.search_calls[0]["sparse_indices"] == [7]
    assert results[0].chunk_id == "chunk-1"
    assert results[0].heading_path == ["Policy", "Access"]
    assert results[0].source_name == "policy.md"
    assert results[0].metadata["tenant_id"] == "default"


def test_retriever_preserves_app_exceptions() -> None:
    class AppFailingEmbeddingProvider:
        def embed_query(self, text: str) -> EmbeddedText:
            _ = text
            raise RagEmbeddingError(details={"error": "model missing"})

    retriever = HybridRetriever(
        vector_store=FakeVectorStore(),
        embedding_provider=AppFailingEmbeddingProvider(),
    )

    try:
        asyncio.run(retriever.search(query="access policy", tenant_id="default", top_k=1))
    except RagEmbeddingError as exc:
        assert exc.code == "RAG_EMBED_500"
    else:
        raise AssertionError("expected RAG embedding error")


def test_retriever_reranks_candidates_before_top_k() -> None:
    class MultiCandidateVectorStore:
        async def query_hybrid(self, **kwargs):
            _ = kwargs
            return [
                {"score": 0.9, "payload": {"chunk_id": "a", "document_id": "d", "text": "alpha"}},
                {"score": 0.5, "payload": {"chunk_id": "b", "document_id": "d", "text": "beta"}},
                {"score": 0.7, "payload": {"chunk_id": "c", "document_id": "d", "text": "gamma"}},
            ]

    # Reranker promotes 'b' (the lowest retrieval score) to the top.
    reranker = FakeReranker(scores=[0.1, 0.95, 0.4])
    retriever = HybridRetriever(
        vector_store=MultiCandidateVectorStore(),
        embedding_provider=FakeEmbeddingProvider(),
        reranker=reranker,
    )

    results = asyncio.run(retriever.search(query="q", tenant_id="default", top_k=2))

    # Reranker ran on all candidate texts, then top_k was applied to the new order.
    assert reranker.calls[0][1] == ["alpha", "beta", "gamma"]
    assert [result.chunk_id for result in results] == ["b", "c"]
    assert results[0].score == 0.95
    # The original hybrid score is preserved for observability.
    assert results[0].metadata["retrieval_score"] == 0.5


def test_retriever_without_reranker_orders_by_retrieval_score() -> None:
    retriever = HybridRetriever(
        vector_store=FakeVectorStore(),
        embedding_provider=FakeEmbeddingProvider(),
        reranker=None,
    )
    retriever.reranker = None  # explicitly disable, bypassing the config default

    results = asyncio.run(retriever.search(query="q", tenant_id="default", top_k=1))

    assert results[0].chunk_id == "chunk-1"
    assert results[0].score == 0.8
    assert "retrieval_score" not in results[0].metadata


def test_retriever_top_k_sorting_is_deterministic() -> None:
    results = [
        RetrievedChunk("b", "doc-2", "b.md", [], "second", 0.5),
        RetrievedChunk("a", "doc-1", "a.md", [], "first", 0.9),
        RetrievedChunk("c", "doc-3", "c.md", [], "third", 0.1),
    ]

    sorted_results = sorted(results, key=lambda item: (-item.score, item.document_id, item.chunk_id))[:2]

    assert [result.chunk_id for result in sorted_results] == ["a", "b"]


def test_ingest_endpoint_returns_ingest_result(monkeypatch) -> None:
    class FakeIngestService:
        async def ingest_document(self, **kwargs):
            assert kwargs["tenant_id"] == "default"
            return {"document_id": "doc-1", "chunk_count": 2, "status": "ingested"}

    monkeypatch.setattr(documents_router, "document_ingest_service", FakeIngestService())

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/documents/ingest",
        json={"source_name": "policy.md", "content": "# Policy\nText", "tenant_id": "default"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {"document_id": "doc-1", "chunk_count": 2, "status": "ingested"}
    assert body["request_id"]


def test_search_endpoint_returns_normalized_results(monkeypatch) -> None:
    class FakeRetriever:
        async def search(self, **kwargs):
            assert kwargs["query"] == "access"
            return [
                SimpleNamespace(
                    chunk_id="chunk-1",
                    document_id="doc-1",
                    source_name="policy.md",
                    heading_path=["Policy"],
                    text="Access text",
                    score=0.7,
                    metadata={"tenant_id": "default"},
                )
            ]

    monkeypatch.setattr(search_router, "hybrid_retriever", FakeRetriever())

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/search", json={"query": "access", "tenant_id": "default", "top_k": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["results"][0]["chunk_id"] == "chunk-1"
    assert body["data"]["results"][0]["metadata"]["tenant_id"] == "default"


def test_search_validation_uses_global_error_shape() -> None:
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/search", json={"query": "", "tenant_id": "default"})

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "REQ_422"


def test_search_app_exception_uses_global_error_shape(monkeypatch) -> None:
    class FakeRetriever:
        async def search(self, **kwargs):
            _ = kwargs
            raise RagEmbeddingError(details={"error": "model missing"})

    monkeypatch.setattr(search_router, "hybrid_retriever", FakeRetriever())

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/search", json={"query": "access", "tenant_id": "default"})

    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "RAG_EMBED_500"
