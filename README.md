# my-mcp-template

A generic template for building [FastMCP](https://gofastmcp.com) servers
for CLI coding agents (Claude Code and similar) -- not chat UIs. It ships
with two working example tools (pure logic, and an external-call tool with
tenacity retries), a unified error format, SSO/OIDC auth, a Prometheus
`/metrics` endpoint, optional Langfuse tool-call tracing, Docker Compose
deployment, and a two-axis test suite. Not RAG-specific: just as suited to
DB-query or file-operation tools.

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
cp .env.example .env          # AUTH_ENABLED=false by default, fine for local dev
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

Two independent groups, plus a fast/slow cost axis that cuts across both:

- **`tests/server/`** -- does the MCP server itself work correctly?
  Schema/description contract, golden-case functional correctness, auth
  verification logic, and a real container integration smoke test.
- **`tests/agent/`** -- can an agent actually use it? Feeds your tool
  descriptions to a real Claude model and checks it picks the right tool.
  This is the layer that actually tests description *quality*.

```bash
uv run pytest -m "not slow"   # fast: no LLM calls, no docker. Run on every PR.
uv run pytest -m slow          # slow: calls Anthropic + docker compose. Run on merge to main.
uv run pytest                  # everything
```

`ANTHROPIC_API_KEY` is required for `tests/agent/` (fixed to Claude on
purpose -- see below). `LLM_JUDGE_BASE_URL`/`LLM_JUDGE_API_KEY`/`LLM_JUDGE_MODEL`
are required for `llm_judge` golden cases -- bring your own OpenAI-compatible
provider (OpenAI, NVIDIA NIM, DeepSeek, Together, a local vLLM/Ollama, ...).
Without them, `llm_judge` cases skip with a clear reason rather than fail.

### Golden cases

Add your own in `tests/golden/*.yaml`. Six `assert_type`s:
`exact_match`, `contains`, `regex_match`, `numeric_tolerance`, `llm_judge`,
`custom` -- see `tests/golden/schema.py` for the shape and
`tests/golden/example.yaml` for one of each.

### Faithfulness layer (optional, deepeval)

For RAG-style tools where you want to check answers stay grounded in
retrieved context, add [deepeval](https://github.com/confident-ai/deepeval)
assertions in your own test module (the `eval` dependency group is already
set up: `uv sync --group eval`). Not wired into a specific test file here
since it only applies if your tools actually do retrieval.

## Connecting a client

```json
{
  "mcpServers": {
    "my-mcp-template": {
      "url": "http://localhost:8000/mcp",
      "headers": { "Authorization": "Bearer <token>" }
    }
  }
}
```

The `Authorization` header is only required when `AUTH_ENABLED=true`. See
`docs/DEPLOYMENT.md` for how tokens get issued in production (SSO/OIDC).

## Project structure

```
src/main/python/    server code (main.py, config.py, auth.py, errors.py, tools/)
tests/server/        does the server work correctly?
tests/agent/          can an agent actually use it?
tests/golden/         golden case schema + data
docs/                  TOOL_GUIDELINES.md, DEPLOYMENT.md
```

## Checklist: what you still need to fill in

**Blocking (fail-fast if missing):**
- Real golden case content in `tests/golden/*.yaml` for your own tools.
- Production `OIDC_ISSUER` / `JWKS_URL` / `AUDIENCE` / `TENANT_CLAIM_NAME`
  -- there's no universal default, every IdP is different.

**Conditional (only if you add the matching feature):**
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
- Whether to upgrade past resource-server-only auth to `OAuthProxy`
  (see `docs/DEPLOYMENT.md`) -- not needed unless your MCP client has no
  other way to obtain a token.
