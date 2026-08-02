# ADR 0001 — FYERS broker integration

- **Status:** accepted
- **Date:** 2026-08-01
- **Scope:** market data and OAuth only. No order placement, positions, or funds.

## Context

MarketCompass needs live NSE index and option-chain data. FYERS was chosen as
the broker. A reference architecture from another application (StrikeFluency)
described a working integration and explicitly separated what that application
does today from what a multi-user port must do instead.

Four decisions in that port are load-bearing enough to record.

---

## 1. Broker connections are per tenant

**Decision.** Each tenant registers their own FYERS API application and connects
their own account. `broker_connections` is keyed by `tenant_id`, with a unique
partial index on `(tenant_id, broker) WHERE status = 'active'`.

**Alternative rejected.** One shared system-wide market-data account, which is
what the reference implementation does (`user_id = None`). Index data is
identical for every user, so a shared feed is defensible and much simpler.

**Why.** MarketCompass is multi-tenant; every user already carries a
`tenant_id`. A shared account means one tenant's usage consumes the rate limit
of all, and only an administrator could ever connect. Per-tenant also keeps the
blast radius of a leaked token to one tenant.

**Cost.** No process-wide provider singleton is possible, so a provider is
resolved per request (see decision 3).

---

## 2. The FYERS SDK is not used; the v3 HTTPS API is called directly

**Decision.** `infrastructure/brokers/fyers/rest_client.py` calls the FYERS v3
REST API with `httpx`. `fyers-apiv3` is not a dependency.

**Why.** Resolving `fyers-apiv3` pulls **26 transitive packages**, including:

- `asyncio==3.4.3` — a PyPI package that shadows the standard library module;
- `boto3`, `botocore`, `aws-xray-sdk`, `aws-lambda-powertools` — the AWS SDK, in
  a trading backend that uses none of it;
- `aiohttp==3.9.3` and `requests==2.31.0`, both pinned to versions predating
  Python 3.14.

The SDK is also synchronous, so every call would need `asyncio.to_thread`. We
already use `httpx`, and FYERS v3 is plain HTTPS.

**Cost.** We hand-write request and response mapping, and the exact endpoint
paths are our responsibility. Mitigated by concentrating every URL and payload
shape in `rest_client.py` and testing the mappers against recorded fixtures.

**Note.** `tests/architecture/test_vendor_imports.py` still confines
`fyers_apiv3` to `infrastructure/brokers/fyers`. The entry is kept deliberately:
it guards this decision if anyone adds the SDK later.

---

## 3. No provider singleton, no runtime `.env` mutation

**Decision.** Providers are constructed per request from the tenant's stored
connection. Credentials live encrypted in Postgres, not in `backend/.env`.

**Alternatives rejected.** The reference implementation writes App ID and Secret
into `.env` at runtime and caches one global provider instance, invalidated by a
`reset_provider()` call after every state change. Its own limitations section
flags both as defects.

**Why.**

- Our `Settings` are frozen and read once at process start; mutating `.env`
  would not affect the running process anyway.
- A process-local cache is invisible to other workers, so "disconnected" in one
  worker means "still connected" in the next.
- Building per request removes the entire cache-invalidation hazard: a
  disconnect takes effect on the very next call, everywhere.

**Cost.** One extra database read per market-data request. Acceptable — it is a
single indexed row, and it buys correctness across workers.

---

## 4. OAuth state is single-use and bound to the initiating tenant

**Decision.** `StartConnect` mints a random `state`, stores
`{tenant_id, user_id, broker}` in Redis under it with a TTL, and puts it in the
authorization URL. `CompleteConnect` consumes the entry with `GETDEL` and takes
the tenant **from the stored state**, never from the request.

**Why.** The reference callback accepts an authorization code without binding it
to whoever began the flow, and stores the resulting token globally. In a
multi-tenant application that lets anyone who can reach the endpoint attach a
broker account to it. Unknown, expired, replayed, and mismatched states are all
rejected identically, so the endpoint reveals nothing.

**Verified by** `tests/integration/postgresql/test_broker_api.py`:
`test_a_state_cannot_be_replayed` and
`test_another_tenant_cannot_use_a_state_it_did_not_create`.

---

## Consequences

- Secrets and tokens are Fernet ciphertext at rest, with the key derived from
  `MC_SECURITY_ENCRYPTION_KEY` via HKDF. Changing that key makes existing
  connections unreadable; they degrade to "expired" and can be reconnected,
  rather than raising on every request.
- `market_data` never imports `broker_connections`. It depends on its own
  `MarketDataProvider` port; `infrastructure/brokers/provider_resolver.py`
  bridges the two. See
  [bounded-contexts.md](../architecture/bounded-contexts.md).
- Degradation is explicit: `fresh cache → live → last-good → mock`, and the
  chosen rung is reported as `provenance.source` on every payload.
- Retries cover timeouts, 5xx and 429 only. **Authentication failures are never
  retried** — a rejected token will be rejected again, and retrying is how an
  application gets throttled.

## Open items

- Endpoint paths were verified against secondary sources; FYERS' own
  documentation is a JavaScript application and could not be read directly.
  They need confirming against a live account.
- Streaming (the periodic poller and websocket fan-out) is deliberately not
  built yet — the data shape should settle first.
- Trading-holiday awareness is missing from `ExchangeCalendar`; it knows
  weekends and session hours only.
