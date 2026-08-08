"""Layer: does the MCP server itself work correctly? (server/ group)

Exercises fetch_json_tool.py's tenacity retry logic against a local
scripted HTTP server -- no real network dependency, deterministic. Proves
out the "external call" class of tool (as opposed to example_tool.py's
pure logic) and the tenacity usage the tech stack calls for.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastmcp.exceptions import ToolError

from src.main.python.errors import ToolErrorPayload


class ScriptedServer:
    """Serves one scripted (status, body) response per request received."""

    def __init__(self, responses: list[tuple[int, dict]]):
        self._responses = list(responses)
        self.request_count = 0
        self.url = ""
        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> str:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                outer.request_count += 1
                status, body = outer._responses.pop(0) if outer._responses else (500, {})
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                pass

        self._httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        self.url = f"http://127.0.0.1:{self._httpd.server_port}/"
        return self.url

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()


@pytest.fixture
def scripted_server():
    servers: list[ScriptedServer] = []

    def _make(responses: list[tuple[int, dict]]) -> ScriptedServer:
        server = ScriptedServer(responses)
        server.start()
        servers.append(server)
        return server

    yield _make
    for server in servers:
        server.stop()


async def test_retries_transient_failures_then_succeeds(client, scripted_server):
    server = scripted_server([(500, {}), (500, {}), (200, {"ok": True})])

    result = await client.call_tool("fetch_json", {"url": server.url})

    assert result.data["status_code"] == 200
    assert result.data["body"] == {"ok": True}
    assert server.request_count == 3


async def test_exhausts_retries_and_raises_recoverable_upstream_error(client, scripted_server):
    server = scripted_server([(500, {}), (500, {}), (500, {})])

    with pytest.raises(ToolError) as exc_info:
        await client.call_tool("fetch_json", {"url": server.url})

    payload = ToolErrorPayload.model_validate_json(str(exc_info.value))
    assert payload.code == "UPSTREAM_ERROR"
    assert payload.recoverable is True
    assert server.request_count == 3  # stop_after_attempt(3), not retried forever


async def test_client_error_fails_immediately_without_retrying(client, scripted_server):
    server = scripted_server([(404, {"error": "not found"})])

    with pytest.raises(ToolError) as exc_info:
        await client.call_tool("fetch_json", {"url": server.url})

    payload = ToolErrorPayload.model_validate_json(str(exc_info.value))
    assert payload.code == "UPSTREAM_ERROR"
    assert payload.recoverable is False
    assert server.request_count == 1  # a 4xx is not retryable, must not be retried


async def test_invalid_url_is_rejected_without_any_network_call(client):
    with pytest.raises(ToolError) as exc_info:
        await client.call_tool("fetch_json", {"url": "not-a-valid-url"})
    payload = ToolErrorPayload.model_validate_json(str(exc_info.value))
    assert payload.code == "VALIDATION_ERROR"
    assert payload.recoverable is False
