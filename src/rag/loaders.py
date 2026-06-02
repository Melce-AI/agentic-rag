import io
from collections.abc import Callable
from pathlib import Path

from src.core.exceptions import DocumentParseError, RagValidationError
from src.rag.models import (
    CONTENT_KIND_BY_FILE_TYPE,
    DocumentFileType,
    LoadedDocument,
)


SUPPORTED_EXTENSIONS = tuple(sorted(file_type.value for file_type in DocumentFileType))


def load_document(*, source_name: str | None, raw_content: bytes) -> LoadedDocument:
    """
    Converts uploaded bytes into the document used by ingest.

    The caller reads the file bytes; this function validates them, extracts plain
    text with the parser its file type requires, and tags the result with the
    chunking strategy (``content_kind``) that text needs. Text-like types are
    decoded as UTF-8; binary types (PDF) are parsed into text.
    """
    normalized_source_name = _normalize_source_name(source_name)
    file_type = _resolve_file_type(normalized_source_name)
    content = _PARSERS[file_type](normalized_source_name, raw_content)

    if not content.strip():
        raise RagValidationError(
            "document content must not be empty",
            details={"source_name": normalized_source_name},
        )

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


def _parse_pdf(source_name: str, raw_content: bytes) -> str:
    # Imported lazily so the text/CSV path does not pay the pypdf import cost.
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(raw_content))
        pages = [page.extract_text() or "" for page in reader.pages]
    except (PdfReadError, ValueError, OSError) as exc:
        raise DocumentParseError(
            details={"source_name": source_name, "error": str(exc)}
        ) from exc

    return "\n\n".join(page.strip() for page in pages if page.strip())


_PARSERS: dict[DocumentFileType, Callable[[str, bytes], str]] = {
    DocumentFileType.MARKDOWN: _parse_utf8_text,
    DocumentFileType.TEXT: _parse_utf8_text,
    DocumentFileType.CSV: _parse_utf8_text,
    DocumentFileType.PDF: _parse_pdf,
}


def _normalize_source_name(source_name: str | None) -> str:
    if source_name is None or not source_name.strip():
        raise RagValidationError("source_name must not be empty")

    stripped = source_name.strip()
    normalized_path = stripped.replace("\\", "/")
    filename = normalized_path.rsplit("/", maxsplit=1)[-1]
    if not filename:
        raise RagValidationError("source_name must not be empty")

    return filename
