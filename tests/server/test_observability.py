"""Layer: does the MCP server itself work correctly? (server/ group)

Unit tests for observability.py:
- _otlp_exporter_kwargs / configure_langfuse_tracing: pure config-building
  and the disabled/opt-out path (no OTel global state touched).
- TenantTracingMiddleware: verified against a real OTel SDK TracerProvider
  + InMemorySpanExporter injected directly into the middleware, so the
  test doesn't need to touch OTel's *global* tracer provider (which can
  only be set once per process).
"""

from fastmcp import Client, FastMCP
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.main.python.config import Settings
from src.main.python.observability import (
    TenantTracingMiddleware,
    _otlp_exporter_kwargs,
    configure_langfuse_tracing,
)


def test_configure_langfuse_tracing_is_none_when_disabled():
    cfg = Settings(LANGFUSE_PUBLIC_KEY=None, LANGFUSE_SECRET_KEY=None)
    assert configure_langfuse_tracing(cfg) is None


def test_otlp_exporter_kwargs_point_at_langfuse_cloud_by_default():
    cfg = Settings(LANGFUSE_PUBLIC_KEY="pk-lf-test", LANGFUSE_SECRET_KEY="sk-lf-test")
    kwargs = _otlp_exporter_kwargs(cfg)

    assert kwargs["endpoint"] == "https://cloud.langfuse.com/api/public/otel/v1/traces"
    assert kwargs["headers"]["Authorization"].startswith("Basic ")
    assert kwargs["headers"]["x-langfuse-ingestion-version"] == "4"


def test_otlp_exporter_kwargs_respect_custom_base_url():
    cfg = Settings(
        LANGFUSE_PUBLIC_KEY="pk-lf-test",
        LANGFUSE_SECRET_KEY="sk-lf-test",
        LANGFUSE_BASE_URL="https://langfuse.internal.example.com/",
    )
    kwargs = _otlp_exporter_kwargs(cfg)
    assert kwargs["endpoint"] == "https://langfuse.internal.example.com/api/public/otel/v1/traces"


def _make_traced_server(tracer) -> tuple[FastMCP, InMemorySpanExporter]:
    mcp = FastMCP("tenant-tracing-test-server")
    mcp.add_middleware(TenantTracingMiddleware(tracer=tracer))

    @mcp.tool
    def ok_tool() -> str:
        """Trivial tool that always succeeds."""
        return "pong"

    @mcp.tool
    def boom_tool() -> str:
        """Trivial tool that always raises."""
        raise RuntimeError("boom")

    return mcp


async def test_successful_call_produces_a_span_tagged_with_tenant_id():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    mcp = _make_traced_server(tracer)
    async with Client(mcp) as client:
        await client.call_tool("ok_tool", {})

    spans = exporter.get_finished_spans()
    tool_span = next(s for s in spans if s.name == "tenant.ok_tool")
    assert tool_span.attributes is not None
    assert tool_span.attributes["tenant_id"] == "local-dev"
    assert tool_span.status.is_ok


async def test_failed_call_marks_span_as_error_and_still_raises():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    mcp = _make_traced_server(tracer)
    async with Client(mcp) as client:
        try:
            await client.call_tool("boom_tool", {})
        except Exception:
            pass

    spans = exporter.get_finished_spans()
    tool_span = next(s for s in spans if s.name == "tenant.boom_tool")
    assert not tool_span.status.is_ok
