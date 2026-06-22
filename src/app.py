import json
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError

from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from src.core.exception_handlers import (
    app_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from src.core.context import request_id_var
from src.core.exceptions import AppException
from src.adapters.vector_store.qdrant import qdrant_manager
from src.agents.tools import MCP_SERVER_NAME, create_mcp_client
from src.observability.logging import setup_logging
from src.observability.tracing import setup_tracing
from langchain_mcp_adapters.tools import load_mcp_tools


logger = logging.getLogger(__name__)
setup_logging()
setup_tracing()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application is starting.")
    await qdrant_manager.init_collection()
    mcp_client = create_mcp_client()
    async with mcp_client.session(MCP_SERVER_NAME) as session:
        app.state.mcp_tools = await load_mcp_tools(session)
        logger.info("MCP tools loaded: %s", [t.name for t in app.state.mcp_tools])
        yield
    logger.info("Application is shutting down.")
    await qdrant_manager.close()
    provider = trace.get_tracer_provider()
    if hasattr(provider, "shutdown"):
        provider.shutdown()


app = FastAPI(
    title="Enterprise Document Processing API",
    description="""
    Enterprise document processing and RAG retrieval API.

    Features:
    - Async endpoint support
    - JSON and file-upload document ingest
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
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("metadata", json.dumps({"request_id": request_id}))
    try:
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response
    finally:
        request_id_var.reset(token)


from src.api.routers.agent import router as agent_router
from src.api.routers.documents import router as documents_router
from src.api.routers.search import router as search_router

# Register exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(documents_router)
app.include_router(search_router)
app.include_router(agent_router)

FastAPIInstrumentor.instrument_app(app, excluded_urls="/health")


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "version": "1.0.0"}
