"""Layer: does the MCP server itself work correctly? (server/ group)

Universal checks every registered tool must pass, regardless of who calls
it. Leans "unit" -- everything here runs against the in-memory Client, no
network or docker involved.
"""

import pytest
from fastmcp.exceptions import ToolError

from src.main.python.errors import ToolErrorPayload
from src.main.python.tools import contract_invalid_cases
from tests.server.contract_checks import (
    check_declares_contract_case,
    check_description_substantial,
    check_param_descriptions,
    check_valid_schema,
)


async def test_every_tool_has_a_valid_schema(client):
    tools = await client.list_tools()
    assert tools, "no tools registered"
    for tool in tools:
        check_valid_schema(tool)


async def test_every_tool_description_is_substantial(client):
    tools = await client.list_tools()
    for tool in tools:
        check_description_substantial(tool)


async def test_every_tool_parameter_has_a_description(client):
    tools = await client.list_tools()
    for tool in tools:
        check_param_descriptions(tool)


async def test_every_tool_declares_a_contract_invalid_case(client):
    tools = await client.list_tools()
    cases = contract_invalid_cases()
    for tool in tools:
        check_declares_contract_case(tool.name, cases)


@pytest.mark.parametrize("tool_name,invalid_args", list(contract_invalid_cases().items()))
async def test_invalid_input_returns_unified_error_format(client, tool_name, invalid_args):
    with pytest.raises(ToolError) as exc_info:
        await client.call_tool(tool_name, invalid_args)

    # This is the actual assertion: it must parse as our unified shape, not
    # an unhandled traceback bubbling up as a plain string.
    payload = ToolErrorPayload.model_validate_json(str(exc_info.value))
    assert payload.code
    assert payload.message
