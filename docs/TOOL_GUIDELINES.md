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
    """Count the words in a piece of text and report who asked.

    Args:
        text: The text to count words in. Must contain at least one
            non-whitespace character.

    Returns:
        A dict with `word_count` (int) and `requested_by` (str).
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

## Error messages

Every tool-level failure must go through `errors.py`'s `raise_tool_error`,
never a bare `raise` or an unhandled exception. The unified shape:

```python
{"code": "...", "message": "...", "recoverable": bool, "details": {...} | None}
```

- `recoverable=True` means retrying the same call, possibly with backoff,
  could plausibly succeed (a transient upstream timeout, a rate limit).
- `recoverable=False` means the agent needs to change something first --
  fix the input, get a fresh token, wait for a resource to exist. Retrying
  verbatim will just fail again.
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
- Prefer explicit names over abbreviations (`tenant_id`, not `tid`) --
  the agent reasons over the schema, it doesn't know your internal jargon.
- Booleans read as questions: `include_archived`, not `archived_flag`.

## Identity and data scoping

Call `get_current_identity()` (from `auth.py`) if your tool needs to know
who's calling. This template guarantees the identity is available; it does
**not** decide whether your tool should use it to scope data access. If
your tool reads/writes tenant-specific data, that scoping is your call to
make and test -- see `example_tool.py` for how to retrieve the identity.
