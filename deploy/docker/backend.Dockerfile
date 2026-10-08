# Build context is the repository root.
#   docker build -f deploy/docker/backend.Dockerfile .

# --------------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS base
# --------------------------------------------------------------------------
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# --------------------------------------------------------------------------
FROM base AS dependencies
# --------------------------------------------------------------------------
# Dependencies resolve from the lockfile alone, so this layer is cached until
# pyproject.toml or uv.lock actually changes.
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# --------------------------------------------------------------------------
FROM base AS development
# --------------------------------------------------------------------------
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project
COPY backend/ ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "chartnexus.entrypoints.main_api:create_app", \
     "--factory", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# --------------------------------------------------------------------------
FROM base AS runtime
# --------------------------------------------------------------------------
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --no-create-home app

COPY --from=dependencies --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app backend/src ./src
COPY --chown=app:app backend/migrations ./migrations
COPY --chown=app:app backend/alembic.ini ./alembic.ini
COPY --chown=app:app backend/pyproject.toml ./pyproject.toml

# The dependency layer installed third-party packages only (--no-install-project),
# so the application is imported from the source tree rather than site-packages.
ENV PYTHONPATH=/app/src

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health/live || exit 1

# Overridden per service (the workers) in compose.prod.yml, which also sets
# the worker count from the environment.
#
# `--proxy-headers` with `--forwarded-allow-ips=*` because this port is only
# ever reachable on the container network, behind the edge proxy: without
# them the request scheme reads as http and `request.client.host` is the
# proxy's address for every caller.
CMD ["uvicorn", "chartnexus.entrypoints.main_api:create_app", \
     "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--no-access-log", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
