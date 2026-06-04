from pathlib import Path

import pytest

from src.core.exceptions import DocumentParseError, RagValidationError
from src.rag.loaders import load_document
from src.rag.models import ContentKind

SAMPLE_PDF = (Path(__file__).parent / "fixtures" / "sample.pdf").read_bytes()


def test_load_document_accepts_markdown_bytes():
    loaded = load_document(
        source_name="policy.md",
        raw_content=b"# Policy\n\nMFA is required.",
    )

    assert loaded.source_name == "policy.md"
    assert loaded.content == "# Policy\n\nMFA is required."
    assert loaded.content_kind is ContentKind.TEXT


def test_load_document_tags_csv_as_tabular():
    loaded = load_document(
        source_name="users.csv",
        raw_content=b"name,role\nAyse,admin\n",
    )

    assert loaded.source_name == "users.csv"
    assert loaded.content_kind is ContentKind.TABULAR


def test_load_document_normalizes_client_paths():
    loaded = load_document(
        source_name=r"C:\fakepath\policy.md",
        raw_content=b"# Policy",
    )

    assert loaded.source_name == "policy.md"


def test_load_document_extracts_pdf_text_as_text_kind():
    loaded = load_document(source_name="policy.pdf", raw_content=SAMPLE_PDF)

    assert loaded.source_name == "policy.pdf"
    assert loaded.content_kind is ContentKind.TEXT
    assert "MFA is required for all admin accounts." in loaded.content
    assert "incident response runbook." in loaded.content


def test_load_document_raises_on_corrupt_pdf():
    with pytest.raises(DocumentParseError) as exc_info:
        load_document(source_name="broken.pdf", raw_content=b"%PDF-1.4 not a real pdf")

    assert exc_info.value.code == "DOC_01"


def test_load_document_rejects_unsupported_extensions():
    with pytest.raises(RagValidationError) as exc_info:
        load_document(source_name="data.xlsx", raw_content=b"content")

    assert exc_info.value.code == "RAG_422"
    assert exc_info.value.details["supported_extensions"] == [".csv", ".md", ".pdf", ".txt"]


def test_load_document_rejects_non_utf8_content():
    with pytest.raises(RagValidationError) as exc_info:
        load_document(source_name="policy.md", raw_content=b"\xff")

    assert exc_info.value.message == "Document must be UTF-8 encoded text"
