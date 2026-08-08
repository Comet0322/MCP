# syntax=docker/dockerfile:1
FROM python:3.14-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency manifests first so this layer caches independently of
# source changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
RUN uv sync --frozen --no-dev


FROM python:3.14-slim AS runtime

RUN useradd --create-home --uid 1000 mcp
WORKDIR /app

COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/src ./src
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh && chown -R mcp:mcp /app

USER mcp
ENV PATH="/app/.venv/bin:${PATH}"
EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
