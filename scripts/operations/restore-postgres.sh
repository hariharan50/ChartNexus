#!/usr/bin/env bash
# Restore the database from a backup-postgres.sh dump.
#
#   ./scripts/operations/restore-postgres.sh backups/chartnexus-20261008T120000Z.dump
#
# THIS REPLACES THE CURRENT DATABASE. Every row written since the dump is lost,
# so the script stops the application first (nothing should be writing during a
# restore) and makes you type the database name to confirm.
#
# The restore is into a fresh database rather than over the existing one:
# pg_restore --clean against a live schema leaves whatever it could not drop,
# and the result is neither the old database nor the new one.
set -euo pipefail

cd "$(dirname "$0")/../.."

DUMP="${1:-}"
ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="deploy/compose/compose.prod.yml"

if [[ -z "$DUMP" ]]; then
    echo "usage: $0 <path-to-dump>" >&2
    echo >&2
    echo "available:" >&2
    ls -1t backups/chartnexus-*.dump 2>/dev/null | head -20 >&2 || echo "  (none)" >&2
    exit 1
fi

if [[ ! -f "$DUMP" ]]; then
    echo "error: $DUMP not found." >&2
    exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
    echo "error: $ENV_FILE not found." >&2
    exit 1
fi

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

: "${POSTGRES_USER:?POSTGRES_USER must be set in $ENV_FILE}"
: "${POSTGRES_DB:?POSTGRES_DB must be set in $ENV_FILE}"

COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
# The dumps live in a bind mount, so the container sees them under /backups.
IN_CONTAINER="/backups/$(basename "$DUMP")"

echo "About to replace the contents of database '${POSTGRES_DB}' with:"
echo "  ${DUMP}"
echo
echo "Everything written since that dump will be lost."
read -r -p "Type the database name to continue: " CONFIRM
if [[ "$CONFIRM" != "$POSTGRES_DB" ]]; then
    echo "aborted." >&2
    exit 1
fi

psql_as_superuser() {
    # `postgres` rather than $POSTGRES_DB: the target database is being dropped
    # and recreated, so the session cannot be connected to it.
    "${COMPOSE[@]}" exec -T postgres \
        psql --username "$POSTGRES_USER" --dbname postgres --set ON_ERROR_STOP=on "$@"
}

echo "==> stopping everything that writes to the database"
# Postgres and nginx stay up: Postgres is the target, and leaving nginx running
# means visitors get the app's own error rather than a connection refused.
"${COMPOSE[@]}" stop api web catalog ingest futures-oi futures-history hugin mme100 report

echo "==> recreating ${POSTGRES_DB}"
# Existing sessions would block the DROP. WITH (FORCE) terminates them, and is
# why this needs Postgres 13 or newer.
psql_as_superuser -c "DROP DATABASE IF EXISTS \"${POSTGRES_DB}\" WITH (FORCE);"
psql_as_superuser -c "CREATE DATABASE \"${POSTGRES_DB}\" OWNER \"${POSTGRES_USER}\";"

echo "==> restoring"
# --single-transaction so a failure leaves an empty database rather than a
# half-populated one. --no-owner/--no-privileges keep it restorable into a
# cluster whose role names differ from the source's.
"${COMPOSE[@]}" exec -T postgres \
    pg_restore \
        --username "$POSTGRES_USER" \
        --dbname "$POSTGRES_DB" \
        --single-transaction \
        --no-owner --no-privileges \
        "$IN_CONTAINER"

echo "==> applying any migrations newer than the dump"
# A dump from before the last deploy is a schema behind. Alembic is idempotent
# at head, so this is a no-op when it is not needed.
"${COMPOSE[@]}" run --rm migrate

echo "==> starting the application"
"${COMPOSE[@]}" up -d

echo
echo "Done. Check that it came back:"
echo "  docker compose --env-file ${ENV_FILE} -f ${COMPOSE_FILE} ps"
echo "  curl -sS https://\${CN_DOMAIN}/healthz"
