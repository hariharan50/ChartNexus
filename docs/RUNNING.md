# Running MarketCompass locally

The Options Lab charts (Multi OI & Volume, Put-Call Ratio, Max Pain, Gamma
Exposure, Vega) plot a per-minute snapshot archive. Something has to **write**
that archive during the session, or those charts have no history for today: they
fall back to a two-point "open vs now" estimate that draws every contract as a
straight line between two points (the crossing straight lines / "cross"), shows
no intraday OI or OI-change history, cannot draw the futures line — and Gamma /
Vega, which have no two-point fallback, show "no data recorded for today yet".

**In local development the API writes that archive itself.** It runs the capture
loop as a background task on startup (`MC_ENVIRONMENT=local`), so starting just
the API populates the charts — no separate process to remember. This is why a
morning with only the API running used to show flat lines: nothing was writing
the archive. Turn it off with `MC_MARKET_INGEST_IN_PROCESS=false` (e.g. when you
run the standalone worker below alongside the API, as `task dev` does, so the two
do not both write and double the archive's density).

Deployed environments do **not** do this — there the standalone
`marketcompass-ingest` worker (below) is the only writer, kept off the API
process so a slow broker call can never occupy an API worker.

## 1. Dependencies (Postgres + Redis)

    docker compose -f deploy/compose/compose.yml up -d

Postgres is on 5433, Redis on 6381 (see backend/.env).

## 2. Backend API — port 8000

    cd backend
    uv run --extra agent --extra llm uvicorn marketcompass.entrypoints.main_api:create_app --factory --reload --port 8000

The `--extra agent --extra llm` flags pull in the AI Console's LangGraph +
Anthropic stack. Without them the API still runs, but the **AI Console → AI
Analysis Agent** tab shows an "offline" notice (it is LLM-only, by design).

### Enable the AI Console (Hella)

The agent is disabled until an LLM is configured. In `backend/.env`:

    MC_LLM_PROVIDER=anthropic
    MC_LLM_ANTHROPIC_API_KEY=sk-ant-...
    MC_LLM_MODEL=claude-sonnet-5          # optional; a good chat default

With a key set and the extras installed, `GET /api/v1/copilot/availability`
returns `{"available": true}` and the tab goes live. Hella reads the live market
through read-only tools (spot/futures/OHLC/option-chain/OI/PCR/max-pain/gamma/
indicators) — so the ingest worker below keeps her OI reads fresh, just like the
charts.

Optional agent tracing: set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` to
send prompts + tool I/O to LangSmith. Leave unset in production.

## 3. Snapshot ingest worker (optional in local — the API already does this)

In local dev you can **skip this**: the API runs the same capture loop in-process
(see above). Run the standalone worker only if you want it as its own process
(closer to production), or for a deployed environment. If you do, set
`MC_MARKET_INGEST_IN_PROCESS=false` on the API so the two do not both write.

It writes one option-chain snapshot per configured symbol every interval during
market hours (09:15–15:40 IST), building the intraday archive the charts plot.
`MC_MARKET_INGEST_ALLOW_MOCK=true` lets it archive the mock feed on a machine
with no live FYERS connection — without it, mock ticks are skipped and nothing is
ever written. (The API's in-process loop forces this on for local.)

    cd backend
    MC_MARKET_INGEST_ALLOW_MOCK=true MC_MARKET_SNAPSHOT_INTERVAL_SECONDS=60 uv run marketcompass-ingest

Either writer: the charts leave the two-point estimate and show real curves once
two snapshots have landed for the day (~2 minutes after start, during market
hours).

## 4. Frontend — port 5173

    cd frontend
    pnpm run dev
    # ➜  Local:   http://localhost:5173/

## Seeing history immediately (optional)

The worker only accumulates history going forward. To get a full session to look
at right now — including outside market hours — fabricate one:

    cd backend
    # today, up to the current minute (nothing before 09:15 IST):
    MC_MARKET_INGEST_ALLOW_MOCK=true uv run marketcompass-oi seed --replace

    # or a full past trading day (whole 09:15–15:30 session):
    MC_MARKET_INGEST_ALLOW_MOCK=true uv run marketcompass-oi seed --date 2026-08-12 --replace

`--replace` only deletes rows this command wrote itself (`source = mock`); it will
refuse to touch a day that holds a real live capture.

## One command for all of the above

If you have [go-task](https://taskfile.dev) installed, `task dev` runs the API and
the ingest worker together (with mock archiving enabled), and `task oi:seed --
--replace` seeds. See `Taskfile.yml`.
