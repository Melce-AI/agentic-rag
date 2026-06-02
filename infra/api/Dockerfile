# syntax=docker/dockerfile:1.7

# ==========================================
# Builder Stage
# ==========================================
FROM python:3.13-slim AS builder

# Keep runtime behavior predictable and logs visible in container environments.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency metadata before application code to preserve Docker layer cache.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./

# Install only locked, non-dev dependencies into the project venv.
RUN --mount=type=cache,target=/root/.cache \
    uv sync \
    --locked \
    --no-dev \
    --no-install-project

# ==========================================
# Runtime Stage
# ==========================================
FROM python:3.13-slim AS runtime

WORKDIR /app

# Runtime uses a non-root user.
RUN useradd --create-home --shell /usr/sbin/nologin app

# Model caches are mounted as Docker volumes in development; create the
# mountpoint with the runtime user as owner so FastEmbed/HF can write to it.
RUN mkdir -p /app/.cache/huggingface && chown -R app:app /app/.cache

# Copy dependencies and application code with the final runtime owner.
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app src ./src

# Ensure runtime entrypoints like python and uvicorn stay executable after the venv copy.
RUN find /app/.venv/bin -type f -exec chmod 755 {} +

USER app
EXPOSE 8089

# Probe the app from inside the container without adding extra runtime packages.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD /app/.venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8089/health', timeout=3)" || exit 1

# Run with the venv interpreter explicitly to avoid PATH/module-resolution surprises.
CMD ["/app/.venv/bin/python", "-m", "uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8089"]
