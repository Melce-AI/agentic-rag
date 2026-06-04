from io import BytesIO
from types import SimpleNamespace
import asyncio

from starlette.datastructures import UploadFile

from src.api.routers import documents


class _FakeDocumentIngestService:
    def __init__(self) -> None:
        self.calls = []

    async def ingest_document(self, *, source_name: str, content: str, tenant_id: str, content_kind: str):
        self.calls.append(
            {
                "source_name": source_name,
                "content": content,
                "tenant_id": tenant_id,
                "content_kind": content_kind,
            }
        )
        return {
            "document_id": "doc-1",
            "chunk_count": 1,
            "status": "ingested",
        }


def test_upload_document_loads_file_and_ingests(monkeypatch):
    fake_service = _FakeDocumentIngestService()
    monkeypatch.setattr(documents, "document_ingest_service", fake_service)
    request = SimpleNamespace(state=SimpleNamespace(request_id="req-1"))
    file = UploadFile(
        filename="policy.md",
        file=BytesIO(b"# Policy\n\nMFA is required."),
    )

    response = asyncio.run(
        documents.upload_document(
            request=request,
            tenant_id="tenant-a",
            file=file,
        )
    )

    assert response.request_id == "req-1"
    assert response.data["status"] == "ingested"
    assert fake_service.calls == [
        {
            "source_name": "policy.md",
            "content": "# Policy\n\nMFA is required.",
            "tenant_id": "tenant-a",
            "content_kind": "text",
        }
    ]
