"""Layer: full multi-turn agent E2E (agent/ group)

Layer 3 in docs/TESTING.md's ladder -- the one test_tool_selection.py's old
filename (test_agent_e2e.py) claimed to be and wasn't. Drives this repo's
own MCP server through a real multi-turn Claude Agent SDK session: user
prompt in, real agent tool-call decisions, a second turn that depends on
the first turn's context being retained, real output out. Crosses the
system boundary into a component this template doesn't own (the Claude
Agent SDK harness, i.e. what Claude Code itself runs on).

This is deliberately NOT wired into the default dev loop:

- **New optional dependency** (`agent-sdk` group: `uv sync --group agent-sdk`)
  -- `claude-agent-sdk`, separate from `eval` (deepeval) and `dev`.
- **Needs the Claude Code CLI installed** (https://code.claude.com) --
  `claude-agent-sdk` shells out to the `claude` binary; it isn't a pure
  Python client. `shutil.which("claude")` gates this file.
- **Claude-only, not provider-agnostic.** Unlike test_tool_selection.py
  (deliberately made provider-agnostic -- see docs/STATUS.md), this is
  categorically Claude Agent SDK, which only drives Claude. That's not a
  gap to fix; it's what this layer *is*.
- **Auth is whatever the CLI already has** (`ANTHROPIC_API_KEY`, or a
  logged-in `claude`/`ant` session) -- not a new setting in config.py, so
  this template doesn't grow an auth surface just for an optional test.

marker: slow -- spins up this repo's own MCP server on a real TCP port
(not the in-memory Client the rest of tests/server/ uses -- the Claude
Agent SDK connects over real HTTP from an OS subprocess) and makes real
Claude API calls through the CLI.
"""

import asyncio
import shutil

import httpx
import pytest

from src.main.python.main import mcp as _mcp

pytestmark = pytest.mark.slow

HOST = "127.0.0.1"
PORT = 8765
BASE_URL = f"http://{HOST}:{PORT}"
MCP_URL = f"{BASE_URL}/mcp"


async def _wait_for_health(timeout: float = 15.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    async with httpx.AsyncClient() as http:
        while asyncio.get_event_loop().time() < deadline:
            try:
                response = await http.get(f"{BASE_URL}/health", timeout=1.0)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.2)
    raise TimeoutError("server did not become healthy in time")


@pytest.fixture
async def running_server():
    """Runs this repo's real MCP server on a real TCP port, in-process.

    Not the in-memory fastmcp.Client the rest of tests/server/ uses -- the
    Claude Agent SDK's `claude` CLI subprocess needs an actual HTTP
    endpoint to connect to, the same way any real MCP client would.
    """
    task = asyncio.create_task(
        _mcp.run_async(
            transport="streamable-http",
            host=HOST,
            port=PORT,
            stateless_http=True,
            show_banner=False,
        )
    )
    try:
        await _wait_for_health()
        yield MCP_URL
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


async def test_multiturn_session_retains_context_across_tool_calls(running_server):
    if shutil.which("claude") is None:
        pytest.skip("Claude Code CLI not installed -- see https://code.claude.com")

    try:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ClaudeSDKClient,
            ResultMessage,
            ToolUseBlock,
        )
    except ImportError:
        pytest.skip("claude-agent-sdk not installed -- run `uv sync --group agent-sdk`")

    # MCP tools are namespaced by the Agent SDK as mcp__<server-name>__<tool-name>.
    mcp_word_count = "mcp__my-mcp-template__word_count"
    options = ClaudeAgentOptions(
        system_prompt="You are a helpful assistant with access to word-counting tools.",
        mcp_servers={"my-mcp-template": {"type": "http", "url": running_server}},
        allowed_tools=[mcp_word_count],
    )

    async def _run_turn(client: "ClaudeSDKClient", prompt: str) -> tuple[set[str], str]:
        await client.query(prompt)
        called: set[str] = set()
        final_text = ""
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        called.add(block.name)
            elif isinstance(message, ResultMessage):
                final_text = message.result or ""
        return called, final_text

    # Real environment/auth issues (CLI not logged in, no network) surface
    # here as SDK-internal exceptions with no documented type to catch by
    # name -- treat any of them as "this optional layer isn't set up", same
    # spirit as the ImportError skip above, not a real test failure. Only
    # the connection/query mechanics are wrapped -- assertions run outside
    # this block so a real wrong-answer failure is never mistaken for a
    # setup problem and silently skipped.
    try:
        async with ClaudeSDKClient(options=options) as client:
            called_1, text_1 = await _run_turn(
                client, "Count how many words are in this sentence: 'the quick brown fox jumps'"
            )
            # Second turn, same session -- proves context (not just the
            # tool result) carries across turns, not just repeatable
            # single-shot tool selection (that's what test_tool_selection.py
            # already covers without needing a real agent loop).
            called_2, text_2 = await _run_turn(client, "Now do the same for this one: 'a b c'")
    except Exception as exc:  # noqa: BLE001 -- SDK doesn't publish typed auth/CLI errors, see comment above
        pytest.skip(f"Claude Agent SDK session failed, likely an auth/CLI setup issue: {exc}")

    assert mcp_word_count in called_1, f"turn 1: expected {mcp_word_count}, got {called_1}"
    assert "5" in text_1, f"turn 1: expected '5' in response, got {text_1!r}"
    assert mcp_word_count in called_2, f"turn 2: expected {mcp_word_count}, got {called_2}"
    assert "3" in text_2, f"turn 2: expected '3' in response, got {text_2!r}"
