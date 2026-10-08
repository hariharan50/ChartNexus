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

_ENV_PREFIX = "CN_"


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
        default=PostgresDsn("postgresql+asyncpg://chartnexus:chartnexus@localhost:5432/chartnexus"),
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
    key_prefix: str = "cn"


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
        "Falls back to CN_SECURITY_SECRET_KEY when empty.",
    )
    jwt_public_key: SecretStr = Field(
        default=SecretStr(""),
        description="RS256 public key in PEM form. Unused for HS256.",
    )
    jwt_key_id: str = Field(
        default="cn-1",
        description="`kid` header, so keys can be rotated without invalidating "
        "every token in flight.",
    )
    issuer: str = "chartnexus"
    audience: str = "chartnexus-api"

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

    access_cookie_name: str = "cn_at"
    refresh_cookie_name: str = "cn_rt"
    csrf_cookie_name: str = "cn_csrf"
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
    # multi-part trade calls mid-sentence; 4096 truncated MME100's detailed
    # six-section pre-market read. Raise further via CN_LLM_MAX_OUTPUT_TOKENS.
    max_output_tokens: int = Field(default=8192, ge=1)
    request_timeout_seconds: float = Field(default=30.0, gt=0)
    daily_token_budget: int = Field(default=1_000_000, ge=0)
    # Appends the "educational, not investment advice" line to analytical agent
    # answers. Set CN_LLM_AGENT_DISCLAIMER=false to bypass it while testing.
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

    service_name: str = "chartnexus"
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
    #
    # Empty means "every index in the instrument catalog", which is the sane
    # default and the only one that survives the catalog changing underneath
    # us. Set it explicitly to pin a subset.
    #
    # Deliberately NOT the whole universe: an option-chain fetch is one broker
    # call per symbol per tick and the quota is 100k/day, so 216 symbols at the
    # default 180s cadence would be ~103,680 calls/day before a single user
    # request. Stock-level analytics need a cheaper feed than this loop.
    ingest_symbols: tuple[str, ...] = ()
    # Off by default: a mock-fallback day writes nothing, leaving an honest gap.
    # Turn on locally to generate test history without a live broker connection.
    ingest_allow_mock: bool = False
    # How many expiries to archive per symbol, nearest first.
    #
    # One by default, which is what the archive has always held - and the reason
    # the Options Lab series charts fall back to "open vs now" the moment a
    # reader picks anything but the front contract. Raising it gives those pages
    # a real session for further expiries, at a directly proportional cost:
    # this multiplies both the broker calls per tick and the stored rows. At the
    # 100k/day quota, two symbols x six expiries on the default 180s cadence is
    # already ~5,760 calls/day. Bounded by the same 42-day horizon the expiry
    # picker uses, so it can never run away.
    ingest_expiries: int = Field(default=1, ge=1, le=12)
    # In LOCAL only, the API runs the capture loop itself as a background task, so
    # a developer who starts just the API still gets a populated archive rather
    # than the Options Lab charts' two-point "open vs now" estimate. Ignored
    # outside local, where the standalone ``chartnexus-ingest`` process is the
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


class HuginSettings(_Section):
    """The autonomous market-memory worker (HUGIN).

    HUGIN wakes on the hour during the IST session, snapshots each instrument per
    tenant, judges last hour's read and records a new one to durable memory. The
    LLM key is per-user (the tenant owner's saved ``ai_settings`` key), so there is
    deliberately no key setting here — only cadence and fan-out controls.
    """

    model_config = _section_config("HUGIN_")

    #: Master switch for the worker. Off leaves the read API returning empty memory.
    enabled: bool = True
    #: LOCAL-only auto-start inside the API lifespan, like ``market.ingest_in_process``.
    in_process: bool = True
    #: Tick cadence. Default hourly; drop to e.g. 60 locally to watch memory accrue.
    interval_seconds: int = Field(default=3600, ge=1)
    #: Snap ticks to the :15 session boundaries rather than free-running from start.
    align_to_open: bool = True
    #: Which instruments HUGIN tracks each tick.
    instruments: tuple[str, ...] = ("NIFTY", "BANKNIFTY", "SENSEX")
    #: Fan-out guard: at most this many tenants processed per tick.
    max_tenants_per_tick: int = Field(default=50, ge=1)
    #: How many top lessons (by reliability) are fed back into the reflect prompt.
    lessons_top_k: int = Field(default=8, ge=0)


class Mme100Settings(_Section):
    """The autonomous pre-market briefing worker (MME100).

    Once each trading morning MME100 builds each enrolled tenant's analyst from the
    owner's saved ``ai_settings`` key and writes the day's six-section pre-market
    briefing. The LLM key is per-user, so there is deliberately no key setting here
    — only cadence, fan-out, and the web-search budget.
    """

    model_config = _section_config("MME100_")

    #: Master switch for the worker. Off leaves the read API returning no briefing.
    enabled: bool = True
    #: LOCAL-only auto-start inside the API lifespan, like ``hugin.in_process``.
    in_process: bool = True
    #: The IST wall-clock time the briefing runs, before the 09:15 open.
    briefing_time_ist: str = "08:30"
    #: Which instruments the briefing covers each morning.
    instruments: tuple[str, ...] = ("NIFTY", "BANKNIFTY", "SENSEX")
    #: Fan-out guard: at most this many tenants processed per run.
    max_tenants_per_tick: int = Field(default=50, ge=1)
    #: Max Anthropic web-searches per analytical turn. 0 disables web search (the
    #: escape hatch if the built-in tool misbehaves), leaving the India tools intact.
    web_search_max_uses: int = Field(default=5, ge=0)


class MessagingSettings(_Section):
    """Outbound messaging channels (Telegram now; WhatsApp later).

    Credentials are per-user (encrypted via ``messaging_cipher``), so there is no
    key here — only the provider endpoints and transport knobs.
    """

    model_config = _section_config("MESSAGING_")

    telegram_api_base: str = "https://api.telegram.org"
    request_timeout_seconds: float = Field(default=10.0, gt=0)


class ReportSettings(_Section):
    """The daily market-report worker.

    Once each trading morning (default 08:35 IST, just after the MME100 briefing so
    it can reuse it) it renders the branded PDF per enrolled tenant and delivers it
    to their channels. Per-user LLM key, so no key setting here — only cadence and
    which instruments the scheduled report covers.
    """

    model_config = _section_config("REPORT_")

    enabled: bool = True
    #: LOCAL-only auto-start inside the API lifespan, like the other workers.
    in_process: bool = True
    #: IST wall-clock time the report runs (after the 08:30 briefing).
    report_time_ist: str = "08:35"
    #: Instruments the scheduled report covers (one by default to stay token-light;
    #: users can generate others on demand).
    instruments: tuple[str, ...] = ("NIFTY",)
    max_tenants_per_tick: int = Field(default=50, ge=1)


class CatalogSettings(_Section):
    """The instrument-catalog refresh worker.

    The F&O universe — which underlyings exist, their lot sizes, and the broker
    symbols needed to quote them — is refreshed daily from the exchange symbol
    master rather than pinned in a seed migration, because NSE revises the list
    and the lot sizes by circular several times a year. The master files are
    public, so this needs no broker account and spends no API quota.
    """

    model_config = _section_config("CATALOG_")

    enabled: bool = True
    #: LOCAL-only auto-start inside the API lifespan, like the other workers.
    in_process: bool = True
    #: IST wall-clock time the refresh runs. Well before the 09:15 open, so a
    #: lot-size revision is in place for the session it applies to.
    refresh_time_ist: str = "07:30"
    #: Fill the catalog at startup *if it is empty*. An empty catalog means no
    #: instrument resolves at all, so a first run should not have to wait for
    #: tomorrow's refresh. A populated catalog is left alone: the masters are
    #: ~19 MB and the API runs this loop under ``--reload``.
    sync_on_start: bool = True
    #: How often every *other* process re-reads the catalog into its own
    #: in-memory registry. One cheap ``SELECT``, so this can be frequent; it is
    #: what carries a refresh from the catalog worker across to the API and the
    #: other workers without a redeploy. See
    #: ``catalog_runtime.run_registry_refresh_loop``.
    registry_refresh_seconds: int = Field(default=900, ge=30)


class FuturesOpenInterestSettings(_Section):
    """The open-interest sweep behind the Future Lab's build-up columns.

    The broker endpoint carrying open interest takes one contract per request,
    so the whole universe is ~220 requests. At the board's refresh rate that
    would be roughly 340,000 a day against a 100,000 quota; on this cadence it
    is about 17,000, and open interest moves slowly enough that a reading a few
    minutes old classifies a build-up just as well as a fresh one.
    """

    model_config = _section_config("FUTURES_OI_")

    enabled: bool = True
    #: LOCAL-only auto-start inside the API lifespan, like the other workers.
    in_process: bool = True
    #: Seconds between sweeps.
    interval_seconds: int = Field(default=300, ge=60)
    #: Requests per second the sweep may use. A deliberately small slice of the
    #: broker's eight, which is shared with every user request: filling a
    #: background column must never make someone's page slow.
    requests_per_second: float = Field(default=2.0, gt=0, le=8.0)
    #: How long a cached reading stays usable. Long enough that one failed
    #: sweep does not blank the board, short enough that yesterday's figures
    #: can never pass for today's.
    ttl_seconds: int = Field(default=45 * 60, ge=60)
    #: How many contract series the sweep covers — 1 is the near month only,
    #: 2 adds the next, 3 the far.
    #:
    #: The cost is linear: each series is another pass over the universe. At
    #: the defaults above (~220 contracts at 2/s) one series takes ~110s of the
    #: 300s interval, so two fit comfortably and three do not — raise
    #: ``interval_seconds`` or ``requests_per_second`` alongside a depth of 3,
    #: and check the depth against the daily quota (~17,000 requests per series
    #: per day against 100,000).
    #:
    #: Series past this depth are still selectable on the board: they show
    #: price, volume and the day's range, and the page says open interest was
    #: not swept for them rather than drawing an empty build-up board.
    expiry_depth: int = Field(default=2, ge=1, le=3)


class FuturesBoardHistorySettings(_Section):
    """The board capture behind Future Lab's intraday charts and Replay.

    Separate from the open-interest sweep, and deliberately faster. Price
    arrives from batched quotes — fifty symbols per request, so the whole
    universe costs five calls and a minute-by-minute cadence is about 1,900
    requests a day. Open interest costs one request per contract, which is why
    its sweep runs on five minutes; each frame carries the most recent reading
    that sweep left behind.
    """

    model_config = _section_config("FUTURES_HISTORY_")

    enabled: bool = True
    #: LOCAL-only auto-start inside the API lifespan, like the other workers.
    in_process: bool = True
    #: Seconds between captures. Frames are stamped on this boundary, so a
    #: restarted worker re-capturing an interval cannot double up the series.
    interval_seconds: int = Field(default=60, ge=15)
    #: Trading days kept before the prune drops them.
    retention_days: int = Field(default=30, ge=1)


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
    hugin: HuginSettings = Field(default_factory=HuginSettings)
    mme100: Mme100Settings = Field(default_factory=Mme100Settings)
    messaging: MessagingSettings = Field(default_factory=MessagingSettings)
    report: ReportSettings = Field(default_factory=ReportSettings)
    catalog: CatalogSettings = Field(default_factory=CatalogSettings)
    futures_oi: FuturesOpenInterestSettings = Field(default_factory=FuturesOpenInterestSettings)
    futures_history: FuturesBoardHistorySettings = Field(
        default_factory=FuturesBoardHistorySettings
    )

    def assert_deployment_safe(self) -> None:
        """Fail fast when a deployed environment still holds development defaults."""
        if not self.environment.is_deployed:
            return

        problems: list[str] = []
        if "dev-only" in self.security.secret_key.get_secret_value():
            problems.append("CN_SECURITY_SECRET_KEY is still the development default")
        if "dev-only" in self.security.encryption_key.get_secret_value():
            problems.append("CN_SECURITY_ENCRYPTION_KEY is still the development default")
        if self.debug:
            problems.append("CN_DEBUG must be false outside local development")
        if not self.security.cookie_secure:
            problems.append("CN_SECURITY_COOKIE_SECURE must be true when deployed")
        if self.broker.provider == "mock":
            problems.append("CN_BROKER_PROVIDER is 'mock' in a deployed environment")
        if self.auth.jwt_algorithm == "HS256" and not self.auth.jwt_signing_key.get_secret_value():
            problems.append(
                "CN_AUTH_JWT_SIGNING_KEY must be set explicitly when deployed "
                "rather than inherited from the application secret key"
            )
        if self.auth.jwt_algorithm == "RS256" and not self.auth.jwt_public_key.get_secret_value():
            problems.append("CN_AUTH_JWT_PUBLIC_KEY is required for RS256")

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
