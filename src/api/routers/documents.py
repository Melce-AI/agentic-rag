from fastapi import APIRouter, Request

from src.rag.ingest import DocumentIngestService
from src.schemas.documents import DocumentIngestRequest, DocumentIngestResult
from src.schemas.response import SuccessResponse

router = APIRouter(prefix="/documents", tags=["Documents"])
document_ingest_service = DocumentIngestService()


@router.post("/ingest", response_model=SuccessResponse[DocumentIngestResult])
async def ingest_document(payload: DocumentIngestRequest, request: Request):
    result = await document_ingest_service.ingest_document(
        source_name=payload.source_name,
        content=payload.content,
        tenant_id=payload.tenant_id,
    )
    return SuccessResponse(data=result, request_id=request.state.request_id)
