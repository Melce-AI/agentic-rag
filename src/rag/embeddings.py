from typing import Protocol

from src.core.config import get_settings
from src.core.exceptions import RagEmbeddingError
from src.rag.models import EmbeddedText, SparseEmbedding


class EmbeddingProvider(Protocol):
    """
    Converts RAG text units into paired dense and sparse embeddings.

    Contract:
    - `embed_documents([])` returns an empty list.
    - Non-empty inputs must not contain blank strings.
    - Result order and length must match the input order and length.
    - Implementations should raise `RagEmbeddingError` for provider/model failures.
    """

    def embed_documents(self, texts: list[str]) -> list[EmbeddedText]:
        """Embed chunk/document texts for indexing."""
        ...

    def embed_query(self, text: str) -> EmbeddedText:
        """Embed one retrieval query."""
        ...


class FastEmbedProvider:
    def __init__(
        self,
        dense_model_name: str | None = None,
        sparse_model_name: str | None = None,
    ) -> None:
        settings = get_settings()
        self.dense_model_name = dense_model_name or settings.RAG_DENSE_MODEL
        self.sparse_model_name = sparse_model_name or settings.RAG_SPARSE_MODEL
        self._dense_model = None
        self._sparse_model = None

    def embed_documents(self, texts: list[str]) -> list[EmbeddedText]:
        if not texts:
            return []

        try:
            self._validate_texts(texts)
            dense_vectors = [self._as_float_list(vector) for vector in self.dense_model.embed(texts)]
            sparse_vectors = [self._to_sparse_embedding(vector) for vector in self.sparse_model.embed(texts)]
            self._validate_embedding_counts(
                expected_count=len(texts),
                dense_count=len(dense_vectors),
                sparse_count=len(sparse_vectors),
            )
            return [
                EmbeddedText(dense=dense, sparse=sparse)
                for dense, sparse in zip(dense_vectors, sparse_vectors)
            ]
        except RagEmbeddingError:
            raise
        except Exception as exc:
            raise RagEmbeddingError(
                details={
                    "dense_model": self.dense_model_name,
                    "sparse_model": self.sparse_model_name,
                    "error": str(exc),
                }
            ) from exc

    def embed_query(self, text: str) -> EmbeddedText:
        embedded = self.embed_documents([text])
        return embedded[0]

    @property
    def dense_model(self):
        if self._dense_model is None:
            try:
                from fastembed import TextEmbedding

                self._dense_model = TextEmbedding(model_name=self.dense_model_name)
            except Exception as exc:
                raise RagEmbeddingError(
                    details={"model": self.dense_model_name, "error": str(exc)}
                ) from exc
        return self._dense_model

    @property
    def sparse_model(self):
        if self._sparse_model is None:
            try:
                from fastembed import SparseTextEmbedding

                self._sparse_model = SparseTextEmbedding(model_name=self.sparse_model_name)
            except Exception as exc:
                raise RagEmbeddingError(
                    details={"model": self.sparse_model_name, "error": str(exc)}
                ) from exc
        return self._sparse_model

    @staticmethod
    def _as_float_list(vector) -> list[float]:
        if hasattr(vector, "tolist"):
            return [float(value) for value in vector.tolist()]
        return [float(value) for value in vector]

    @classmethod
    def _to_sparse_embedding(cls, vector) -> SparseEmbedding:
        indices = getattr(vector, "indices")
        values = getattr(vector, "values")
        return SparseEmbedding(
            indices=[int(value) for value in cls._as_plain_list(indices)],
            values=[float(value) for value in cls._as_plain_list(values)],
        )

    @staticmethod
    def _as_plain_list(values) -> list:
        return values.tolist() if hasattr(values, "tolist") else list(values)

    @staticmethod
    def _validate_texts(texts: list[str]) -> None:
        for index, text in enumerate(texts):
            if not text.strip():
                raise RagEmbeddingError(
                    details={"error": "embedding input text must not be blank", "index": index}
                )

    @staticmethod
    def _validate_embedding_counts(
        *,
        expected_count: int,
        dense_count: int,
        sparse_count: int,
    ) -> None:
        if dense_count != expected_count or sparse_count != expected_count:
            raise RagEmbeddingError(
                details={
                    "error": "embedding provider returned an unexpected number of vectors",
                    "expected_count": expected_count,
                    "dense_count": dense_count,
                    "sparse_count": sparse_count,
                }
            )
