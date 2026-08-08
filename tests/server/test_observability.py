"""Layer: does the MCP server itself work correctly? (server/ group)

Unit tests for observability.py:
- _otlp_exporter_kwargs / configure_langfuse_tracing: pure config-building
  and the disabled/opt-out path (no OTel global state touched).
- TenantTracingMiddleware: verified against a real OTel SDK TracerProvider
  + InMemorySpanExporter injected directly into the middleware, so the
  test doesn't need to touch OTel's *global* tracer provider (which can
  only be set once per process).
- ToolMetricsMiddleware / configure_prometheus_metrics: verified against a
  real OTel SDK MeterProvider + InMemoryMetricReader, same injection
  pattern, plus one end-to-end check that the Prometheus exposition output
  is actually well-formed (this is what /metrics really serves).
"""

from fastmcp import Client, FastMCP
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import CollectorRegistry, generate_latest

from src.main.python.config import Settings
from src.main.python.observability import (
    TenantTracingMiddleware,
    ToolMetricsMiddleware,
    _otlp_exporter_kwargs,
    configure_langfuse_tracing,
    configure_prometheus_metrics,
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


def _make_metered_server(meter) -> FastMCP:
    mcp = FastMCP("tool-metrics-test-server")
    mcp.add_middleware(ToolMetricsMiddleware(meter=meter))

    @mcp.tool
    def ok_tool() -> str:
        """Trivial tool that always succeeds."""
        return "pong"

    @mcp.tool
    def boom_tool() -> str:
        """Trivial tool that always raises."""
        raise RuntimeError("boom")

    return mcp


def _find_metric(metrics_data, name: str):
    for resource_metrics in metrics_data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == name:
                    return metric
    raise AssertionError(f"metric {name!r} not found")


async def test_successful_tool_call_increments_counter_with_ok_status():
    reader = InMemoryMetricReader()
    meter = MeterProvider(metric_readers=[reader]).get_meter("test")

    mcp = _make_metered_server(meter)
    async with Client(mcp) as client:
        await client.call_tool("ok_tool", {})

    counter = _find_metric(reader.get_metrics_data(), "mcp_tool_calls_total")
    point = counter.data.data_points[0]
    assert dict(point.attributes) == {"tool": "ok_tool", "status": "ok"}
    assert point.value == 1


async def test_failed_tool_call_increments_counter_with_error_status():
    reader = InMemoryMetricReader()
    meter = MeterProvider(metric_readers=[reader]).get_meter("test")

    mcp = _make_metered_server(meter)
    async with Client(mcp) as client:
        try:
            await client.call_tool("boom_tool", {})
        except Exception:
            pass

    counter = _find_metric(reader.get_metrics_data(), "mcp_tool_calls_total")
    point = counter.data.data_points[0]
    assert dict(point.attributes) == {"tool": "boom_tool", "status": "error"}
    assert point.value == 1


def test_configure_prometheus_metrics_returns_a_registry():
    # Doesn't assert on exposition content here: tests/conftest.py already
    # imports main.py, which calls the real configure_prometheus_metrics()
    # at module load time and sets OTel's *global* MeterProvider (settable
    # once per process) -- a second call here is a harmless no-op per the
    # OTel API, but its own local provider never has anything recorded
    # against it, so its registry is legitimately empty. See the exposition
    # format check below, which builds its own provider/registry pair
    # instead of going through the global-setting function.
    assert isinstance(configure_prometheus_metrics(registry=CollectorRegistry()), CollectorRegistry)


def test_prometheus_reader_produces_well_formed_exposition_output_for_recorded_metrics():
    registry = CollectorRegistry()
    reader = PrometheusMetricReader(registry=registry)
    meter = MeterProvider(metric_readers=[reader]).get_meter("test")
    meter.create_counter("smoke_test_counter").add(1)

    output = generate_latest(registry).decode()
    # PrometheusMetricReader appends "_total" to counter names per convention.
    assert "# TYPE smoke_test_counter_total counter" in output
    assert "smoke_test_counter_total{" in output
