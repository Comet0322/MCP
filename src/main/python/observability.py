import base64

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp.types import CallToolRequestParams
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode

from src.main.python.auth import get_current_identity
from src.main.python.config import Settings, settings


def _otlp_exporter_kwargs(cfg: Settings) -> dict:
    """Pure helper: builds the OTLPSpanExporter endpoint/headers for Langfuse.

    Split out from configure_langfuse_tracing() so the endpoint/auth-header
    construction is testable without touching OTel's global tracer provider
    (which, by API design, can only be set once per process).
    """
    assert cfg.LANGFUSE_PUBLIC_KEY is not None and cfg.LANGFUSE_SECRET_KEY is not None
    credentials = f"{cfg.LANGFUSE_PUBLIC_KEY}:{cfg.LANGFUSE_SECRET_KEY.get_secret_value()}"
    auth_header = base64.b64encode(credentials.encode()).decode()
    return {
        "endpoint": f"{cfg.LANGFUSE_BASE_URL.rstrip('/')}/api/public/otel/v1/traces",
        "headers": {
            "Authorization": f"Basic {auth_header}",
            "x-langfuse-ingestion-version": "4",
        },
    }


def configure_langfuse_tracing(cfg: Settings = settings) -> TracerProvider | None:
    """Wires FastMCP's built-in OpenTelemetry instrumentation to Langfuse.

    FastMCP already emits an OTel span (tool/resource/prompt name, auth,
    session id, exceptions -- see fastmcp.server.telemetry) for every call.
    This just points a standard OTel SDK TracerProvider at Langfuse's OTLP
    endpoint so those spans get exported there; no per-tool tracing code
    needed. Opt-in: returns None (tracer stays a no-op) unless both keys
    are set. Call once at startup, before the FastMCP instance is created.
    """
    if not cfg.langfuse_enabled:
        return None

    exporter = OTLPSpanExporter(**_otlp_exporter_kwargs(cfg))
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return provider


class TenantTracingMiddleware(Middleware):
    """Wraps every tool call in its own span, tagged with the caller's tenant_id.

    FastMCP's own OTel instrumentation (fastmcp.server.telemetry) already
    creates a "tools/call" span per call, but empirically it's created
    *inside* call_next(), in a context this middleware's on_call_tool can't
    reach -- trace.get_current_span() before or after call_next() is not
    that span (verified: neither is a valid/recording span at that point).
    So rather than trying to tag a span we can't actually reach, this opens
    its own span around call_next(). It shows up alongside FastMCP's native
    span in Langfuse, not nested under it.
    """

    def __init__(self, tracer: trace.Tracer | None = None) -> None:
        # Injectable for tests, so they don't have to touch OTel's global
        # tracer provider (which can only be set once per process).
        self._tracer = tracer or trace.get_tracer("my-mcp-template.tenant")

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        tool_name = context.message.name
        try:
            tenant_id = get_current_identity().tenant_id
        except Exception:
            tenant_id = "unknown"

        with self._tracer.start_as_current_span(
            f"tenant.{tool_name}", attributes={"tenant_id": tenant_id}
        ) as span:
            try:
                return await call_next(context)
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
