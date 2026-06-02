from typing import Any, Optional


class AppException(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[Any] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class DocumentParseError(AppException):
    def __init__(self, details: Optional[Any] = None):
        super().__init__(
            code="DOC_01",
            message="Document could not be parsed",
            status_code=422,
            details=details,
        )


class DatabaseConnectionError(AppException):
    def __init__(self, details: Optional[Any] = None):
        super().__init__(
            code="DB_01",
            message="Database connection failed",
            status_code=503,
            details=details,
        )


class ResourceNotFoundError(AppException):
    def __init__(self, resource: str, details: Optional[Any] = None):
        super().__init__(
            code="RES_404",
            message=f"{resource} not found",
            status_code=404,
            details=details,
        )


class VectorStoreError(AppException):
    def __init__(self, message: str, code: str = "VEC_00", status_code: int = 500, details: Optional[Any] = None):
        super().__init__(
            code=code,
            message=message,
            status_code=status_code,
            details=details,
        )


class VectorStoreInitializationError(VectorStoreError):
    def __init__(self, details: Optional[Any] = None):
        super().__init__(
            code="VEC_01",
            message="Vector store initialization failed",
            status_code=500,
            details=details,
        )


class VectorStoreOperationError(VectorStoreError):
    def __init__(self, operation: str, details: Optional[Any] = None):
        super().__init__(
            code="VEC_02",
            message=f"Vector store operation '{operation}' failed",
            status_code=500,
            details=details,
        )


class RagError(AppException):
    def __init__(
        self,
        message: str,
        code: str = "RAG_00",
        status_code: int = 500,
        details: Optional[Any] = None,
    ):
        super().__init__(
            code=code,
            message=message,
            status_code=status_code,
            details=details,
        )


class RagValidationError(RagError):
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(
            code="RAG_422",
            message=message,
            status_code=422,
            details=details,
        )


class RagConfigurationError(RagError):
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(
            code="RAG_CFG_500",
            message=message,
            status_code=500,
            details=details,
        )


class RagEmbeddingError(RagError):
    def __init__(self, details: Optional[Any] = None):
        super().__init__(
            code="RAG_EMBED_500",
            message="Embedding generation failed",
            status_code=500,
            details=details,
        )


class RagIngestError(RagError):
    def __init__(self, details: Optional[Any] = None):
        super().__init__(
            code="RAG_INGEST_500",
            message="Document ingest failed",
            status_code=500,
            details=details,
        )


class RagDeleteError(RagError):
    def __init__(self, details: Optional[Any] = None):
        super().__init__(
            code="RAG_DELETE_500",
            message="Document deletion failed",
            status_code=500,
            details=details,
        )


class RagRetrievalError(RagError):
    def __init__(self, details: Optional[Any] = None):
        super().__init__(
            code="RAG_SEARCH_500",
            message="Hybrid retrieval failed",
            status_code=500,
            details=details,
        )


class RagRerankError(RagError):
    def __init__(self, details: Optional[Any] = None):
        super().__init__(
            code="RAG_RERANK_500",
            message="Reranking failed",
            status_code=500,
            details=details,
        )
