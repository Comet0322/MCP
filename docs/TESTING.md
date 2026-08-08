# Test layers

This repo isn't RAG-specific (see README), so the usual RAG eval vocabulary
("retrieval", "faithfulness") doesn't map cleanly onto it. This doc uses a
generalized version of that same ladder -- scope (how many components are
involved) crossed with determinism (does the same input always produce the
same pass/fail) -- and maps it onto the actual test files.

| Layer | What it tests | Determinism | Current file(s) |
|---|---|---|---|
| **0 -- contract** | One component, in isolation, external deps mocked/absent. | Deterministic. | `test_contract.py` (schema/description hygiene, all tools); `test_functional.py` golden cases with `assert_type` in `exact_match`/`contains`/`regex_match`/`numeric_tolerance` |
| **1 -- real dependency, single component** | Still one component, but its real logic runs against a real (if controlled) dependency -- not mocked away. | Deterministic, because the dependency is a fixed local stand-in (scripted server), not the live third party. | `test_fetch_json_tool.py` (real tenacity retry logic against a local scripted HTTP server) |
| **2 -- multi-component pipeline, LLM-judged** | Multiple components chained, with an LLM doing the actual judging/scoring. | Non-deterministic -- assert against a threshold, not an exact value. | `test_functional.py` golden cases with `assert_type: llm_judge` (`LLM_JUDGE_THRESHOLD`); `test_tool_selection_quality.py` (`ToolCorrectnessMetric` *with* `available_tools=`, `eval` group -- see below, template not load-bearing yet) |
| **3 -- full E2E** | User prompt in, through real multi-turn agent decision-making and tool calls, to final output. Crosses the system boundary into components you don't own (e.g. Claude Code itself). | Non-deterministic. | `test_agent_e2e_multiturn.py` (`agent-sdk` group -- see below) |

## One gap this ladder makes visible, and two things it clarified

**`test_container_smoke.py` doesn't fit any row.** It chains multiple real
components (container, network) like a layer-2 test, but it's a
deterministic pass/fail, not a threshold assertion -- there's no LLM in the
loop. Treat "multi-component but deterministic" as its own axis rather than
forcing it into this ladder; the fast/slow pytest marker (cost, not
scope/determinism) already tags it correctly as `slow`.

**`test_tool_selection.py` doesn't fit cleanly.** It looks like layer 2
(calls an LLM), but as wired it isn't LLM-judged at all:
`ToolCorrectnessMetric` is called without `available_tools=`, so scoring is
a plain deterministic set comparison (`tools_called` vs `expected_tools`),
not an LLM judgment -- the `LocalModel` handed to it exists only to satisfy
the constructor and is never actually invoked for scoring. So it's
layer-1-*shaped* (deterministic check, single component), except the
dependency being exercised is the LLM-under-test's own response, which --
unlike `test_fetch_json_tool.py`'s scripted server -- isn't a fully
controlled, guaranteed-reproducible stand-in even at `temperature=0`.

**`test_tool_selection_quality.py` is the actual layer-2 version.** Same
setup, but `ToolCorrectnessMetric` is given `available_tools=`, which turns
on a real LLM-judged score: "was the tool actually called the best choice
among everything available", not just "was the required tool present".
Real LLM call to `LLM_JUDGE_*`, verified passing against a real NIM
endpoint. Template, not load-bearing yet: this repo's two tools
(`word_count`/`fetch_json`) are semantically distinct enough that the
judge's extra discrimination doesn't earn its keep until you add tools
with overlapping purposes -- see `docs/TOOL_GUIDELINES.md`.

**`test_agent_e2e_multiturn.py` is the real layer-3 test.** Multi-turn
Claude Agent SDK session (`agent-sdk` dependency group: `claude-agent-sdk`,
plus the Claude Code CLI itself -- the SDK shells out to the `claude`
binary, it isn't a pure Python client) driving this repo's actual MCP
server over real HTTP on a real port (not the in-memory `fastmcp.Client`
the rest of `tests/server/` uses -- an OS subprocess can't reach an
in-memory object). Verified end-to-end: two turns in one session, second
turn's correctness depends on the first turn's context surviving, real
`mcp__my-mcp-template__word_count` tool calls both turns, correct answers
both turns. Categorically Claude-only (the SDK doesn't wrap any other
provider) -- unlike `test_tool_selection.py`'s deliberate
provider-agnosticism, that's not a gap here, it's what this layer *is*.

## Orthogonal to this ladder: the fast/slow marker

The layers above are about scope and determinism. `pytest.mark.slow` is
about cost (network/LLM calls, docker) -- it cuts across all four layers
independently. Don't conflate the two: a layer-0 test is always fast, but a
layer-1 test can be fast too (`test_fetch_json_tool.py`'s scripted server
needs no network egress and isn't marked slow), while layer 2/3 tests are
slow by nature (real LLM calls).
