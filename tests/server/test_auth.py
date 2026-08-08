"""Layer: does the MCP server itself work correctly? (server/ group)

Unit tests for auth.py -- JWTVerifier wiring and claim-extraction logic --
using a self-signed mock JWKS server (see auth/mock_jwks.py). No docker,
no real IdP.
"""

import pytest
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.auth import AccessToken

from src.main.python import auth
from src.main.python.config import Settings
from src.main.python.errors import ToolErrorPayload
from tests.server.conftest import TEST_AUDIENCE, TEST_ISSUER, TEST_TENANT_CLAIM


def test_build_auth_provider_is_none_when_disabled():
    cfg = Settings(AUTH_ENABLED=False)
    assert auth.build_auth_provider(cfg) is None


def test_settings_fail_fast_when_auth_enabled_without_oidc_config():
    with pytest.raises(ValueError, match="AUTH_ENABLED is on but missing"):
        Settings(AUTH_ENABLED=True)


def test_settings_force_auth_enabled_in_prod():
    # ENV=prod must force AUTH_ENABLED=True, so this fails fast on missing
    # OIDC config rather than silently starting unauthenticated.
    with pytest.raises(ValueError, match="AUTH_ENABLED is on but missing"):
        Settings(ENV="prod")


async def test_build_auth_provider_accepts_a_token_signed_by_the_configured_jwks(
    auth_settings, mock_jwks_server
):
    server, _ = mock_jwks_server
    token = server.issue_token(
        issuer=TEST_ISSUER,
        audience=TEST_AUDIENCE,
        claims={TEST_TENANT_CLAIM: "tenant-42"},
    )
    provider = auth.build_auth_provider(auth_settings)
    assert provider is not None

    access_token = await provider.verify_token(token)
    assert access_token is not None
    assert access_token.claims[TEST_TENANT_CLAIM] == "tenant-42"


async def test_build_auth_provider_rejects_a_token_with_the_wrong_audience(
    auth_settings, mock_jwks_server
):
    server, _ = mock_jwks_server
    token = server.issue_token(
        issuer=TEST_ISSUER,
        audience="someone-elses-server",
        claims={TEST_TENANT_CLAIM: "tenant-42"},
    )
    provider = auth.build_auth_provider(auth_settings)
    assert provider is not None

    access_token = await provider.verify_token(token)
    assert access_token is None


def test_get_current_identity_uses_a_fixed_dev_identity_when_auth_disabled():
    cfg = Settings(AUTH_ENABLED=False)
    identity = auth.get_current_identity(cfg)
    assert identity.tenant_id == "local-dev"


def test_get_current_identity_extracts_the_configured_tenant_claim(auth_settings, monkeypatch):
    fake_token = AccessToken(
        token="irrelevant",
        client_id="irrelevant",
        scopes=[],
        claims={TEST_TENANT_CLAIM: "tenant-42", "other": "ignored"},
    )
    monkeypatch.setattr(auth, "get_access_token", lambda: fake_token)

    identity = auth.get_current_identity(auth_settings)
    assert identity.tenant_id == "tenant-42"
    assert identity.claims == fake_token.claims


def test_get_current_identity_raises_unified_error_when_tenant_claim_missing(
    auth_settings, monkeypatch
):
    fake_token = AccessToken(token="irrelevant", client_id="irrelevant", scopes=[], claims={})
    monkeypatch.setattr(auth, "get_access_token", lambda: fake_token)

    with pytest.raises(ToolError) as exc_info:
        auth.get_current_identity(auth_settings)

    payload = ToolErrorPayload.model_validate_json(str(exc_info.value))
    assert payload.code == "AUTH_ERROR"
    assert payload.recoverable is False
