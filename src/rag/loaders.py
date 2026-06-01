from pathlib import Path

from src.core.exceptions import RagValidationError
from src.rag.models import DocumentFileType, LoadedTextDocument


SUPPORTED_TEXT_EXTENSIONS = tuple(sorted(file_type.value for file_type in DocumentFileType))


def load_text_document(*, source_name: str | None, raw_content: bytes) -> LoadedTextDocument:
    """
    Converts uploaded text bytes into the text document used by ingest.

    The caller reads the file bytes; this function only validates and decodes them.
    """
    normalized_source_name = _normalize_source_name(source_name)
    extension = Path(normalized_source_name).suffix.lower()
    if extension not in SUPPORTED_TEXT_EXTENSIONS:
        raise RagValidationError(
            "Unsupported document type",
            details={
                "source_name": normalized_source_name,
                "supported_extensions": list(SUPPORTED_TEXT_EXTENSIONS),
            },
        )

    try:
        content = raw_content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RagValidationError(
            "Document must be UTF-8 encoded text",
            details={"source_name": normalized_source_name},
        ) from exc

    if not content.strip():
        raise RagValidationError(
            "document content must not be empty",
            details={"source_name": normalized_source_name},
        )

    return LoadedTextDocument(source_name=normalized_source_name, content=content)


def _normalize_source_name(source_name: str | None) -> str:
    if source_name is None or not source_name.strip():
        raise RagValidationError("source_name must not be empty")

    stripped = source_name.strip()
    normalized_path = stripped.replace("\\", "/")
    filename = normalized_path.rsplit("/", maxsplit=1)[-1]
    if not filename:
        raise RagValidationError("source_name must not be empty")

    return filename
