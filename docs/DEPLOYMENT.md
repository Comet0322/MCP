# Deploying this server

## Scope

This is a **single-instance** deployment (`docker compose`, not k8s) that
acts as a **multi-tenant SSO/OIDC resource server**: it verifies bearer
tokens issued by your organization's existing identity provider. It does
**not** implement login/authorization flows itself -- how a caller obtains
a token in the first place is out of scope, by design (see below).

## Connecting your SSO / OIDC provider

Set these in `.env` (see `.env.example`):

| Variable            | What it is                                                        |
|----------------------|--------------------------------------------------------------------|
| `AUTH_ENABLED`       | `true` in production. `ENV=prod` forces this on regardless.        |
| `OIDC_ISSUER`        | Your IdP's issuer URL (the `iss` claim it stamps on tokens).       |
| `JWKS_URL`           | Your IdP's JWKS endpoint (public keys used to verify signatures).  |
| `AUDIENCE`           | The `aud` value your IdP issues tokens for this server with.       |
| `TENANT_CLAIM_NAME`  | Which JWT claim holds the tenant/user id. **IdP-specific** -- e.g. Azure AD uses `tid`. Check your provider's token format. |

If `AUTH_ENABLED` is on and any of these is missing, the server refuses to
start (fail-fast, not a silent unauthenticated fallback).

## How clients get a token

This template deliberately does **not** implement an interactive OAuth
login flow (no `/authorize` redirect, no `OAuthProxy`). That's a
full OAuth-client-level integration, and MCP client support for driving an
arbitrary org's IdP through that flow varies. Instead, assume your
organization already has a way to mint a token for a user (a company SSO
CLI, a login portal, whatever you use for other internal tools) and that
token gets passed to the MCP client as a bearer token, e.g.:

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

**Upgrade path**: if you later need the server itself to drive an
interactive login redirect (no other way for the client to get a token),
look at FastMCP's `OAuthProxy` (`fastmcp.server.auth`). Not implemented
here on purpose -- see the reasoning above.

## Data isolation

The server exposes the caller's identity to tools via
`get_current_identity()`, but does not enforce any isolation policy
itself. Whether a tool scopes its data access by tenant/user is that
tool's own logic -- see `docs/TOOL_GUIDELINES.md`.

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
if self-hosted, defaults to Langfuse Cloud) to enable tracing. Two things
happen:

1. FastMCP's own built-in OpenTelemetry instrumentation
   (`fastmcp.server.telemetry`) starts exporting its per-call spans --
   method name, tool/resource/prompt name, auth, session id, errors -- to
   Langfuse's OTLP endpoint. This covers every call automatically, not
   just the two tools shipped here, with no per-tool code required.
2. A small `TenantTracingMiddleware` (`observability.py`) adds a second
   span per tool call tagged with `tenant_id` (the claim FastMCP's generic
   auth attributes don't carry). It shows up alongside FastMCP's native
   span in Langfuse rather than nested under it -- empirically, middleware
   runs outside the context where FastMCP's own span is current, so there
   was no reliable way to tag that span directly.

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
