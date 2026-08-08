import logging
import sys

import structlog
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from src.main.python.auth import build_auth_provider
from src.main.python.config import settings
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

mcp = FastMCP(name="my-mcp-template", auth=build_auth_provider())
register_all(mcp)


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


def main() -> None:
    log.info(
        "starting_server",
        host=settings.HOST,
        port=settings.PORT,
        env=settings.ENV,
        auth_enabled=settings.AUTH_ENABLED,
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
