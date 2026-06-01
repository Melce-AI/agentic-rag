from typing import Any

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=20)


class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    source_name: str
    heading_path: list[str]
    text: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponseData(BaseModel):
    results: list[SearchResult]
