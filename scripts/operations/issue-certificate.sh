#!/usr/bin/env bash
# Obtain the first real TLS certificate for CN_DOMAIN.
#
#   ./scripts/operations/issue-certificate.sh
#
# Run once, after `docker compose up -d` has nginx answering on port 80. The
# nginx image generates a self-signed placeholder on first start so it can boot
# at all — certbot cannot prove a domain to a server that is not running, and
# nginx will not start without a certificate file to open. This replaces the
# placeholder and reloads nginx in place.
#
# Renewal after this is automatic: the `certbot` service in compose.prod.yml
# attempts it twice a day, and nginx reloads within the hour.
set -euo pipefail

cd "$(dirname "$0")/../.."

ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_FILE="deploy/compose/compose.prod.yml"
COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

if [[ ! -f "$ENV_FILE" ]]; then
    echo "error: $ENV_FILE not found. Copy .env.production.example and fill it in." >&2
    exit 1
fi

# shellcheck disable=SC1090  # the path is a variable by design
set -a; source "$ENV_FILE"; set +a

: "${CN_DOMAIN:?CN_DOMAIN must be set in $ENV_FILE}"
: "${CN_ACME_EMAIL:?CN_ACME_EMAIL must be set in $ENV_FILE (expiry warnings go there)}"

CERTBOT_FLAGS=()
if [[ "${CN_ACME_STAGING:-false}" == "true" ]]; then
    # Let's Encrypt rate-limits failures hard — five per hostname per hour — so
    # it is worth proving the plumbing against staging first. The certificate it
    # issues is untrusted by browsers; re-run without this to get a real one.
    CERTBOT_FLAGS+=(--staging)
    echo "note: using the Let's Encrypt STAGING environment — the result is not trusted"
fi

if ! "${COMPOSE[@]}" ps --status running --services | grep -qx nginx; then
    echo "error: the nginx service is not running. Start the stack first:" >&2
    echo "  docker compose --env-file $ENV_FILE -f $COMPOSE_FILE up -d" >&2
    exit 1
fi

# --- preflight -------------------------------------------------------------
# Proves end to end that a request from the internet reaches the webroot
# volume. This is the step most likely to be wrong — DNS not pointing here
# yet, or port 80 closed in the provider's firewall — and the one certbot
# reports most obscurely.
echo "==> checking that http://${CN_DOMAIN}/.well-known/acme-challenge/ is reachable"
TOKEN="chartnexus-preflight-$(date +%s)"
CHALLENGE_DIR="/var/www/certbot/.well-known/acme-challenge"

"${COMPOSE[@]}" exec -T nginx sh -c \
    "mkdir -p '$CHALLENGE_DIR' && printf '%s' '$TOKEN' > '$CHALLENGE_DIR/$TOKEN'"

cleanup_token() {
    "${COMPOSE[@]}" exec -T nginx rm -f "$CHALLENGE_DIR/$TOKEN" >/dev/null 2>&1 || true
}
trap cleanup_token EXIT

if ! curl -fsS --max-time 15 "http://${CN_DOMAIN}/.well-known/acme-challenge/${TOKEN}" \
     | grep -qx "$TOKEN"; then
    echo "error: the test file was not served back." >&2
    echo "       Check that ${CN_DOMAIN} resolves to this VPS and that port 80 is open." >&2
    exit 1
fi
cleanup_token
trap - EXIT
echo "    reachable"

# --- clear the placeholder -------------------------------------------------
# certbot keeps each certificate as a *lineage*: real files under archive/ and
# symlinks under live/<domain>/. Handed a live/<domain>/ it has no renewal
# config for — which is exactly what the self-signed placeholder looks like —
# it leaves that directory alone and issues into `<domain>-0001` instead. nginx
# would go on serving the placeholder, and the browser warning would never go
# away. So the placeholder is removed first, on the marker the entrypoint left.
LIVE_DIR="/etc/nginx/certs/live/${CN_DOMAIN}"
if "${COMPOSE[@]}" exec -T nginx test -f "${LIVE_DIR}/.self-signed"; then
    echo "==> removing the self-signed placeholder"
    # nginx keeps the loaded certificate in memory, so it carries on serving
    # HTTPS with no file on disk until the reload at the end.
    "${COMPOSE[@]}" exec -T nginx rm -rf "$LIVE_DIR"
fi

# --- issue -----------------------------------------------------------------
echo "==> requesting a certificate for ${CN_DOMAIN}"
"${COMPOSE[@]}" run --rm --entrypoint certbot certbot \
    certonly \
    --webroot --webroot-path /var/www/certbot \
    --email "$CN_ACME_EMAIL" \
    --agree-tos --no-eff-email \
    --non-interactive \
    --cert-name "$CN_DOMAIN" \
    "${CERTBOT_FLAGS[@]}" \
    -d "$CN_DOMAIN"

echo "==> reloading nginx"
"${COMPOSE[@]}" exec -T nginx nginx -s reload

echo
echo "Done. Verify with:"
echo "  curl -sSI https://${CN_DOMAIN}/healthz | head -1"
