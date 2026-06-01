import pytest

from src.core.exceptions import RagValidationError
from src.rag.loaders import load_text_document


def test_load_text_document_accepts_markdown_bytes():
    loaded = load_text_document(
        source_name="policy.md",
        raw_content=b"# Policy\n\nMFA is required.",
    )

    assert loaded.source_name == "policy.md"
    assert loaded.content == "# Policy\n\nMFA is required."


def test_load_text_document_normalizes_client_paths():
    loaded = load_text_document(
        source_name=r"C:\fakepath\policy.md",
        raw_content=b"# Policy",
    )

    assert loaded.source_name == "policy.md"


def test_load_text_document_rejects_unsupported_extensions():
    with pytest.raises(RagValidationError) as exc_info:
        load_text_document(source_name="policy.pdf", raw_content=b"content")

    assert exc_info.value.code == "RAG_422"
    assert exc_info.value.details["supported_extensions"] == [".md", ".txt"]


def test_load_text_document_rejects_non_utf8_content():
    with pytest.raises(RagValidationError) as exc_info:
        load_text_document(source_name="policy.md", raw_content=b"\xff")

    assert exc_info.value.message == "Document must be UTF-8 encoded text"
