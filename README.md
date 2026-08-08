# my-mcp-template

A generic template for building [FastMCP](https://gofastmcp.com) servers
for CLI coding agents (Claude Code and similar) -- not chat UIs. It ships
with two working example tools (pure logic, and an external-call tool with
tenacity retries), a unified error format, a Prometheus `/metrics`
endpoint, optional Langfuse tool-call tracing, Docker Compose deployment,
and a two-axis test suite. Not RAG-specific: just as suited to DB-query or
file-operation tools. Ships with **no auth layer** -- see
`docs/DEPLOYMENT.md` if your deployment needs one.

## Using this as a template

This repo is a plain [GitHub template repository]("Use this template"
button), not a cookiecutter project -- there's no templating variables to
fill in. To start a new project from it:

1. Click "Use this template" on GitHub (or `git clone` + re-init).
2. Rename the package path if you want something other than
   `src.main.python` -- it's a literal directory structure
   (`src/main/python/`), so a plain find-replace across the repo handles it.
3. Replace `example_tool.py` with your own tools (see
   `docs/TOOL_GUIDELINES.md`).

## Local development

```bash
uv sync
cp .env.example .env
uv run python -m src.main.python.main
```

The server listens on `http://0.0.0.0:8000/mcp` (streamable HTTP,
stateless). Point [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
or any streamable-HTTP-capable client at that URL to try it out.

## Running with Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

Health check: `curl http://localhost:8000/health`.

## Tests

Two independent groups, plus a fast/slow cost axis that cuts across both.
See `docs/TESTING.md` for how these map onto a general 4-layer scope/determinism
ladder (contract -> real-dependency component -> LLM-judged pipeline -> full
agent E2E), and where the current suite's gaps are relative to it.

- **`tests/server/`** -- does the MCP server itself work correctly?
  Schema/description contract, golden-case functional correctness, and a
  real container integration smoke test.
- **`tests/agent/`** -- can an agent actually use it? Feeds your tool
  descriptions to your configured `LLM_JUDGE_*` model and checks it picks
  the right tool (scored with deepeval's `ToolCorrectnessMetric`, `eval`
  dependency group). `test_tool_selection.py`/`test_tool_selection_quality.py`
  are deterministic/LLM-judged variants of the same check (layer 1/2);
  `test_agent_e2e_multiturn.py` is a real multi-turn Claude Agent SDK
  session (`agent-sdk` group, needs the Claude Code CLI installed --
  layer 3). This is the group that actually tests description *quality*.

```bash
uv sync --group eval           # tests/agent/'s deterministic + LLM-judged checks
uv sync --group agent-sdk      # tests/agent/test_agent_e2e_multiturn.py only (needs Claude Code CLI too)
uv run pytest -m "not slow"   # fast: no LLM calls, no docker. Run on every PR.
uv run pytest -m slow          # slow: calls your LLM_JUDGE_* provider + docker compose. Run on merge to main.
uv run pytest                  # everything
```

### Security scanning (CI, part of the fast job)

- **`ruff check .`** includes the `S` (flake8-bandit) ruleset -- basic
  Python SAST, e.g. hardcoded credentials, insecure defaults.
- **`pip-audit`** -- known CVEs in resolved Python dependencies.
- **Trivy** -- scans the built container image (OS packages + Python deps
  baked into it) and uploads results to the repo's Security tab. Report-only
  (doesn't fail the build): base-image OS CVEs with no fix published yet
  are common and not actionable, and failing on those would make this
  template permanently red for no fixable reason.

`LLM_JUDGE_BASE_URL`/`LLM_JUDGE_API_KEY`/`LLM_JUDGE_MODEL` are required for
both `llm_judge` golden cases and `tests/agent/` (tool-selection check) --
bring your own OpenAI-compatible provider (OpenAI, NVIDIA NIM, DeepSeek,
Together, a local vLLM/Ollama, ...); the model must support tool/function
calling for `tests/agent/` to work. Without them, both skip with a clear
reason rather than fail.

### Golden cases

Add your own in `tests/golden/*.yaml`. Six `assert_type`s:
`exact_match`, `contains`, `regex_match`, `numeric_tolerance`, `llm_judge`,
`custom` -- see `tests/golden/schema.py` for the shape and
`tests/golden/example.yaml` for one of each.

### deepeval (`eval` dependency group)

[deepeval](https://github.com/confident-ai/deepeval) is used a few ways:

- `tests/agent/test_tool_selection.py` -- `ToolCorrectnessMetric`, no
  `available_tools=`: deterministic set comparison, no real LLM judge call.
  Handed a `LocalModel` built from `LLM_JUDGE_*` directly, so it never
  touches `OPENAI_API_KEY`.
- `tests/agent/test_tool_selection_quality.py` -- same metric, *with*
  `available_tools=`: a real LLM-judged "was this the best tool among
  alternatives" score, not just presence/absence. See `docs/TESTING.md`.
- **RAG faithfulness (optional, bring your own)** -- for RAG-style tools
  where you want to check answers stay grounded in retrieved context, add
  deepeval assertions in your own test module. Not wired into a specific
  test file here since it only applies if your tools actually do retrieval.

`uv sync --group eval` installs it.

### Claude Agent SDK (`agent-sdk` dependency group)

`tests/agent/test_agent_e2e_multiturn.py` is the layer-3 test in
`docs/TESTING.md`'s ladder -- a real multi-turn `claude-agent-sdk` session
driving this repo's actual MCP server over HTTP on a real port, not the
in-memory client the rest of the suite uses. Needs the Claude Code CLI
installed (the SDK shells out to it) on top of `uv sync --group agent-sdk`.
Categorically Claude-only -- unlike `LLM_JUDGE_*`, there's no
bring-your-own-provider option here, because the SDK itself only drives
Claude.

## Connecting a client

```json
{
  "mcpServers": {
    "my-mcp-template": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

No auth by default -- see `docs/DEPLOYMENT.md` if your deployment needs
one; a client would then pass a bearer token via `headers`.

## Project structure

```
src/main/python/    server code (main.py, config.py, errors.py, tools/)
tests/server/        does the server work correctly?
tests/agent/          can an agent actually use it?
tests/golden/         golden case schema + data
docs/                  TOOL_GUIDELINES.md, DEPLOYMENT.md
```

## Checklist: what you still need to fill in

**Blocking:**
- Real golden case content in `tests/golden/*.yaml` for your own tools.

**Conditional (only if you add the matching feature):**
- Auth, if your deployment needs it -- see `docs/DEPLOYMENT.md`. Not
  wired in by default.
- A `volumes:` entry in `docker-compose.yml`, if you add a real
  file-operation tool.
- `LLM_JUDGE_BASE_URL` / `LLM_JUDGE_API_KEY` / `LLM_JUDGE_MODEL`, only if
  you use the `llm_judge` assert_type in a golden case -- no universal
  default, bring your own OpenAI-compatible provider. Cases skip (not fail)
  if unset.
- `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_BASE_URL`, only
  if you want tool-call tracing. Unset = no middleware added.

**Already have a reasonable default -- tune if needed:**
- `LLM_JUDGE_THRESHOLD` in `config.py`.
- `ALLOWED_ORIGINS` (empty = CORS off; only needed for browser clients).
