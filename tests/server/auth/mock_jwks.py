"""Self-signed JWKS server for testing JWT verification without a real IdP.

Used by test_auth.py (fast, unit-level) and test_container_smoke.py (slow,
full container integration) so neither depends on an external SSO provider.
"""

import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _b64url_uint(n: int) -> str:
    byte_length = (n.bit_length() + 7) // 8 or 1
    return base64.urlsafe_b64encode(n.to_bytes(byte_length, "big")).rstrip(b"=").decode()


class MockJWKSServer:
    def __init__(self) -> None:
        self._private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "test-key-1"
        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self, bind_host: str = "127.0.0.1", advertise_host: str | None = None) -> str:
        """Start serving JWKS on an ephemeral port; returns the JWKS URL.

        bind_host: interface to listen on. Use "0.0.0.0" so a docker
        container can reach this server on the host (see test_container_smoke.py).
        advertise_host: hostname to put in the returned URL, if different
        from bind_host (e.g. "host.docker.internal" from inside a container).
        """
        jwks_body = json.dumps(self._build_jwks()).encode()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 (stdlib method name)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(jwks_body)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                pass  # keep test output quiet

        self._httpd = HTTPServer((bind_host, 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        host = advertise_host or bind_host
        return f"http://{host}:{self._httpd.server_port}/jwks.json"

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()

    def issue_token(
        self,
        *,
        issuer: str,
        audience: str,
        claims: dict,
        expires_in: int = 300,
        algorithm: str = "RS256",
    ) -> str:
        now = int(time.time())
        payload = {"iss": issuer, "aud": audience, "iat": now, "exp": now + expires_in, **claims}
        private_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        return jwt.encode(payload, private_pem, algorithm=algorithm, headers={"kid": self.kid})

    def _build_jwks(self) -> dict:
        public_numbers = self._private_key.public_key().public_numbers()
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "kid": self.kid,
                    "use": "sig",
                    "alg": "RS256",
                    "n": _b64url_uint(public_numbers.n),
                    "e": _b64url_uint(public_numbers.e),
                }
            ]
        }
