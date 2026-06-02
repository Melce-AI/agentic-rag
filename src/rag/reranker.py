from typing import Protocol

from src.core.config import get_settings
from src.core.exceptions import RagRerankError


class Reranker(Protocol):
    """
    Re-scores retrieved candidate texts against a query with a cross-encoder.

    Contract:
    - `rerank(query, [])` returns an empty list.
    - The returned scores match the input document order and length.
    - Higher score means more relevant.
    - Implementations should raise `RagRerankError` for provider/model failures.
    """

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Return one relevance score per document, aligned with input order."""
        ...


class FastEmbedReranker:
    """Cross-encoder reranker backed by fastembed's TextCrossEncoder.

    Unlike the bi-encoder used for retrieval (which embeds query and documents
    separately), a cross-encoder reads the (query, document) pair together, so it
    ranks relevance far more accurately — at a higher cost. That is why it runs
    only on the ~20 candidates retrieval already narrowed down, not the whole corpus.
    """

    def __init__(self, model_name: str | None = None) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.rag_rerank_model
        self._model = None

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []

        try:
            scores = [float(score) for score in self.model.rerank(query, documents)]
            if len(scores) != len(documents):
                raise RagRerankError(
                    details={
                        "error": "reranker returned an unexpected number of scores",
                        "expected_count": len(documents),
                        "score_count": len(scores),
                    }
                )
            return scores
        except RagRerankError:
            raise
        except Exception as exc:
            raise RagRerankError(
                details={"model": self.model_name, "error": str(exc)}
            ) from exc

    @property
    def model(self):
        if self._model is None:
            try:
                from fastembed.rerank.cross_encoder import TextCrossEncoder

                self._model = TextCrossEncoder(model_name=self.model_name)
            except Exception as exc:
                raise RagRerankError(
                    details={"model": self.model_name, "error": str(exc)}
                ) from exc
        return self._model
