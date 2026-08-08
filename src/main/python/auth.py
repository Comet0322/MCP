from dataclasses import dataclass

from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.dependencies import get_access_token

from src.main.python.config import Settings, settings
from src.main.python.errors import raise_tool_error

_DEV_TENANT_ID = "local-dev"


def build_auth_provider(cfg: Settings = settings) -> JWTVerifier | None:
    """Resource-server auth: only verifies tokens, never issues them.

    How a user's client gets hold of a token in the first place is out of
    scope for this template — that's handled by whatever SSO mechanism your
    organization already has (see docs/DEPLOYMENT.md).
    """
    if not cfg.AUTH_ENABLED:
        return None
    return JWTVerifier(jwks_uri=cfg.JWKS_URL, issuer=cfg.OIDC_ISSUER, audience=cfg.AUDIENCE)


@dataclass(frozen=True)
class Identity:
    tenant_id: str
    claims: dict


def get_current_identity(cfg: Settings = settings) -> Identity:
    """Identity of the caller, derived from the validated bearer token.

    Whether to use this to scope data access (per-tenant isolation) is up
    to each tool's own logic — this template only guarantees the identity
    is available, it does not enforce any isolation policy.
    """
    if not cfg.AUTH_ENABLED:
        return Identity(tenant_id=_DEV_TENANT_ID, claims={})

    token = get_access_token()
    if token is None:
        raise_tool_error(
            "AUTH_ERROR",
            "No authenticated identity found for this call.",
            recoverable=False,
        )

    assert cfg.TENANT_CLAIM_NAME is not None  # noqa: S101 -- type narrowing, enforced by Settings validator when AUTH_ENABLED
    tenant_id = token.claims.get(cfg.TENANT_CLAIM_NAME)
    if not tenant_id:
        raise_tool_error(
            "AUTH_ERROR",
            f"Token is missing the configured tenant claim '{cfg.TENANT_CLAIM_NAME}'.",
            recoverable=False,
            details={"available_claims": sorted(token.claims.keys())},
        )
    return Identity(tenant_id=tenant_id, claims=token.claims)
