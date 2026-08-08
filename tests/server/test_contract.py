"""Layer: does the MCP server itself work correctly? (server/ group)

Universal checks every registered tool must pass, regardless of who calls
it. Leans "unit" -- everything here runs against the in-memory Client, no
network or docker involved.
"""

import pytest
from fastmcp.exceptions import ToolError

from src.main.python.errors import ToolErrorPayload
from src.main.python.tools import contract_invalid_cases


async def test_every_tool_has_a_valid_schema(client):
    tools = await client.list_tools()
    assert tools, "no tools registered"
    for tool in tools:
        schema = tool.inputSchema
        assert isinstance(schema, dict)
        assert schema.get("type") == "object"
        properties = schema.get("properties", {})
        assert isinstance(properties, dict)
        for required_name in schema.get("required", []):
            assert required_name in properties, (
                f"{tool.name}: required field '{required_name}' is not declared in properties"
            )


async def test_every_tool_description_is_substantial(client):
    tools = await client.list_tools()
    for tool in tools:
        assert tool.description, f"{tool.name} has no description"
        assert len(tool.description) >= 20, (
            f"{tool.name} description is only {len(tool.description)} chars, need >= 20"
        )


async def test_every_tool_parameter_has_a_description(client):
    tools = await client.list_tools()
    for tool in tools:
        properties = tool.inputSchema.get("properties", {})
        for param_name, param_schema in properties.items():
            assert param_schema.get("description"), f"{tool.name}.{param_name} has no description"


async def test_every_tool_declares_a_contract_invalid_case(client):
    tools = await client.list_tools()
    cases = contract_invalid_cases()
    missing = [tool.name for tool in tools if tool.name not in cases]
    assert not missing, (
        f"tools missing a CONTRACT_INVALID_CASE declaration: {missing}. "
        "See docs/TOOL_GUIDELINES.md."
    )


@pytest.mark.parametrize("tool_name,invalid_args", list(contract_invalid_cases().items()))
async def test_invalid_input_returns_unified_error_format(client, tool_name, invalid_args):
    with pytest.raises(ToolError) as exc_info:
        await client.call_tool(tool_name, invalid_args)

    # This is the actual assertion: it must parse as our unified shape, not
    # an unhandled traceback bubbling up as a plain string.
    payload = ToolErrorPayload.model_validate_json(str(exc_info.value))
    assert payload.code
    assert payload.message
