# Changelog

Notable changes to ChartNexus. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project is
pre-release and does not yet version its API.

Releases 1.2.0 through 1.5.0 were tagged without changelog entries; their
changes are not recorded here.

## [Unreleased]

## [1.6.0] — 2026-10-01

Futures: a real instrument universe, the Future Lab build-out, institutional
flow and index internals, global markets and a pre-market screener.

### Added

**The F&O universe (`instrument_catalog`)**

- The tradeable universe is now the full NSE F&O list — 210 stocks plus the
  index contracts, 219 catalog rows — carrying lot size, strike step, tick size,
  expiry style and the broker symbols needed to quote each one.
- Refreshed daily at 07:30 IST from the exchange's public symbol master, not
  pinned in a seed migration: NSE revises the list and the lot sizes by
  circular several times a year. The master files are public, so this needs no
  broker account and spends no API quota. New worker:
  `uv run chartnexus-catalog`.
- Reference prices, index membership and front-expiry columns, each with its own
  migration, so a page can rank or group the universe without a quote call.
- Stock expiries are monthly-only and strike steps are fractional for some
  names; both are modelled rather than assumed away.

**Future Lab**

- Stocks board, market movers (board, table and heatmap views), price-vs-OI and
  a session header with a data-source badge.
- An expiry picker that takes a *series index* — 0 near month, 1 next, 2 far —
  rather than a date, so a board stays valid across a rollover.
- Build-up classification (long build-up, short build-up, long unwinding, short
  covering) from price and open-interest change, with a legend.
- Open-interest sweep worker (`uv run chartnexus-futures-oi`): the broker's
  OI endpoint takes one contract per request, so the sweep is rate-limited to a
  small slice of the broker's throughput, runs every 300s, caches for 45
  minutes, and covers two series by default. Series past that depth still show
  price, volume and range, and the page says OI was not swept for them rather
  than drawing an empty board.
- Futures board capture worker (`uv run chartnexus-futures-history`): one
  frame a minute from batched quotes into `futures_board_snapshots`, 30 trading
  days retained, with `--once`, `--prune` and a guarded `--seed <date>` that
  fabricates a full 09:15–15:30 session stamped `mock`. Live boards only —
  generated numbers are never archived.
- `futures_analytics` context: the board dashboard and the price/OI series.

**Analysis — institutional flow and index internals (`market_breadth`)**

- Six pages under Future Lab: FII/DII summary, FII/DII cash, index
  contributors, advance/decline, index weightage and sector rotation.
- FII/DII reads four real NSE files. The cash segment has no archive, so it is
  journalled locally as it is observed.
- Intraday advance/decline is derived from the futures board archive; there is
  no separate breadth store.
- Index point contribution, a diverging board and a sector-breadth chart, all
  computed from catalog weights.

**Global Index Analysis (`global_markets`)**

- `/global-index-analysis`: overnight global markets and the handoff into the
  Indian session, with GIFT Nifty and settlement sources from NSE IX, Yahoo
  quotes and charts, and a simulated source so the page works with no feed.
- A gap journal, since the overnight gap cannot be reconstructed after the fact.

**Pre-Market Screener (`pre_market`)**

- `/pre-market-screener`: gap reading, expected move, regime and composed
  pre-market view, built on the shared level and statistics helpers now in the
  shared kernel.

**Options Lab**

- Intraday max-pain with a magnet-zone gauge on the Max Pain page, backed by a
  new max-pain series service.
- The expiry picker is now shared across the Options Lab pages, and the ingest
  can archive more than the front expiry (`CN_INGEST_EXPIRIES`, bounded by the
  same 42-day horizon the picker uses) so the series charts have a real session
  for further contracts.

**Dashboard**

- A gap indicator card, replacing quick actions.
- Self-hosted company logos in `frontend/public/logos/` with a symbol avatar
  fallback; the domain table is hand-authored on purpose.

### Changed

- `instrument_catalog` is now the source of truth for symbol resolution; the
  FYERS and mock adapters, the symbol/quote/option-chain mappers and the ingest
  loop all resolve through it.
- Ingest symbol selection defaults to every index in the catalog instead of a
  hard-coded pair, and is deliberately not the whole universe: an option-chain
  fetch is one broker call per symbol per tick against a 100k/day quota.
- Nifty 50 gap card rearranged on the dashboard; the Analyse page's symbol
  picker was replaced by the shared picker.
- `docs/RUNNING.md` documents the three new workers; `README.md` and
  `docs/architecture/bounded-contexts.md` now reflect fifteen implemented
  contexts.

### Fixed

- GIFT Nifty value mismatch between the dashboard card and the global view.
- The instrument-catalog registry retries its load, so a startup DB race no
  longer kills every page that needs symbol resolution.
- Future Lab expiry-dropdown behaviour across rollovers, and several FII/DII
  parsing and display bugs.
- Ampersand tickers (`M&M`, `L&TFH`) now resolve: they survive URL and broker
  symbol construction.
- The futures expiry picker reads the exchange date from its injected clock
  instead of the wall clock, so a pinned instant actually pins it.

### Removed

- Future Lab's `intraday` and `sentiment-cycle` routes, superseded by the board
  capture and the Analysis pages.

## [1.0.0] — 2026-08-13

### Changed

**Frontend migrated from SvelteKit to React** — see `docs/MIGRATION.md`.

- `frontend/` is now React Router v8 (framework mode) on React 19 and Vite 8,
  replacing SvelteKit 2 / Svelte 5. The backend, API contract, session cookies,
  CSRF handling and the `--cn-*` design tokens are unchanged.
- A framework swap, not a redesign: a pixel-diff harness (`pnpm parity`) checks
  every screen against the SvelteKit build at six viewport widths. All 96 checks
  pass. The last SvelteKit commit is `7a3144b`.
- Component styles moved to CSS Modules; state moved from Svelte runes to
  Zustand; `@tanstack/svelte-query` to `@tanstack/react-query`.
- New reusable chart layer under `app/lib/shared/charts` — one `<EChart>` mount
  point, a lifecycle hook, and chart options as pure, testable functions.
- Removed `layerchart`, `d3-scale`, `d3-shape` and `zod`: all four were declared
  but imported nowhere.
- New server-only `API_INTERNAL_URL` tells loaders where to reach the API,
  replacing SvelteKit's `handleFetch`.

### Fixed

- `/healthz` now exists. The container healthcheck in
  `deploy/docker/frontend.Dockerfile` has always requested it, but no such route
  was ever defined, so the probe was hitting the 404 page.
- No flash of the dark theme on load for users who chose a light one; the stored
  theme is applied before first paint.
- The Open Interest chart takes its axis, grid and tooltip colours from the
  design tokens, so the `warm` and `terminal` themes render correctly. It
  previously chose between two hard-coded palettes on a dark/light boolean.
- Token refresh no longer runs during SSR, where its single-flight promise was
  shared across concurrent requests instead of being scoped to one browser tab.

### Added

**Broker connections (`broker_connections` context)**

- FYERS OAuth 2.0 connect flow, per tenant. Each tenant registers their own
  broker API application; there is no shared system-wide account.
- Six endpoints under `/api/v1/broker/fyers`: save credentials, status, connect,
  callback, disconnect, revoke.
- Credentials and access tokens are encrypted at rest with AES-256-GCM, with the
  key derived from `CN_SECURITY_ENCRYPTION_KEY` through HKDF and separated by
  purpose. Secrets are never returned to a client and never logged.
- Each ciphertext is bound to its tenant, broker, and column as GCM associated
  data, so a value copied into another row or column fails to decrypt rather
  than being accepted.
- `CN_SECURITY_PREVIOUS_ENCRYPTION_KEYS` accepts retired keys, so the encryption
  key can be rotated without stranding existing connections.
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
- UI control scale tightened to a shared `--cn-control-h` token: 40px controls
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
