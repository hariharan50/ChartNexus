# ChartNexus — Production Guide

**Live at:** https://chartnexus.profitalgo.in
**App folder on server:** `/opt/chartnexus`
**Server:** Contabo VPS (`vmi3616797`), Ubuntu 26.04, IP `13.140.57.59`, 7.8 GB RAM
**GitHub:** `hariharan50/ChartNexus` (private, read-only deploy key on server)
**Traffic:** Cloudflare Tunnel (no open web ports on the server)
**First deployed:** 8 October 2026, commit `c40b622 Production Ready`

---

## 1. TO UPDATE THE APP (the everyday task)

> ⏰ **Prefer deploying outside market hours (9:15 to 15:30 IST).** A deploy restarts the API and the 7 market-data workers. Option-chain snapshots taken during the restart are missed, and logged-in users are briefly disconnected.

**Step 1: On your PC.** Commit and push to `main`.

```bash
git add .
git commit -m "describe the change"
git push
```

If you added or changed any `.sh` script, mark it executable before committing (your PC has `core.fileMode=false`):

```bash
git update-index --chmod=+x scripts/operations/*.sh
```

**Step 2: On the server.**

```bash
ssh root@13.140.57.59
/opt/chartnexus/update.sh
```

It must end with **`✅ DEPLOY OK`**. If any step fails, the script stops right there and shows the error.

> **Know your windows.** A prompt starting with `root@vmi3616797` is the **server**. A prompt like `C:\Users\sriha\...>` or `PS C:\...>` is **your PC**. Pushing only works from your PC; the server's GitHub key is read-only.

---

## 2. THE update.sh SCRIPT (create once)

Paste this whole block on the server once. Paste it again to recreate the script if it's ever lost.

```bash
cat > /opt/chartnexus/update.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd /opt/chartnexus
C="docker compose --env-file .env.production -f deploy/compose/compose.prod.yml -f deploy/compose/compose.server.yml"
PGUSER=$(grep '^POSTGRES_USER=' .env.production | cut -d= -f2)
PGDB=$(grep '^POSTGRES_DB=' .env.production | cut -d= -f2)

echo "== 1/6 Backing up database =="
mkdir -p /root/chartnexus-backups
$C exec -T postgres pg_dump -U "$PGUSER" "$PGDB" | gzip > "/root/chartnexus-backups/db-$(date +%F-%H%M).sql.gz"
find /root/chartnexus-backups -name 'db-*.sql.gz' -mtime +14 -delete
ls -lh /root/chartnexus-backups | tail -n 1

echo "== 2/6 Pulling latest code =="
git pull --ff-only
git log --oneline -1

echo "== 3/6 Safety check: ports =="
if $C config | grep -E 'published: "(80|443)"' ; then
  echo "❌ ChartNexus would publish 80/443 and break every other site. Check deploy/compose/compose.server.yml."
  exit 1
fi
echo "Ports OK (127.0.0.1:8093 / 8094 only)"

echo "== 4/6 Building and restarting =="
$C up -d --build

echo "== 5/6 Waiting for services =="
sleep 45
$C ps -a --format 'table {{.Service}}\t{{.Status}}'

echo "== 6/6 Health check =="
LOCAL=$(curl -sk --resolve chartnexus.profitalgo.in:8094:127.0.0.1 -o /dev/null -w "%{http_code}" https://chartnexus.profitalgo.in:8094/)
PUBLIC=$(curl -s -o /dev/null -w "%{http_code}" https://chartnexus.profitalgo.in/)
echo "local nginx: $LOCAL   public via tunnel: $PUBLIC"
[ "$LOCAL" = "200" ] && [ "$PUBLIC" = "200" ] && echo "✅ DEPLOY OK" || { echo "❌ Health check failed"; exit 1; }
EOF

chmod +x /opt/chartnexus/update.sh
grep -qx 'update.sh' /opt/chartnexus/.git/info/exclude || echo 'update.sh' >> /opt/chartnexus/.git/info/exclude
ls -l /opt/chartnexus/update.sh
```

The last two lines add `update.sh` to git's local exclude list, so it never shows up as an untracked file or blocks a `git pull`.

**Test it after creating it.** With nothing new pushed, it backs up, pulls (no changes), rebuilds nothing and confirms everything is healthy:

```bash
/opt/chartnexus/update.sh
```

It must end with **`✅ DEPLOY OK`**.

### Every deploy from now on

1. On your PC: `git push`
2. On the server:
   ```bash
   /opt/chartnexus/update.sh
   ```

What each step does:

| Step | Purpose |
|---|---|
| 1. Backup | `pg_dump` of the database to `/root/chartnexus-backups/`, outside the repo; keeps 14 days |
| 2. Pull | `git pull --ff-only` refuses if the server copy was edited by hand |
| 3. Port guard | Stops if the stack would grab ports 80/443 (that would take down OpenAlgo, StrikeFluency, Todo and Home Launcher) |
| 4. Build | Rebuilds only what changed; `migrate` applies new database migrations automatically |
| 5. Wait | Gives the API and workers time to start |
| 6. Health | Checks Chart Nexus's nginx locally **and** the public site through the tunnel |

---

## 3. HOW IT IS WIRED

```
Browser
  -> Cloudflare (proxied, valid public HTTPS certificate)
  -> Cloudflare Tunnel (cloudflared.service on the server, encrypted)
  -> https://127.0.0.1:8094   (ChartNexus's own nginx container, self-signed cert)
       /api/*  -> api   (FastAPI)
       /*      -> web   (React Router server)
       /ws     -> 501, deliberately (see the handoff doc)
  -> postgres, redis  (container network only, never published)
```

### Services (15)

| Service | Expected status | Role |
|---|---|---|
| `postgres` | Up (healthy) | Database |
| `redis` | Up (healthy) | Market snapshots and sessions |
| `migrate` | **Exited (0)** | One-time release task: runs DB migrations, then exits. That's correct. |
| `catalog-sync` | **Exited (0)** | One-time release task: syncs the catalog, then exits. That's correct. |
| `api` | Up (healthy) | FastAPI backend |
| `web` | Up (healthy) | Frontend server |
| `nginx` | Up (healthy) | Reverse proxy, on `127.0.0.1:8093/8094` only |
| `certbot` | Up | Renewal loop. Idle here: we don't use Let's Encrypt for this app. |
| `catalog`, `ingest`, `futures-oi`, `futures-history`, `hugin`, `mme100`, `report` | Up (no health) | The 7 market-data workers. Healthchecks are **disabled on purpose**. |

### Files and paths

| Item | Path |
|---|---|
| App folder | `/opt/chartnexus` |
| Production compose file | `deploy/compose/compose.prod.yml` (in git; project name `chartnexus`) |
| **Server-only override** | `deploy/compose/compose.server.yml` (**not in git**) |
| Secrets | `/opt/chartnexus/.env.production` (chmod 600, **not in git**) |
| Git-ignore for server-only files | `/opt/chartnexus/.git/info/exclude` (lists `compose.server.yml`, `.env.production` and `update.sh`) |
| Update script | `/opt/chartnexus/update.sh` (server only) |
| DB backups | `/root/chartnexus-backups/` |
| Deploy key | `/root/.ssh/chartnexus_deploy` (host alias `github-chartnexus`) |
| Tunnel config (live) | `/etc/cloudflared/config.yml` |
| Tunnel config (reference copy) | `/opt/cloudflare-tunnel/configs/cloudflared-config.yml` |
| Tunnel README | `/opt/cloudflare-tunnel/README.md` |
| Developer handoff | `docs/runbooks/production-handoff.md` (in the repo) |

### The server-only override (`deploy/compose/compose.server.yml`)

```yaml
# SERVER ONLY - not in git.
services:
  nginx:
    ports: !override
      - "127.0.0.1:8093:80"
      - "127.0.0.1:8094:443"
```

The repo's `compose.prod.yml` publishes `80:80` and `443:443`, which belong to the host nginx and the other apps. `!override` **replaces** the ports list; a plain override would *append* to it and still grab 80/443. To recreate it:

```bash
cd /opt/chartnexus
cat > deploy/compose/compose.server.yml <<'EOF'
services:
  nginx:
    ports: !override
      - "127.0.0.1:8093:80"
      - "127.0.0.1:8094:443"
EOF
```

### The compose command

Every manual command uses all three pieces:

```bash
cd /opt/chartnexus
C="docker compose --env-file .env.production -f deploy/compose/compose.prod.yml -f deploy/compose/compose.server.yml"
$C ps
```

> **Never run** `docker compose -f deploy/compose/compose.prod.yml up` **without** `compose.server.yml`. It would grab 80/443 and take down every site on the server.

---

## 4. CHECK STATUS AND LOGS

```bash
cd /opt/chartnexus
C="docker compose --env-file .env.production -f deploy/compose/compose.prod.yml -f deploy/compose/compose.server.yml"

$C ps -a --format 'table {{.Service}}\t{{.Status}}'      # compare with section 3
$C logs --tail=50 api
$C logs --tail=50 nginx
$C logs --tail=50 ingest            # any worker by name
$C logs -f api                      # live, Ctrl+C to stop
```

**Health checks:**

```bash
# ChartNexus's nginx directly (bypasses Cloudflare)
curl -sk --resolve chartnexus.profitalgo.in:8094:127.0.0.1 -o /dev/null -w "%{http_code}\n" https://chartnexus.profitalgo.in:8094/

# All five sites through the tunnel
for u in https://chartnexus.profitalgo.in/ https://myalgo.profitalgo.in/ https://strikeflu.profitalgo.in/ https://home.profitalgo.in/login https://todo.profitalgo.in/; do
  curl -s -o /dev/null -w "%{http_code} $u\n" $u; done
```

All should be **200**.

**Restart one service:** `$C restart api`

**Resource use:** `docker stats --no-stream | grep chartnexus`

---

## 5. SECRETS (.env.production)

### What's in it

| Variable | Value | Note |
|---|---|---|
| `CN_DOMAIN` | `chartnexus.profitalgo.in` | Cookie domain, CORS, OAuth redirects |
| `POSTGRES_USER` / `POSTGRES_DB` | `chartnexus` | |
| `POSTGRES_PASSWORD` | generated (`token_urlsafe(32)`) | **Never change after first start.** The database keeps the old one. |
| `REDIS_PASSWORD` | generated (`token_urlsafe(32)`) | |
| `CN_SECURITY_SECRET_KEY` | generated (`token_urlsafe(48)`) | Signs sessions and WebSocket tickets |
| `CN_SECURITY_ENCRYPTION_KEY` | generated (`token_urlsafe(48)`) | ⚠️ **See below** |
| `CN_AUTH_JWT_SIGNING_KEY` | generated (`token_urlsafe(48)`) | |
| `CN_BROKER_PROVIDER` | `fyers` | Only valid value in production (`mock` is rejected) |
| `CN_AUTH_REGISTRATION_ENABLED` | `false` | Open only while creating accounts (section 6) |
| `CN_AUTH_REQUIRE_EMAIL_VERIFICATION` | `false` | |
| `CN_GOOGLE_CLIENT_ID` / `_SECRET` | blank | Google sign-in disabled |
| Sizing | defaults | API 1 GB, Postgres 1 GB, Redis 768 MB, web 512 MB |
| `CN_MARKET_SNAPSHOT_INTERVAL_SECONDS` | `180` | Main consumer of the FYERS daily quota |
| `CN_MARKET_SNAPSHOT_RETENTION_DAYS` | `30` | Disk grows linearly with this |
| `CN_ACME_EMAIL` | blank | Not used (no Let's Encrypt for this app) |

### ⚠️ The encryption key

`CN_SECURITY_ENCRYPTION_KEY` encrypts every user's **FYERS credentials** (and LLM keys) in the database. **If it's lost, every stored broker connection is lost for good**, and every user must reconnect FYERS.

- **Never change it** casually. Rotating means putting the old value in `CN_SECURITY_PREVIOUS_ENCRYPTION_KEYS` (comma-separated) so existing rows still decrypt.
- **Never print it** in a terminal you're copying from, and never paste it into a chat, ticket or git.
- During setup the key was replaced twice because it had been exposed. The current one starts with `oScI…`, and the app has only ever run with this key.

### Back up the whole file to your PC

Run this on your **PC**, in PowerShell (`PS C:\...>`), **not** on the server:

```powershell
scp root@13.140.57.59:/opt/chartnexus/.env.production "$env:USERPROFILE\Documents\chartnexus.env.production.BACKUP"
```

Keep that file **out of any git folder**. Ideally also store it in your password manager's secure notes or on an encrypted USB drive.

### Check secrets without showing them

```bash
grep -E '^(POSTGRES_PASSWORD|REDIS_PASSWORD|CN_SECURITY_SECRET_KEY|CN_SECURITY_ENCRYPTION_KEY|CN_AUTH_JWT_SIGNING_KEY)=' /opt/chartnexus/.env.production | sed -E 's/=(.{4}).*/=\1****  (set)/'
```

### Change a non-secret setting

```bash
cd /opt/chartnexus
nano .env.production
C="docker compose --env-file .env.production -f deploy/compose/compose.prod.yml -f deploy/compose/compose.server.yml"
$C up -d
```

---

## 6. USERS AND FYERS

### Create an account (registration is closed by default)

```bash
cd /opt/chartnexus
C="docker compose --env-file .env.production -f deploy/compose/compose.prod.yml -f deploy/compose/compose.server.yml"

# 1. Open registration
sed -i 's/^CN_AUTH_REGISTRATION_ENABLED=.*/CN_AUTH_REGISTRATION_ENABLED=true/' .env.production
$C up -d

# 2. Register at https://chartnexus.profitalgo.in (Ctrl+Shift+R first)

# 3. Close registration straight away
sed -i 's/^CN_AUTH_REGISTRATION_ENABLED=.*/CN_AUTH_REGISTRATION_ENABLED=false/' .env.production
$C up -d
grep '^CN_AUTH_REGISTRATION_ENABLED=' .env.production      # must say false
```

While registration is open, **anyone** who finds the site can sign up. Don't leave it open.

### Connect FYERS

No FYERS credentials go in `.env.production`. Each user connects their own FYERS app **inside Chart Nexus**:

**Settings → Broker → connect FYERS**

These credentials are stored encrypted with `CN_SECURITY_ENCRYPTION_KEY` (section 5).

> The FYERS integration was **not tested against a real account before deployment**, according to the handoff. After connecting, watch the worker logs (`$C logs -f ingest`) during market hours to confirm live data arrives.

---

## 7. CLOUDFLARE TUNNEL ROUTE

Chart Nexus is the fifth hostname on the existing tunnel `58318ec6-ae2b-42fa-b475-bb17b110b6b7`.

**The route** in `/etc/cloudflared/config.yml` (before the final `http_status:404` rule):

```yaml
  - hostname: chartnexus.profitalgo.in
    service: https://127.0.0.1:8094
    originRequest:
      originServerName: chartnexus.profitalgo.in
      noTLSVerify: true
```

- It points at Chart Nexus's **own nginx** on `8094`, not at the host nginx. Chart Nexus already routes `/api`, `/ws` and the web app itself, so there's no host nginx vhost for it.
- **`noTLSVerify: true` is for this route only.** Chart Nexus's nginx serves a self-signed placeholder certificate. The hop is `127.0.0.1` to `127.0.0.1` inside the server, and the tunnel to Cloudflare is encrypted. Visitors see Cloudflare's valid certificate.
- It must use **HTTPS port 8094**, not HTTP 8093. The container's port 80 redirects to HTTPS, which would loop forever behind the tunnel.

**The DNS record**: a CNAME `chartnexus` pointing to `58318ec6-ae2b-42fa-b475-bb17b110b6b7.cfargotunnel.com` (Proxied), created with:

```bash
cloudflared tunnel route dns --overwrite-dns 58318ec6-ae2b-42fa-b475-bb17b110b6b7 chartnexus.profitalgo.in
```

(The Cloudflare dashboard rejected a hand-typed CNAME with "Content for CNAME record is invalid", which is why the CLI was used.)

### Changing tunnel routes safely

```bash
cp /etc/cloudflared/config.yml /etc/cloudflared/config.yml.bak-$(date +%F-%H%M)
nano /etc/cloudflared/config.yml
cloudflared tunnel --config /etc/cloudflared/config.yml ingress validate          # must say OK
cloudflared tunnel --config /etc/cloudflared/config.yml ingress rule https://chartnexus.profitalgo.in
systemctl restart cloudflared && sleep 5 && systemctl is-active cloudflared
cp /etc/cloudflared/config.yml /opt/cloudflare-tunnel/configs/cloudflared-config.yml
```

**Restarting cloudflared briefly drops all five sites.** Afterwards, run the five-site curl check (section 4).

---

## 8. BACKUPS, ROLLBACK, RESTORE

### Database backups

```bash
ls -lh /root/chartnexus-backups/                       # every update.sh makes one; 14 days kept

# Manual backup
cd /opt/chartnexus
C="docker compose --env-file .env.production -f deploy/compose/compose.prod.yml -f deploy/compose/compose.server.yml"
mkdir -p /root/chartnexus-backups
$C exec -T postgres pg_dump -U chartnexus chartnexus | gzip > /root/chartnexus-backups/db-$(date +%F-%H%M).sql.gz
```

**Optional daily backup at 3 AM:**

```bash
cat > /root/chartnexus-backup.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd /opt/chartnexus
docker compose --env-file .env.production -f deploy/compose/compose.prod.yml -f deploy/compose/compose.server.yml \
  exec -T postgres pg_dump -U chartnexus chartnexus | gzip > /root/chartnexus-backups/db-$(date +%F-%H%M).sql.gz
find /root/chartnexus-backups -name 'db-*.sql.gz' -mtime +14 -delete
EOF
chmod +x /root/chartnexus-backup.sh
(crontab -l 2>/dev/null; echo '0 3 * * * /root/chartnexus-backup.sh >> /var/log/chartnexus-backup.log 2>&1') | crontab -
crontab -l
```

> Backups live on the same VPS. If the VPS is lost, so are they. Copy one to your PC now and then:
> `scp root@13.140.57.59:/root/chartnexus-backups/<file>.sql.gz "$env:USERPROFILE\Documents\"`
> A database backup is useless **without the matching `.env.production`**, because the encrypted broker credentials need the encryption key.

### Roll back the code

```bash
cd /opt/chartnexus
git log --oneline -5                       # find the last good commit
git checkout <good-commit-id>
C="docker compose --env-file .env.production -f deploy/compose/compose.prod.yml -f deploy/compose/compose.server.yml"
$C up -d --build
```

Go back to the latest with `git checkout main && /opt/chartnexus/update.sh`.

**A code rollback does not undo a database migration.** If a migration broke things, restore the database.

### Restore the database

```bash
cd /opt/chartnexus
C="docker compose --env-file .env.production -f deploy/compose/compose.prod.yml -f deploy/compose/compose.server.yml"
$C stop api web nginx catalog ingest futures-oi futures-history hugin mme100 report
gunzip -c /root/chartnexus-backups/<file>.sql.gz | $C exec -T postgres psql -U chartnexus -d chartnexus
$C up -d
```

For a clean restore into an empty database, drop and recreate the schema first, or ask before doing it. Test a restore once while nothing is wrong.

---

## 9. DO NOT UNDO THESE (from the developer handoff)

These look wrong, but the tidy-looking alternative is the **broken** one. Each has a comment in the code. See `docs/runbooks/production-handoff.md` for details.

| Looks wrong | Why it's right |
|---|---|
| nginx uses `set $api_upstream` instead of an `upstream` block | An `upstream` block caches container IPs at startup, so every deploy would cause 502 errors |
| Workers start with `python -m ...` | The `chartnexus-*` console scripts don't exist in the runtime image |
| Web starts with `node_modules/.bin/react-router-serve` | `pnpm` isn't in the runtime image |
| Worker healthchecks are disabled | They inherited the API's HTTP healthcheck and showed "unhealthy" forever |
| `/ws` returns 501 | Deliberate |
| `migrate` / `catalog-sync` show `Exited (0)` | One-time release tasks. Exiting with 0 means success. |

If you ask an AI tool to "clean up" this code, **point it at this section first**.

---

## 10. IMPORTANT NOTES

1. **Ports 80/443 are closed** in the firewall (`ufw`). All web traffic arrives through the Cloudflare Tunnel. Only SSH (22) is open.
2. **Don't run `scripts/operations/issue-certificate.sh`.** It's for a server where Chart Nexus owns ports 80/443 and gets its own Let's Encrypt certificate. Here, Cloudflare provides the public certificate.
3. **Don't run the repo's other deploy scripts** unless they include `compose.server.yml`. Use `update.sh`.
4. **Never edit code on the server.** Change it on your PC, push, then run `update.sh`. Local edits make `git pull --ff-only` refuse. `compose.server.yml`, `.env.production` and `update.sh` are excluded from git through `.git/info/exclude`, so they never block a pull.
5. **Never paste secrets anywhere.** Only paste output that shows `****`.
6. **Memory.** Chart Nexus is sized for about 4 GB; the server has 7.8 GB shared with five other apps. Check `free -h` after big changes.
7. **Not done yet** (from the handoff): off-site backups, metrics, four empty CI workflows, empty Helm/Terraform skeletons.

---

## 11. TROUBLESHOOTING

| Symptom | Cause and fix |
|---|---|
| Cloudflare **522** (timed out) | DNS isn't pointing at the tunnel (an A record instead of the tunnel CNAME), or cloudflared is down: `systemctl status cloudflared` |
| Cloudflare **502** / **1033** | cloudflared can't reach `127.0.0.1:8094`. Check `$C ps nginx` and the local curl (section 4). |
| Redirect loop | The tunnel route points at `http://...:8093`. It must be `https://127.0.0.1:8094` (section 7). |
| Other sites went down after a Chart Nexus deploy | Something published 80/443. Check `ss -tlnp \| grep -E ':(80\|443)\b'` and `compose.server.yml`. |
| `api` unhealthy or restarting | `$C logs --tail=100 api`. Usually `.env.production` (`assert_deployment_safe()` rejects default or mock values) or a migration. |
| `migrate` shows `Exited (1)` | A migration failed: `$C logs migrate`. Restore the backup if needed. |
| A worker keeps restarting | `$C logs --tail=100 <worker>`. Usually FYERS not connected or the quota exhausted. |
| `required variable ... missing` | You ran compose without `--env-file .env.production`, or outside `/opt/chartnexus` |
| Can't register | Correct: registration is closed (section 6) |
| Users must reconnect FYERS | The encryption key changed or was lost (section 5) |
| `git pull` refuses ("local changes") | `git status`; someone edited files on the server. Discard with `git checkout <file>`. |
| "Permission denied" on a repo script | Committed from Windows without the execute flag. Run it with `bash <script>`, and fix it on the PC (section 1). |
| `update.sh` says ports 80/443 | `compose.server.yml` is missing or broken. Recreate it (section 3). |

---

## 12. QUICK REFERENCE

```bash
/opt/chartnexus/update.sh                                       # deploy
cd /opt/chartnexus
C="docker compose --env-file .env.production -f deploy/compose/compose.prod.yml -f deploy/compose/compose.server.yml"
$C ps -a --format 'table {{.Service}}\t{{.Status}}'             # status
$C logs --tail=50 api                                           # logs
$C restart api                                                  # restart one service
ls -lh /root/chartnexus-backups/                                # backups
systemctl status cloudflared                                    # tunnel
```

---

## 13. OTHER APPS ON THIS SERVER (do not touch)

| App | Domain | How it runs | Tunnel target |
|---|---|---|---|
| OpenAlgo | myalgo.profitalgo.in | systemd `openalgo.service` | host nginx :443 |
| StrikeFluency | strikeflu.profitalgo.in | `/opt/strikefluency`, Docker, 127.0.0.1:8080 | host nginx :443 |
| Todo | todo.profitalgo.in | Docker, 127.0.0.1:8081 | host nginx :443 |
| Home Launcher | home.profitalgo.in | `/opt/homelauncher`, Docker, 127.0.0.1:8091/8092 | host nginx :443 |
| **ChartNexus** | chartnexus.profitalgo.in | `/opt/chartnexus`, Docker, 127.0.0.1:8093/8094 | **its own nginx :8094** |
| IC Bot | (none) | `/opt/ic-bot`, started by OpenAlgo | (none) |

Used ports: 8080, 8081, 8091, 8092, 8093, 8094, plus 8778 (IC bot dashboard). For a new app, check what's free first:
`ss -tlnp | grep -E ':(8095|8096)\b' || echo free`

---

## 14. FIRST-TIME SETUP (reference only, already done 8 Oct 2026)

1. Pushed the production code from the PC (`c40b622`).
2. Created the deploy key `/root/.ssh/chartnexus_deploy`, added it in GitHub (read-only), and set the alias `github-chartnexus`.
3. Cloned to `/opt/chartnexus`.
4. Created `deploy/compose/compose.server.yml` (nginx on 127.0.0.1:8093/8094), and added it and `.env.production` to `.git/info/exclude`.
5. `cp .env.production.example .env.production`, generated 5 secrets with `secrets.token_urlsafe`, set `CN_DOMAIN`, and ran `chmod 600`.
6. Checked with `$C config` that only 127.0.0.1:8093/8094 are published.
7. `$C up -d --build`: all 15 services in the expected state, local curl 200.
8. Added the tunnel route to `/etc/cloudflared/config.yml` (validated, restarted, reference copy updated).
9. `cloudflared tunnel route dns --overwrite-dns ...` replaced the old A record with the tunnel CNAME.
10. All five sites returned 200 through the tunnel.
11. Created `update.sh` (section 2) and added it to `.git/info/exclude`.
12. Still to do: create an account (section 6), connect FYERS, back up `.env.production` to the PC (section 5).
