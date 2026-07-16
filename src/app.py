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
from src.agents.checkpointer import create_checkpointer
from src.agents.graph import build_graph
from src.agents.mcp_client import MCP_SERVER_NAME, create_mcp_client
from src.auth.keys import load_private_key, load_public_key
from src.core.config import get_settings
from src.observability.logging import setup_logging
from src.observability.tracing import setup_tracing
from langchain_mcp_adapters.tools import load_mcp_tools
from src.api.routers.auth import router as auth_router
from src.api.routers.chat import router as chat_router

logger = logging.getLogger(__name__)
setup_logging()
setup_tracing()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application is starting.")
    settings = get_settings()
    # Fail fast: load the JWT signing keys at startup so a missing or malformed
    # key crashes the app here with a clear error, not on the first /auth/login.
    load_private_key()
    load_public_key()
    logger.info("JWT signing keys loaded.")
    await qdrant_manager.init_collection()
    mcp_client = create_mcp_client()
    async with mcp_client.session(MCP_SERVER_NAME) as session:
        app.state.mcp_tools = await load_mcp_tools(session)
        logger.info("MCP tools loaded: %s", [t.name for t in app.state.mcp_tools])
        async with create_checkpointer(settings.redis_url) as checkpointer:
            app.state.checkpointer = checkpointer
            app.state.graph = build_graph(
                mcp_tools=app.state.mcp_tools, checkpointer=checkpointer
            )
            logger.info("Operator graph compiled with Redis checkpointer.")
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
app.include_router(auth_router)  # Include the auth router for login endpoint
app.include_router(chat_router)  # Include the chat router for chat endpoint

FastAPIInstrumentor.instrument_app(app, excluded_urls="/health")


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "ok", "version": "1.0.0"}
