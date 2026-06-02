from pydantic import BaseModel, Field


class DocumentIngestRequest(BaseModel):
    source_name: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)


class DocumentIngestResult(BaseModel):
    document_id: str
    chunk_count: int
    status: str


class DocumentSummary(BaseModel):
    document_id: str
    tenant_id: str
    source_name: str
    chunk_count: int
    created_at: str
    content_hash: str


class DocumentListResult(BaseModel):
    documents: list[DocumentSummary]
    count: int


class DocumentDeleteResult(BaseModel):
    document_id: str
    tenant_id: str
    status: str
