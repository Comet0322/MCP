"""Layer: tool-selection *quality*, judged (agent/ group)

Layer 2 in docs/TESTING.md's ladder: a multi-component pipeline where an
LLM does the actual judging, not a deterministic comparison. Unlike
test_tool_selection.py (ToolCorrectnessMetric called without
`available_tools=`, which only checks "was the required tool present"),
this passes `available_tools=` so the metric's tool-selection judge kicks
in and asks a harder question: "given every tool the model could have
picked, was this the best choice" -- not just "was it present at all".
That's a real LLM call to LLM_JUDGE_*, not free.

Template, not a load-bearing check right now: this repo's two tools
(word_count, fetch_json) are semantically distinct enough that picking the
wrong one is already a hard failure test_tool_selection.py catches --
there's no "technically valid but suboptimal" case for the judge to earn
its keep on yet. Once you add tools with overlapping purposes (two search
tools, a "quick" vs "detailed" variant of the same operation), this is
where you'd actually see it disagree with the deterministic check. See
docs/TOOL_GUIDELINES.md's "Evaluating tool quality" section.

marker: slow -- two real LLM calls (one to pick a tool, one to judge the
pick), both against LLM_JUDGE_*.
"""

import pytest

from src.main.python.config import settings
from tests.agent._helpers import called_tool_names, openai_client, tool_specs

pytestmark = pytest.mark.slow

PROMPT = "Count how many words are in this sentence: 'the quick brown fox jumps'"
EXPECTED_TOOL = "word_count"


async def test_tool_selection_quality(client):
    if not settings.LLM_JUDGE_BASE_URL or not settings.LLM_JUDGE_MODEL:
        pytest.skip("LLM_JUDGE_BASE_URL / LLM_JUDGE_MODEL not configured -- see .env.example")

    try:
        from deepeval.metrics import ToolCorrectnessMetric
        from deepeval.test_case import LLMTestCase, ToolCall

        from tests.agent._helpers import local_judge_model
    except ImportError:
        pytest.skip("deepeval not installed -- run `uv sync --group eval`")

    tools = await client.list_tools()
    specs = await tool_specs(client)
    called = await called_tool_names(openai_client(), specs, PROMPT)

    metric = ToolCorrectnessMetric(
        model=local_judge_model(),
        available_tools=[ToolCall(name=t.name, description=t.description) for t in tools],
    )
    test_case = LLMTestCase(
        input=PROMPT,
        tools_called=[ToolCall(name=name) for name in called],
        expected_tools=[ToolCall(name=EXPECTED_TOOL)],
    )
    metric.measure(test_case)
    assert metric.success, metric.reason
