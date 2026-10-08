#!/bin/sh
# Runs before nginx starts (the official image executes /docker-entrypoint.d/*).
#
# nginx refuses to start when `ssl_certificate` points at a file that is not
# there, and certbot cannot obtain the real certificate until nginx is already
# answering on port 80. Breaking that circle with a throwaway self-signed pair
# means a first `docker compose up` always comes up serving HTTPS — with a
# browser warning — and `scripts/operations/issue-certificate.sh` then replaces
# it with the real one.
set -eu

domain="${CN_DOMAIN:?CN_DOMAIN must be set}"
live="/etc/nginx/certs/live/${domain}"

if [ -s "${live}/fullchain.pem" ] && [ -s "${live}/privkey.pem" ]; then
    echo "ensure-certificate: using the existing certificate for ${domain}"
    exit 0
fi

echo "ensure-certificate: no certificate for ${domain}; generating a self-signed placeholder"
mkdir -p "${live}"
openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 30 \
    -keyout "${live}/privkey.pem" \
    -out "${live}/fullchain.pem" \
    -subj "/CN=${domain}" \
    -addext "subjectAltName=DNS:${domain}" 2>/dev/null
chmod 600 "${live}/privkey.pem"

# A marker the issue script looks for, so it can tell a placeholder it should
# overwrite from a real certificate it should leave alone.
touch "${live}/.self-signed"
