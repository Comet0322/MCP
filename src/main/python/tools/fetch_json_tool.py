import httpx
from fastmcp import FastMCP
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.main.python.auth import get_current_identity
from src.main.python.errors import raise_tool_error


def register(mcp: FastMCP) -> None:
    mcp.tool(fetch_json)


# Contract: test_contract.py requires every tool to declare a known-invalid
# input it rejects via the unified ToolError format (see errors.py).
CONTRACT_TOOL_NAME = "fetch_json"
CONTRACT_INVALID_CASE = {"url": "not-a-valid-url"}


class _TransientFetchError(Exception):
    """Internal signal for tenacity: retry on this, nothing else."""


@retry(
    retry=retry_if_exception_type(_TransientFetchError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.05, max=1),
    reraise=True,
)
async def _get_with_retry(client: httpx.AsyncClient, url: str) -> httpx.Response:
    try:
        response = await client.get(url)
    except httpx.TransportError as exc:
        raise _TransientFetchError(str(exc)) from exc
    if response.status_code >= 500:
        raise _TransientFetchError(f"upstream returned {response.status_code}")
    return response


async def fetch_json(url: str) -> dict:
    """Fetch JSON from an external HTTP endpoint, retrying on transient failures.

    Represents the "external call" class of tool (DB queries, third-party
    APIs, ...) as opposed to example_tool.py's pure logic. Connection errors
    and 5xx responses are retried up to 3 times with exponential backoff
    (tenacity); an invalid URL or a 4xx response fails immediately since
    retrying it wouldn't help.

    Args:
        url: The absolute URL to fetch JSON from. Must start with http://
            or https://.

    Returns:
        A dict with `status_code` (int), `body` (the parsed JSON payload),
        and `requested_by` (str, the caller's tenant id).
    """
    if not url.startswith(("http://", "https://")):
        raise_tool_error(
            "VALIDATION_ERROR",
            "`url` must start with http:// or https://.",
            recoverable=False,
        )

    identity = get_current_identity()

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await _get_with_retry(client, url)
    except _TransientFetchError as exc:
        raise_tool_error(
            "UPSTREAM_ERROR",
            f"Upstream did not respond successfully after retries: {exc}",
            recoverable=True,
        )

    if response.status_code >= 400:
        raise_tool_error(
            "UPSTREAM_ERROR",
            f"Upstream returned {response.status_code}: {response.text[:200]}",
            recoverable=False,
        )

    return {
        "status_code": response.status_code,
        "body": response.json(),
        "requested_by": identity.tenant_id,
    }
