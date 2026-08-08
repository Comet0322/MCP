from fastmcp import FastMCP

from src.main.python.auth import get_current_identity
from src.main.python.errors import raise_tool_error


def register(mcp: FastMCP) -> None:
    mcp.tool(word_count)


# Contract: test_contract.py requires every tool to declare a known-invalid
# input it rejects via the unified ToolError format (see errors.py).
CONTRACT_TOOL_NAME = "word_count"
CONTRACT_INVALID_CASE = {"text": "   "}


async def word_count(text: str) -> dict:
    """Count the words in a piece of text and report who asked.

    This is a pure-logic example: it demonstrates the unified ToolError
    format (triggered on empty input) and how to read the caller's
    identity via get_current_identity(). It does not read or write any
    files -- see docs/TOOL_GUIDELINES.md if your tool needs to.

    Args:
        text: The text to count words in. Must contain at least one
            non-whitespace character.

    Returns:
        A dict with `word_count` (int, number of whitespace-separated
        words) and `requested_by` (str, the caller's tenant id).
    """
    stripped = text.strip()
    if not stripped:
        raise_tool_error(
            "VALIDATION_ERROR",
            "`text` must contain at least one non-whitespace character.",
            recoverable=False,
        )

    identity = get_current_identity()
    return {"word_count": len(stripped.split()), "requested_by": identity.tenant_id}
