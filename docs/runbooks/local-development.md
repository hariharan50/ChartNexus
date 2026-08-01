# Running MarketCompass locally

Everything below assumes the repository root, `C:\Users\sriha\Documents\vscode\MarketCompass`.

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
uv run uvicorn marketcompass.entrypoints.main_api:create_app --factory --reload --port 8000
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
`REDIS_PORT`), and keep `backend/.env` (`MC_DB_URL`, `MC_REDIS_URL`) in step.

**If you run the web app on a port other than 5173**, also update
`MC_GOOGLE_REDIRECT_URI` in `backend/.env` and the authorized redirect URI in
the Google console — the OAuth callback URL must match exactly.

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
MC_GOOGLE_CLIENT_ID=<client id>
MC_GOOGLE_CLIENT_SECRET=<client secret>
MC_GOOGLE_REDIRECT_URI=http://localhost:5173/auth/google/callback
```

5. Restart the API.

## 7. Everything in containers

An alternative to terminals 2 and 3, at the cost of slower reloads:

```bash
docker compose up --build          # postgres, redis, api, web
docker compose --profile full up   # also ingest, score, realtime
```

## 8. Common commands

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

## 9. Troubleshooting

**`Port 5173 is already in use`**
Another dev server has it. `pnpm dev --port 5174`, and see the port note above
about the Google redirect URI.

**`error while attempting to bind on address ('127.0.0.1', 8000)`**
An API instance is already running. Find it with
`netstat -ano | findstr :8000`, then `taskkill /PID <pid> /F`.

**`Bind for 0.0.0.0:5433 failed: port is already allocated`**
Another project's container has the port. Change `POSTGRES_PORT` in `.env`,
update `MC_DB_URL` in `backend/.env`, then `docker compose up -d` again.

**`/health/ready` returns `"postgres": "error: InvalidPasswordError"`**
`MC_DB_URL` credentials do not match `POSTGRES_USER`/`POSTGRES_PASSWORD` in the
root `.env`. If you changed them after the first start, the database was already
initialised with the old ones — `docker compose down -v` and start again
(this deletes local data).

**`Target database is not up to date`**
Run `cd backend && uv run alembic upgrade head`.

**API starts but every login returns 500**
Usually a missing migration. Check `uv run alembic current` against
`migrations/versions/`.

**`the JWT signing key must be at least 32 bytes for HS256`**
`MC_AUTH_JWT_SIGNING_KEY` is set but too short. Generate one:
`python -c "import secrets; print(secrets.token_urlsafe(48))"`, or leave it
empty locally to inherit `MC_SECURITY_SECRET_KEY`.

**Frontend loads but every API call is 401**
The Vite proxy targets `http://localhost:8000`. If the API is on another port,
set `API_PROXY_TARGET` in `frontend/.env`.

## 10. Resetting

```bash
docker compose down          # stop, keep data
docker compose down -v       # stop and delete the database and cache
```

After `down -v`, re-run `alembic upgrade head` before starting the API.
