#!/bin/sh
set -e

# ── Run DB migrations ────────────────────────────────────────────────────────
echo "[entrypoint] Running database migrations…"
python manage.py migrate --noinput

# ── Collect static files ─────────────────────────────────────────────────────
echo "[entrypoint] Collecting static files…"
python manage.py collectstatic --noinput --clear

# ── Determine which process to start ─────────────────────────────────────────
# SERVICE is set by docker-compose to either "web" or "worker"
SERVICE="${SERVICE:-web}"

if [ "$SERVICE" = "worker" ]; then
    echo "[entrypoint] Starting async task worker…"
    exec python manage.py process_async_task

else
    echo "[entrypoint] Starting Gunicorn on port ${BACKEND_PORT:-8000}…"
    exec gunicorn videoapp.wsgi:application \
        --bind "0.0.0.0:${BACKEND_PORT:-8000}" \
        --workers "${GUNICORN_WORKERS:-4}" \
        --timeout "${GUNICORN_TIMEOUT:-120}" \
        --access-logfile - \
        --error-logfile -
fi
