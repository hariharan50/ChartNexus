# Deploying ChartNexus to a VPS

The whole application runs on one machine with `docker compose`. Nothing below
needs Kubernetes, and the Helm chart under `deploy/helm/` is empty scaffolding —
ignore it.

- **Stack:** [`deploy/compose/compose.prod.yml`](../../deploy/compose/compose.prod.yml)
- **Configuration:** one file, `.env.production`, from `.env.production.example`
- **Edge:** nginx terminates TLS and maps one hostname onto the API and the web
  app, because the browser bundle calls `/api/v1/...` as a same-origin path

## What you need

| Thing   | Minimum                | Notes                                        |
| ------- | ---------------------- | -------------------------------------------- |
| RAM     | 4 GB                   | 8 GB if the AI agents get real use           |
| vCPU    | 2                      | 4 is comfortable                             |
| Disk    | 40 GB SSD              | The snapshot archive grows with retention    |
| OS      | Ubuntu 24.04 LTS       | Anything with Docker Engine 27+ works        |
| Docker  | Engine 27+, Compose v2 | `docker compose version` must print v2 or v5 |
| DNS     | An A record            | Pointing at the VPS **before** step 5        |
| Ports   | 80 and 443 inbound     | Open at the provider's firewall too          |

Fifteen containers run: Postgres, Redis, nginx, certbot, the API, the web app,
and seven workers. The workers are not optional — see
[What the workers do](#what-the-workers-do).

## 1. Prepare the server

```bash
# Docker Engine + Compose, from Docker's own repository rather than Ubuntu's.
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"   # log out and back in for this to take effect

# Only 22, 80 and 443 reach the machine. Nothing else in the stack publishes a
# port, but a host firewall is what makes that a guarantee rather than a hope.
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

Docker publishes ports by writing iptables rules that bypass ufw, so a service
that publishes to `0.0.0.0` is reachable even with ufw denying it. This stack
publishes only 80 and 443 (from nginx) for exactly that reason — if you add a
published port later, bind it to `127.0.0.1` explicitly.

## 2. Get the code

```bash
sudo mkdir -p /srv/chartnexus && sudo chown "$USER" /srv/chartnexus
git clone <your-remote> /srv/chartnexus
cd /srv/chartnexus

# The repository is developed on Windows, where git has core.fileMode=false and
# records every file as non-executable. Without this the scripts below fail with
# "Permission denied". Harmless to re-run.
chmod +x scripts/operations/*.sh
```

## 3. Configure

```bash
cp .env.production.example .env.production
chmod 600 .env.production
```

Then fill in every value the file marks REQUIRED. The secrets, each generated
separately:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # x5
```

Read the comments in the file; three points are worth repeating here.

**`CN_SECURITY_ENCRYPTION_KEY` is not recoverable.** It encrypts every stored
broker credential and per-user LLM key. Lose it and those rows are ciphertext
with no key — a database backup will not save you. Copy it somewhere that is
not this VPS before the first user connects a broker account.

**Passwords go into connection URLs.** Keep `POSTGRES_PASSWORD` and
`REDIS_PASSWORD` to URL-safe characters; `token_urlsafe` already is. A `@` or
`/` in a password produces a DSN that parses into the wrong host.

**`CN_BROKER_PROVIDER` must be `fyers`.** The process refuses to start in a
deployed environment with `mock`, by design: a chart drawn from generated
numbers is pixel-identical to one drawn from the exchange, and only
`provenance.source` distinguishes them. No FYERS credentials go in this file —
each tenant connects their own broker application in the app.

## 4. First deploy

```bash
./scripts/operations/deploy.sh
```

It validates the config, builds the three images, runs migrations to completion,
starts everything, and waits for `/health/ready`. On a 2-vCPU box the first
build takes 5–10 minutes.

At this point the site answers on HTTPS with a **self-signed** certificate, so a
browser will warn. nginx generates one on first start because it will not start
without a certificate to open, and certbot cannot prove a domain to a server
that is not running. Step 5 replaces it.

## 5. Get a real certificate

Check DNS has propagated first — this is the step that fails most often:

```bash
dig +short A "$(grep -E '^CN_DOMAIN=' .env.production | cut -d= -f2)"
```

That must print this VPS's public address. Then:

```bash
./scripts/operations/issue-certificate.sh
```

The script proves the challenge path is reachable from the internet before it
asks Let's Encrypt for anything, because Let's Encrypt rate-limits failures to
five per hostname per hour. To rehearse against their staging environment
first, set `CN_ACME_STAGING=true` in `.env.production`, run it, then remove the
line and run it again.

Renewal is automatic from here: the `certbot` service tries twice a day.

## 6. Create the first account

Registration defaults to closed (`CN_AUTH_REGISTRATION_ENABLED=false`). Open
it, sign up, close it again:

```bash
sed -i 's/^CN_AUTH_REGISTRATION_ENABLED=.*/CN_AUTH_REGISTRATION_ENABLED=true/' .env.production
docker compose --env-file .env.production -f deploy/compose/compose.prod.yml up -d api
# ... sign up at https://<your domain> ...
sed -i 's/^CN_AUTH_REGISTRATION_ENABLED=.*/CN_AUTH_REGISTRATION_ENABLED=false/' .env.production
docker compose --env-file .env.production -f deploy/compose/compose.prod.yml up -d api
```

Then, in the app:

- **Settings → Broker** — connect a FYERS account, or the market data stays empty
- **Settings → AI** — paste your own Anthropic key to switch the AI Console on.
  Keys are per-user and stored encrypted; there is no server key.

## 7. Schedule the backups

```bash
crontab -e
```

```cron
# Nightly, after the F&O close. Keeps 14 days.
30 18 * * 1-5 cd /srv/chartnexus && ./scripts/operations/backup-postgres.sh >> /var/log/chartnexus-backup.log 2>&1
```

Dumps land in `/srv/chartnexus/backups/`, which is on the VPS — so it survives
a container rebuild but not the VPS. Copy them off the machine; so far nothing
does that for you.

A backup you have never restored is a hypothesis. Restore one into a throwaway
database and look at it before you need to.

---

## Everyday operations

Every command assumes `cd /srv/chartnexus`. The compose invocation is long, so:

```bash
alias cnx='docker compose --env-file .env.production -f deploy/compose/compose.prod.yml'
```

| Task                  | Command                                              |
| --------------------- | ---------------------------------------------------- |
| Deploy a new revision | `git pull && ./scripts/operations/deploy.sh`          |
| What is running       | `cnx ps`                                              |
| Follow the API log    | `cnx logs -f api`                                     |
| One worker's log      | `cnx logs -f ingest`                                  |
| Restart one service   | `cnx restart api`                                     |
| Readiness, in detail  | `cnx exec api curl -s localhost:8000/health/ready`     |
| Liveness, externally  | `curl -sS https://<domain>/healthz`                    |
| A psql shell          | `cnx exec postgres psql -U chartnexus chartnexus`      |
| Back up now           | `./scripts/operations/backup-postgres.sh`              |
| Restore               | `./scripts/operations/restore-postgres.sh backups/...` |
| Stop everything       | `cnx down`                                             |

`cnx down -v` deletes the database and the certificates. There is no prompt.

### Rolling back

`CN_IMAGE_TAG` names the images a deploy builds. Set it to a git SHA in CI and
a rollback is that tag plus the matching checkout:

```bash
git checkout <previous-sha>
CN_IMAGE_TAG=<previous-sha> ./scripts/operations/deploy.sh
```

A migration is not undone by this. `alembic downgrade` is a decision to make
deliberately, with the backup `deploy.sh` took before it migrated.

---

## What the workers do

In local development the API runs all of these in-process. That is gated on
`CN_ENVIRONMENT=local`, so here they are separate containers — a slow broker
call can then never occupy an API worker. **None of them is decorative:** stop
one and a part of the product goes quietly blank rather than erroring.

| Service           | What stops working without it                                   |
| ----------------- | --------------------------------------------------------------- |
| `catalog`         | Nothing resolves at all. It owns the F&O universe and the lot sizes, which NSE revises by circular several times a year. |
| `ingest`          | The Options Lab charts lose their intraday history and fall back to a two-point "open vs now" estimate; Gamma and Vega show nothing. |
| `futures-oi`      | The Future Lab build-up columns go empty.                        |
| `futures-history` | Future Lab's intraday charts and Replay have no frames.          |
| `hugin`           | HUGIN stops accumulating graded market memory.                   |
| `mme100`          | No morning pre-market briefing.                                  |
| `report`          | No daily PDF for enrolled tenants.                               |

`catalog-sync` and `migrate` are one-shot release tasks, not workers — they run
to completion on each deploy and exit. A `docker compose ps` showing them as
`exited (0)` is correct.

### Not deployed, because it does not exist yet

- **`score`** — `main_score.py` is empty. `chartnexus-signals` is an offline
  fit/backtest CLI, not a worker.

---

## Troubleshooting

### Every request says "NIFTY is not a tradeable instrument"

The instrument catalog is empty, so nothing resolves. Check it:

```bash
cnx exec postgres psql -U chartnexus chartnexus -c "select count(*) from instrument_catalog;"
```

Zero means the symbol-master download has not succeeded. Run it in the
foreground to see why:

```bash
cnx run --rm catalog-sync
```

A process that starts before the catalog is populated recovers on its own now —
every one of them re-reads the catalog on a timer
(`CN_CATALOG_REGISTRY_REFRESH_SECONDS`, default 900s), so a successful sync
reaches the running API without a restart.

### A container restarts in a loop

Almost always configuration. `Settings.assert_deployment_safe()` refuses to
start with a development default still in place, and names the variable:

```bash
cnx logs api | tail -30
```

`unsafe configuration for production: ...` is that check. Fix the variable in
`.env.production` and `cnx up -d api`.

### The browser still warns about the certificate

Either step 5 has not run, or it failed. Check which certificate nginx opened:

```bash
cnx exec nginx openssl x509 -noout -issuer -dates \
  -in "/etc/nginx/certs/live/$(grep -E '^CN_DOMAIN=' .env.production | cut -d= -f2)/fullchain.pem"
```

An issuer equal to the subject is the self-signed placeholder. Re-run
`./scripts/operations/issue-certificate.sh` and read its preflight output.

### Charts are flat, or the Open Interest timeline has nothing to scrub

The ingest worker is the only writer of that archive. It also only writes
during market hours, and deliberately refuses to write mock frames in
production (`CN_MARKET_INGEST_ALLOW_MOCK=false`), so a weekend looks identical
to a broken worker:

```bash
cnx logs --tail=50 ingest
```

`skipped_mock` on every tick means no FYERS account is connected — the archive
stays empty by design until one is. Connect it under **Settings → Broker**.

### Sign-in fails with no error in the API log

`CN_SECURITY_COOKIE_SECURE=true` and `CN_SECURITY_COOKIE_DOMAIN` are set from
`CN_DOMAIN`. If you reach the app by IP address or through a different
hostname, the browser will not store the session cookie and will not say so.
Use the domain in `CN_DOMAIN`.

### Disk filling up

Three candidates, in order of likelihood:

```bash
docker system df                                    # images and build cache
du -sh backups/                                     # old dumps
cnx exec postgres psql -U chartnexus chartnexus -c \
  "select pg_size_pretty(pg_database_size('chartnexus'));"
```

Container logs are capped at 100 MB each by the compose file. For the database,
`CN_MARKET_SNAPSHOT_RETENTION_DAYS` is the lever — the archive is the bulk of
it and grows linearly with that number. `docker system prune -af` reclaims old
images, and is safe: the running containers hold references to theirs.

---

## Security notes

What the stack does:

- Only nginx publishes a port. Postgres and Redis are on the compose network
  with no host binding, and Redis requires a password.
- TLS 1.2+, HSTS preloaded, and the hardening headers on every response — set
  both by the app and by nginx, so a misconfigured proxy cannot silently drop
  them.
- `/api/v1/auth/` is rate-limited at the edge (12 r/m per address) on top of
  the application's own per-account lockout. The two cover different attacks:
  one address walking many accounts, and many addresses walking one account.
- Containers run as a non-root user, built from pinned base images.
- API docs and the OpenAPI schema are disabled when deployed.
- Broker credentials and per-user LLM keys are encrypted at rest with
  AES-256-GCM; passwords are Argon2id.

What it does not do, and you may want:

- **Off-site backups.** `backups/` is on the same disk as the database.
- **An uptime monitor** pointed at `https://<domain>/healthz`.
- **Metrics.** `observability/prometheus/prometheus.yml` and the backend's
  `metrics.py` are both empty files; there is no `/metrics` endpoint to scrape
  yet. Logs are structured JSON on stdout and `docker compose logs` is the
  only collector.
- **fail2ban** on SSH, and key-only SSH authentication.
