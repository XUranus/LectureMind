# ── Stage 1: Python dependency builder ──────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System libs needed to compile Python wheels (opencv, Pillow, scikit-image…)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: Runtime image ───────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy Django application source
COPY app/ .

# Persistent data lives in a volume; pre-create directories so they are owned
# by the app user even before the volume is mounted.
RUN mkdir -p \
        /data/media/audio \
        /data/media/streams \
        /data/media/thumbnails \
        /data/media/chromadb \
        /data/logs \
    && useradd -r -u 1001 -s /sbin/nologin appuser \
    && chown -R appuser:appuser /app /data

USER appuser

# Default env — can all be overridden at runtime (docker run -e / compose env_file)
ENV DJANGO_SETTINGS_MODULE=videoapp.settings \
    MEDIA_ROOT=/data/media \
    LOG_DIR=/data/logs \
    DB_PATH=/data/db.sqlite3 \
    BACKEND_PORT=8000 \
    DEBUG=False \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# entrypoint: migrate → collect static → start gunicorn
COPY --chown=appuser:appuser docker-entrypoint.sh /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]
