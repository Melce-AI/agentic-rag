from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DocumentFileType(StrEnum):
    MARKDOWN = ".md"
    TEXT = ".txt"
    CSV = ".csv"
    PDF = ".pdf"
    DOCX = ".docx"
    PPTX = ".pptx"
    XLSX = ".xlsx"


class ContentKind(StrEnum):
    """How a loaded document should be chunked.

    TEXT  -> prose/markdown, split with the heading-aware chunker.
    TABULAR -> row-oriented data, split with the table (record) chunker.
    """

    TEXT = "text"
    TABULAR = "tabular"


# Maps a supported file extension to the chunking strategy it needs.
CONTENT_KIND_BY_FILE_TYPE: dict[DocumentFileType, ContentKind] = {
    DocumentFileType.MARKDOWN: ContentKind.TEXT,
    DocumentFileType.TEXT: ContentKind.TEXT,
    DocumentFileType.CSV: ContentKind.TABULAR,
    DocumentFileType.PDF: ContentKind.TEXT,
    DocumentFileType.DOCX: ContentKind.TEXT,
    DocumentFileType.PPTX: ContentKind.TEXT,
    DocumentFileType.XLSX: ContentKind.TABULAR,
}


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
    chunk_token_count: int
    section_title: str | None
    section_index: int
    source_name: str
    created_at: str
    content_hash: str


@dataclass(frozen=True)
class ChunkDraft:
    text: str
    heading_path: list[str]
    chunk_index: int
    chunk_token_count: int
    section_title: str | None
    section_index: int


@dataclass(frozen=True)
class LoadedDocument:
    source_name: str
    content: str
    content_kind: ContentKind


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
