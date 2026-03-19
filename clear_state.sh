#!/usr/bin/env bash
#
# clear_state.sh — Reset all application state
#
# Removes:
#   - SQLite database
#   - Django migrations (except __init__.py)
#   - All media files (videos, audio, thumbnails, HLS streams, chromadb)
#   - All log files
#
# Usage:
#   bash clear_state.sh          # interactive confirmation
#   bash clear_state.sh --force  # skip confirmation
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR/server/app"
MEDIA_DIR="$APP_DIR/media"
LOG_DIR="$APP_DIR/logs"
DB_FILE="$APP_DIR/db.sqlite3"
MIGRATIONS_DIR="$APP_DIR/api/migrations"

echo "=== PolyU Video Agent — State Reset ==="
echo ""
echo "This will DELETE:"
echo "  [DB]         $DB_FILE"
echo "  [Media]      $MEDIA_DIR/ (videos, audio, thumbnails, streams, chromadb)"
echo "  [Logs]       $LOG_DIR/"
echo "  [Migrations] $MIGRATIONS_DIR/ (except __init__.py)"
echo ""

if [ "$1" != "--force" ] && [ "$1" != "-f" ]; then
    read -p "Are you sure? Type 'yes' to confirm: " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Aborted."
        exit 0
    fi
fi

echo ""

# 1. Remove database
if [ -f "$DB_FILE" ]; then
    rm -f "$DB_FILE"
    echo "[OK] Removed database: $DB_FILE"
else
    echo "[--] No database found"
fi

# 2. Remove media files
if [ -d "$MEDIA_DIR" ]; then
    # Remove specific subdirs
    for subdir in videos audio thumbnails streams chromadb; do
        target="$MEDIA_DIR/$subdir"
        if [ -d "$target" ]; then
            rm -rf "$target"
            echo "[OK] Removed media/$subdir/"
        fi
    done
    # Remove any other files in media root
    find "$MEDIA_DIR" -type f -delete 2>/dev/null || true
    echo "[OK] Cleaned media directory"
else
    echo "[--] No media directory found"
fi

# 3. Remove logs
if [ -d "$LOG_DIR" ]; then
    rm -rf "$LOG_DIR"
    echo "[OK] Removed logs directory"
fi
# Also remove any .log files in app dir
find "$APP_DIR" -maxdepth 1 -name "*.log" -delete 2>/dev/null || true

# 4. Remove migrations (keep __init__.py)
if [ -d "$MIGRATIONS_DIR" ]; then
    find "$MIGRATIONS_DIR" -type f -name "*.py" ! -name "__init__.py" -delete 2>/dev/null || true
    find "$MIGRATIONS_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    echo "[OK] Cleaned migrations (kept __init__.py)"
fi

# 5. Remove __pycache__ dirs
find "$APP_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
echo "[OK] Removed __pycache__ directories"

echo ""
echo "=== State cleared. Run these to reinitialize: ==="
echo "  cd $APP_DIR"
echo "  python manage.py makemigrations api"
echo "  python manage.py migrate"
echo "  python manage.py process_async_task"
