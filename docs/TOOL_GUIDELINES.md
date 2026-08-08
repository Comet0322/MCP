# Writing tools for this template

The client is a CLI coding agent (Claude Code and similar), not a human
reading a chat UI. It only ever sees your tool's name, description, and
JSON schema before deciding whether to call it, and only ever sees your
error message when deciding whether to retry. Write for that reader.

## Tool descriptions

- **Lead with what it does and when to use it**, in plain language. The
  agent is choosing between your tool and every other tool it has; a vague
  description loses that competition.
- **State constraints and side effects up front** ("read-only", "creates a
  file", "irreversible") -- an agent can't infer this from the name.
- Every parameter needs its own description (Google-style docstring `Args:`
  section -- FastMCP parses this automatically into the JSON schema).
  `test_contract.py` fails the build if any parameter is missing one.
- Minimum ~20 characters for the tool description -- also enforced by
  `test_contract.py`. Treat that as a floor, not a target.

### Good example

```python
async def word_count(text: str) -> dict:
    """Count the words in a piece of text.

    Args:
        text: The text to count words in. Must contain at least one
            non-whitespace character.

    Returns:
        A dict with `word_count` (int).
    """
```

Why this works: the summary line says exactly what it does. The `Args:`
entry tells the agent the exact failure condition (empty/whitespace-only
text) before it ever calls the tool with bad input.

### Bad example

```python
async def wc(t: str) -> dict:
    """Word count tool."""
```

Why this fails: `wc`/`t` give the agent nothing to reason about naming-wise;
"Word count tool" restates the name rather than explaining behavior,
inputs, or constraints; there's no `Args:` entry, so `t` ships with no
parameter description at all -- `test_contract.py` would reject this.

## Tool annotations

Every tool's `register()` call must pass `annotations=` with all four MCP
hints -- clients use these for UI treatment and safety gating (e.g. asking
for confirmation before a destructive call). See `example_tool.py` /
`fetch_json_tool.py` for the pattern:

```python
mcp.tool(
    my_tool,
    annotations={
        "title": "Human-Readable Title",
        "readOnlyHint": True,  # doesn't modify anything
        "destructiveHint": False,  # doesn't destroy/overwrite data
        "idempotentHint": True,  # repeat calls, same args -> no extra effect
        "openWorldHint": False,  # doesn't talk to an external system
    },
)
```

These are hints, not enforcement -- don't rely on them for actual security
decisions, just accurate disclosure.

## Naming, once you replace the example tools

`word_count`/`fetch_json` have no prefix because this template doesn't know
what service you're wrapping yet. Once you add real tools, prefix with your
service name (`slack_send_message`, not `send_message`) -- an MCP client
often has multiple servers loaded at once, and an unprefixed name collides
easily.

## Response format and pagination, for data-heavy tools

Both example tools return a single small dict -- no formatting choice, no
pagination needed. If your tool lists/searches real data (the DB-query
class of tool this template doesn't demonstrate yet -- see `docs/STATUS.md`),
budget for:
- A `response_format` param (`"json"` for programmatic use, `"markdown"`
  default for a human-readable summary) rather than one fixed shape.
- `limit`/`offset` (or cursor) params, and return `has_more`/`next_offset`/
  `total_count` alongside the page -- never load an unbounded result set
  into the tool response.

## Evaluating tool quality once you have real data

Once your tools front real data (not this template's two toy examples),
`test_tool_selection.py`'s single-scenario tool-selection check stops being
enough signal. Two things to reach for, in order:

- **`test_tool_selection_quality.py`** -- same idea, but scored with a real
  LLM judge (`ToolCorrectnessMetric` + `available_tools=`) instead of a
  deterministic set comparison, so it can tell "technically valid but not
  the best choice" apart from "wrong". Worth it once you have tools with
  overlapping purposes (two search variants, a "quick" vs "detailed"
  operation) -- this repo's two example tools don't need it yet.
- **The `mcp-builder` skill's evaluation methodology** -- write ~10
  realistic, multi-hop, read-only questions with a single verifiable
  answer, solve them yourself first, then run an agent against only your
  MCP server. A stronger, broader test of whether your tool
  descriptions/schemas hold up under real use than either check above.
  Worth reaching for once you have enough real data to write hard
  questions against, not before.

For an actual multi-turn agent loop (not single-shot tool selection),
`test_agent_e2e_multiturn.py` is a working template: `claude-agent-sdk`
(`agent-sdk` dependency group) driving this repo's real MCP server over
HTTP. Needs the Claude Code CLI installed, and is Claude-only by
construction -- see `docs/TESTING.md`.

## Error messages

Every tool-level failure must go through `errors.py`'s `raise_tool_error`,
never a bare `raise` or an unhandled exception. The unified shape:

```python
{"code": "...", "message": "...", "recoverable": bool, "details": {...} | None}
```

- `recoverable=True` means retrying the same call, possibly with backoff,
  could plausibly succeed (a transient upstream timeout, a rate limit).
- `recoverable=False` means the agent needs to change something first --
  fix the input, wait for a resource to exist. Retrying verbatim will just
  fail again.
- `message` should say what to do differently, not just what went wrong.
  "`text` must be non-empty" is more useful than "ValidationError".
- Every tool must declare a `CONTRACT_INVALID_CASE` (see `example_tool.py`)
  so `test_contract.py` can verify it actually uses this format instead of
  leaking a raw traceback.

## Retrying external calls

If your tool calls something outside the process (a DB, a third-party API
-- see `fetch_json_tool.py` for a worked example), wrap the call with
`tenacity`: retry connection errors and 5xx responses with backoff, but let
4xx / validation failures fail immediately since retrying them can't help.
Whichever bucket a failure ends up in should also match its
`raise_tool_error(recoverable=...)` value once retries are exhausted.

## Parameter naming

- Use the same name for the same concept across every tool in this server
  (e.g. always `text`, never `text` in one tool and `content` in another).
- Prefer explicit names over abbreviations (`user_id`, not `uid`) -- the
  agent reasons over the schema, it doesn't know your internal jargon.
- Booleans read as questions: `include_archived`, not `archived_flag`.

## Identity and auth

This template ships with no auth layer -- see `docs/DEPLOYMENT.md` for how
to add one. If your deployment needs to know who's calling (e.g. to scope
data access per tenant/user), that's on you to wire up and is a decision
FastMCP supports natively (`auth=` on `FastMCP(...)` in `main.py`,
`get_access_token()` inside a tool via `fastmcp.server.dependencies`) --
this template just doesn't make that choice for you.
