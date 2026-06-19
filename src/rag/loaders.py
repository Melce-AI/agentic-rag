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


class DoclingParser:
    """Lazy-loading Docling converter — initialised once per process, reused per request.

    ``to_markdown`` is used for prose formats (PDF, DOCX, PPTX).
    ``to_csv_tables`` is used for spreadsheets (XLSX) so the output feeds
    directly into ``TableChunker`` without row-boundary splits.
    """

    def __init__(self) -> None:
        self._converter = None

    @property
    def converter(self):
        if self._converter is None:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption

            pipeline_opts = PdfPipelineOptions()

            self._converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts)
                }
            )
        return self._converter

    def to_markdown(self, source_name: str, raw_content: bytes) -> str:
        return self._convert(source_name, raw_content).document.export_to_markdown()

    def to_csv_tables(self, source_name: str, raw_content: bytes) -> str:
        result = self._convert(source_name, raw_content)
        tables = [
            table.export_to_dataframe().to_csv(index=False)
            for table in result.document.tables
        ]
        return "\n".join(tables)

    def _convert(self, source_name: str, raw_content: bytes):
        from docling.datamodel.base_models import ConversionStatus
        from docling.datamodel.document import DocumentStream

        try:
            stream = DocumentStream(name=source_name, stream=io.BytesIO(raw_content))
            result = self.converter.convert(stream)
        except Exception as exc:
            raise DocumentParseError(
                details={"source_name": source_name, "error": str(exc)}
            ) from exc

        if result.status == ConversionStatus.FAILURE:
            raise DocumentParseError(
                details={"source_name": source_name, "status": result.status.value}
            )

        return result


docling_parser = DoclingParser()


_PARSERS: dict[DocumentFileType, Callable[[str, bytes], str]] = {
    DocumentFileType.MARKDOWN: _parse_utf8_text,
    DocumentFileType.TEXT: _parse_utf8_text,
    DocumentFileType.CSV: _parse_utf8_text,
    DocumentFileType.PDF: docling_parser.to_markdown,
    DocumentFileType.DOCX: docling_parser.to_markdown,
    DocumentFileType.PPTX: docling_parser.to_markdown,
    DocumentFileType.XLSX: docling_parser.to_csv_tables,
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
