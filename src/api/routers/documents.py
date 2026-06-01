from fastapi import APIRouter, File, Form, Request, UploadFile

from src.rag.ingest import DocumentIngestService
from src.rag.loaders import load_text_document
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


@router.post("/upload", response_model=SuccessResponse[DocumentIngestResult])
async def upload_document(
    request: Request,
    tenant_id: str = Form(..., min_length=1),
    file: UploadFile = File(...),
):
    loaded_document = load_text_document(
        source_name=file.filename,
        raw_content=await file.read(),
    )
    result = await document_ingest_service.ingest_document(
        source_name=loaded_document.source_name,
        content=loaded_document.content,
        tenant_id=tenant_id,
    )
    return SuccessResponse(data=result, request_id=request.state.request_id)
