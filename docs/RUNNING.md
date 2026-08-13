# Running MarketCompass locally

The app has **three** processes, not two. The third — the snapshot ingest
worker — is what the Options Lab charts (Multi OI & Volume, Put-Call Ratio, Max
Pain, Gamma Exposure) read. Skip it and those charts have no history for today:
they fall back to a two-point "open vs now" estimate that draws every contract as
a straight line between two points (the crossing straight lines / "cross"), shows
no intraday OI or OI-change history, and cannot draw the futures line. Run all
three.

## 1. Dependencies (Postgres + Redis)

    docker compose -f deploy/compose/compose.yml up -d

Postgres is on 5433, Redis on 6381 (see backend/.env).

## 2. Backend API — port 8000

    cd backend
    uv run uvicorn marketcompass.entrypoints.main_api:create_app --factory --reload --port 8000

## 3. Snapshot ingest worker (REQUIRED for the Options Lab charts)

Writes one option-chain snapshot per configured symbol every interval during
market hours (09:15–15:30 IST), building the intraday archive the charts plot.
`MC_MARKET_INGEST_ALLOW_MOCK=true` lets it archive the mock feed on a machine
with no live FYERS connection — without it, mock ticks are skipped and nothing is
ever written.

    cd backend
    MC_MARKET_INGEST_ALLOW_MOCK=true MC_MARKET_SNAPSHOT_INTERVAL_SECONDS=60 uv run marketcompass-ingest

The charts leave the two-point estimate and show real curves once two snapshots
have landed for the day (~2 minutes after you start it, during market hours).

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
