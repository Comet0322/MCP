# Contributing

This is a template repo, so most changes fall into one of two buckets:
fixes/improvements to the template itself (this file is for that), or
downstream customization after "Use this template" (see README's
"Using this as a template" section for that instead).

## Setup

```bash
uv sync --group dev
uv run pre-commit install
cp .env.example .env
```

## Before opening a PR

```bash
uv run pytest -m "not slow"   # fast suite: no LLM calls, no docker
uv run ruff check .
uv run ruff format --check .
```

`pre-commit` runs ruff, gitleaks, and a `uv.lock` sync check on every commit
-- if it's installed (above), most of this is already enforced locally.

The `slow` marker (real Anthropic calls + docker compose) isn't required to
pass locally -- it needs `ANTHROPIC_API_KEY` and a docker daemon, and runs in
CI. If you're touching auth, tracing, or the container build, run it anyway:

```bash
uv run pytest -m slow
```

## Conventions

- Every tool needs a golden case (`tests/golden/*.yaml`) and must exercise
  the unified error format (`errors.py`) -- see `docs/TOOL_GUIDELINES.md`.
- Keep `pyproject.toml`'s pinned `ruff` version and
  `.pre-commit-config.yaml`'s `ruff-pre-commit` `rev` in sync; they're
  independent toolchains and won't drift-check each other automatically.
- No secrets in commits -- gitleaks runs in pre-commit and CI, but double
  check before pushing anyway.

## Reporting issues

Open a GitHub issue with what you expected vs. what happened. For security
issues, see `SECURITY.md` if present, otherwise flag it in the issue title
so it doesn't get triaged as a normal bug.
