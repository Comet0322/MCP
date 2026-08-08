from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- server ---
    HOST: str = "0.0.0.0"  # noqa: S104 -- must bind all interfaces to be reachable from outside the container
    PORT: int = 8000
    ENV: Literal["dev", "prod"] = "dev"
    LOG_LEVEL: str = "INFO"

    # --- CORS ---
    # Comma-separated, e.g. "https://a.example.com,https://b.example.com".
    # Empty by default: MCP clients are CLI agents, not browsers. Only fill
    # this in if a browser-based client (e.g. a web inspector) needs access.
    # Plain str (not list[str]) so a hand-edited .env doesn't need JSON syntax.
    ALLOWED_ORIGINS: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    # --- LLM judge (tests/golden/ assert_type: llm_judge) and tool selection
    # eval (tests/agent/test_tool_selection.py) ---
    # Bring-your-own OpenAI-compatible provider: works with OpenAI itself,
    # NVIDIA NIM, DeepSeek, Together, a local vLLM/Ollama, etc. Both layers
    # only need plain chat-completions + tool-calling, no provider-specific
    # features, so no vendor is hardcoded and both share this one config.
    # The model must support tool/function calling for tests/agent/ to work.
    # No universal default -- fill in for whichever provider you use, e.g.:
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


settings = Settings()
