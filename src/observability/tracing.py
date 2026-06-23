import asyncio
import functools
import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import StatusCode
from openinference.instrumentation.langchain import LangChainInstrumentor

from src.core.config import get_settings

logger = logging.getLogger(__name__)


def setup_tracing() -> None:
    settings = get_settings()
    if not settings.otel_enabled:
        logger.info("OpenTelemetry tracing is disabled.")
        return

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": settings.version,
            "deployment.environment": settings.environment,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces",
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    # Instrument LangChain/LangGraph AFTER the provider is set, binding to it
    # explicitly. This is what gives Phoenix named spans for each node, LLM
    # call, retriever and tool — without it the trace lands but is unnamed.
    LangChainInstrumentor().instrument(tracer_provider=provider)
    logger.info(
        "OpenTelemetry tracing initialized.",
        extra={"otlp_endpoint": settings.otel_exporter_otlp_endpoint},
    )


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


def traced(span_name: str, span_kind: str | None = None):
    """Wraps an async or sync method in a span. Errors are recorded automatically."""

    def decorator(fn):
        tracer = get_tracer(fn.__module__)

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name) as span:
                if span_kind:
                    span.set_attribute("openinference.span.kind", span_kind)
                try:
                    result = await fn(*args, **kwargs)
                    span.set_status(StatusCode.OK)
                    return result
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(StatusCode.ERROR, str(exc))
                    raise

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name) as span:
                if span_kind:
                    span.set_attribute("openinference.span.kind", span_kind)
                try:
                    result = fn(*args, **kwargs)
                    span.set_status(StatusCode.OK)
                    return result
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(StatusCode.ERROR, str(exc))
                    raise

        return async_wrapper if asyncio.iscoroutinefunction(fn) else sync_wrapper

    return decorator
