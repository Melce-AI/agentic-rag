from fastapi import APIRouter, Request

from src.rag.retriever import HybridRetriever
from src.schemas.response import SuccessResponse
from src.schemas.search import SearchRequest, SearchResponseData, SearchResult

router = APIRouter(prefix="/search", tags=["Search"])
hybrid_retriever = HybridRetriever()


@router.post("", response_model=SuccessResponse[SearchResponseData])
async def search_documents(payload: SearchRequest, request: Request):
    results = await hybrid_retriever.search(
        query=payload.query,
        tenant_id=payload.tenant_id,
        top_k=payload.top_k,
    )
    return SuccessResponse(
        data=SearchResponseData(
            results=[
                SearchResult(
                    chunk_id=result.chunk_id,
                    document_id=result.document_id,
                    source_name=result.source_name,
                    heading_path=result.heading_path,
                    text=result.text,
                    score=result.score,
                    metadata=result.metadata,
                )
                for result in results
            ]
        ),
        request_id=request.state.request_id,
    )
