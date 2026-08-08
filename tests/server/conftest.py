import pytest

from tests.server.auth.mock_jwks import MockJWKSServer

TEST_ISSUER = "https://mock-idp.test"
TEST_AUDIENCE = "my-mcp-template"
TEST_TENANT_CLAIM = "tid"


@pytest.fixture(scope="session")
def mock_jwks_server():
    server = MockJWKSServer()
    jwks_url = server.start()
    yield server, jwks_url
    server.stop()


@pytest.fixture
def auth_settings(mock_jwks_server):
    from src.main.python.config import Settings

    _, jwks_url = mock_jwks_server
    return Settings(
        AUTH_ENABLED=True,
        OIDC_ISSUER=TEST_ISSUER,
        JWKS_URL=jwks_url,
        AUDIENCE=TEST_AUDIENCE,
        TENANT_CLAIM_NAME=TEST_TENANT_CLAIM,
    )
