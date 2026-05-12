# syntax=docker/dockerfile:1.7

# ---------------------------------------------------------------------------
# Builder stage: compile any wheels that need a toolchain, install Python
# dependencies into an isolated virtual environment, then discard the rest.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /tmp/requirements.txt


# ---------------------------------------------------------------------------
# Runtime stage: minimal image with the prebuilt venv, application code,
# bundled grocery fixtures, a non-root user, and a curl-based healthcheck.
# ---------------------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

WORKDIR /code
COPY app /code/app

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /code
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl --fail "http://localhost:${PORT:-8000}/health" || exit 1

CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WORKERS:-1}"]
