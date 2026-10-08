#!/usr/bin/env bash
# Take a compressed logical backup of the Postgres database.
#
#   ./scripts/operations/backup-postgres.sh
#
# Writes ./backups/chartnexus-<timestamp>.dump — the custom pg_dump format, so
# restore-postgres.sh can run in parallel and restore selectively. `backups/`
# is a bind mount on the postgres container, so the file lands on the host and
# survives `docker compose down -v`.
#
# Run it from cron on the VPS, nightly after the session closes:
#   30 18 * * 1-5 cd /srv/chartnexus && ./scripts/operations/backup-postgres.sh >> /var/log/chartnexus-backup.log 2>&1
#
# This covers the database only. Two things it does NOT cover, and losing
# either is unrecoverable:
#   * CN_SECURITY_ENCRYPTION_KEY — without it every stored broker credential
#     and per-user LLM key in this dump is undecryptable ciphertext.
#   * .env.production as a whole.
# Keep both somewhere other than this VPS.
set -euo pipefail

cd "$(dirname "$0")/../.."

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="deploy/compose/compose.prod.yml"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "error: $ENV_FILE not found." >&2
    exit 1
fi

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

: "${POSTGRES_USER:?POSTGRES_USER must be set in $ENV_FILE}"
: "${POSTGRES_DB:?POSTGRES_DB must be set in $ENV_FILE}"

COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="chartnexus-${STAMP}.dump"

mkdir -p backups

echo "==> dumping ${POSTGRES_DB} to backups/${NAME}"
# Written to a .partial name first and renamed on success, so a backup
# interrupted halfway cannot be mistaken for a complete one by the restore
# script or by the retention sweep below.
"${COMPOSE[@]}" exec -T postgres \
    pg_dump \
        --username "$POSTGRES_USER" \
        --dbname "$POSTGRES_DB" \
        --format=custom \
        --compress=9 \
        --file "/backups/${NAME}.partial"

"${COMPOSE[@]}" exec -T postgres mv "/backups/${NAME}.partial" "/backups/${NAME}"

SIZE="$(du -h "backups/${NAME}" | cut -f1)"
echo "    wrote backups/${NAME} (${SIZE})"

# A dump that cannot be read back is not a backup. pg_restore --list parses the
# whole archive's table of contents, which is enough to catch a truncated or
# corrupt file right now rather than during an incident.
echo "==> verifying the archive is readable"
if ! "${COMPOSE[@]}" exec -T postgres pg_restore --list "/backups/${NAME}" >/dev/null; then
    echo "error: the dump is not a readable pg_restore archive. Keeping it for inspection." >&2
    exit 1
fi
echo "    ok"

echo "==> removing backups older than ${RETENTION_DAYS} days"
# -mtime needs whole days; +N means strictly older than N+1 days, which is why
# the arithmetic is one less than the retention figure.
find backups -maxdepth 1 -name 'chartnexus-*.dump' -type f \
    -mtime "+$((RETENTION_DAYS - 1))" -print -delete
# Partials from an interrupted run are never useful.
find backups -maxdepth 1 -name 'chartnexus-*.dump.partial' -type f \
    -mtime +1 -print -delete

echo "Done."
