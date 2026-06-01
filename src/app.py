import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError

from src.core.exception_handlers import (
    app_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from src.core.exceptions import AppException
from src.core.logger import setup_logging
from src.storage.qdrant_client import qdrant_manager


logger = logging.getLogger(__name__)
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application is starting.")
    await qdrant_manager.init_collection()
    yield
    logger.info("Application is shutting down.")
    await qdrant_manager.close()


app = FastAPI(
    title="Enterprise Document Processing API",
    description="""
    Enterprise document processing and RAG retrieval API.

    Features:
    - Async endpoint support
    - Global exception handling
    - Standard JSON error format
    - OpenAPI documentation
    - Request tracing
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "Health", "description": "Service health checks"},
        {"name": "Documents", "description": "Document ingest operations"},
        {"name": "Search", "description": "Hybrid RAG retrieval operations"},
    ],
    lifespan=lifespan,
)


@app.middleware("http")
async def add_request_id_middleware(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-Id"] = request.state.request_id
    return response


from src.api.routers.documents import router as documents_router
from src.api.routers.search import router as search_router

# Register exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(documents_router)
app.include_router(search_router)


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "version": "1.0.0"}
