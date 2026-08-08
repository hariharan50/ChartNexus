# MarketCompass

Options and futures market intelligence terminal for NSE instruments — option
chain analytics, futures positioning, signal synthesis, and an explainable
copilot over the resulting data.

> **Status:** early construction. Three bounded contexts are implemented —
> `identity` (email/password + Google sign-in), `broker_connections` (FYERS
> OAuth), and `market_data` (spot prices and option chains). The application
> runs end to end against a mock feed with no broker account; connecting FYERS
> swaps in live NSE data. The remaining contexts under
> `backend/src/marketcompass/contexts/` are still empty.
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
cd backend  && uv run uvicorn marketcompass.entrypoints.main_api:create_app --factory --reload --port 8000
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
deploy/      Dockerfiles, compose stack, Helm chart
docs/        architecture, ADRs, runbooks
```

Four backend processes are deployed separately so a slow broker call can never
occupy an API worker:

| Process    | Entrypoint          | Responsibility                          |
| ---------- | ------------------- | --------------------------------------- |
| `api`      | `main_api.py`       | REST surface                            |
| `ingest`   | `main_ingest.py`    | broker polling and snapshot commits     |
| `score`    | `main_score.py`     | analytics and signal synthesis          |
| `realtime` | `main_realtime.py`  | websocket fan-out from Redis pub/sub    |

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
| Type-check frontend | `cd frontend && pnpm check`                               |
| Fast tests          | `cd backend && uv run pytest tests/unit tests/architecture` |
| Integration tests   | `cd backend && uv run pytest tests/integration -m integration` |
| Frontend tests      | `cd frontend && pnpm test`                                |
| End-to-end tests    | `cd frontend && pnpm test:e2e`                            |
| New migration       | `cd backend && uv run alembic revision --autogenerate -m "msg" --version-path migrations/versions/<area>` |
| Regenerate API client | `cd frontend && pnpm api:generate`                      |

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
provider serves generated quotes and option chains, and
`MC_LLM_PROVIDER=rule_based` makes the copilot deterministic. Everything is
labelled `source: "mock"`.

To make the copilot generative, set `MC_LLM_PROVIDER` to `anthropic`, `openai`,
or `openrouter` (after `uv sync --extra llm`) and supply the matching key.
OpenRouter uses namespaced model IDs via `MC_LLM_OPENROUTER_MODEL`
(e.g. `anthropic/claude-3.7-sonnet`), not `MC_LLM_MODEL`.

To use live NSE data, connect a FYERS account under **Settings → Broker**. Each
tenant connects their own broker application; credentials and tokens are stored
encrypted per tenant and never returned to the browser. Setup steps are in the
[runbook](docs/runbooks/local-development.md#7-optional-connect-a-fyers-broker-account),
and the design decisions are recorded in
[ADR 0001](docs/adr/0001-fyers-broker-integration.md).

## Disclaimer

MarketCompass is analytics software. It does not provide investment advice, and
nothing it produces is a recommendation to buy or sell any instrument.
