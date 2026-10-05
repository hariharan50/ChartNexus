# Running ChartNexus locally

Everything below assumes the repository root, `C:\Users\sriha\Documents\vscode\ChartNexus`.

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

## 4. Ports

Host ports are deliberately shifted so other projects on this machine keep working.

| Service    | Host port | Notes                                                  |
| ---------- | --------- | ------------------------------------------------------ |
| Web app    | 5173      | `pnpm dev --port 5174` if something else has 5173       |
| API        | 8000      | docs at <http://localhost:8000/docs>                    |
| Postgres   | 5433      | container listens on 5432 internally                    |
| Redis      | 6381      | container listens on 6379 internally                    |

Change the database and cache ports in the root `.env` (`POSTGRES_PORT`,
`REDIS_PORT`), and keep `backend/.env` (`CN_DB_URL`, `CN_REDIS_URL`) in step.

**If you run the web app on a port other than 5173**, update both OAuth
redirect URIs — `CN_GOOGLE_REDIRECT_URI` and `CN_BROKER_FYERS_REDIRECT_URI` in
`backend/.env` — and the matching entries in the Google console and the FYERS
dashboard. Both providers require an exact string match.

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

## 7. Optional: connect a FYERS broker account

Also optional. Without it the app serves a deterministic mock feed, labelled
`source: "mock"` in every response and shown as **Simulated** in the UI.

Each tenant connects their own broker application — there is no shared
system-wide account.

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

## 7b. Optional: enable the AI Console (Hella / STRYX)

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

An alternative to terminals 2 and 3, at the cost of slower reloads:

```bash
docker compose up --build          # postgres, redis, api, web
docker compose --profile full up   # also ingest, score, realtime
```

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
cd frontend && pnpm lint && pnpm check

# Database
cd backend && uv run alembic upgrade head
cd backend && uv run alembic downgrade -1
cd backend && uv run alembic current --verbose
cd backend && uv run alembic revision --autogenerate -m "message" \
  --version-path migrations/versions/identity
```

With [go-task](https://taskfile.dev) installed (`winget install Task.Task`), the
`Taskfile.yml` wraps these: `task setup`, `task up`, `task dev`, `task check`,
`task db:migrate`.

## 10. Troubleshooting

**`Port 5173 is already in use`**
Another dev server has it. `pnpm dev --port 5174`, and see the port note above
about the Google redirect URI.

**`error while attempting to bind on address ('127.0.0.1', 8000)`**
An API instance is already running. Find it with
`netstat -ano | findstr :8000`, then `taskkill /PID <pid> /F`.

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

## 11. Resetting

```bash
docker compose down          # stop, keep data
docker compose down -v       # stop and delete the database and cache
```

After `down -v`, re-run `alembic upgrade head` before starting the API.
