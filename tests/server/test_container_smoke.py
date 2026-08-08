"""Layer: does the MCP server itself work correctly? (server/ group)

marker: slow. A real integration/system test -- builds and runs the actual
container via `docker compose`, then talks to it over streamable HTTP.
Verifies the pieces that unit tests can't: Dockerfile, entrypoint.sh,
docker-compose.yml, and config wiring actually work together. Auth
verification *logic* is already covered by test_auth.py; this only checks
that AUTH_ENABLED=true is correctly enforced end-to-end.
"""

import shutil
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from tests.server.auth.mock_jwks import MockJWKSServer

pytestmark = pytest.mark.slow

REPO_ROOT = Path(__file__).parent.parent.parent
BASE_URL = "http://127.0.0.1:8000"
MCP_URL = f"{BASE_URL}/mcp"

TEST_ISSUER = "https://mock-idp.test"
TEST_AUDIENCE = "my-mcp-template"
TEST_TENANT_CLAIM = "tid"


def _wait_for_health(timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{BASE_URL}/health", timeout=2.0)
            if response.status_code == 200:
                return
        except httpx.HTTPError as e:
            last_error = e
        time.sleep(1)
    raise TimeoutError(f"server did not become healthy in time (last error: {last_error})")


@pytest.fixture(scope="module")
def running_container():
    jwks = MockJWKSServer()
    jwks_url = jwks.start(bind_host="0.0.0.0", advertise_host="host.docker.internal")

    env_path = REPO_ROOT / ".env"
    backup_path = REPO_ROOT / ".env.smoke-backup"
    had_existing_env = env_path.exists()
    if had_existing_env:
        shutil.move(env_path, backup_path)

    env_path.write_text(
        "HOST=0.0.0.0\n"
        "PORT=8000\n"
        "ENV=dev\n"
        "AUTH_ENABLED=true\n"
        f"OIDC_ISSUER={TEST_ISSUER}\n"
        f"JWKS_URL={jwks_url}\n"
        f"AUDIENCE={TEST_AUDIENCE}\n"
        f"TENANT_CLAIM_NAME={TEST_TENANT_CLAIM}\n"
    )

    try:
        subprocess.run(
            ["docker", "compose", "up", "-d", "--build"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        _wait_for_health()
        yield jwks
    finally:
        subprocess.run(
            ["docker", "compose", "down", "-v"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        jwks.stop()
        env_path.unlink(missing_ok=True)
        if had_existing_env:
            shutil.move(backup_path, env_path)


async def test_health_endpoint_reachable(running_container):
    response = httpx.get(f"{BASE_URL}/health")
    assert response.status_code == 200


async def test_list_tools_and_call_example_tool_over_streamable_http(running_container):
    jwks = running_container
    token = jwks.issue_token(
        issuer=TEST_ISSUER,
        audience=TEST_AUDIENCE,
        claims={TEST_TENANT_CLAIM: "tenant-smoke"},
    )
    transport = StreamableHttpTransport(url=MCP_URL, headers={"Authorization": f"Bearer {token}"})
    async with Client(transport) as client:
        tools = await client.list_tools()
        assert any(t.name == "word_count" for t in tools)

        result = await client.call_tool("word_count", {"text": "smoke test words"})
        assert result.data["word_count"] == 3


async def test_metrics_endpoint_reflects_the_call_above(running_container):
    # Runs after test_list_tools_and_call_example_tool_over_streamable_http
    # in the same module-scoped container -- confirms /metrics is reachable
    # and reflects real tool-call traffic, not just that it returns 200.
    response = httpx.get(f"{BASE_URL}/metrics")
    assert response.status_code == 200
    assert "mcp_tool_calls_total{" in response.text
    assert 'tool="word_count"' in response.text


async def test_call_without_token_is_rejected(running_container):
    transport = StreamableHttpTransport(url=MCP_URL)
    with pytest.raises(Exception):  # noqa: B017 -- exact type is transport-level (httpx/mcp), just needs to fail
        async with Client(transport) as client:
            await client.list_tools()
