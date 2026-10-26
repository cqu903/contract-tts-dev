# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm

# Pin uv while leaving the Debian/Python patch level on the maintained 3.12 tag.
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="/app/.venv/bin:$PATH"

# Azure Speech SDK native runtime dependencies on Debian 12.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        libasound2 \
        libssl3 \
        libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 contracttts \
    && useradd --system --uid 10001 --gid contracttts \
        --home-dir /home/contracttts --create-home contracttts

WORKDIR /app

# Dependency layer changes only when the project metadata or lockfile changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project

# Copy only runtime files; secrets and local data are excluded by .dockerignore.
COPY backend ./backend
COPY frontend ./frontend
COPY scripts ./scripts
COPY refs ./refs

RUN mkdir -p \
        /app/cache \
        /app/uploaded \
        /app/.scratch/microsoft-edge-tts/diagnostics \
    && chown -R contracttts:contracttts \
        /app/cache \
        /app/uploaded \
        /app/.scratch \
        /home/contracttts

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=3).read(1)"]

CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
