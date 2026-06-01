from pydantic import BaseModel, Field


class DocumentIngestRequest(BaseModel):
    source_name: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)


class DocumentIngestResult(BaseModel):
    document_id: str
    chunk_count: int
    status: str
