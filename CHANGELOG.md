# Changelog

Notable changes to MarketCompass. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project is
pre-release and does not yet version its API.

## [Unreleased]

### Added

**Broker connections (`broker_connections` context)**

- FYERS OAuth 2.0 connect flow, per tenant. Each tenant registers their own
  broker API application; there is no shared system-wide account.
- Six endpoints under `/api/v1/broker/fyers`: save credentials, status, connect,
  callback, disconnect, revoke.
- Credentials and access tokens are Fernet-encrypted at rest, with the key
  derived from `MC_SECURITY_ENCRYPTION_KEY` through HKDF and separated by
  purpose. Secrets are never returned to a client and never logged.
- OAuth `state` is single-use, TTL-bounded, and bound to the tenant and user
  that began the flow. Unknown, expired, replayed and mismatched states are
  rejected identically.
- Disconnect and revoke are distinct: disconnect drops the token and keeps the
  API keys; revoke drops both.
- Status is verified against the broker's profile endpoint rather than inferred
  from the presence of a token.

**Market data (`market_data` context)**

- Four endpoints under `/api/v1/market`: status, spot, option-chain, expiries,
  covering NIFTY, BANKNIFTY and SENSEX.
- Canonical option chain with put/call ratio and at-the-money strike computed
  from the listed strikes.
- Every payload carries `provenance.source` (`live` / `cached` / `mock`) and
  `age_seconds`. Degradation follows `fresh cache → live → last-good → mock` and
  the rung reached is always reported.
- A deterministic mock provider, so the application runs fully without a broker
  account.

**FYERS adapter**

- Direct HTTPS client against the v3 API — the `fyers-apiv3` SDK is deliberately
  not a dependency (see ADR 0001).
- Response mappers that parse the broker's snake_case keys and treat the
  `strike_price == -1` entry as the underlying index rather than a strike.
- Expiry dates read from the broker and normalised to ISO from four formats;
  epoch values resolve in exchange time (IST), not UTC.
- Retry with jittered backoff for timeouts, 5xx and 429 only — authentication
  failures are never retried. Circuit breaker and Redis-backed request quota.

**Frontend**

- Broker settings page with connection status, credential entry, and connect /
  disconnect / revoke.
- OAuth callback route at `/settings/broker/callback`.
- `DataSourceBadge` component distinguishing live, cached and simulated data.

**Documentation**

- [ADR 0001](docs/adr/0001-fyers-broker-integration.md) recording the four
  load-bearing decisions.
- [docs/architecture/bounded-contexts.md](docs/architecture/bounded-contexts.md)
  describing the context boundary rule and how to verify it.

### Changed

- Shared FastAPI plumbing (`get_session`, `SessionUnitOfWork`, `Principal`,
  `CurrentPrincipal`) moved from `contexts/identity/api/dependencies.py` to
  `infrastructure/transport/http/dependencies.py`. Every context's router needs
  it, so leaving it in `identity` forced other contexts to import across a
  boundary. Identity re-exports the names, so existing imports still resolve.
- UI control scale tightened to a shared `--mc-control-h` token: 40px controls
  and 14px body text, down from 52px and 16px.
- Removed the non-functional "Continue with Microsoft" button; there is no
  Microsoft identity provider behind it.

### Security

- Verified by integration test that broker secrets reach Postgres as ciphertext
  and that the plaintext appears in no column.
- Verified that an OAuth state cannot be replayed, and that one tenant cannot
  redeem a state created by another.
- Broker connections are isolated per tenant, enforced by a unique partial index
  on `(tenant_id, broker) WHERE status = 'active'`.

### Known limitations

- FYERS endpoint paths were confirmed from secondary sources; their published
  documentation is a JavaScript application and could not be read directly. All
  URLs are isolated in `infrastructure/brokers/fyers/rest_client.py` and have
  not yet been exercised against a live account.
- Streaming — the periodic poller and websocket fan-out — is not built yet.
- `ExchangeCalendar` knows weekends and session hours but not trading holidays.
- Email verification and password reset remain stubbed pending an email adapter.

## [0.1.0] — 2026-08-01

### Added

- Project skeleton: FastAPI backend, SvelteKit frontend, Docker Compose stack,
  Alembic migrations, and the architecture test suite.
- `identity` context: registration, email/password sign-in, Google SSO, JWT
  access tokens with refresh rotation and reuse detection, and session
  management over both httpOnly cookies and `Authorization: Bearer`.
