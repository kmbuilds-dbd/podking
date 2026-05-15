# Multi-stage build: Node for frontend, Python for backend.
# Final image runs the FastAPI app, which serves the built SPA from
# frontend/dist via main.py's StaticFiles mount + SPA fallback.

# ── Stage 1: frontend bundle ────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


# ── Stage 2: runtime image ──────────────────────────────────────────────
FROM python:3.13-slim AS runtime

# Runtime deps:
#   - ffmpeg for audio extraction (yt-dlp / ElevenLabs upload)
#   - git for the TTS publisher (clones + pushes to GitHub Pages)
#   - ca-certificates for HTTPS to external APIs
#   - curl is handy for healthcheck debugging
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates ffmpeg git curl \
    && rm -rf /var/lib/apt/lists/*

# uv: pinned binary copy from the official image. Faster than installing
# via pip because no Python interpreter setup needed.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install Python deps first (cached layer when only source code changes).
COPY pyproject.toml uv.lock ./
COPY backend/ ./backend/
RUN uv sync --frozen --no-dev

# App configuration that lives outside backend/
COPY alembic.ini ./

# Built frontend bundle from stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# /data/audio is the audio cache target (TTL'd by the retention scheduler).
# Railway gives us an ephemeral filesystem unless a volume is attached;
# mkdir is enough for the app to start either way.
RUN mkdir -p /data/audio

ENV AUDIO_STORAGE_PATH=/data/audio

EXPOSE 8000

# Run migrations on boot, then start the app. Uses sh so $PORT (Railway)
# substitutes at runtime; falls back to 8000 for plain `docker run`.
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn podking.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
