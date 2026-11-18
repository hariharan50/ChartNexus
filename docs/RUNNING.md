# Running ChartNexus locally

The Options Lab charts (Multi OI & Volume, Put-Call Ratio, Max Pain, Gamma
Exposure, Vega) plot a per-minute snapshot archive. Something has to **write**
that archive during the session, or those charts have no history for today: they
fall back to a two-point "open vs now" estimate that draws every contract as a
straight line between two points (the crossing straight lines / "cross"), shows
no intraday OI or OI-change history, cannot draw the futures line — and Gamma /
Vega, which have no two-point fallback, show "no data recorded for today yet".

**In local development the API writes that archive itself.** It runs the capture
loop as a background task on startup (`CN_ENVIRONMENT=local`), so starting just
the API populates the charts — no separate process to remember. This is why a
morning with only the API running used to show flat lines: nothing was writing
the archive. Turn it off with `CN_MARKET_INGEST_IN_PROCESS=false` (e.g. when you
run the standalone worker below alongside the API, as `task dev` does, so the two
do not both write and double the archive's density).

Deployed environments do **not** do this — there the standalone
`chartnexus-ingest` worker (below) is the only writer, kept off the API
process so a slow broker call can never occupy an API worker.

## 1. Dependencies (Postgres + Redis)

    docker compose -f deploy/compose/compose.yml up -d

Postgres is on 5433, Redis on 6381 (see backend/.env).

> **On Windows, run the API and the web app on the host, not in containers.**
> The dev compose file's `web` service never hot-reloads host edits (file
> events do not cross the Windows bind mount, and Vite is not set to poll), so
> it silently serves stale code. If the `web` or `api` containers are up, stop
> them first — `docker compose stop web api` — or `localhost:5173` / `:8000`
> can reach *two different* servers depending on IPv4/IPv6 preference, which
> shows up as random 502s and lost sessions.

## 2. Backend API — port 8000

    cd backend
    uv run --extra agent --extra llm uvicorn chartnexus.entrypoints.main_api:create_app --factory --reload --port 8000

The `--extra agent --extra llm` flags pull in the AI Console's LangGraph +
Anthropic stack. Without them the API still runs, but the **AI Console → AI
Analysis Agent** tab shows an "offline" notice (it is LLM-only, by design).

### Enable the AI Console (Hella / STRYX)

LLM keys are **per-user**, not a backend env var. With the extras installed, sign
in and go to **Settings → AI**: pick a provider (Claude), paste your own API key,
choose a model, and save. The key is stored encrypted at rest and the agents read
it per request.

Until *that user* saves a key, their AI Console tab shows an "offline" notice and
`GET /api/v1/copilot/availability` returns `{"available": false}`. Once saved it
flips to `true` and the tab goes live. Hella reads the live market
through read-only tools (spot/futures/OHLC/option-chain/OI/PCR/max-pain/gamma/
indicators) — so the ingest worker below keeps her OI reads fresh, just like the
charts.

Optional agent tracing: set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` to
send prompts + tool I/O to LangSmith. Leave unset in production.

## 3. Snapshot ingest worker (optional in local — the API already does this)

In local dev you can **skip this**: the API runs the same capture loop in-process
(see above). Run the standalone worker only if you want it as its own process
(closer to production), or for a deployed environment. If you do, set
`CN_MARKET_INGEST_IN_PROCESS=false` on the API so the two do not both write.

It writes one option-chain snapshot per configured symbol every interval during
market hours (09:15–15:40 IST), building the intraday archive the charts plot.
By default the symbols are every **index** in the instrument catalog;
`CN_MARKET_INGEST_SYMBOLS` overrides that (`["*"]` means the whole F&O universe).

The chain comes from whichever broker is connected — **Kite first, then FYERS**
(any tenant's active connection; see [ADR 0002](adr/0002-kite-broker-integration.md)) —
and falls back to the mock feed when neither is, or when the broker cannot serve
a symbol. `CN_MARKET_INGEST_ALLOW_MOCK=true` lets it archive that mock feed —
without it, mock ticks are skipped and nothing is written. (The API's
in-process loop forces this on for local.)

    cd backend
    CN_MARKET_INGEST_ALLOW_MOCK=true CN_MARKET_SNAPSHOT_INTERVAL_SECONDS=60 uv run chartnexus-ingest

Either writer: the charts leave the two-point estimate and show real curves once
two snapshots have landed for the day (~2 minutes after start, during market
hours).

**A symbol-day is never part real, part simulated.** Every `ingest_tick` log
line says what happened to each symbol:

| Log field | Meaning |
| --- | --- |
| `written` | stored a new snapshot |
| `purged_mock` | the broker came online mid-session; that day's mock frames for the symbol were deleted, so the day reads as a gap followed by real data |
| `skipped_mock` | mock data, and either mock is not allowed or the day already has a live capture (the broker dropped out — a gap is left rather than a simulated afternoon) |
| `skipped_unchanged` | identical to the previous snapshot — a frozen tape |
| `skipped_empty` / `failed` | no strikes came back / the fetch raised (`failure_reasons` says why) |

Outside 09:15–15:40 IST every tick logs `ingest_tick_skipped reason=market_closed`,
which is normal. Indices the connected broker does not list (e.g. `FOCIT` and
`NIFTYFPI` under Kite) stay on mock data all day.

## 3b. Futures board capture — the Future Lab archive

Separate from the option-chain ingest above, and separate again from the
open-interest sweep: this one archives the **futures board** — each contract's
front-month price and its own open interest — which is what Future Lab's Price
vs OI chart, Historical and Replay read.

The API starts it in process for local, so normally you need nothing. To run it
standalone (and set `CN_FUTURES_HISTORY_IN_PROCESS=false` on the API so the two
do not both write):

    cd backend
    uv run chartnexus-futures-history

It captures every 60s. **Live boards only** — with no broker connection the board
degrades to generated numbers, and those are deliberately never archived: a
stored frame outlives the process that wrote it, and a mislabelled one cannot be
detected later. On a machine with no broker, seed instead (below).

    uv run chartnexus-futures-history --once     # one frame, then exit
    uv run chartnexus-futures-history --prune    # drop past the retention window

## 3c. Trade Buddy watcher

Trade Buddy watches the six levels (S1–S3, R1–R3) you mark each morning and
alerts on approaches, touches, breaks, rejections, reclaims and opening gaps —
to Telegram always, and to WhatsApp (CallMeBot) for the events worth it.

Local dev runs it inside the API (`CN_TRADE_BUDDY_IN_PROCESS=true`), so normally
you need nothing. Standalone, with the in-process copy turned off:

    cd backend
    uv run --extra fyers-stream chartnexus-trade-buddy

It takes its broker from the connection made in **Settings → Broker** (Kite
first, then FYERS) — a Kite connection streams over the Kite ticker, a FYERS one
over the FYERS socket, which needs the `fyers-stream` extra. Alerts need
`CN_TRADE_BUDDY_TELEGRAM_BOT_TOKEN` and `CN_TRADE_BUDDY_TELEGRAM_CHAT_ID` in
`backend/.env`; every band and threshold is a `CN_TRADE_BUDDY_*` setting (see
`backend/.env.example`). Marked levels and watcher state are JSON files in
`var/trade_buddy/`, relative to where the process starts — `backend/var/trade_buddy/`
for the commands above (`CN_TRADE_BUDDY_STATE_DIRECTORY`). **Quick Reset** on the
page (`POST /api/v1/trade-buddy/reset`) starts one instrument's day over: it
clears the marked levels, their live states and today's alerts, but keeps that
instrument's sensitivity overrides. The watcher drops it within ~15 seconds.

## 3d. Realtime websocket — port 8001

The browser's `/ws` connection (the live indicator, and instant refetch when a
snapshot lands) is served by a separate process. Without it the app still works:
the client sits in *Reconnecting* and falls back to 15-second polling.

    docker compose --profile full up -d realtime     # container
    # or, on the host:
    cd backend && uv run chartnexus-realtime

It reads only the Redis channel the ingest loop publishes to; Vite proxies `/ws`
to `127.0.0.1:8001`.

## 4. Frontend — port 5173

    cd frontend
    pnpm run dev
    # ➜  Local:   http://localhost:5173/

`vite.config.ts` sets `strictPort: true`, so if 5173 is taken it fails instead of
moving to 5174. The holder is almost always the `chartnexus-web-1` container —
`docker compose stop web`.

## Seeing history immediately (optional)

The worker only accumulates history going forward. To get a full session to look
at right now — including outside market hours — fabricate one:

    cd backend
    # today, up to the current minute (nothing before 09:15 IST):
    CN_MARKET_INGEST_ALLOW_MOCK=true uv run chartnexus-oi seed --replace

    # or a full past trading day (whole 09:15–15:30 session):
    CN_MARKET_INGEST_ALLOW_MOCK=true uv run chartnexus-oi seed --date 2026-08-12 --replace

`--replace` only deletes rows this command wrote itself (`source = mock`); it will
refuse to touch a day that holds a real live capture.

The futures board has its own seeder, with the same guards — it refuses a
deployed environment, a future date, and any day the real capture has touched:

    cd backend
    uv run chartnexus-futures-history --seed 2026-09-18 --replace

That fabricates a whole 09:15–15:30 session for all 219 contracts (today's stops
at the current minute). Seeded frames are stamped `mock`, so the page's data-source
badge says so rather than passing them off as captured.

## One command for all of the above

If you have [go-task](https://taskfile.dev) installed, `task dev` starts Postgres
and Redis, then runs the API (with its in-process ingest turned off) and the
ingest worker together, with mock archiving enabled. Run `task dev:web` for the
frontend, and `task oi:seed -- --replace` to seed. See `Taskfile.yml`.

## Checking it is all up

| What | URL / command | Healthy answer |
| --- | --- | --- |
| Web app | <http://localhost:5173> | the login page |
| API liveness | <http://localhost:8000/health/live> | `{"status":"ok",…}` |
| API readiness | <http://localhost:8000/health/ready> | `postgres: ok, redis: ok` |
| API docs | <http://localhost:8000/docs> | Swagger UI (local only) |
| Realtime | `ws://localhost:8001/ws` | reached through `/ws` on 5173 |
| Ingest | its log | `ingest_tick` (or `market_closed` outside hours) |

API paths are all under `/api/v1/…`; plain `/health` is a 404.
