from fastapi import APIRouter, File, Form, Query, Request, UploadFile

from src.rag.ingest import DocumentIngestService
from src.rag.loaders import load_document
from src.schemas.documents import (
    DocumentDeleteResult,
    DocumentIngestRequest,
    DocumentIngestResult,
    DocumentListResult,
)
from src.schemas.response import SuccessResponse

router = APIRouter(prefix="/documents", tags=["Documents"])
document_ingest_service = DocumentIngestService()


@router.get("", response_model=SuccessResponse[DocumentListResult])
async def list_documents(
    request: Request,
    tenant_id: str = Query(..., min_length=1),
    limit: int = Query(100, ge=1, le=500),
):
    result = await document_ingest_service.list_documents(
        tenant_id=tenant_id,
        limit=limit,
    )
    return SuccessResponse(data=result, request_id=request.state.request_id)


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
    loaded_document = load_document(
        source_name=file.filename,
        raw_content=await file.read(),
    )
    result = await document_ingest_service.ingest_document(
        source_name=loaded_document.source_name,
        content=loaded_document.content,
        tenant_id=tenant_id,
        content_kind=loaded_document.content_kind,
    )
    return SuccessResponse(data=result, request_id=request.state.request_id)


@router.delete("/{document_id}", response_model=SuccessResponse[DocumentDeleteResult])
async def delete_document(
    document_id: str,
    request: Request,
    tenant_id: str = Query(..., min_length=1),
):
    result = await document_ingest_service.delete_document(
        document_id=document_id,
        tenant_id=tenant_id,
    )
    return SuccessResponse(data=result, request_id=request.state.request_id)
