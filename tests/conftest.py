import pytest
from fastmcp import Client, FastMCP

from src.main.python.main import mcp as _mcp


@pytest.fixture
def mcp() -> FastMCP:
    return _mcp


@pytest.fixture
async def client(mcp: FastMCP):
    async with Client(mcp) as c:
        yield c
