# Running ChartNexus locally

Everything below assumes the repository root, `C:\Users\sriha\Documents\ProductionVPS\ChartNexus`.
[RUNNING.md](../RUNNING.md) covers the background workers (ingest, futures board,
Trade Buddy, realtime) in more depth.

## 1. Prerequisites

| Tool   | Minimum | Check with        | Install                          |
| ------ | ------- | ----------------- | -------------------------------- |
| Docker | 27      | `docker --version` | Docker Desktop                   |
| uv     | 0.11    | `uv --version`     | `winget install astral-sh.uv`    |
| Node   | 22      | `node --version`   | `winget install OpenJS.NodeJS`   |
| pnpm   | 10      | `pnpm --version`   | `corepack enable`                |

Python itself is not required — `uv` downloads and manages the 3.13+ interpreter.

## 2. First-time setup

Run once per clone.

```bash
# Environment files (all three are gitignored)
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# Dependencies
cd backend  && uv sync   && cd ..
cd frontend && pnpm install && cd ..

# Start Postgres + Redis, then create the schema
docker compose -f deploy/compose/compose.yml up -d
cd backend && uv run alembic upgrade head && cd ..
```

`alembic upgrade head` is the step people forget. Without it the API starts fine
but every request that touches the database fails.

## 3. Daily start

Three things need to be running. Use three terminals.

**Terminal 1 — dependencies** (leave running; survives reboots via Docker)

```bash
docker compose -f deploy/compose/compose.yml up -d
```

**Terminal 2 — API** (hot reloads on save)

```bash
cd backend
uv run uvicorn chartnexus.entrypoints.main_api:create_app --factory --reload --port 8000
```

**Terminal 3 — web app** (hot reloads on save)

```bash
cd frontend
pnpm dev
```

Then open <http://localhost:5173>.

In `local`, the API also runs every background loop in-process — catalog, option-
chain ingest, futures OI, futures board, HUGIN, MME100, report and Trade Buddy —
so these three terminals are the whole app. Each loop has its own
`CN_*_IN_PROCESS` switch for when you run that worker standalone instead (as
`task dev` does for ingest).

Optional fourth piece — the realtime websocket (live indicator, instant
refetch). Without it the app falls back to polling:

```bash
docker compose --profile full up -d realtime
```

**Run the API and web app on the host, not in the `api`/`web` containers.** On
Windows the container's Vite never sees host edits (no hot reload), and if a
container and a host process both hold 5173 or 8000, `localhost` reaches either
one depending on IPv4/IPv6 — random 502s and lost sessions. If they are up:
`docker compose stop web api`.

## 4. Ports

Host ports are deliberately shifted so other projects on this machine keep working.

| Service    | Host port | Notes                                                  |
| ---------- | --------- | ------------------------------------------------------ |
| Web app    | 5173      | `strictPort` — fails rather than moving if 5173 is taken |
| API        | 8000      | docs at <http://localhost:8000/docs>                    |
| Realtime   | 8001      | websocket; the web app proxies `/ws` to it              |
| Postgres   | 5433      | container listens on 5432 internally                    |
| Redis      | 6381      | container listens on 6379 internally                    |

Change the database and cache ports in the root `.env` (`POSTGRES_PORT`,
`REDIS_PORT`), and keep `backend/.env` (`CN_DB_URL`, `CN_REDIS_URL`) in step.

**If you run the web app on a port other than 5173** (`pnpm dev --port 5174`),
update all three OAuth redirect URIs — `CN_GOOGLE_REDIRECT_URI`,
`CN_BROKER_FYERS_REDIRECT_URI` and `CN_KITE_REDIRECT_URI` in `backend/.env` —
and the matching entries in the Google console, the FYERS dashboard and the Kite
developer console. All three providers require an exact string match.

## 5. Confirm it works

```bash
curl http://localhost:8000/health/ready
```

Expected:

```json
{"status":"ok","version":"0.1.0","dependencies":{"postgres":"ok","redis":"ok"}}
```

A `503` with `"postgres":"error: …"` means the containers are not up or the
migration has not been applied.

Then sign up at <http://localhost:5173/register>. You should land on the
dashboard with your email in the header.

## 6. Optional: Google sign-in

The app runs fully without it — the Google button reports that it is not
configured, and email/password works normally.

1. Go to <https://console.cloud.google.com/apis/credentials>.
2. Create an **OAuth 2.0 Client ID**, application type **Web application**.
3. Add an authorized redirect URI: `http://localhost:5173/auth/google/callback`.
4. Put the credentials in `backend/.env`:

```bash
CN_GOOGLE_CLIENT_ID=<client id>
CN_GOOGLE_CLIENT_SECRET=<client secret>
CN_GOOGLE_REDIRECT_URI=http://localhost:5173/auth/google/callback
```

5. Restart the API.

## 7. Optional: connect a broker (Kite or FYERS)

Also optional. Without one the app serves a deterministic mock feed, labelled
`source: "mock"` in every response and shown as **Simulated** in the UI.

Each tenant connects their own broker application — there is no shared
system-wide account. You can save keys for **both** brokers, but only one
connection is active at a time: connecting one disconnects the other (its keys
are kept). Market-wide jobs — ingest, the futures OI sweep, the futures board
and Trade Buddy — use Kite when any tenant has it active, then FYERS, then mock.

### 7a. Zerodha Kite Connect

1. Create an app at <https://developers.kite.trade> (a paid Kite Connect app).
2. Set its redirect URL to **exactly**
   `http://localhost:5173/settings/broker/kite/callback`.
3. In ChartNexus, **Settings → Broker**, under **Zerodha Kite**: paste the
   **API key** and **API secret**. Optionally add your **Zerodha Client ID** —
   then a login as any other Zerodha account is refused and that session is
   revoked.
4. Click **Connect with Zerodha Kite** and log in at Zerodha.

Things specific to Kite:

- **The token dies at 06:00 IST every day.** That is Zerodha's rule, not a
  fault: reconnect each morning. The status shows *expired* without making a
  network call.
- The connection is **read-only by construction** — the code has no order,
  position, holding, margin or GTT path at all (an architecture test enforces
  it), even though a Kite token could trade.
- Disconnecting also logs the session out at Zerodha.
- Connecting triggers an instrument-catalog sync into `kite_instruments`, and a
  morning run at 08:35 IST captures yesterday's OI so OI-change columns work.
  Without that morning capture, OI change shows as blank rather than zero.

Design: [ADR 0002](../adr/0002-kite-broker-integration.md).

### 7b. FYERS

1. Create an app at <https://myapi.fyers.in/dashboard>.
2. Set its redirect URI to **exactly**
   `http://localhost:5173/settings/broker/callback`. Scheme, host, port and path
   must match; `localhost` and `127.0.0.1` are different values to the broker.
3. In ChartNexus, go to **Settings → Broker**, paste the App ID and Secret ID,
   and save.
4. Click **Connect with FYERS** and authorise.

Confirm it worked:

```bash
curl -s http://localhost:8000/api/v1/market/status          # needs a session cookie
```

You want `"connected": true` and `"source": "live"`. If `/market/option-chain`
still returns `"source": "mock"`, the connection is not live — check
**Settings → Broker**, which validates the token against the broker rather than
merely reporting that one exists.

Notes:

- The App ID must match `ABCDE123XY-100` in shape. The server upper-cases it.
- The Secret ID is stored encrypted and is never returned; the form is
  write-only.
- **Disconnect** drops the token and keeps your API keys, so reconnecting is one
  click. **Remove credentials** drops both.
- Changing the App ID invalidates any existing token, so the connection returns
  to *pending*.
- If the redirect URI in `backend/.env` (`CN_BROKER_FYERS_REDIRECT_URI`) does not
  match what you registered with FYERS, the consent screen will reject the
  request before it reaches us.

The design decisions behind this flow are recorded in
[ADR 0001](../adr/0001-fyers-broker-integration.md).

## 7c. Optional: enable the AI Console (Hella / STRYX)

The AI Console runs on a **per-user** LLM key — there is no shared server key.

1. Install the model SDK once: `cd backend && uv sync --extra llm` (and run the
   API with `--extra agent --extra llm`, see [RUNNING.md](../RUNNING.md)).
2. In ChartNexus, go to **Settings → AI**, pick **Claude**, paste your own
   Anthropic API key, choose a model, and save.

The key is stored encrypted at rest (AES-256-GCM, HKDF purpose `ai-settings`),
bound to your user row so it cannot be lifted into another user's row. Until you
save one, your AI Console tabs show an "offline" notice and
`GET /api/v1/copilot/availability` returns `{"available": false}`; after saving
it flips to `true`. Remove the key any time with **Remove key** on the same page.

If the encryption secret (`CN_SECURITY_ENCRYPTION_KEY`) changes, a stored key
becomes undecryptable and is reported as absent — just re-enter it, or set the old
value in `CN_SECURITY_PREVIOUS_ENCRYPTION_KEYS` when rotating.

## 8. Everything in containers

An alternative to terminals 2 and 3 — **not recommended on Windows**, where the
`web` container never hot-reloads host edits (see section 3):

```bash
docker compose up --build          # postgres, redis, api, web, ingest
docker compose --profile full up   # also score and realtime
```

`ingest` has no profile on purpose — it is the only writer of the option-chain
archive. `score` is an empty placeholder; `realtime` is the websocket.

## 9. Common commands

```bash
# Tests
cd backend  && uv run pytest tests/unit tests/architecture   # fast, no containers
cd backend  && uv run pytest tests/integration               # needs containers
cd frontend && pnpm test                                     # vitest
cd frontend && pnpm test:e2e                                 # playwright

# Quality
cd backend  && uv run ruff check --fix . && uv run ruff format .
cd backend  && uv run mypy
cd backend  && uv run lint-imports          # architecture contracts
cd frontend && pnpm lint && pnpm typecheck

# Database
cd backend && uv run alembic upgrade head
cd backend && uv run alembic downgrade -1
cd backend && uv run alembic current --verbose
cd backend && uv run alembic revision --autogenerate -m "message" \
  --version-path migrations/versions/identity
```

With [go-task](https://taskfile.dev) installed (`winget install Task.Task`), the
`Taskfile.yml` wraps these: `task setup`, `task up`, `task dev`, `task dev:web`,
`task check` (lint + types + unit tests, both sides), `task test:integration`,
`task arch`, `task db:migrate`.

**Integration tests use your dev database** (`localhost:5433/chartnexus`). They
create throwaway users and uniquely-named symbols, so they do not touch your
data, but they do leave those rows behind. On Windows a few may report
`PytestUnraisableExceptionWarning … unclosed transport` — an asyncio socket
warning the suite promotes to an error, not an application failure; re-run the
file to confirm.

## 10. Troubleshooting

**`Port 5173 is already in use`**
Almost always the `chartnexus-web-1` container, not a stale Vite —
`docker compose stop web`. If it really is another project, `pnpm dev --port
5174` and see the port note above about the OAuth redirect URIs.

**`error while attempting to bind on address ('127.0.0.1', 8000)`**
An API instance is already running — often the `chartnexus-api-1` container
(`docker compose stop api`). Otherwise find it with
`netstat -ano | findstr :8000`, then `taskkill /PID <pid> /F`. If `netstat` shows
`com.docker.backend` owning the port, a container holds it.

**Random 502s on login, or a session that "forgets" you**
Two backends on one port — a container on `0.0.0.0:8000` and a host uvicorn on
`127.0.0.1:8000`. Windows lets both bind, and `localhost` picks one by IPv4/IPv6
preference. Stop the container: `docker compose stop api web`.

**"Can't reach the server" page**
The web app is up but the API is not answering. Start the API (section 3) and
reload.

**Kite shows *expired* every morning**
Expected — Kite tokens end at 06:00 IST daily. Reconnect from
**Settings → Broker**.

**`Bind for 0.0.0.0:5433 failed: port is already allocated`**
Another project's container has the port. Change `POSTGRES_PORT` in `.env`,
update `CN_DB_URL` in `backend/.env`, then `docker compose up -d` again.

**`/health/ready` returns `"postgres": "error: InvalidPasswordError"`**
`CN_DB_URL` credentials do not match `POSTGRES_USER`/`POSTGRES_PASSWORD` in the
root `.env`. If you changed them after the first start, the database was already
initialised with the old ones — `docker compose down -v` and start again
(this deletes local data).

**`Target database is not up to date`**
Run `cd backend && uv run alembic upgrade head`.

**API starts but every login returns 500**
Usually a missing migration. Check `uv run alembic current` against
`migrations/versions/`.

**`the JWT signing key must be at least 32 bytes for HS256`**
`CN_AUTH_JWT_SIGNING_KEY` is set but too short. Generate one:
`python -c "import secrets; print(secrets.token_urlsafe(48))"`, or leave it
empty locally to inherit `CN_SECURITY_SECRET_KEY`.

**Broker says connected but data is still `source: "mock"`**
The token is present but the broker is rejecting it. **Settings → Broker**
validates against the broker's profile endpoint rather than trusting that a
token exists, so it will show *expired* — reconnect. If it shows *active*,
check the API log for a `broker_circuit_opened` warning, which means the
provider is failing and requests are short-circuiting to cached or mock data.

**Broker connection disappears after changing `CN_SECURITY_ENCRYPTION_KEY`**
Expected. That key encrypts stored credentials; changing it makes existing rows
undecryptable. They are reported as *expired* rather than raising, so reconnect
through **Settings → Broker**. Keep the key stable, or put the old value in
`CN_SECURITY_PREVIOUS_ENCRYPTION_KEYS` when rotating — rows then keep decrypting
and are re-encrypted under the new key the next time they are saved.

**`This connection link expired. Start again.`**
The OAuth `state` was unknown, already used, or older than its ten-minute TTL.
States are single-use by design. Start the connection again from
**Settings → Broker**.

**Frontend loads but every API call is 401**
The Vite proxy targets `http://localhost:8000`. If the API is on another port,
set `API_PROXY_TARGET` in `frontend/.env`.

**The Options Lab / Open Interest charts are flat or empty**
Nothing has written today's snapshot archive yet, or the market is closed. Check
the API log (or the ingest worker's) for `ingest_tick` lines; outside 09:15–15:40
IST they read `market_closed`. To get history now, seed one — see
[RUNNING.md](../RUNNING.md#seeing-history-immediately-optional).

## 11. Resetting

```bash
docker compose down          # stop, keep data
docker compose down -v       # stop and delete the database and cache
```

After `down -v`, re-run `alembic upgrade head` before starting the API.
