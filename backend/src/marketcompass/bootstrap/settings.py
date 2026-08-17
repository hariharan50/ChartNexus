"""Application settings.

Every value is read from the environment exactly once, at process start, and
validated here. Nothing below this module reads ``os.environ`` — code takes a
settings object instead, so tests can construct one without touching the
process environment.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_PREFIX = "MC_"


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"

    @property
    def is_deployed(self) -> bool:
        return self in (Environment.STAGING, Environment.PRODUCTION)


def _section_config(suffix: str) -> SettingsConfigDict:
    """Shared config for every settings section, differing only in env prefix."""
    return SettingsConfigDict(
        env_prefix=f"{_ENV_PREFIX}{suffix}",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        validate_default=True,
    )


class _Section(BaseSettings):
    model_config = _section_config("")


class DatabaseSettings(_Section):
    model_config = _section_config("DB_")

    url: PostgresDsn = Field(
        default=PostgresDsn(
            "postgresql+asyncpg://marketcompass:marketcompass@localhost:5432/marketcompass"
        ),
        description="Async SQLAlchemy DSN. Must use the asyncpg driver.",
    )
    pool_size: int = Field(default=10, ge=1, le=100)
    max_overflow: int = Field(default=10, ge=0, le=100)
    pool_timeout_seconds: float = Field(default=10.0, gt=0)
    pool_recycle_seconds: int = Field(default=1800, gt=0)
    statement_timeout_ms: int = Field(default=15_000, gt=0)
    echo: bool = False

    @field_validator("url")
    @classmethod
    def _require_async_driver(cls, value: PostgresDsn) -> PostgresDsn:
        if value.scheme != "postgresql+asyncpg":
            msg = f"database URL must use the postgresql+asyncpg driver, got {value.scheme!r}"
            raise ValueError(msg)
        return value


class RedisSettings(_Section):
    model_config = _section_config("REDIS_")

    url: RedisDsn = Field(default=RedisDsn("redis://localhost:6379/0"))
    max_connections: int = Field(default=50, ge=1)
    socket_timeout_seconds: float = Field(default=5.0, gt=0)
    key_prefix: str = "mc"


class SecuritySettings(_Section):
    model_config = _section_config("SECURITY_")

    secret_key: SecretStr = Field(
        default=SecretStr("dev-only-insecure-secret-key-change-me"),
        description="Signs sessions and websocket tickets. Rotate per environment.",
    )
    encryption_key: SecretStr = Field(
        default=SecretStr("dev-only-insecure-encryption-key-change"),
        description="AES-256-GCM key material for broker credentials at rest. "
        "At least 32 bytes; derived through HKDF, so any long string works.",
    )
    previous_encryption_keys: SecretStr = Field(
        default=SecretStr(""),
        description="Comma-separated retired encryption keys. Values still "
        "decrypt under these, but are re-encrypted under the current key on "
        "the next write. Drop a key once nothing decrypts with it.",
    )

    session_ttl_seconds: int = Field(default=60 * 60 * 12, gt=0)
    session_idle_timeout_seconds: int = Field(default=60 * 60 * 2, gt=0)
    websocket_ticket_ttl_seconds: int = Field(default=60, gt=0)
    cookie_domain: str | None = None
    cookie_secure: bool = True
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    password_min_length: int = Field(default=12, ge=8)
    argon2_time_cost: int = Field(default=3, ge=1)
    argon2_memory_cost_kib: int = Field(default=65_536, ge=8192)
    argon2_parallelism: int = Field(default=4, ge=1)

    @property
    def retired_encryption_keys(self) -> tuple[str, ...]:
        """Retired keys, newest first, as the cipher wants them."""
        raw = self.previous_encryption_keys.get_secret_value()
        return tuple(part.strip() for part in raw.split(",") if part.strip())


class AuthSettings(_Section):
    """JWT issuance and session policy."""

    model_config = _section_config("AUTH_")

    jwt_algorithm: Literal["HS256", "RS256"] = "HS256"
    jwt_signing_key: SecretStr = Field(
        default=SecretStr(""),
        description="HS256 secret, or the RS256 private key in PEM form. "
        "Falls back to MC_SECURITY_SECRET_KEY when empty.",
    )
    jwt_public_key: SecretStr = Field(
        default=SecretStr(""),
        description="RS256 public key in PEM form. Unused for HS256.",
    )
    jwt_key_id: str = Field(
        default="mc-1",
        description="`kid` header, so keys can be rotated without invalidating "
        "every token in flight.",
    )
    issuer: str = "marketcompass"
    audience: str = "marketcompass-api"

    # Short access tokens because they cannot be revoked; revocation happens at
    # refresh time, so the blast radius of a leaked access token is this window.
    access_token_ttl_seconds: int = Field(default=15 * 60, gt=0)
    refresh_token_ttl_seconds: int = Field(default=30 * 24 * 60 * 60, gt=0)
    # Rotation invalidates the old refresh token immediately; a small grace
    # window keeps a double-submit from a racing tab from logging the user out.
    refresh_reuse_grace_seconds: int = Field(default=10, ge=0)
    max_active_sessions_per_user: int = Field(default=10, ge=1)

    registration_enabled: bool = True
    require_email_verification: bool = False

    login_max_attempts: int = Field(default=8, ge=1)
    login_attempt_window_seconds: int = Field(default=15 * 60, gt=0)
    login_lockout_seconds: int = Field(default=15 * 60, gt=0)

    access_cookie_name: str = "mc_at"
    refresh_cookie_name: str = "mc_rt"
    csrf_cookie_name: str = "mc_csrf"
    # The refresh cookie is only ever sent to the endpoints that need it.
    refresh_cookie_path: str = "/api/v1/auth"


class GoogleOAuthSettings(_Section):
    model_config = _section_config("GOOGLE_")

    client_id: str = ""
    client_secret: SecretStr = SecretStr("")
    redirect_uri: str = "http://localhost:5173/auth/google/callback"
    scopes: tuple[str, ...] = ("openid", "email", "profile")
    # When set, only Workspace accounts in these domains may sign in.
    allowed_hosted_domains: tuple[str, ...] = ()
    # Login attempts must complete inside this window; it bounds how long a
    # stolen state parameter stays usable.
    state_ttl_seconds: int = Field(default=10 * 60, gt=0)
    request_timeout_seconds: float = Field(default=10.0, gt=0)
    jwks_cache_seconds: int = Field(default=60 * 60, gt=0)

    authorization_endpoint: str = "https://accounts.google.com/o/oauth2/v2/auth"
    token_endpoint: str = "https://oauth2.googleapis.com/token"  # noqa: S105 — a URL
    jwks_uri: str = "https://www.googleapis.com/oauth2/v3/certs"
    issuers: tuple[str, ...] = ("https://accounts.google.com", "accounts.google.com")

    @property
    def enabled(self) -> bool:
        return bool(self.client_id and self.client_secret.get_secret_value())


class BrokerSettings(_Section):
    model_config = _section_config("BROKER_")

    provider: Literal["fyers", "mock"] = "mock"
    fyers_app_id: str = ""
    fyers_secret_id: SecretStr = SecretStr("")
    fyers_redirect_uri: str = "http://localhost:5173/settings/broker/callback"
    rest_base_url: str = "https://api-t1.fyers.in/api/v3"
    quota_requests_per_second: int = Field(default=8, ge=1)
    quota_requests_per_day: int = Field(default=100_000, ge=1)
    request_timeout_seconds: float = Field(default=10.0, gt=0)
    circuit_breaker_failure_threshold: int = Field(default=5, ge=1)
    circuit_breaker_reset_seconds: float = Field(default=30.0, gt=0)


class LLMSettings(_Section):
    model_config = _section_config("LLM_")

    provider: Literal["anthropic", "openai", "openrouter", "rule_based"] = "rule_based"
    anthropic_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    model: str = "claude-sonnet-5"
    # Room for a full agent answer plus any model-side thinking. 2048 truncated
    # multi-part trade calls mid-sentence; raise via MC_LLM_MAX_OUTPUT_TOKENS.
    max_output_tokens: int = Field(default=4096, ge=1)
    request_timeout_seconds: float = Field(default=30.0, gt=0)
    daily_token_budget: int = Field(default=1_000_000, ge=0)
    # Appends the "educational, not investment advice" line to analytical agent
    # answers. Set MC_LLM_AGENT_DISCLAIMER=false to bypass it while testing.
    agent_disclaimer: bool = True

    # OpenRouter is the OpenAI wire protocol pointed at an aggregator, so model
    # IDs are namespaced (e.g. "anthropic/claude-3.7-sonnet") and won't match the
    # native ``model`` above — it gets its own field, selected by ``resolved_model``.
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_model: str = "anthropic/claude-3.7-sonnet"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Optional OpenRouter ranking headers. Sent only when set.
    openrouter_site_url: str = ""  # HTTP-Referer
    openrouter_app_name: str = ""  # X-Title

    @property
    def resolved_model(self) -> str:
        """The model ID for the selected provider (OpenRouter uses its own)."""
        return self.openrouter_model if self.provider == "openrouter" else self.model

    @property
    def openrouter_headers(self) -> dict[str, str]:
        """OpenRouter ranking headers, omitting any that are unset."""
        headers: dict[str, str] = {}
        if self.openrouter_site_url:
            headers["HTTP-Referer"] = self.openrouter_site_url
        if self.openrouter_app_name:
            headers["X-Title"] = self.openrouter_app_name
        return headers


class ObservabilitySettings(_Section):
    model_config = _section_config("OTEL_")

    service_name: str = "marketcompass"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    traces_enabled: bool = False
    metrics_enabled: bool = True
    exporter_endpoint: str = "http://localhost:4317"
    trace_sample_ratio: float = Field(default=0.1, ge=0.0, le=1.0)


class MarketSettings(_Section):
    """Exchange-facing constants. India/NSE by default."""

    model_config = _section_config("MARKET_")

    timezone: str = "Asia/Kolkata"
    session_open: str = "09:15"
    # 15:40, not the 15:30 cash close: from 3 August 2026 equity derivatives run
    # ten minutes past it, and every consumer of this setting — market status,
    # the ingest worker — is derivatives-facing.
    session_close: str = "15:40"
    snapshot_interval_seconds: int = Field(default=180, ge=1)
    quote_staleness_seconds: int = Field(default=15, ge=1)
    # FYERS' option chain never includes IV/greeks, so ATM IV is back-solved
    # from price via Black-Scholes. This is the annualised risk-free rate that
    # solve uses — a ballpark short-term G-Sec yield, not precise enough to
    # trade on, only to display.
    risk_free_rate: float = Field(default=0.07, ge=0.0, le=1.0)

    # Ingestion (the option-chain snapshot writer).
    ingest_symbols: tuple[str, ...] = ("NIFTY", "BANKNIFTY", "SENSEX")
    # Off by default: a mock-fallback day writes nothing, leaving an honest gap.
    # Turn on locally to generate test history without a live broker connection.
    ingest_allow_mock: bool = False
    # In LOCAL only, the API runs the capture loop itself as a background task, so
    # a developer who starts just the API still gets a populated archive rather
    # than the Options Lab charts' two-point "open vs now" estimate. Ignored
    # outside local, where the standalone ``marketcompass-ingest`` process is the
    # only writer. Set false when running that separate worker alongside the API
    # (as ``task dev`` does) to avoid double captures.
    ingest_in_process: bool = True
    # How long the option-chain archive is kept. Its only consumer reads today,
    # so a month is generous; a year of unpruned ingest is ~8M rows.
    snapshot_retention_days: int = Field(default=30, ge=1)
    # Strikes either side of ATM kept in the intraday series the OI tool reads.
    # Tunable because it is the main lever on payload size: the widest filter
    # the UI offers is +-20, so anything at or above that is a superset.
    snapshot_max_series_strikes: int = Field(default=25, ge=1)
    # How many days of price candles the durable chart cache keeps. It is a
    # bounded write-through cache pruned on every write, so this stays small; the
    # chart shows three days of intraday history comfortably.
    candle_cache_retention_days: int = Field(default=3, ge=1)


class Settings(BaseSettings):
    """Root settings object. Build it once per process via :func:`get_settings`."""

    model_config = SettingsConfigDict(
        env_prefix=_ENV_PREFIX,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    environment: Environment = Environment.LOCAL
    debug: bool = False
    api_root_path: str = ""
    cors_allow_origins: tuple[str, ...] = ("http://localhost:5173",)
    request_timeout_seconds: float = Field(default=30.0, gt=0)

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    google: GoogleOAuthSettings = Field(default_factory=GoogleOAuthSettings)
    broker: BrokerSettings = Field(default_factory=BrokerSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    market: MarketSettings = Field(default_factory=MarketSettings)

    def assert_deployment_safe(self) -> None:
        """Fail fast when a deployed environment still holds development defaults."""
        if not self.environment.is_deployed:
            return

        problems: list[str] = []
        if "dev-only" in self.security.secret_key.get_secret_value():
            problems.append("MC_SECURITY_SECRET_KEY is still the development default")
        if "dev-only" in self.security.encryption_key.get_secret_value():
            problems.append("MC_SECURITY_ENCRYPTION_KEY is still the development default")
        if self.debug:
            problems.append("MC_DEBUG must be false outside local development")
        if not self.security.cookie_secure:
            problems.append("MC_SECURITY_COOKIE_SECURE must be true when deployed")
        if self.broker.provider == "mock":
            problems.append("MC_BROKER_PROVIDER is 'mock' in a deployed environment")
        if self.auth.jwt_algorithm == "HS256" and not self.auth.jwt_signing_key.get_secret_value():
            problems.append(
                "MC_AUTH_JWT_SIGNING_KEY must be set explicitly when deployed "
                "rather than inherited from the application secret key"
            )
        if self.auth.jwt_algorithm == "RS256" and not self.auth.jwt_public_key.get_secret_value():
            problems.append("MC_AUTH_JWT_PUBLIC_KEY is required for RS256")

        if problems:
            msg = "unsafe configuration for {}: {}".format(
                self.environment.value, "; ".join(problems)
            )
            raise RuntimeError(msg)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, constructing them on first use."""
    settings = Settings()
    settings.assert_deployment_safe()
    return settings
