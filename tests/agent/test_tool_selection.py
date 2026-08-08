"""Layer: can an agent actually use this? (agent/ group)

Despite the directory name, this is NOT an end-to-end test -- it's a
single-shot tool-calling check, not a multi-turn agent loop (see
docs/TESTING.md for the full layer breakdown; this sits at layer 2, not
layer 3). Renamed from test_agent_e2e.py for that reason. For the layer-3
multi-turn version, see test_agent_e2e_multiturn.py.

marker: slow -- calls a real LLM API. This tests tool *description*
quality, not tool correctness (tests/server/test_functional.py's job):
does a real model pick the right tool given nothing but its name,
description, and schema? Single-shot tool-calling check, not a full agent
loop -- so it shares LLM_JUDGE_* config (see config.py) rather than needing
its own provider. temperature=0, no majority-vote retries -- if a scenario
proves flaky in practice, escalate that one scenario rather than the whole
layer.

Positive assertions (expect_tool_called) are scored with deepeval's
ToolCorrectnessMetric (`eval` dependency group: `uv sync --group eval`) --
called *without* `available_tools=`, so this is a deterministic set
comparison, no extra LLM call, that also gives a human-readable reason on
failure. It's handed a `LocalModel` built directly from LLM_JUDGE_* so it
never touches OPENAI_API_KEY. Negative assertions (expect_not_called) stay
a plain `assert`: ToolCorrectnessMetric only checks that expected tools
were called, not that uncalled-but-present tools were withheld, so it
can't express that half on its own. For a *judged* version of this check
(is the chosen tool the best one among alternatives, not just present),
see test_tool_selection_quality.py.
"""

from dataclasses import dataclass, field

import pytest

from src.main.python.config import settings
from tests.agent._helpers import called_tool_names, openai_client, tool_specs

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


def _tool_correctness_metric_and_test_case_cls():
    try:
        from deepeval.metrics import ToolCorrectnessMetric
        from deepeval.test_case import LLMTestCase, ToolCall

        from tests.agent._helpers import local_judge_model
    except ImportError:
        pytest.skip("deepeval not installed -- run `uv sync --group eval`")

    return ToolCorrectnessMetric(model=local_judge_model()), LLMTestCase, ToolCall


@pytest.mark.parametrize("scenario", AGENT_SCENARIOS, ids=[s.prompt for s in AGENT_SCENARIOS])
async def test_agent_selects_the_right_tool(client, scenario: AgentScenario):
    if not settings.LLM_JUDGE_BASE_URL or not settings.LLM_JUDGE_MODEL:
        pytest.skip("LLM_JUDGE_BASE_URL / LLM_JUDGE_MODEL not configured -- see .env.example")

    metric, LLMTestCase, ToolCall = _tool_correctness_metric_and_test_case_cls()

    specs = await tool_specs(client)
    called = await called_tool_names(openai_client(), specs, scenario.prompt)

    for tool_name in scenario.expect_not_called:
        assert tool_name not in called, (
            f"expected '{tool_name}' NOT to be called for {scenario.prompt!r}, got {called}"
        )

    test_case = LLMTestCase(
        input=scenario.prompt,
        tools_called=[ToolCall(name=name) for name in called],
        expected_tools=[ToolCall(name=name) for name in scenario.expect_tool_called],
    )
    metric.measure(test_case)
    assert metric.success, metric.reason
