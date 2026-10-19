# Edge proxy: terminates TLS and maps one hostname onto the two upstreams.
# Build context is the repository root.
#   docker build -f deploy/docker/nginx.Dockerfile .

FROM nginx:1.29-alpine

# Alpine's package index moves faster than any base image is rebuilt, so a tag
# ships packages that already have fixes published against them: 1.27-alpine sat
# on Alpine 3.21.3 and carried 25 HIGH, and even nginx:alpine, two Alpine
# releases newer, carried three. Upgrading the index is what actually clears
# them, and what keeps security-scan's HIGH/CRITICAL gate reachable at all —
# moving the pin alone never reaches zero.
#
# This layer is also the one thing in the image that goes stale invisibly: it is
# cached on its instruction text, so a builder that has run it once reuses it —
# and keeps shipping that day's package set — for as long as the base image
# digest holds. security-scan therefore builds this image without a layer cache;
# see the note on its `nginx` matrix entry.
#
# openssl for the placeholder certificate the entrypoint generates; curl for
# the healthcheck below.
RUN apk upgrade --no-cache \
    && apk add --no-cache openssl curl

# The base image ships a `default.conf` serving the "Welcome to nginx" page on
# port 80. nginx.conf includes conf.d/*.conf, so leaving it there adds a second
# server block for the same port — which answers for any Host header the real
# one does not claim.
RUN rm -f /etc/nginx/conf.d/default.conf

COPY deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY deploy/nginx/snippets/ /etc/nginx/snippets/
COPY deploy/nginx/templates/ /etc/nginx/templates/
# The official image runs /docker-entrypoint.d/* in lexical order before
# starting nginx; 25 puts this after the template substitution at 20.
COPY deploy/nginx/entrypoint/25-ensure-certificate.sh /docker-entrypoint.d/
RUN chmod +x /docker-entrypoint.d/25-ensure-certificate.sh

# Without a filter, envsubst would also eat nginx's own $host, $request_uri and
# friends — every one of which is part of the config, not a value to expand.
ENV NGINX_ENVSUBST_FILTER="CN_"

EXPOSE 80 443

# Over the loopback on port 80, which answers without a certificate, so an
# expired or placeholder cert can never mark the proxy unhealthy. The expected
# answer is the 301 to HTTPS: `--max-redirs 0` stops curl following it, and a
# 3xx is not a failure for `-f`, which only rejects 4xx and 5xx.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS --max-redirs 0 -o /dev/null http://127.0.0.1/
