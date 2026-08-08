"""Shared helpers for tests/agent/ -- not a test module itself.

Both the layer-2 tool-selection tests and (if you build one) any real
layer-3 harness need "ask an OpenAI-compatible model to pick a tool and see
what it called". Factored out so it's written once.
"""

from src.main.python.config import settings


async def tool_specs(client) -> list[dict]:
    tools = await client.list_tools()
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.inputSchema,
            },
        }
        for t in tools
    ]


async def called_tool_names(openai_client, specs: list[dict], prompt: str) -> set[str]:
    response = await openai_client.chat.completions.create(
        model=settings.LLM_JUDGE_MODEL,
        max_tokens=1024,
        temperature=0,
        tools=specs,
        messages=[{"role": "user", "content": prompt}],
    )
    tool_calls = response.choices[0].message.tool_calls or []
    return {call.function.name for call in tool_calls}


def openai_client():
    from openai import AsyncOpenAI

    api_key = (
        settings.LLM_JUDGE_API_KEY.get_secret_value()
        if settings.LLM_JUDGE_API_KEY
        else "not-needed"
    )
    return AsyncOpenAI(base_url=settings.LLM_JUDGE_BASE_URL, api_key=api_key)


def local_judge_model():
    """A deepeval LocalModel pointed at LLM_JUDGE_* -- never touches OPENAI_API_KEY."""
    from deepeval.models import LocalModel

    return LocalModel(
        model=settings.LLM_JUDGE_MODEL,
        base_url=settings.LLM_JUDGE_BASE_URL,
        api_key=(
            settings.LLM_JUDGE_API_KEY.get_secret_value()
            if settings.LLM_JUDGE_API_KEY
            else "not-needed"
        ),
    )
