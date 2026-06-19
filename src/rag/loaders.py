import logging
from collections.abc import Callable
from pathlib import Path

from opentelemetry import trace

from src.core.exceptions import RagValidationError
from src.rag.models import (
    CONTENT_KIND_BY_FILE_TYPE,
    DocumentFileType,
    LoadedDocument,
)
from src.rag.parsers import binary_parser
from src.observability.tracing import traced

log = logging.getLogger(__name__)
log.info("Document parser selected: %s", type(binary_parser).__name__)

SUPPORTED_EXTENSIONS = tuple(sorted(file_type.value for file_type in DocumentFileType))


@traced("rag.parse", span_kind="CHAIN")
def load_document(*, source_name: str | None, raw_content: bytes) -> LoadedDocument:
    """
    Converts uploaded bytes into the document used by ingest.

    Text-like types are decoded as UTF-8. Binary types (PDF, DOCX, PPTX, XLSX)
    are parsed by DoclingParser when docling is installed (ML layout + table
    extraction), or by LightweightParser otherwise (plain text extraction).
    """
    normalized_source_name = _normalize_source_name(source_name)
    file_type = _resolve_file_type(normalized_source_name)

    span = trace.get_current_span()
    span.set_attribute("input.value", normalized_source_name)
    span.set_attribute("rag.source_name", normalized_source_name)
    span.set_attribute("rag.file_type", file_type.value)
    span.set_attribute("rag.parser", type(binary_parser).__name__)

    log.info(
        "Parsing '%s' as %s via %s",
        normalized_source_name,
        file_type.value,
        type(binary_parser).__name__,
    )
    content = _PARSERS[file_type](normalized_source_name, raw_content)

    if not content.strip():
        raise RagValidationError(
            "document content must not be empty",
            details={"source_name": normalized_source_name},
        )

    span.set_attribute("output.value", f"{len(content)} chars")
    log.debug("Parsed '%s': %d chars", normalized_source_name, len(content))
    return LoadedDocument(
        source_name=normalized_source_name,
        content=content,
        content_kind=CONTENT_KIND_BY_FILE_TYPE[file_type],
    )


def _resolve_file_type(source_name: str) -> DocumentFileType:
    extension = Path(source_name).suffix.lower()
    try:
        return DocumentFileType(extension)
    except ValueError as exc:
        raise RagValidationError(
            "Unsupported document type",
            details={
                "source_name": source_name,
                "supported_extensions": list(SUPPORTED_EXTENSIONS),
            },
        ) from exc


def _parse_utf8_text(source_name: str, raw_content: bytes) -> str:
    try:
        return raw_content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RagValidationError(
            "Document must be UTF-8 encoded text",
            details={"source_name": source_name},
        ) from exc


def _normalize_source_name(source_name: str | None) -> str:
    if source_name is None or not source_name.strip():
        raise RagValidationError("source_name must not be empty")

    stripped = source_name.strip()
    normalized_path = stripped.replace("\\", "/")
    filename = normalized_path.rsplit("/", maxsplit=1)[-1]
    if not filename:
        raise RagValidationError("source_name must not be empty")

    return filename


_PARSERS: dict[DocumentFileType, Callable[[str, bytes], str]] = {
    DocumentFileType.MARKDOWN: _parse_utf8_text,
    DocumentFileType.TEXT: _parse_utf8_text,
    DocumentFileType.CSV: _parse_utf8_text,
    DocumentFileType.PDF: binary_parser.to_markdown,
    DocumentFileType.DOCX: binary_parser.to_markdown,
    DocumentFileType.PPTX: binary_parser.to_markdown,
    DocumentFileType.XLSX: binary_parser.to_csv_tables,
}
