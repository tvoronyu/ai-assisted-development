ARG PYTHON_VERSION=3.13-slim

# ── 1. builder — runtime deps only ─────────────────────────────────
FROM python:${PYTHON_VERSION} AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt


# ── 2. runtime — production image, app + alembic ───────────────────
FROM python:${PYTHON_VERSION} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

RUN groupadd --system --gid 1001 app \
    && useradd  --system --uid 1001 --gid app app

COPY --from=builder /opt/venv /opt/venv

COPY src/         ./src/
COPY alembic/     ./alembic/
COPY alembic.ini  ./

RUN chown -R app:app /app

USER app

EXPOSE 8000

# Auto-apply migrations on every start, then run the API.
# Container will restart-on-failure (per compose) until Postgres is reachable.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn src.main:app --host 0.0.0.0 --port 8000"]


# ── 3. test — runtime + dev deps + tests/ source ───────────────────
FROM runtime AS test

USER root

COPY requirements.txt requirements-dev.txt ./
RUN /opt/venv/bin/pip install -r requirements-dev.txt

COPY pyproject.toml ./
COPY tests/ ./tests/

RUN chown -R app:app /app

USER app

# Default: full pytest with coverage gate. Override via `command:` if needed.
CMD ["pytest", "--cov=src", "--cov-report=term-missing"]
