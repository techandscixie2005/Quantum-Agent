# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.12.13-slim-bookworm
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.10.4@sha256:4cac394b6b72846f8a85a7a0e577c6d61d4e17fe2ccee65d9451a8b3c9efb4ac

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS dependencies

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    UV_COMPILE_BYTECODE=1 \
    UV_CONCURRENT_DOWNLOADS=1 \
    UV_HTTP_RETRIES=10 \
    UV_HTTP_TIMEOUT=600 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /build

COPY --from=uv /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
COPY quantum_agent ./quantum_agent

RUN uv sync --frozen --no-dev --no-editable


FROM dependencies AS test-dependencies

RUN uv sync --frozen --extra dev --no-editable


FROM ${PYTHON_IMAGE} AS runtime-base

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/workspace/services/api \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    XDG_CACHE_HOME=/tmp/quantum-agent-cache \
    MPLCONFIGDIR=/tmp/matplotlib

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates libgomp1 bubblewrap \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 quantum-agent \
    && useradd \
        --uid 10001 \
        --gid 10001 \
        --no-create-home \
        --home-dir /nonexistent \
        --shell /usr/sbin/nologin \
        quantum-agent \
    && mkdir -p /var/lib/quantum-agent/attachments \
    && chown -R 10001:10001 /var/lib/quantum-agent

WORKDIR /workspace/services/api

COPY --from=dependencies /opt/venv /opt/venv
COPY --chown=10001:10001 pyproject.toml alembic.ini ./
COPY --chown=10001:10001 alembic ./alembic
COPY --chown=10001:10001 quantum_agent ./quantum_agent

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=12 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3).read()"]


FROM runtime-base AS test

USER 0:0
COPY --from=test-dependencies /opt/venv /opt/venv
COPY --chown=10001:10001 tests ./tests
USER 10001:10001

CMD ["pytest", "-q"]


FROM runtime-base AS runtime

CMD ["uvicorn", "quantum_agent.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=127.0.0.1"]
