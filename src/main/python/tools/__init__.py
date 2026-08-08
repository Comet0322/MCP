import importlib
import pkgutil

from fastmcp import FastMCP


def _iter_tool_modules():
    for module_info in pkgutil.iter_modules(__path__, prefix=f"{__name__}."):
        yield importlib.import_module(module_info.name)


def register_all(mcp: FastMCP) -> None:
    """Import every sibling tool module and let it register itself.

    A module opts in by exposing a `register(mcp: FastMCP) -> None` function.
    Modules without one (helpers, shared utilities) are imported but skipped.
    """
    for module in _iter_tool_modules():
        register = getattr(module, "register", None)
        if register is not None:
            register(mcp)


def contract_invalid_cases() -> dict[str, dict]:
    """tool_name -> known-invalid arguments the tool must reject via the unified ToolError format.

    A tool module opts in by declaring both CONTRACT_TOOL_NAME and
    CONTRACT_INVALID_CASE. test_contract.py uses this registry to verify
    every registered tool actually exercises errors.py instead of letting
    an unhandled traceback reach the caller.
    """
    cases: dict[str, dict] = {}
    for module in _iter_tool_modules():
        name = getattr(module, "CONTRACT_TOOL_NAME", None)
        case = getattr(module, "CONTRACT_INVALID_CASE", None)
        if name is not None and case is not None:
            cases[name] = case
    return cases
