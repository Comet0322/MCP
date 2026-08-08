from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ENV: Literal["dev", "prod"] = "dev"
    LOG_LEVEL: str = "INFO"

    # --- auth (SSO / OIDC resource server, multi-tenant) ---
    AUTH_ENABLED: bool = False
    OIDC_ISSUER: str | None = None
    JWKS_URL: str | None = None
    AUDIENCE: str | None = None
    # Claim to read the tenant/user id from. No universal default: every IdP
    # names this differently (Azure AD uses "tid", others use custom claims).
    TENANT_CLAIM_NAME: str | None = None

    # --- CORS ---
    # Comma-separated, e.g. "https://a.example.com,https://b.example.com".
    # Empty by default: MCP clients are CLI agents, not browsers. Only fill
    # this in if a browser-based client (e.g. a web inspector) needs access.
    # Plain str (not list[str]) so a hand-edited .env doesn't need JSON syntax.
    ALLOWED_ORIGINS: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    # --- agent e2e eval (tests/agent/) ---
    # Deliberately fixed to Anthropic/Claude: this layer tests whether a
    # Claude Code-like agent picks the right tool, so it should stay
    # representative of that actual client, not be provider-agnostic.
    ANTHROPIC_API_KEY: SecretStr | None = None
    AGENT_EVAL_MODEL: str = "claude-sonnet-5"

    # --- LLM judge (tests/golden/ assert_type: llm_judge) ---
    # Bring-your-own OpenAI-compatible provider: works with OpenAI itself,
    # NVIDIA NIM, DeepSeek, Together, a local vLLM/Ollama, etc. This is a
    # plain semantic-equivalence check, no provider-specific features
    # needed, so no vendor is hardcoded. No universal default -- fill in
    # for whichever provider you use, e.g.:
    #   LLM_JUDGE_BASE_URL=https://integrate.api.nvidia.com/v1
    #   LLM_JUDGE_MODEL=meta/llama-3.1-8b-instruct
    LLM_JUDGE_BASE_URL: str | None = None
    LLM_JUDGE_API_KEY: SecretStr | None = None
    LLM_JUDGE_MODEL: str | None = None
    LLM_JUDGE_THRESHOLD: float = 0.7  # TODO: tune per case

    # --- observability (Langfuse via OpenTelemetry, optional) ---
    # Opt-in, like LLM_JUDGE_*: unset by default, no tracer configured, zero
    # overhead. FastMCP has native OTel instrumentation (fastmcp.server.telemetry)
    # that emits a span for every tool/resource/prompt call automatically --
    # see observability.py, which just points a standard OTel SDK at
    # Langfuse's OTLP endpoint. LANGFUSE_BASE_URL defaults to Langfuse Cloud;
    # override for a self-hosted instance.
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: SecretStr | None = None
    LANGFUSE_BASE_URL: str = "https://cloud.langfuse.com"

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.LANGFUSE_PUBLIC_KEY and self.LANGFUSE_SECRET_KEY)

    @model_validator(mode="after")
    def _enforce_prod_auth(self) -> "Settings":
        if self.ENV == "prod":
            object.__setattr__(self, "AUTH_ENABLED", True)
        if self.AUTH_ENABLED:
            missing = [
                name
                for name, value in (
                    ("OIDC_ISSUER", self.OIDC_ISSUER),
                    ("JWKS_URL", self.JWKS_URL),
                    ("AUDIENCE", self.AUDIENCE),
                    ("TENANT_CLAIM_NAME", self.TENANT_CLAIM_NAME),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    "AUTH_ENABLED is on but missing required settings: "
                    f"{', '.join(missing)}. Set these to your organization's "
                    "OIDC provider values before starting in this mode."
                )
        return self


settings = Settings()
