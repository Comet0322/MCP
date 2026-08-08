from typing import Any, Literal

from fastmcp.exceptions import ToolError
from pydantic import BaseModel

ErrorCode = Literal[
    "VALIDATION_ERROR",
    "NOT_FOUND",
    "AUTH_ERROR",
    "UPSTREAM_ERROR",
    "INTERNAL_ERROR",
]


class ToolErrorPayload(BaseModel):
    """Unified error shape surfaced to the calling agent.

    `recoverable` tells the agent whether retrying the same call could
    plausibly succeed (e.g. a transient upstream timeout) versus whether
    retrying is pointless without changing the input or the environment
    (e.g. a validation error, an expired auth token).
    """

    code: ErrorCode
    message: str
    recoverable: bool
    details: dict[str, Any] | None = None


def raise_tool_error(
    code: ErrorCode,
    message: str,
    *,
    recoverable: bool,
    details: dict[str, Any] | None = None,
) -> None:
    payload = ToolErrorPayload(code=code, message=message, recoverable=recoverable, details=details)
    raise ToolError(payload.model_dump_json())
