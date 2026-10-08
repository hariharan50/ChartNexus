# Production handoff — what changed, and why

A record of the work that made this repository deployable, written for whoever
(or whatever) does the deploy next. [vps-deployment.md](vps-deployment.md) is
the procedure; this is the context behind it.

Read [Do not undo these](#do-not-undo-these) before touching the deployment
files. Four of them look wrong and are not.

**Starting point.** The application code was already sound — 1299 unit and
architecture tests passing, 61 integration tests, mypy clean across 589 files,
ruff clean, all three import contracts kept. What did not exist was any way to
run it on a server: `deploy/docker/nginx.Dockerfile`, every file in the Helm
chart, all nine CI workflows, `compose.test.yml`, `compose.observability.yml`,
`observability/prometheus/prometheus.yml`, `metrics.py` and `tracing.py` were
all zero bytes. The only compose stack was the development one — bind mounts,
hot reload, `CN_DEBUG=true`, `localhost` URLs.

Nothing in the business logic was changed. Every edit below is deployment
plumbing, except the registry fix (#5), which was a real bug that only
manifests outside `CN_ENVIRONMENT=local`.

---

## Six things that would have failed on the server

Found by building and running the stack, not by reading it.

### 1. The frontend image could not build at all

`COPY frontend/ ./` in the build stage dropped the host's pnpm symlink tree on
top of the `node_modules` the `dependencies` stage had installed. BuildKit
stopped with `cannot copy to non-directory: .../@types/json-schema`. There was
no `.dockerignore` anywhere in the repository, so the same copy would also have
baked `frontend/.env` into an image layer, where it stays readable after any
later `rm`.

**Fixed by** `.dockerignore` (new). It excludes `**/node_modules`, `**/.venv`,
`**/.env*` (except the examples), build output, caches, `.git` and test
artefacts. This also repaired the *development* image targets, which had the
same latent problem — the dev compose file was papering over it with an
anonymous volume on `/app/node_modules`.

### 2. No worker could start

`compose.prod.yml` invoked the `chartnexus-catalog`, `chartnexus-ingest` (etc.)
console scripts declared in `backend/pyproject.toml`. The runtime image never
creates them: `backend.Dockerfile` installs dependencies with
`uv sync --frozen --no-install-project --no-dev`, deliberately, so the
application is imported from `PYTHONPATH=/app/src` rather than site-packages.

```
exec: "chartnexus-catalog": executable file not found in $PATH
```

**Fixed by** invoking the modules instead —
`python -m chartnexus.entrypoints.main_catalog` — which is also what
`compose.dev.yml` already did. Every entrypoint has an `if __name__ ==
"__main__"` guard, verified.

### 3. The web container crash-looped

The frontend `runtime` stage is `FROM node:22-alpine` — a fresh base that never
ran `corepack enable`. `CMD ["pnpm", "start"]` therefore failed with
`Error: Cannot find module '/app/pnpm'`, restarting forever.

**Fixed by** running the binary the `start` script wraps:
`CMD ["node_modules/.bin/react-router-serve", "./build/server/index.js"]`.
Re-adding corepack would have fixed the PATH but made the container fetch its
own package manager on first boot — a network dependency a production start does
not need.

### 4. nginx would 502 after every deploy

nginx resolves a literal hostname in `proxy_pass` **once**, at startup, and
caches the address for the life of the process. `docker compose up -d`
recreates `api` and `web` without recreating nginx, so nginx kept dialling
addresses nothing was listening on.

Observed, not theorised: after a rebuild the two containers' IPs **swapped**
(`web` .8→.12, `api` .12→.8), so API traffic would have been served by the web
process and vice versa.

**Fixed by** `resolver 127.0.0.11 valid=10s ipv6=off` (Docker's embedded DNS)
in `deploy/nginx/nginx.conf`, plus a *variable* in every `proxy_pass` — nginx
only re-resolves when the host comes from a variable. Verified by recreating
both containers with nginx untouched: both routes stayed at 200.

### 5. The instrument registry never recovered in production

The real bug. Every long-running process — the API and six workers — called
`load_registry()` exactly once at startup, with no retry and no refresh. The
only thing that ever *filled* the catalog was `run_catalog_loop`, which the API
starts in-process **only when `CN_ENVIRONMENT=local`**. So in production:

- A first deploy, or any start that beat Postgres to accepting connections, left
  the process with an empty registry and nothing to fix it. Every request
  answered *"NIFTY is not a tradeable instrument"* until a human restarted it.
- A process that started cleanly still never saw the next morning's refresh.
  After a lot-size circular the API would keep quoting yesterday's.

`ensure_registry`'s own docstring describes this exact outage. The API did not
use it.

**Fixed by** `run_registry_refresh_loop` in `catalog_runtime.py`: re-reads the
catalog from the database on a timer, escalating from 5s to 60s while the
registry is empty and settling at `CN_CATALOG_REGISTRY_REFRESH_SECONDS`
(default 900) once it is not. It **never syncs** — the ~19 MB symbol-master
download stays the catalog worker's job alone, so six processes cannot stampede
the rows they all read. The API runs it in every environment; the workers get it
through the `registry_kept_current` context manager. Six tests.

### 6. All seven workers reported `unhealthy` forever

They inherited the backend image's `HEALTHCHECK`, which curls the API's
`/health/live`. A worker is a loop with no socket, so the check could never
pass and `docker compose ps` read as a wholly broken stack.

**Fixed by** `healthcheck: {disable: true}` on the worker anchor and the two
release tasks. A worker that dies exits its container, which
`restart: unless-stopped` already handles.

---

## New files

| Path | What it is |
| --- | --- |
| `deploy/compose/compose.prod.yml` | The stack: 15 services. Self-contained, **not** layered over `compose.yml` — compose merges list keys by appending, so a `ports:` entry in a base file cannot be removed by an override, and layering would have published Postgres and Redis to the internet. |
| `.env.production.example` | The only file to edit on the server. Maps ~15 inputs onto the application's ~90 `CN_*` settings. |
| `.dockerignore` | See #1. Load-bearing, not an optimisation. |
| `deploy/nginx/nginx.conf` | Main config: the resolver (#4), rate-limit zones, real-IP recovery, log format, gzip. |
| `deploy/nginx/templates/chartnexus.conf.template` | The server blocks. `envsubst`'d at container start for `${CN_DOMAIN}`; `NGINX_ENVSUBST_FILTER="CN_"` keeps nginx's own `$host` etc. intact. |
| `deploy/nginx/snippets/proxy-api.conf` | The proxy headers, shared by the two API locations. nginx locations do not inherit from one another, and a header forgotten in one copy fails silently. |
| `deploy/nginx/entrypoint/25-ensure-certificate.sh` | Generates a self-signed placeholder if no certificate exists, so nginx can start at all. Breaks the circle where certbot needs a running server and nginx needs a certificate file. |
| `scripts/operations/deploy.sh` | Build → back up → migrate → start → wait for `/health/ready`. Ordered so a failed build stops nothing and a failed migration leaves the old release serving. |
| `scripts/operations/issue-certificate.sh` | First real certificate. Proves the ACME path is reachable *before* asking Let's Encrypt, which rate-limits failures to five per hostname per hour. |
| `scripts/operations/backup-postgres.sh` | `pg_dump --format=custom`, written to `.partial` and renamed on success, then verified with `pg_restore --list`. |
| `scripts/operations/restore-postgres.sh` | Stops writers, recreates the database, restores in one transaction, re-runs migrations. |
| `docs/runbooks/vps-deployment.md` | The procedure, with sizing, troubleshooting and rollback. |
| `backend/tests/unit/entrypoints/test_registry_refresh.py` | 6 tests for #5. |
| `backend/tests/unit/infrastructure/transport/test_security_headers.py` | 6 tests for the headers middleware. |

## Modified files

**Application** — paths below are relative to `backend/src/chartnexus/`.

- `infrastructure/transport/http/middleware.py` — was empty. Now
  `SecurityHeadersMiddleware`: the hardening headers on every response, HSTS
  only when deployed. The strict JSON content policy (`default-src 'none';
  sandbox`) is skipped for `text/html`, so it cannot be the reason Swagger UI
  renders blank locally.
- `entrypoints/main_api.py` — wires that middleware; starts the registry
  refresh loop in **all** environments; adds `proxy_headers=True` and
  `forwarded_allow_ips="*"` to the `run()` helper.
- `entrypoints/catalog_runtime.py` — adds `run_registry_refresh_loop` and the
  `registry_kept_current` context manager.
- `bootstrap/settings.py` — adds `CatalogSettings.registry_refresh_seconds`
  (env: `CN_CATALOG_REGISTRY_REFRESH_SECONDS`, default 900, floor 30).
- `main_ingest.py`, `main_hugin.py`, `main_mme100.py`, `main_report.py`,
  `main_futures_oi.py`, `main_futures_history.py` — each wraps its long-running
  loop in `registry_kept_current`. The one-shot modes (`--once`, `seed`,
  `prune`) are untouched; they exit immediately and need no refresh.

**Images**

- `backend.Dockerfile` — runtime `CMD` gains `--proxy-headers
  --forwarded-allow-ips *`, so the image default is correct behind a proxy.
- `frontend.Dockerfile` — runtime `CMD` fixed (#3); `ARG PUBLIC_ENVIRONMENT`
  added, because Vite inlines `PUBLIC_*` at **build** time, not run time.
- `nginx.Dockerfile` — was empty. Also `rm -f /etc/nginx/conf.d/default.conf`:
  the base image ships a "Welcome to nginx" server on port 80, and
  `nginx.conf` includes `conf.d/*.conf`, so leaving it there answers for any
  Host header the real server block does not claim.

**CI** — five workflows filled in: `backend-ci`, `frontend-ci`,
`architecture-check` (the checks the README calls "enforced by CI", which
nothing was running), `migration-check` (including `alembic check` for
model/migration drift), `security-scan` (gitleaks, pip-audit, pnpm audit,
Trivy).

**README** — corrected `pnpm check` → `pnpm typecheck`; replaced the process
table, which advertised `score` and `realtime` as deployed processes when both
entrypoints are empty files; added a Deploying section.

---

## Do not undo these

Four places where the obvious-looking code is the broken one. Each has a
comment at the site saying so; this is the index.

1. **`proxy_pass http://$api_upstream;` with a `set` directive**, rather than an
   `upstream` block. Looks like a pointless indirection. It is the whole fix for
   #4 — a named upstream cannot be re-resolved, and reverting it reintroduces a
   502 on every deploy. The cost (no upstream keepalive pool) is negligible on a
   local bridge network.
2. **`python -m chartnexus.entrypoints.main_*`** in `compose.prod.yml`, rather
   than the tidier `chartnexus-*` console scripts. Those scripts do not exist in
   the runtime image (#2).
3. **`node_modules/.bin/react-router-serve`** rather than `pnpm start` (#3).
4. **`healthcheck: {disable: true}`** on the workers. Not laziness — the
   inherited check is for an HTTP server they are not (#6).

Also: `compose.prod.yml` is intentionally **not** layered over `compose.yml`.
Merging them to "remove duplication" republishes Postgres and Redis to the host.

---

## What a deployer needs to know

- **`CN_BROKER_PROVIDER` must be `fyers`.** `assert_deployment_safe()` refuses
  to start with `mock` outside local, by design — a chart from generated numbers
  is pixel-identical to one from the exchange, and only `provenance.source`
  separates them. There is no way to run a production environment on mock data,
  and that is deliberate. No FYERS app credentials go in `.env.production`;
  each tenant connects their own in-app.
- **Seven workers, none optional.** `catalog`, `ingest`, `futures-oi`,
  `futures-history`, `hugin`, `mme100`, `report`. Stop one and a part of the
  product goes quietly blank rather than erroring. The table in
  [vps-deployment.md](vps-deployment.md#what-the-workers-do) says what each one
  owns.
- **`migrate` and `catalog-sync` are release tasks.** They run to completion and
  exit on every deploy. `exited (0)` in `docker compose ps` is correct, not a
  failure. `catalog-sync` exists so a first deploy comes up usable instead of
  waiting on the catalog worker's 19 MB download.
- **`CN_SECURITY_ENCRYPTION_KEY` is unrecoverable.** It encrypts every stored
  broker credential and per-user LLM key. A database backup without it is
  ciphertext. Copy it off the VPS before the first user connects a broker.
- **Postgres and Redis publish no host ports.** Use `docker compose exec`.
  Redis requires a password, which is carried in `CN_REDIS_URL`; keep both
  passwords URL-safe, since they are interpolated into DSNs.
- **`/ws` returns 501 on purpose.** `main_realtime.py` is an empty file and
  nothing in the browser opens a socket. An explicit 501 beats a hang. When that
  process is written, add it to the compose file and point the location at it.
- **First boot serves a self-signed certificate** and the browser will warn,
  until `issue-certificate.sh` runs. That is the designed sequence, not a fault.

### The sequence

```bash
# on the VPS
cp .env.production.example .env.production   # fill in the REQUIRED values
chmod 600 .env.production
chmod +x scripts/operations/*.sh             # see the note on file modes below
./scripts/operations/deploy.sh               # build, migrate, start
./scripts/operations/issue-certificate.sh    # real TLS; needs DNS live first
```

`chmod +x` is needed because this repository is developed on Windows with
`core.fileMode=false`, so git records the scripts as non-executable. Either run
that line after cloning, or fix it once at commit time with
`git update-index --chmod=+x scripts/operations/*.sh`.

---

## Already verified — no need to repeat

Done locally against Docker, with the whole stack up:

- All three images build. 13 containers running, `migrate` and `catalog-sync`
  exited 0.
- HTTPS served the real application — `<title>ChartNexus — NSE options
  analytics with provenance on every number</title>`, 30 KB of SSR output.
- `/api/v1/market/status` returned a proper RFC 7807 401 with a request id.
  `/healthz` 200. Readiness reported `postgres: ok, redis: ok` — so Redis
  password auth works end to end.
- All eight nginx routes correct, including longest-prefix precedence for
  `/api/v1/auth/` over `/api/v1/`.
- Rate limits fired at the configured thresholds: 11 requests through then 429
  on the login zone, 20 straight through on the API zone.
- No duplicated security headers; the application's stricter JSON CSP survived
  the proxy intact.
- Redeploy test: `api` and `web` recreated with nginx untouched, IPs swapped,
  both routes still 200.
- No `.env` in any image; all containers non-root (`uid=1001`).
- Backend gate green: ruff, ruff format, mypy (589 files), `lint-imports` (3/3
  contracts), 1299 unit + architecture tests, 61 integration tests.
- `alembic`: single head, `downgrade -1` / `upgrade head` round-trips, `alembic
  check` reports no model drift.

What was **not** verified, because it needs a real server: Let's Encrypt
issuance (no public DNS here), and the FYERS integration (no broker account).

---

## Not done — decide before or soon after launch

- **Off-site backups.** `backups/` is a bind mount on the same disk as the
  database. The dump script and the cron line exist; copying them off the VPS
  does not.
- **Metrics.** `observability/prometheus/prometheus.yml`,
  `backend/src/chartnexus/infrastructure/observability/metrics.py` and its
  `tracing.py` are all empty files; there is no `/metrics` endpoint to scrape. Logs are structured JSON on
  stdout and `docker compose logs` is the only collector. `CN_OTEL_TRACES_ENABLED`
  is a setting with nothing behind it.
- **Source maps are public.** `frontend/vite.config.ts` sets `sourcemap: true`,
  which publishes the analytics logic to anyone who opens devtools. One line to
  change; it is a product decision, so it was left alone.
- **Four CI workflows are still 0 bytes** — `build-images.yml`,
  `contract-check.yml`, `deploy-staging.yml`, `deploy-production.yml`. GitHub
  will report "Invalid workflow file" for each on the first push. Delete them or
  fill them. `tests/contract/` contains no test files, so `contract-check` has
  nothing to run; the deploy workflows need SSH credentials for your VPS.
- **The Helm chart and Terraform modules are empty skeletons.** There is no
  Kubernetes path. Ignore `deploy/helm/` and `infrastructure/`, or delete them
  so they stop implying one exists.
- **No uptime monitor** pointed at `https://<domain>/healthz`, and no fail2ban
  or key-only SSH on the host itself.
