"""Layer: does the MCP server itself work correctly? (server/ group)

Loads tests/golden/*.yaml and dispatches each case by assert_type. Six
assert_types: exact_match/contains/regex_match/numeric_tolerance are plain
comparisons against the tool's own output (unit-ish, no external calls).
llm_judge calls the Anthropic API (see config.LLM_JUDGE_MODEL) and is
marked slow. custom loads a user-provided validator via importlib.
"""

import importlib
import re
from pathlib import Path

import pytest
import yaml

from src.main.python.config import settings
from tests.golden.schema import GoldenCase

GOLDEN_DIR = Path(__file__).parent.parent / "golden"


def _load_cases() -> list[GoldenCase]:
    cases = []
    for path in sorted(GOLDEN_DIR.glob("*.yaml")):
        for entry in yaml.safe_load(path.read_text()) or []:
            cases.append(GoldenCase(**entry))
    return cases


def _to_param(case: GoldenCase):
    marks = [pytest.mark.slow] if case.assert_type == "llm_judge" else []
    case_id = case.description or f"{case.tool_name}:{case.assert_type}"
    return pytest.param(case, marks=marks, id=case_id)


CASES = [_to_param(c) for c in _load_cases()]


def _extract(data, field: str | None):
    return data[field] if field else data


async def _judge_semantic_match(actual: str, expected: str) -> bool:
    # Bring-your-own OpenAI-compatible provider (OpenAI, NVIDIA NIM,
    # DeepSeek, Together, a local vLLM/Ollama, ...). See config.py.
    if not settings.LLM_JUDGE_BASE_URL or not settings.LLM_JUDGE_MODEL:
        pytest.skip("LLM_JUDGE_BASE_URL / LLM_JUDGE_MODEL not configured -- see .env.example")

    from openai import AsyncOpenAI

    api_key = (
        settings.LLM_JUDGE_API_KEY.get_secret_value()
        if settings.LLM_JUDGE_API_KEY
        else "not-needed"
    )
    client = AsyncOpenAI(base_url=settings.LLM_JUDGE_BASE_URL, api_key=api_key)
    response = await client.chat.completions.create(
        model=settings.LLM_JUDGE_MODEL,
        max_tokens=8,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": (
                    "Does the ACTUAL output convey the same meaning as the EXPECTED "
                    "description? Answer with exactly one word: yes or no.\n\n"
                    f"EXPECTED: {expected}\n\nACTUAL: {actual}"
                ),
            }
        ],
    )
    verdict = (response.choices[0].message.content or "").strip().lower()
    return verdict.startswith("yes")


def _run_custom_assertion(custom_assertion: str, actual, expected) -> None:
    module_path, func_name = custom_assertion.split(":")
    module = importlib.import_module(module_path)
    getattr(module, func_name)(actual, expected)


@pytest.mark.parametrize("case", CASES)
async def test_golden_case(client, case: GoldenCase):
    result = await client.call_tool(case.tool_name, case.input)
    actual = _extract(result.data, case.field)

    if case.assert_type == "exact_match":
        assert actual == case.expected

    elif case.assert_type == "contains":
        if isinstance(case.expected, dict) and isinstance(actual, dict):
            for key, value in case.expected.items():
                assert actual.get(key) == value, f"{case.tool_name}: missing/mismatched key '{key}'"
        else:
            assert str(case.expected) in str(actual)

    elif case.assert_type == "regex_match":
        assert re.search(case.expected, str(actual)) is not None, (
            f"{case.tool_name}: '{actual}' does not match /{case.expected}/"
        )

    elif case.assert_type == "numeric_tolerance":
        assert case.tolerance is not None  # enforced by GoldenCase validator
        assert abs(float(actual) - float(case.expected)) <= case.tolerance

    elif case.assert_type == "llm_judge":
        assert await _judge_semantic_match(str(actual), str(case.expected))

    elif case.assert_type == "custom":
        assert case.custom_assertion is not None  # enforced by GoldenCase validator
        _run_custom_assertion(case.custom_assertion, actual, case.expected)
