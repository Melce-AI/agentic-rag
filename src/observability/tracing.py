import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from src.core.config import get_settings

logger = logging.getLogger(__name__)


def setup_tracing() -> None:
    settings = get_settings()
    if not settings.otel_enabled:
        logger.info("OpenTelemetry tracing is disabled.")
        return

    resource = Resource.create({
        "service.name": settings.otel_service_name,
        "service.version": settings.version,
        "deployment.environment": settings.environment,
    })
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces",
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    logger.info(
        "OpenTelemetry tracing initialized.",
        extra={"otlp_endpoint": settings.otel_exporter_otlp_endpoint},
    )


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)
