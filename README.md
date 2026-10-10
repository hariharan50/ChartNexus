# ChartNexus

Options and futures market intelligence terminal for NSE instruments — option
chain analytics, futures positioning, signal synthesis, and an explainable
copilot over the resulting data.

> **Status:** under construction. Fifteen bounded contexts are implemented,
> covering identity and broker connections, market data and ingestion, the
> options and futures analytics, the signals engine, four AI agents (HELLA,
> STRYX, HUGIN, MME100), outbound messaging and the daily report. A handful
> under `backend/src/chartnexus/contexts/` are still empty placeholders.
>
> The instrument universe is the full NSE F&O list — 210 stocks plus the index
> contracts — held in `instrument_catalog` and refreshed daily from the
> exchange symbol master. The application runs end to end against a mock feed
> with no broker account; connecting FYERS swaps in live NSE data.
>
> Market data is read-only. No order placement, positions, or funds.

## Prerequisites

| Tool   | Version | Notes                                         |
| ------ | ------- | --------------------------------------------- |
| Python | 3.13+   | installed automatically by `uv`                |
| uv     | 0.11+   | `winget install astral-sh.uv`                  |
| Node   | 22+     | `winget install OpenJS.NodeJS`                 |
| pnpm   | 10+     | `corepack enable`                              |
| Docker | 27+     | Postgres 18 and Redis 7 run in containers      |

`task` ([go-task](https://taskfile.dev)) is optional — every command below is
also shown in its raw form.

## Getting started

```bash
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

docker compose -f deploy/compose/compose.yml up -d   # Postgres + Redis
cd backend  && uv sync   && uv run alembic upgrade head
cd frontend && pnpm install
```

Then run the two dev servers in separate terminals:

```bash
cd backend  && uv run uvicorn chartnexus.entrypoints.main_api:create_app --factory --reload --port 8000
cd frontend && pnpm dev
```

- API — <http://localhost:8000>, docs at `/docs`, health at `/health/ready`
- Web — <http://localhost:5173>

With go-task installed the same thing is `task setup && task up && task dev`.

Host ports are deliberately shifted (Postgres `5433`, Redis `6381`) so a
Postgres or Redis already installed on the machine keeps working. Change them in
the root `.env`.

Full runbook, including Google sign-in setup and troubleshooting:
[docs/runbooks/local-development.md](docs/runbooks/local-development.md).

## Layout

```
backend/     FastAPI + SQLAlchemy, one package per bounded context
frontend/    React Router terminal UI, mirroring the same context boundaries
contracts/   OpenAPI, websocket, event, and analytics contracts — the source of truth
deploy/      Dockerfiles, compose stacks (dev and production), nginx config
docs/        architecture, ADRs, runbooks
```

The backend runs as several processes, deployed separately so a slow broker
call can never occupy an API worker. In local development the API runs all the
workers in-process (gated on `CN_ENVIRONMENT=local`), so `uv run uvicorn ...`
alone gives you a populated application.

| Process           | Entrypoint                 | Responsibility                                   |
| ----------------- | -------------------------- | ------------------------------------------------ |
| `api`             | `main_api.py`              | REST surface                                     |
| `catalog`         | `main_catalog.py`          | the F&O universe and lot sizes, refreshed daily  |
| `ingest`          | `main_ingest.py`           | option-chain snapshots — the intraday OI archive |
| `futures-oi`      | `main_futures_oi.py`       | the open-interest sweep behind Future Lab        |
| `futures-history` | `main_futures_history.py`  | board capture for Future Lab's charts and Replay |
| `hugin`           | `main_hugin.py`            | HUGIN's hourly graded market memory              |
| `mme100`          | `main_mme100.py`           | the MME100 pre-market briefing                   |
| `report`          | `main_report.py`           | the daily PDF, per enrolled tenant               |
| `realtime`        | `main_realtime.py`         | the websocket fan-out, on its own port (8001)    |

`main_score.py` is still an **empty placeholder** — there is no scoring worker
yet. `chartnexus-signals` and `chartnexus-oi` are offline operator CLIs
(fit/backtest, and seed/prune of the archive), not workers.

### The realtime process

`realtime` serves `/ws` on port 8001 and is the one process that holds long-lived
connections, which is why it is not an API worker: a socket held for a trading
session would occupy one for the same length of time.

It reads no Postgres and calls no broker. The ingest loop publishes a
`snapshot_committed` event on Redis after each write; this process subscribes
once, routes by symbol, and pushes a frame carrying headline numbers — not the
chain. The browser then refetches detail over REST into the same query cache the
polled reads fill, so one transport owns the shapes and the socket never has to
version a 54-strike payload.

Authentication is by **single-use ticket**, not the session cookie: a browser
cannot set headers on a websocket handshake, and the cross-origin cookie does
not travel. `POST /api/v1/realtime/ticket` mints one, valid 60 seconds and for
one connection; present it as `?ticket=`. Fetch a fresh one per attempt,
including every reconnect — a replayed ticket is refused with
`ticket_already_used`.

The protocol lives in `contracts/websocket/v1/`, and
`tests/contract/websocket/` keeps the codec and those schemas in step.

In production it runs as the `realtime` service and nginx proxies `/ws` to it.
Locally it runs under the `full` profile (`docker compose --profile full up -d`)
or directly:

```bash
cd backend && uv run chartnexus-realtime
```

## Architecture rules

Enforced by CI, not by convention:

- The domain layer imports no framework, driver, or vendor SDK.
- Bounded contexts never import each other — they integrate through ports and
  domain events. Shared HTTP plumbing lives in
  `infrastructure/transport/http/dependencies.py`, never in another context.
- Vendor SDKs (Fyers, Anthropic, OpenAI) may only be imported inside their own
  adapter directory. The OpenRouter provider reuses the OpenAI SDK by subclassing
  the OpenAI adapter, so `import openai` stays confined to `llm/openai`.
- Infrastructure never imports the container or the entrypoints.

```bash
cd backend && uv run lint-imports && uv run pytest tests/architecture
```

Run **both**. A green `lint-imports` has been observed to pass while
`tests/architecture` caught real cross-context imports; the test suite is the
stricter check. See
[docs/architecture/bounded-contexts.md](docs/architecture/bounded-contexts.md).

## Everyday commands

| Task                | Command                                                   |
| ------------------- | --------------------------------------------------------- |
| Lint and format     | `cd backend && uv run ruff check --fix . && uv run ruff format .` |
| Type-check backend  | `cd backend && uv run mypy`                               |
| Type-check frontend | `cd frontend && pnpm typecheck`                           |
| Fast tests          | `cd backend && uv run pytest tests/unit tests/architecture` |
| Integration tests   | `cd backend && uv run pytest tests/integration -m integration` |
| Frontend tests      | `cd frontend && pnpm test`                                |
| End-to-end tests    | `cd frontend && pnpm test:e2e`                            |
| New migration       | `cd backend && uv run alembic revision --autogenerate -m "msg" --version-path migrations/versions/<area>` |
| Regenerate API client | `cd frontend && pnpm api:generate`                      |

## Deploying

The production target is a single VPS running `docker compose`. nginx terminates
TLS and maps one hostname onto the API and the web app — the browser bundle calls
`/api/v1/...` as a same-origin path, so a reverse proxy is required rather than
optional.

```bash
cp .env.production.example .env.production   # fill in, then
./scripts/operations/deploy.sh
./scripts/operations/issue-certificate.sh
```

Full runbook, including sizing, backups, rollback and troubleshooting:
[docs/runbooks/vps-deployment.md](docs/runbooks/vps-deployment.md).

The Helm chart under `deploy/helm/` and the Terraform modules under
`infrastructure/` are empty skeletons — there is no Kubernetes path yet.

## Market data

The API serves spot prices and option chains for NIFTY, BANKNIFTY and SENSEX:

```
GET /api/v1/market/status         session state and the active data source
GET /api/v1/market/spot           index spot price
GET /api/v1/market/option-chain   strikes with PCR and ATM
GET /api/v1/market/expiries       available expiry dates
```

**Every response states where its numbers came from** — `provenance.source` is
`live`, `cached`, or `mock`, with an `age_seconds`. Nothing downstream may treat
these as interchangeable: a chart drawn from a stale snapshot looks identical to
a live one, and only that field distinguishes them.

## Working without a broker account

The whole application runs with no external credentials. A deterministic mock
provider serves generated quotes and option chains, everything labelled
`source: "mock"`. The AI Console (Hella, STRYX) simply stays offline until a key
is added — no server key is required to run the rest of the app.

The AI Console runs on **per-user** LLM keys, not a backend env var. To turn it
on, install the model SDK (`uv sync --extra llm`), then in the app go to
**Settings → AI**, pick Claude, and paste your own API key. The key is stored
encrypted at rest and each user's agents run on their own key. (OpenAI and
OpenRouter are reserved for a later release.)

To use live NSE data, connect a FYERS account under **Settings → Broker**. Each
tenant connects their own broker application; credentials and tokens are stored
encrypted per tenant and never returned to the browser. Setup steps are in the
[runbook](docs/runbooks/local-development.md#7-optional-connect-a-fyers-broker-account),
and the design decisions are recorded in
[ADR 0001](docs/adr/0001-fyers-broker-integration.md).

## Disclaimer

ChartNexus is analytics software. It does not provide investment advice, and
nothing it produces is a recommendation to buy or sell any instrument.
