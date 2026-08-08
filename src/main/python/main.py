import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastmcp import FastMCP
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

from src.main.python.config import settings
from src.main.python.observability import (
    ToolMetricsMiddleware,
    configure_langfuse_tracing,
    configure_prometheus_metrics,
)
from src.main.python.tools import register_all


def configure_logging() -> None:
    renderer = (
        structlog.dev.ConsoleRenderer()
        if settings.ENV == "dev"
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
    )
    logging.basicConfig(level=settings.LOG_LEVEL, stream=sys.stdout)


configure_logging()
log = structlog.get_logger()

_tracer_provider = configure_langfuse_tracing()
_metrics_registry = configure_prometheus_metrics()


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
    try:
        yield
    finally:
        if _tracer_provider is not None:
            _tracer_provider.shutdown()  # flushes buffered spans, then stops the exporter


mcp = FastMCP(name="my-mcp-template", lifespan=lifespan)
mcp.add_middleware(ToolMetricsMiddleware())
register_all(mcp)


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


@mcp.custom_route("/metrics", methods=["GET"])
async def metrics_endpoint(_request: Request) -> Response:
    return Response(generate_latest(_metrics_registry), media_type=CONTENT_TYPE_LATEST)


def main() -> None:
    log.info(
        "starting_server",
        host=settings.HOST,
        port=settings.PORT,
        env=settings.ENV,
        langfuse_enabled=settings.langfuse_enabled,
    )
    mcp.run(
        transport="streamable-http",
        host=settings.HOST,
        port=settings.PORT,
        stateless_http=True,
        allowed_origins=settings.allowed_origins_list or None,
    )


if __name__ == "__main__":
    main()
