# ChartNexus — guide for coding agents

ChartNexus is an NSE/BSE **options and futures analytics** web app (Options Lab,
Future Lab, OI tools, breadth, AI agents, the Trade Buddy level-alert watcher). Each
user brings **their own broker** (Zerodha Kite or FYERS) for live market data. It is
being prepared for release as a multi-user SaaS.

Read this file before changing anything. Deeper material lives in `docs/` — start
with [`docs/RUNNING.md`](docs/RUNNING.md) and
[`docs/runbooks/local-development.md`](docs/runbooks/local-development.md).

---

## Stack and layout

| Part | Tech | Where |
| --- | --- | --- |
| Backend | Python ≥ 3.13, FastAPI, SQLAlchemy 2 async, Alembic, managed by **uv** | `backend/` |
| Frontend | React Router 8 (framework mode), React 19, Vite 8, TanStack Query, Zustand, CSS Modules, **pnpm** | `frontend/` |
| Database | PostgreSQL 18 (uses built-in `uuidv7()`) | container, host port **5433** |
| Cache / pub-sub | Redis | container, host port **6381** |
| Realtime | websocket fan-out process | port **8001**, browser path `/ws` |
| Deploy | Docker Compose on one VPS, nginx, certbot | `deploy/`, `scripts/operations/` |

```
backend/src/chartnexus/
  contexts/<name>/{domain,application,api}   one bounded context each — see below
  infrastructure/                             adapters: brokers, persistence, notifications, …
  entrypoints/                                API app, workers, CLIs (main_*.py, *_runtime.py)
  bootstrap/                                  settings (CN_* env), container, route registry
  shared_kernel/                              ids, base errors, tiny shared types
backend/migrations/versions/<context>/        Alembic migrations, one folder per context
backend/tests/{unit,architecture,integration}/
frontend/app/routes/…                         pages; frontend/app/lib/contexts/… API wrappers
docs/                                         ADRs, runbooks, RUNNING.md, schema reference
```

## Running locally (Windows dev machine)

**Run the API and the web app on the host, not in their containers.** The `web`
container never hot-reloads on Windows, and if a container and a host process both hold
5173/8000, `localhost` reaches either at random (502s, lost sessions). If the `api`/`web`
containers are up: `docker compose stop web api`.

```bash
docker compose -f deploy/compose/compose.yml up -d      # postgres + redis
docker compose --profile full up -d realtime            # websocket (optional)
cd backend && uv run alembic upgrade head               # schema
cd backend && CN_MARKET_INGEST_IN_PROCESS=false uv run uvicorn chartnexus.entrypoints.main_api:create_app --factory --reload --port 8000
cd backend && CN_MARKET_INGEST_ALLOW_MOCK=true CN_MARKET_SNAPSHOT_INTERVAL_SECONDS=60 uv run chartnexus-ingest
cd frontend && pnpm dev                                 # http://localhost:5173 (strictPort)
```

- In `local`, the API runs every background loop **in-process** (catalog, futures OI,
  futures board, HUGIN, MME100, report, Trade Buddy). Each has a `CN_*_IN_PROCESS`
  switch for when it is run standalone.
- Health: `GET /health/live`, `/health/ready`. API routes are under `/api/v1/…`;
  plain `/health` is a 404. Swagger at `/docs` (local only).
- **Port already in use** → almost always an orphaned earlier server. Find it with
  `netstat -ano | findstr :5173` (or `:8000`), check the command line, then stop it.
- This machine runs low on RAM; long-lived dev processes can be killed for memory.
  If the app goes down, check the processes before debugging the code.

## Checks — run before saying "done"

```bash
cd backend  && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports
cd backend  && uv run pytest tests/unit tests/architecture          # ~2,100 tests, no containers
cd backend  && uv run pytest tests/integration -m integration       # needs postgres + redis
cd frontend && pnpm lint && pnpm typecheck && pnpm test             # ~1,440 vitest tests
cd backend  && uv run alembic check                                 # models vs migrations drift
```

`task check` (go-task) wraps lint + types + unit tests. Notes:

- **Integration tests use the real dev database** (`localhost:5433/chartnexus`). They
  create throwaway users and unique symbols, so they don't touch real data, but they
  leave rows behind. Build test apps with every background loop off (see
  `tests/integration/postgresql/test_trade_buddy_per_user.py`), or a test run can
  watch and alert on real levels.
- On Windows a few integration tests may report `PytestUnraisableExceptionWarning …
  unclosed transport`. That's an asyncio socket warning, not an app failure. Re-run with
  `-W "ignore::ResourceWarning" -W "ignore::pytest.PytestUnraisableExceptionWarning"`.

## Architecture rules (enforced — the build fails if broken)

- **Bounded contexts never import each other.** A context needing another's services
  imports exactly one `infrastructure/<x>/build_*.py` bridge from its
  `api/dependencies.py`. That edge is listed in `ignore_imports` in
  `backend/pyproject.toml`. See
  [`docs/architecture/bounded-contexts.md`](docs/architecture/bounded-contexts.md).
- `domain/` imports no framework, driver or vendor SDK. Ports are `Protocol`s in
  `application/ports.py`; adapters live in `infrastructure/`.
- Infrastructure never imports `entrypoints/` or the container.
- Vendor SDKs are confined to their adapter directory (`tests/architecture/test_vendor_imports.py`).
- **Broker access is read-only.** The Kite adapter may contain no order, portfolio,
  margin or GTT path (`tests/architecture/test_kite_read_only.py`). Never add trading.
- Background loops live in `entrypoints/<name>_runtime.py`, shared by the standalone
  `main_<name>.py` and the API's local in-process task.

## Brokers and market data

- Two brokers: **Kite** ([ADR 0002](docs/adr/0002-kite-broker-integration.md)) and
  **FYERS** ([ADR 0001](docs/adr/0001-fyers-broker-integration.md)). A user can save keys
  for both; only **one** connection is active per tenant.
- Market-wide jobs (option-chain ingest, futures OI sweep, futures board, Trade Buddy)
  use `find_market_feed()`: any tenant's active, **unexpired** Kite connection, else
  FYERS, else the mock feed. Per-request reads use the caller's own connection.
- **Kite tokens expire at 06:00 IST every day**: the user reconnects each morning.
- **FYERS cut its free-plan limits (Oct 2026):** Data APIs on Standard allow **5/s, 50/min,
  5,000/day**. Prime (₹499/month) allows 10/s, 500/min, 500,000/day. Exceeding the
  per-minute limit more than 3 times a day **blocks the account for the day**. The code
  still assumes 8/s and 100k/day and has no per-minute guard. See open items.
- Every payload carries `provenance.source` (`live` / `mock` / …). Production refuses
  `CN_BROKER_PROVIDER=mock`.
- The option-chain archive never mixes real and simulated data for one symbol-day. Live
  data arriving after mock purges that day's mock frames; mock after live is skipped.

## Trade Buddy (per user)

Each user marks their own levels and gets alerts on **their own** Telegram bot and
WhatsApp (CallMeBot), connected in the app.

- State: one Postgres row per (user, index) in `trade_buddy_watch_states`, a JSON
  document read and written by `PostgresLevelStore` with `SELECT … FOR UPDATE`.
- Channels: `trade_buddy_channels`. The secret **and** the target (chat id / phone)
  are AES-256-GCM, bound by AAD to `trade_buddy:{user}:{channel}:{secret|target}`, and
  never returned in full (the API masks them to their last 4 characters).
- Worker: one shared feed socket; each tick goes concurrently to every user's engine for
  that index. `CoalescingLevelStore` batches per-tick writes; `SessionAtrCache` makes one
  ATR call per index per day.
- There are **no alert credentials in `.env`**. The old `CN_TRADE_BUDDY_TELEGRAM_*` /
  `…_WHATSAPP_*` variables are ignored.
- `uv run chartnexus-trade-buddy import-legacy --email <user>` copies old single-operator
  JSON files into one account.

## Database and migrations

- Alembic, one folder per context under `backend/migrations/versions/`. **Current head:
  `d3e8a1f5c9b2`** (Trade Buddy per-user). Models are auto-discovered.
- Every migration starts with the repo's checklist header: safe while the old release
  runs? indexes concurrent? does downgrade reverse upgrade? Copy an existing one.
- Migration `d3e8a1f5c9b2` encrypts data in place, so it needs
  `CN_SECURITY_ENCRYPTION_KEY`.
- Back up before schema work: `docker exec chartnexus-postgres-1 pg_dump -U chartnexus
  -d chartnexus --format=custom > backups/<name>.dump` (`*.dump` is git-ignored).
- `docs/sqldb/postgres_db_creation.sql` is a generated schema **reference**. Create
  databases with `alembic upgrade head`, never with that file.

## Secrets and security

- `CN_SECURITY_ENCRYPTION_KEY` encrypts every broker credential, LLM key and alert
  channel. Losing it makes them unreadable; rotate with
  `CN_SECURITY_PREVIOUS_ENCRYPTION_KEYS`.
- Never print, log, or put into an error message a token, API key, chat id or phone
  number. Several providers put credentials in the URL (CallMeBot query string,
  Telegram bot path), so rebuild `httpx` errors without the URL (`from None`), as the
  senders in `infrastructure/trade_buddy/` and `notifications/` do.
- Never commit `.env*` files (only the `*.example` templates), `backups/` or `backend/var/`.

## Git and collaboration rules (from the repo owner)

- **Commit only when the user explicitly says "commit".** Finishing work, "continue"
  or "go ahead" is not permission.
- **No AI attribution in commits.** No `Co-Authored-By` trailer and no mention of
  Claude/AI in messages. Commits must look authored solely by the user.
- **Never run `git reset`, `git stash`, `git checkout .`, `git clean` or force-push**
  without asking first. The working tree may hold the user's uncommitted work.
- Work on `main` unless told otherwise. Remotes: `origin` and `backup`; push to both,
  and only when asked.
- Commit messages: conventional style (`fix(scope): …`, `feat(scope): …`, `docs: …`),
  with a body explaining **why**, including how it was verified.
- Before a destructive data operation (deleting rows, dropping tables, downgrading a
  migration on the dev DB) explain what will happen and confirm with the user.
- When the user asks for an explanation first, explain and stop. Don't start
  changing code until they say so. For larger work, propose a plan first.

## Production

- One VPS: `deploy/compose/compose.prod.yml` + `.env.production` (from
  `.env.production.example`) + `scripts/operations/deploy.sh`. Read
  [`docs/runbooks/vps-deployment.md`](docs/runbooks/vps-deployment.md) and
  [`docs/runbooks/production-handoff.md`](docs/runbooks/production-handoff.md) (its "Do not
  undo these" section) before touching deployment files.
- `x-backend-env` in `compose.prod.yml` is an **explicit list**. A setting reaches
  containers only if it is named there *and* documented in `.env.production.example`.

## Open items (as of 2026-11-18)

1. **Live verification**: compare live Kite values with Kite's own terminal during
   market hours (spot, futures + OI, futures board, option chain incl. OI change,
   history), and run a live Trade Buddy check: two users, one feed, alerts on each
   user's own channels.
2. **FYERS limits**: the quota settings are outdated and there's no per-minute guard.
   Researched ways to cut usage, none implemented yet:
   - skip the futures-OI sweep on FYERS (Kite only)
   - a shared short-lived cache per instrument for page reads
   - futures quote from the catalog's `front_expiry` instead of a whole option chain
   - socket prices
   - fewer ingest symbols, slower board capture
   - enforce the per-plan limits

   The user still has to say which FYERS plan they're on and FYERS's role (full source
   or backup).
3. **SaaS readiness**:
   - market-wide jobs serve every user from one user's broker connection. That
     redistributes broker data and spends one user's quota, so it needs a licensed data
     vendor or strictly per-user data.
   - SEBI Research Analyst registration likely applies to STRYX / signals /
     recommendation features.
   - no payment flow.
4. `ExchangeCalendar` takes a holiday set but nothing fills it for market-wide jobs.
5. Ops gaps: no metrics (`metrics.py` and `prometheus.yml` are empty), no off-site
   backups, 4 empty CI workflows, no uptime monitor.
6. `FOCIT` and `NIFTYFPI` have no Kite option chain and run on mock data under Kite.
