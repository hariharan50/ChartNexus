# Build context is the repository root.
#   docker build -f deploy/docker/frontend.Dockerfile .

# --------------------------------------------------------------------------
FROM node:22-alpine AS base
# --------------------------------------------------------------------------
ENV PNPM_HOME=/pnpm \
    PATH="/pnpm:$PATH" \
    CI=true
RUN corepack enable
WORKDIR /app

# --------------------------------------------------------------------------
FROM base AS dependencies
# --------------------------------------------------------------------------
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile

# --------------------------------------------------------------------------
FROM base AS development
# --------------------------------------------------------------------------
COPY --from=dependencies /app/node_modules ./node_modules
COPY frontend/ ./
EXPOSE 5173
CMD ["pnpm", "dev", "--host", "0.0.0.0", "--port", "5173"]

# --------------------------------------------------------------------------
FROM dependencies AS build
# --------------------------------------------------------------------------
# Vite inlines PUBLIC_-prefixed variables into the browser bundle at build
# time, so they are build arguments and not runtime environment. The other
# two are deliberately left to their defaults in
# `app/lib/shared/config/env.ts`: `/api/v1` and `/ws` are same-origin paths,
# which is exactly what the single hostname behind nginx serves.
ARG PUBLIC_ENVIRONMENT=production
ENV PUBLIC_ENVIRONMENT=$PUBLIC_ENVIRONMENT

COPY frontend/ ./
RUN pnpm build \
    && pnpm prune --prod

# --------------------------------------------------------------------------
FROM node:22-alpine AS runtime
# --------------------------------------------------------------------------
ENV NODE_ENV=production \
    PORT=3000 \
    HOST=0.0.0.0
WORKDIR /app

# npm, corepack and yarn ship with the base image and are never used here: the
# server starts from the `react-router-serve` binary in node_modules, and the
# healthcheck shells out to `node`. They were also the entirety of this image's
# container-scan findings — ten HIGH, every one of them inside npm's own bundled
# dependencies, none in the application's.

# `apk upgrade` for the same reason nginx.Dockerfile runs one: node:22-alpine
# is rebuilt on its own cadence and Alpine publishes security updates in
# between, so without it the image ships whatever package set existed when the
# base tag was last cut.
RUN apk upgrade --no-cache \
    && rm -rf /usr/local/lib/node_modules/npm \
        /usr/local/lib/node_modules/corepack \
        /opt/yarn-v* \
        /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
        /usr/local/bin/yarn /usr/local/bin/yarnpkg \
    && addgroup --system --gid 1001 app \
    && adduser --system --uid 1001 --ingroup app app

# React Router build output — `build/client` (static assets) and `build/server`
# (the request handler) — plus the pruned production dependencies.
# `@react-router/serve` is a runtime dependency, not a dev one, so
# `pnpm prune --prod` above keeps it.
COPY --from=build --chown=app:app /app/build ./build
COPY --from=build --chown=app:app /app/node_modules ./node_modules
COPY --from=build --chown=app:app /app/package.json ./package.json

USER app
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD node -e "fetch('http://localhost:3000/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

# The package's own `start` script is `react-router-serve ./build/server/index.js`,
# and this runs that binary directly rather than through `pnpm start`.
#
# `pnpm start` cannot work here: this stage is a fresh node:22-alpine that never
# ran `corepack enable`, so there is no pnpm on PATH and node reads the argument
# as a module path ("Cannot find module '/app/pnpm'"). Adding corepack back
# would fix the PATH but make the container fetch its own package manager on
# first start, which is a network dependency a production boot does not need.
#
# `@react-router/serve` is a runtime dependency, not a dev one, so the
# `pnpm prune --prod` above keeps the binary in node_modules/.bin.
CMD ["node_modules/.bin/react-router-serve", "./build/server/index.js"]
