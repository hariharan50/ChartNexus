# ADR 0002 — Zerodha Kite Connect integration

- **Status:** accepted
- **Date:** 2026-11-18
- **Scope:** market data only — login, profile, quotes, futures and OI, the
  futures board, option chains, expiries, history, live ticks and the daily
  instrument catalog. No orders, positions, holdings, margins or GTT. ADR 0001's
  read-only promise holds for Kite too.
- **Supersedes:** nothing. Extends ADR 0001 to a second broker.

## Context

ChartNexus reads live NSE/BSE data through each tenant's own broker account.
FYERS was the only broker (ADR 0001). Zerodha Kite Connect is added as a second
one for this single-user-per-tenant SaaS. Kite differs from FYERS in ways that
matter: its access token is a **trading** credential and dies at 06:00 IST
every day, its quote endpoint allows one request per second (but 500
instruments per request), it has no option-chain endpoint, it has no
previous-day OI, and it streams over a binary WebSocket keyed by integer
instrument tokens.

StrikeFluency's Kite integration was read as a reference. We adopted its daily
06:00 expiry tracking, `redirect_params` state transport, Client ID account
binding, validate-then-replace catalog sync, coalesced quoting and read-only
guard. We rejected its global settings mutation, "last connector wins" feed,
SDK proxies and public callback endpoint — ChartNexus already resolves providers
per request, keeps the callback on the frontend, and authenticates the API.

---

## 1. No `kiteconnect` SDK

**Decision.** REST goes through `httpx` in
`infrastructure/brokers/kite/rest_client.py`, which holds every Kite URL,
header, form field and envelope shape. The ticker is a native asyncio client on
`websockets` (`kite/ticker.py`).

**Why.** The SDK is synchronous, and its `KiteTicker` runs a Twisted reactor on
its own thread — every thread-to-loop workaround `fyers/data_socket.py` already
carries, for no gain. Kite Connect v3 and its binary tick format are documented
and small.

**Guard.** `tests/architecture/test_vendor_imports.py` confines `kiteconnect`
to `infrastructure/brokers/kite` should it ever be added.

## 2. Read-only by construction

**Decision.** The adapter has no method for any order, portfolio, margin, GTT or
mutual-fund endpoint. `tests/architecture/test_kite_read_only.py` fails the
build if any such path or verb appears under `infrastructure/brokers/kite/`.

**Why.** A Kite access token can trade. Keeping the capability out of the code is
cheaper to verify than any runtime check. For the same reason, disconnecting
(or being displaced by FYERS) logs the session out at Zerodha
(`DELETE /session/token`), best-effort — a remote failure never blocks the
local drop.

## 3. OAuth state rides in `redirect_params`

**Decision.** The login URL is
`kite.zerodha.com/connect/login?v=3&api_key=…&redirect_params=state%3D<state>`.
Zerodha returns to the redirect URL registered on the app with
`request_token`, `status` and our `state` as plain query parameters. The
frontend route `/settings/broker/kite/callback` posts
`{auth_code: request_token, state}` to `POST /broker/kite/callback`, which
consumes the single-use, tenant-bound state exactly as for FYERS.

**Why.** Kite ignores extra query parameters on the login URL except
`redirect_params`. The token exchange is `POST /session/token` with
`checksum = sha256(api_key + request_token + api_secret)`; the secret never
travels.

**Expiry.** `expires_at` is set to the next 06:00 IST at login.
`BrokerConnection.require_access_token(now)` treats a lapsed token as expired
without a network call.

**Account binding.** An optional Zerodha Client ID can be saved with the keys.
When set, a login as any other account raises `BrokerAccountMismatchError`
before anything is stored, and the stray session is revoked.

## 4. One active broker per tenant

**Decision.** A tenant may save credentials for both brokers, but only one
connection is `active`. `CompleteConnect` disconnects any other active broker
(keys kept) in the same unit of work, writing the displaced row first. The
database backs this with the partial unique index
`uq_broker_connections_one_active (tenant_id) WHERE status = 'active'`, which
replaced ADR 0001's per-`(tenant_id, broker)` index.

**Why.** One feed per user keeps provenance unambiguous: every page knows which
broker its numbers came from. `GET /broker/connections` reports both brokers and
which is active; per-broker routes are `/broker/{fyers|kite}/…`, so existing
FYERS URLs are unchanged.

## 5. Shared jobs prefer Kite

**Decision.** Market-wide jobs — option-chain capture, the futures OI sweep, the
futures board and Trade Buddy — use `find_market_feed()`: any tenant's active
connection, Kite first, then FYERS, then the mock.

**Why.** Index prices are facts about the market, not a tenant. Kite carries OI
on `/quote` for 500 contracts at once, so the OI sweep is one request per series
instead of a paced per-contract walk.

## 6. Hot-set batching for the 1 quote/s limit

**Decision.** `kite/quote_cache.py` records every requested instrument in a
per-API-key Redis sorted set. Whichever caller wins a short Redis lock makes one
`/quote` request for what is missing **plus** everything asked about in the
last ~10 s, and writes all of it to a 1.5 s cache. Callers that lose the lock
poll the cache briefly; a stuck lock degrades to the last-good ladder rather
than queueing.

Quotas are named buckets (`quote`, `historical`, `other`) in
`infrastructure/brokers/quota.py`.

## 7. Option chains are composed; OI change comes from a pre-open capture

**Decision.** Kite has no chain endpoint. The provider picks the expiry from the
synced `kite_instruments` table, takes ±`strikes_each_side` strikes around ATM
(anchored on the cached spot), and quotes every leg plus spot, front future and
INDIA VIX in one ≤500-instrument request. IV is back-filled by the existing
`backfill_implied_volatility`.

Kite has no previous-day OI. Before 09:15 its `oi` *is* the prior close, so the
morning catalog run (08:35 IST, `CN_KITE_CATALOG_SYNC_TIME_IST`) captures it for
futures and the index option windows into `cn:kite:prev-oi:<session>:<token>`.
Without that capture, `previous_oi` and OI change are `None`, never zero.

## 8. Instrument catalog: validate, then replace atomically

**Decision.** The gzip CSV dump is filtered to index spots, catalog equities,
NFO and BFO, validated (row count, required exchanges, index spots present) and
swapped in one transaction. A bad download keeps yesterday's rows. It syncs after
every Kite connect and every morning.

---

## Open items

- **Verify on a live account — in progress.** A real Kite Connect app was
  connected on 2026-11-18. The login, token exchange, catalog sync and live
  option-chain capture work: that afternoon's ingest stored live chains for
  NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, NIFTYNXT50, SENSEX and BANKEX.
  Fixtures in `backend/tests/fixtures/kite/` are still the documented v3 shapes,
  not recordings. Still to check against the live account: the
  `/instruments/historical` per-interval range limits (60/100/200/400/2000 days
  assumed), the 06:00 IST logout, the ticker packet layouts (8/28/32/44/184),
  and that live values match Kite's own terminal.
- **Indices Kite does not list.** `FOCIT` and `NIFTYFPI` are in the catalog
  (from the FYERS symbol master) but have no Kite chain, so under Kite they fall
  back to mock data every tick.
- ~~`compose.prod.yml` needs `CN_KITE_REDIRECT_URI`.~~ **Done** (`5a34d55`).
  Without it production failed `assert_deployment_safe()` and did not start.

## Amendments

- **§5, 2026-11-18 (`482fea2`).** `find_market_feed()` now skips a connection
  whose `expires_at` has passed. Before, a Kite row stayed `active` after its
  06:00 IST expiry and still outranked a working FYERS connection, leaving the
  shared jobs on mock data until the morning reconnect. FYERS has no
  `expires_at`, so it is never skipped on that basis.

## Related

- Mid-session broker changes in the snapshot archive: a symbol-day is never
  stored part-mock, part-live. Live after mock purges that day's mock frames;
  mock after live is skipped. (`market_ingestion/application/capture.py`.)
