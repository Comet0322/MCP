"""Mutation-testing-style self-check for test_contract.py.

The checks in test_contract.py had only ever been observed passing on
well-formed tools -- nobody had confirmed they actually fail on a real
violation. This file deliberately constructs broken tools/schemas and
asserts the checks catch them.
"""

from dataclasses import dataclass

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import ValidationError

from src.main.python.errors import ToolErrorPayload
from tests.server.contract_checks import (
    check_declares_contract_case,
    check_description_substantial,
    check_param_descriptions,
    check_valid_schema,
)


@dataclass
class FakeTool:
    name: str
    description: str
    inputSchema: dict


def test_required_field_missing_from_properties_is_caught():
    broken = FakeTool(
        name="broken",
        description="a tool whose required field isn't declared in properties",
        inputSchema={"type": "object", "properties": {}, "required": ["text"]},
    )
    with pytest.raises(AssertionError):
        check_valid_schema(broken)


def test_short_description_is_caught():
    broken = FakeTool(name="broken", description="too short", inputSchema={"type": "object"})
    with pytest.raises(AssertionError):
        check_description_substantial(broken)


def test_missing_param_description_is_caught():
    broken = FakeTool(
        name="broken",
        description="a tool whose parameter has no description",
        inputSchema={"type": "object", "properties": {"text": {"type": "string"}}},
    )
    with pytest.raises(AssertionError):
        check_param_descriptions(broken)


def test_undeclared_contract_case_is_caught():
    with pytest.raises(AssertionError):
        check_declares_contract_case("undeclared_tool", {"other_tool": {}})


async def test_unhandled_exception_does_not_pass_as_unified_error_format():
    """A tool that raises a plain exception instead of raise_tool_error()
    must fail the same payload-parsing assertion test_contract.py uses --
    proving that check would catch the regression, not silently pass it.
    """
    mcp = FastMCP("broken")

    @mcp.tool
    def broken_tool(text: str) -> dict:
        """A tool that forgets to use the unified ToolError format."""
        if not text.strip():
            raise ValueError("text must not be blank")
        return {"ok": True}

    async with Client(mcp) as client:
        with pytest.raises(ToolError) as exc_info:
            await client.call_tool("broken_tool", {"text": "   "})

        with pytest.raises(ValidationError):
            ToolErrorPayload.model_validate_json(str(exc_info.value))
