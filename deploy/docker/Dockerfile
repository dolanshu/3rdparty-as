# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:python3.10-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY platform/pyproject.toml platform/README.md platform/
COPY apps/translation/pyproject.toml apps/translation/README.md apps/translation/
COPY apps/anti-fraud/pyproject.toml apps/anti-fraud/README.md apps/anti-fraud/
COPY services/config-service/pyproject.toml services/config-service/README.md services/config-service/
COPY services/console/pyproject.toml services/console/README.md services/console/
COPY testbed/simulators/pyproject.toml testbed/simulators/README.md testbed/simulators/
COPY testbed/load/pyproject.toml testbed/load/README.md testbed/load/

RUN uv sync --frozen --no-dev --package as-platform --no-install-workspace

COPY platform/src platform/src
RUN uv sync --frozen --no-dev --package as-platform --no-editable

FROM python:3.10-slim AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN groupadd --gid 10001 as-runtime \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin as-runtime

COPY --from=builder --chown=10001:10001 /app/.venv /app/.venv

# These are the Helm container ports. See ADR-0013.
EXPOSE 5060/udp 5061/tcp

USER 10001:10001
ENTRYPOINT ["python", "-m", "as_platform"]
