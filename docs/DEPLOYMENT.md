# Deploying this server

## Scope

This is a **single-instance** deployment (`docker compose`, not k8s). It
ships with **no auth layer** -- every call is unauthenticated by default.
That's deliberate: identity/tenancy requirements vary too much across
organizations (which IdP, which claim carries the tenant id, whether you
even have multiple tenants) to bake in a default that wouldn't just be
ripped out. Add auth yourself if your deployment needs it (see below)
rather than fighting a built-in scheme designed for a use case that isn't
yours.

## Adding auth, if you need it

FastMCP (the framework this template is built on) has this built in --
this template just doesn't wire it up. Two starting points:

- **Resource server (verify tokens someone else issued)**: pass
  `auth=JWTVerifier(jwks_uri=..., issuer=..., audience=...)` to
  `FastMCP(...)` in `main.py` (`fastmcp.server.auth.providers.jwt`). Read
  the validated identity inside a tool with `get_access_token()`
  (`fastmcp.server.dependencies`) and its `.claims` dict -- whichever claim
  your IdP uses for tenant/user id is IdP-specific (e.g. Azure AD uses
  `tid`); there's no universal default.
- **Interactive login (server drives the OAuth flow itself)**: look at
  `OAuthProxy` (`fastmcp.server.auth`) if there's no other way for your
  client to obtain a token in the first place.

Once wired up, an MCP client passes the token as a bearer header:

```json
{
  "mcpServers": {
    "my-mcp-template": {
      "url": "https://mcp.your-domain.internal/mcp",
      "headers": { "Authorization": "Bearer <token>" }
    }
  }
}
```

Whether/how a tool then scopes data access by whatever identity you
extract is your tool's own logic -- see `docs/TOOL_GUIDELINES.md`.

## CORS

Off by default -- MCP clients here are CLI agents, not browsers. Only set
`ALLOWED_ORIGINS` (comma-separated) if a browser-based client (e.g. a web
inspector) needs to call this server directly. Never combine a wildcard
origin with credentialed requests.

## Reverse proxy / TLS / rate limiting

Put this behind a reverse proxy (nginx, Traefik, Caddy) for TLS
termination in production -- the container itself only speaks plain HTTP
on the internal network. Rate limiting, if you need it, belongs at the
proxy layer too; it's not implemented in this template.

## Observability (Langfuse via OpenTelemetry, optional)

Set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` (`LANGFUSE_BASE_URL` too
if self-hosted, defaults to Langfuse Cloud) to enable tracing.
FastMCP's own built-in OpenTelemetry instrumentation
(`fastmcp.server.telemetry`) starts exporting its per-call spans -- method
name, tool/resource/prompt name, session id, errors -- to Langfuse's OTLP
endpoint. This covers every call automatically, not just the two tools
shipped here, with no per-tool code required.

Unset by default: no tracer is configured, zero overhead.

## Metrics (Prometheus exposition, always on)

`GET /metrics` exposes `mcp_tool_calls_total` (counter, labeled by `tool`
and `status`: ok/error) and `mcp_tool_call_duration_seconds` (histogram,
same labels) via `ToolMetricsMiddleware`. Unlike Langfuse this needs no
external credentials and isn't opt-in -- it's pull-based, costs nothing
unless something scrapes it, and doesn't commit this template to any
specific backend. Point Prometheus, a Grafana Agent, the Datadog Agent's
Prometheus check, or anything else that scrapes Prometheus-format
endpoints at it. If you're running under Kubernetes with the Prometheus
Operator, this is what a `ServiceMonitor` would target -- that resource
itself lives in your cluster manifests, not this repo (see "Scope" above:
single-instance/docker-compose only, no k8s manifests here).

## Volume mounts

`example_tool.py` is pure logic and touches no files, so
`docker-compose.yml` has no volume mount by default. If you add a real
file-operation tool, add a `volumes:` entry mapping a host path into the
container -- there's a commented placeholder in `docker-compose.yml`.
