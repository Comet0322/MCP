"""Layer: can an agent actually use this? (agent/ group)

marker: slow -- calls the real Anthropic API. This tests tool *description*
quality, not tool correctness (tests/server/test_functional.py's job):
does a real model pick the right tool given nothing but its name,
description, and schema? Uses AGENT_EVAL_MODEL (Sonnet by default, to be
representative of what real MCP clients like Claude Code actually run),
temperature=0, no majority-vote retries -- if a scenario proves flaky in
practice, escalate that one scenario rather than the whole layer.
"""

from dataclasses import dataclass, field

import pytest
from anthropic import AsyncAnthropic

from src.main.python.config import settings

pytestmark = pytest.mark.slow


@dataclass
class AgentScenario:
    prompt: str
    expect_tool_called: list[str] = field(default_factory=list)
    expect_not_called: list[str] = field(default_factory=list)


AGENT_SCENARIOS = [
    AgentScenario(
        prompt="Count how many words are in this sentence: 'the quick brown fox jumps'",
        expect_tool_called=["word_count"],
    ),
    AgentScenario(
        prompt="What is the capital of France?",
        expect_not_called=["word_count"],
    ),
]


async def _tool_specs(client) -> list[dict]:
    tools = await client.list_tools()
    return [
        {"name": t.name, "description": t.description, "input_schema": t.inputSchema} for t in tools
    ]


async def _called_tool_names(
    anthropic_client: AsyncAnthropic, tool_specs: list[dict], prompt: str
) -> set[str]:
    response = await anthropic_client.messages.create(
        model=settings.AGENT_EVAL_MODEL,
        max_tokens=1024,
        temperature=0,
        tools=tool_specs,
        messages=[{"role": "user", "content": prompt}],
    )
    return {block.name for block in response.content if block.type == "tool_use"}


@pytest.mark.parametrize("scenario", AGENT_SCENARIOS, ids=[s.prompt for s in AGENT_SCENARIOS])
async def test_agent_selects_the_right_tool(client, scenario: AgentScenario):
    if not settings.ANTHROPIC_API_KEY:
        pytest.skip("ANTHROPIC_API_KEY not configured -- see .env.example")

    anthropic_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())
    tool_specs = await _tool_specs(client)

    called = await _called_tool_names(anthropic_client, tool_specs, scenario.prompt)

    for tool_name in scenario.expect_tool_called:
        assert tool_name in called, (
            f"expected '{tool_name}' to be called for {scenario.prompt!r}, got {called}"
        )
    for tool_name in scenario.expect_not_called:
        assert tool_name not in called, (
            f"expected '{tool_name}' NOT to be called for {scenario.prompt!r}, got {called}"
        )
