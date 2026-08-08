"""Assertion bodies shared by test_contract.py and test_contract_self_check.py.

Pulled out so the self-check test can run the exact same checks against a
deliberately broken tool instead of duplicating (and risking drift from) the
real assertion logic.
"""


def check_valid_schema(tool) -> None:
    schema = tool.inputSchema
    assert isinstance(schema, dict)
    assert schema.get("type") == "object"
    properties = schema.get("properties", {})
    assert isinstance(properties, dict)
    for required_name in schema.get("required", []):
        assert required_name in properties, (
            f"{tool.name}: required field '{required_name}' is not declared in properties"
        )


def check_description_substantial(tool) -> None:
    assert tool.description, f"{tool.name} has no description"
    assert len(tool.description) >= 20, (
        f"{tool.name} description is only {len(tool.description)} chars, need >= 20"
    )


def check_param_descriptions(tool) -> None:
    properties = tool.inputSchema.get("properties", {})
    for param_name, param_schema in properties.items():
        assert param_schema.get("description"), f"{tool.name}.{param_name} has no description"


def check_declares_contract_case(tool_name: str, cases: dict) -> None:
    assert tool_name in cases, (
        f"{tool_name} missing a CONTRACT_INVALID_CASE declaration. See docs/TOOL_GUIDELINES.md."
    )
