# Changelog

Notable changes to ChartNexus. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project is
pre-release and does not yet version its API.

Releases 1.2.0 through 1.5.0 were tagged without changelog entries; their
changes are not recorded here.

## [Unreleased]

## [1.8.0] — 2026-10-19

A real Relative Rotation Graph for sector rotation, the two inert Global
Settings controls wired up to something, and the three failing CI checks
greened — which meant fixing the bugs the drifted end-to-end suite had stopped
being able to report.

### Added

**Sector Rotation**

- Sector rotation is a classical Relative Rotation Graph now: RS-Ratio against
  RS-Momentum, each a z-score centred on 100, every sector carrying a tail that
  rotates clockwise through leading, weakening, lagging and improving.
  `GET /api/v1/breadth/sector-rotation/rrg` serves it at `15m`, `1h` or `1d`
  with a configurable tail length.
- The page used to plot strength against *participation* — the share of a
  sector's members advancing — because a momentum axis needs multi-period
  history and nothing stored it. The futures board archive is that history, so
  both axes are the real measure. Its depth is what decides what can be drawn,
  and the board says which limit it hit: thirteen captured sessions before the
  daily axis fills its window, two for the intraday ones. "24 of 35 periods"
  and "no sector could be priced" are different problems with different fixes.

**Future Lab**

- Flame glyph on the Future Lab header panel.

### Changed

- `--cn-bullish` / `--cn-bearish` were doing two unrelated jobs — direction (a
  price up, a sector advancing) and option side (CE vs PE) — so inverting calls
  and puts would have turned every falling price green. The meanings are
  separate now: direction keeps those tokens and the `up`/`down` chart roles
  and never follows the preference, while `--cn-call` / `--cn-put` and
  `--cn-call-series` / `--cn-put-series` carry the option side and swap under
  one `:root[data-callput='inverted']` rule.
- The `CALL_COLOR` / `PUT_COLOR` constants a dozen Options Lab pages imported
  are replaced by the chart theme's roles and a `useCallPutColors()` hook; a
  constant cannot follow a preference. Charts that asked for the `call`/`put`
  roles without drawing calls at all — advance/decline, the RRG quadrants, the
  futures heatmap, candles, the PCR reference line, the IV-HV spread — moved to
  `up`/`down`: same colours, now immune to the setting.
- Stock Watch loses its `New` chip in the Future Lab panel.
- The nginx image is scanned without a GitHub Actions layer cache. `apk
  upgrade` caches on its instruction text alone, so once a builder had run that
  layer the scanned image kept shipping the package set from whenever it was
  first built. Backend and web keep their caches, where the content moves with
  the Dockerfile and the lockfiles.

### Fixed

- Both controls on Settings → Global were inert: the preferences store wrote
  localStorage and a `data-callput` attribute nothing read, and the chart
  tooltip switch had no consumer at all.
- The tooltip preference lands in `EChart` as `showContent: false` rather than
  `show: false` — the latter drops the axis pointer and the `updateAxisPointer`
  event with it, which Gamma Exposure drives its side panel off.
- `useChartTheme` cached its palette behind a `MutationObserver` that only
  exists while a chart is mounted, so changing the setting on the chartless
  Settings page and navigating back repainted nothing. Theme switching was
  affected the same way.
- Futures Lab stock watch was hard-wired to call=red/put=green, contradicting
  the Options Lab. It follows the setting now.
- Every price, strike and greek on Stock Watch fell back to Consolas: the
  global `.cn-numeric` class asks for JetBrains Mono, the one font the app
  never self-hosted.
- Real bugs the end-to-end suite had stopped being able to report — a second
  `<main>` nested inside the one `root.tsx` already wraps every route in, in
  all three layouts; the landing drawer's `position: fixed` panel, which left
  the `<dialog>` no height, so a menu taller than the phone could not scroll
  and measured as hidden; Gamma Exposure's chart collapsing to nothing on a
  phone once the plot row stacked; and two contrast failures, the landing
  accent at 4.27:1 on a card and the settings sub-nav's active description
  against `--cn-accent-weak`.
- CI installed chromium only while `playwright.config.ts` also declares a
  firefox project, so every firefox test failed on a missing executable. Two
  flake sources closed with it: the stub API kept Node's 5s keep-alive timeout,
  which surfaced as `ECONNRESET` on whichever test sat between fetches, and the
  stub proxies now swallow a response disposed during teardown.

### Security

- `CVE-2026-77214` (HIGH, libexpat) in the nginx image, which Alpine had
  already fixed in `2.9.0-r0`. The gate was measuring a months-old `apk
  upgrade` layer rather than the package set the image actually ships.

## [1.7.0] — 2026-10-18

Realtime delivery over websockets, the Future Lab market-watch build-out, a
production deployment path with runbooks, and a sweep through the dependency
and container advisories.

### Added

**Realtime delivery**

- Websocket fan-out replaces polling for live quotes, with a browser client and
  a versioned message contract under `contracts/websocket/v1`. Wired through to
  production rather than left behind a flag.

**Future Lab**

- Market-watch page and a per-stock watch workspace: futures and chain panels,
  levels, contract compare, a trade plan, journal, alerts and events.
- Option-chain analytics for the workspace — Black-Scholes pricing, Greeks and
  derived levels — computed client-side from the chain.

**Operations**

- Deployment, backup, restore and certificate-issuance scripts under
  `scripts/operations/`, plus runbooks for local development, VPS deployment
  and production handoff.

### Changed

- Header nav collapses to five top-level items; the Options Lab mega-panel
  carries what the header no longer has room for.
- Nav-bar search panel for jumping to a module or instrument.
- Unbuilt placeholder boxes are gone from the Tools grid, and the `New` chip is
  gone from Sector Rotation — a menu full of dead entries trains readers to
  ignore it.
- Options Lab drops the `Timeseries` and `PE-CE Difference` placeholders. Both
  addresses redirect to the Lab index, so an open tab or a bookmark does not
  land on the root error page.
- The dev web container reaches the API over the compose network instead of its
  own loopback, which had failed every SSR render with `ECONNREFUSED`.

### Fixed

- Charts collapsed to 0px height in the production build.
- Premium Decay, Vega Analysis and the GAP indicator each read the chain wrong
  in ways that only showed on live data.
- The integration database now has a catalog to load, so the suite no longer
  depends on a catalog refresh having run first.

### Security

- Locked dependencies upgraded out of 24 advisories, including the critical and
  high findings under `react-router-serve`.
- Container CVEs cleared out of the base-image tooling, and `trivy-action`
  pinned to a tag that exists so the scan actually runs.

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
