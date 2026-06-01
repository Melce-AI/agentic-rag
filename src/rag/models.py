from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DocumentFileType(StrEnum):
    MARKDOWN = ".md"
    TEXT = ".txt"


@dataclass(frozen=True)
class Document:
    document_id: str
    tenant_id: str
    source_name: str
    content_hash: str


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    tenant_id: str
    text: str
    heading_path: list[str]
    chunk_index: int
    source_name: str
    created_at: str
    content_hash: str


@dataclass(frozen=True)
class ChunkDraft:
    text: str
    heading_path: list[str]
    chunk_index: int


@dataclass(frozen=True)
class LoadedTextDocument:
    source_name: str
    content: str


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    document_id: str
    source_name: str
    heading_path: list[str]
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SparseEmbedding:
    indices: list[int]
    values: list[float]


@dataclass(frozen=True)
class EmbeddedText:
    dense: list[float]
    sparse: SparseEmbedding
