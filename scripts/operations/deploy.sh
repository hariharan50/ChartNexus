#!/usr/bin/env bash
# Build and roll out the current checkout.
#
#   ./scripts/operations/deploy.sh
#
# Safe to re-run. The order matters and is the reason this is a script rather
# than a line in a runbook:
#
#   1. Build first. A build that fails must not have stopped anything.
#   2. Back up. The migration in step 4 is the point of no easy return.
#   3. Migrate as a one-shot container, to completion, before any process that
#      opens a session — a worker booting against a half-migrated schema fails
#      in ways that are hard to read.
#   4. Recreate the services.
#
# Rollback is by tag: CN_IMAGE_TAG=<previous> ./scripts/operations/deploy.sh,
# having first checked out that revision. A migration is not rolled back by
# this script; `alembic downgrade` is a decision, not a step.
set -euo pipefail

cd "$(dirname "$0")/../.."

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="deploy/compose/compose.prod.yml"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "error: $ENV_FILE not found. Copy .env.production.example and fill it in." >&2
    exit 1
fi

COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

echo "==> validating the compose configuration and the environment file"
# Catches a missing required variable here, where the message names it, rather
# than on the fourth container to start.
"${COMPOSE[@]}" config --quiet

echo "==> building images"
"${COMPOSE[@]}" build

# Only after a successful build, and only if there is something to back up.
if "${COMPOSE[@]}" ps --status running --services | grep -qx postgres; then
    echo "==> backing up the database before migrating"
    ./scripts/operations/backup-postgres.sh
else
    echo "==> first run: no database to back up yet"
    "${COMPOSE[@]}" up -d postgres redis
fi

echo "==> applying migrations"
# `run --rm` rather than `up`, so this blocks until alembic exits and a
# non-zero status stops the deploy here, with the old release still serving.
"${COMPOSE[@]}" run --rm migrate

echo "==> starting services"
# --remove-orphans so a service deleted from the compose file is not left
# running from a previous release.
"${COMPOSE[@]}" up -d --remove-orphans

echo "==> waiting for the API to report ready"
# /health/ready checks Postgres and Redis, so this covers the whole dependency
# chain and not merely "the process started".
READY=false
for _ in $(seq 1 30); do
    if "${COMPOSE[@]}" exec -T api \
        python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/ready', timeout=3).status == 200 else 1)" \
        >/dev/null 2>&1; then
        READY=true
        echo "    ready"
        break
    fi
    sleep 2
done

if [[ "$READY" != "true" ]]; then
    echo "error: the API did not report ready within 60s. The containers are left" >&2
    echo "       running so the logs can be read:" >&2
    echo "       docker compose --env-file $ENV_FILE -f $COMPOSE_FILE logs --tail=100 api" >&2
    exit 1
fi

echo
"${COMPOSE[@]}" ps
echo
echo "Logs:    docker compose --env-file ${ENV_FILE} -f ${COMPOSE_FILE} logs -f api"
echo "Health:  curl -sS https://\$(grep -E '^CN_DOMAIN=' ${ENV_FILE} | cut -d= -f2)/healthz"
