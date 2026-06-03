"""Pydantic models for MCP tool inputs and outputs."""

from pydantic import BaseModel


class MCPSearchResult(BaseModel):
    document_id: str
    source_name: str
    heading_path: list[str]
    text: str
    score: float
