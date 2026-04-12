# LectureMind Configuration Reference

This document is the authoritative reference for all configurable settings in LectureMind — covering environment variables, the `SystemConfig` runtime store, Docker Compose variables, and the `ConfigManager` Python API.

---

## Table of Contents

1. [Configuration Sources & Priority](#1-configuration-sources--priority)
2. [Environment Variables Reference](#2-environment-variables-reference)
3. [LLM / API Configuration (SystemConfig)](#3-llm--api-configuration-systemconfig)
4. [Docker Compose Variables](#4-docker-compose-variables)
5. [Frontend Runtime Configuration](#5-frontend-runtime-configuration)
6. [ConfigManager Python API](#6-configmanager-python-api)
7. [REST API Endpoints](#7-rest-api-endpoints)
8. [.env File Setup](#8-env-file-setup)
9. [Security Notes](#9-security-notes)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Configuration Sources & Priority

Settings are resolved in this order (highest priority first):

```
1. Shell environment variables   (export FOO=bar)
2. .env file                     (loaded automatically by settings.py)
3. SystemConfig database model   (runtime overrides via UI or API)
4. Django / code defaults
```

The `.env` file is searched starting from `manage.py`'s directory and walking up the tree. The first file found is used.

---

## 2. Environment Variables Reference

All variables below can be set in the `.env` file or as shell environment variables.

### Server

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | insecure dev key | Django secret key — **change in production** |
| `DEBUG` | `True` | Set to `False` in production |
| `BACKEND_PORT` | `8000` | Port `manage.py runserver` and Gunicorn listen on |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated list of allowed hostnames |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated allowed CORS origins |

### Storage Paths

All path variables accept absolute paths. Sub-directory variables (`MEDIA_AUDIO_DIR`, etc.) also accept bare names resolved relative to `MEDIA_ROOT`.

| Variable | Default | Description |
|---|---|---|
| `MEDIA_ROOT` | `<BASE_DIR>/media` | Root for all uploaded and generated media files |
| `MEDIA_URL` | `/media/` | URL prefix Django uses to serve media files |
| `MEDIA_AUDIO_DIR` | `<MEDIA_ROOT>/audio` | Extracted `.wav` files for ASR |
| `MEDIA_STREAMS_DIR` | `<MEDIA_ROOT>/streams` | HLS `.m3u8` playlists and segments |
| `MEDIA_THUMBNAILS_DIR` | `<MEDIA_ROOT>/thumbnails` | Slide thumbnail images (both resolutions) |
| `DB_PATH` | `<BASE_DIR>/db.sqlite3` | SQLite database file path |
| `LOG_DIR` | `<BASE_DIR>/logs` | Directory for rotating log files |
| `CHROMA_PERSIST_DIR` | `<MEDIA_ROOT>/chromadb` | ChromaDB persistent storage directory |

### LLM & API Keys

| Variable | Default | Description |
|---|---|---|
| `LLM_API_BASE` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | OpenAI-compatible API base URL |
| `DASHSCOPE_API_KEY` | — | Alibaba DashScope API key (ASR + LLM) |
| `LLM_MODEL` | `qwen2.5-7b-instruct` | Default model for task pipeline |
| `CHAT_MODEL` | `qwen3-max` | Model for chat / agentic RAG |
| `VL_MODEL` | `qwen2.5-vl-72b-instruct` | Vision-language model for slide OCR |

### Tencent COS (audio hosting for ASR)

| Variable | Description |
|---|---|
| `COS_SECRECT_ID` | Tencent COS SecretId |
| `COS_SECRECT_KEY` | Tencent COS SecretKey |
| `COS_REGION` | COS region (e.g. `ap-singapore`) |
| `COS_BUCKET` | COS bucket name |

### Docker Compose only

| Variable | Default | Description |
|---|---|---|
| `FRONTEND_PORT` | `3000` | Host port mapped to the frontend nginx container |

---

## 3. LLM / API Configuration (SystemConfig)

`LLM_MODEL`, `CHAT_MODEL`, `VL_MODEL`, `LLM_API_BASE`, and all API / COS keys are also stored in the `SystemConfig` database model. This allows changing them at runtime without restarting the server.

**Priority within this group**: environment variable → database (`SystemConfig`) → default.

Access via `ConfigManager` (see §6) or the REST API (see §7).

---

## 4. Docker Compose Variables

`docker-compose.yml` reads from the root `.env` file. The key variables used directly by Compose are:

| Variable | Used by | Effect |
|---|---|---|
| `BACKEND_PORT` | `web` service | Maps `${BACKEND_PORT}:8000` on the host |
| `FRONTEND_PORT` | `frontend` service | Maps `${FRONTEND_PORT}:3000` on the host |

All other variables (`DASHSCOPE_API_KEY`, `COS_*`, etc.) are passed through to containers via `env_file: .env`.

**Service-level environment overrides in `docker-compose.yml`** (these take precedence over `.env` inside containers):

```yaml
web:
  environment:
    SERVICE: web
    DEBUG: "False"
    MEDIA_ROOT: /data/media
    LOG_DIR: /data/logs
    DB_PATH: /data/db.sqlite3
    CHROMA_PERSIST_DIR: /data/media/chromadb
    ALLOWED_HOSTS: "localhost,127.0.0.1,web"
    CORS_ALLOWED_ORIGINS: "http://localhost:3000,http://frontend:3000"
```

To override ports or paths for a specific deployment, set them in `.env`:

```bash
BACKEND_PORT=9000
FRONTEND_PORT=8080
MEDIA_ROOT=/mnt/storage/lecturemind
LOG_DIR=/var/log/lecturemind
```

---

## 5. Frontend Runtime Configuration

The React frontend reads `window.__ENV__` injected by `frontend/docker-entrypoint.sh` at container startup:

```js
// /usr/share/nginx/html/env-config.js  (written at container start)
window.__ENV__ = {
  API_PREFIX: "http://your-server:8000"
};
```

`src/config.ts` reads this with a local fallback:

```ts
export const API_PREFIX: string =
    window.__ENV__?.API_PREFIX ?? "http://127.0.0.1:8000"
```

**To change the API URL without rebuilding the image**, set `API_PREFIX` in the environment passed to the `frontend` container:

```bash
# docker-compose.yml
frontend:
  environment:
    API_PREFIX: "https://api.myserver.com"
```

For local `pnpm start` (outside Docker), edit `frontend/public/env-config.js` directly — it is loaded as a static file by the dev server and serves as the development default.

---

## 6. ConfigManager Python API

```python
from api.config_utils import ConfigManager

# Read a value (env → DB → default)
model = ConfigManager.get('chat_model', default='qwen-turbo')

# Write a value (persists to DB and .env)
ConfigManager.set('chat_model', 'qwen3.6-plus')

# Write multiple values at once
ConfigManager.set_multiple({
    'llm_model':  {'value': 'qwen-turbo',  'description': 'Task pipeline model'},
    'chat_model': {'value': 'qwen3-max',   'description': 'Chat/agent model'},
})

# Read all values (secrets masked by default)
all_cfg = ConfigManager.get_all()
all_cfg_with_secrets = ConfigManager.get_all(include_secrets=True)

# Sync .env → database (useful after manual .env edits)
ConfigManager.sync_from_env()

# Force-reset the LLM client singleton after a model change
ConfigManager.reset_llm_client()
```

### Secret masking

Keys containing `api_key`, `secret_id`, or `secret_key` are masked in API responses: only the last 4 characters are shown (`****xxxx`).

---

## 7. REST API Endpoints

All endpoints require no authentication in the current development build.

### `GET /api/config/`

Returns all `SystemConfig` entries with secrets masked.

```json
{
  "chat_model": {
    "value": "qwen3-max",
    "description": "Model for chat/agent endpoints",
    "is_secret": false
  },
  "dashscope_api_key": {
    "value": "****6ba",
    "description": "DashScope API key",
    "is_secret": true
  }
}
```

### `POST /api/config/update/`

Update one or multiple values. Persists to the database and `.env` file.

```bash
# Single update
curl -X POST http://localhost:8000/api/config/update/ \
  -H "Content-Type: application/json" \
  -d '{"key": "chat_model", "value": "qwen3.6-plus"}'

# Batch update
curl -X POST http://localhost:8000/api/config/update/ \
  -H "Content-Type: application/json" \
  -d '[{"key": "llm_model", "value": "qwen-turbo"},
       {"key": "chat_model", "value": "qwen3-max"}]'
```

### `POST /api/config/sync-from-env/`

Reads the current `.env` file and writes all recognised keys into the database. Useful after manually editing `.env` without restarting.

```bash
curl -X POST http://localhost:8000/api/config/sync-from-env/
```

---

## 8. .env File Setup

```bash
cp .env.example .env
```

Minimum required values for a working deployment:

```bash
# Required: LLM and ASR
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx
LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1

# Required: Tencent COS (for ASR audio upload)
COS_SECRECT_ID=AKIDxxxxxxxx
COS_SECRECT_KEY=xxxxxxxx
COS_REGION=ap-singapore
COS_BUCKET=my-bucket-name

# Recommended: models
LLM_MODEL=qwen2.5-7b-instruct
CHAT_MODEL=qwen3-max
VL_MODEL=qwen2.5-vl-72b-instruct
```

Optional overrides (all have safe defaults):

```bash
# Ports
BACKEND_PORT=8000
FRONTEND_PORT=3000

# Paths (absolute or relative to MEDIA_ROOT)
MEDIA_ROOT=/data/media
LOG_DIR=/data/logs
DB_PATH=/data/db.sqlite3
CHROMA_PERSIST_DIR=/data/media/chromadb

# Security (change in production)
SECRET_KEY=your-long-random-secret-key
DEBUG=False
ALLOWED_HOSTS=myserver.com,www.myserver.com
CORS_ALLOWED_ORIGINS=https://myserver.com
```

---

## 9. Security Notes

- **Never commit `.env`** — it is in `.gitignore`
- Set `SECRET_KEY` to a random string in production (`python -c "import secrets; print(secrets.token_hex(50))"`)
- Set `DEBUG=False` in production
- Restrict `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS` to actual hostnames
- The `.env` file must be readable by the process user; avoid world-readable permissions (`chmod 600 .env`)
- In Docker, secrets are injected via `env_file` — avoid baking them into images

---

## 10. Troubleshooting

### Port already in use

```bash
BACKEND_PORT=9000 python manage.py runserver
# or set BACKEND_PORT=9000 in .env
```

### Media files not served

Verify `MEDIA_ROOT` exists and is writable. In development Django serves it automatically; in production configure your web server (nginx) to serve `MEDIA_URL` from `MEDIA_ROOT`.

### ChromaDB errors on startup

ChromaDB is created automatically on first use. If you see permission errors, check that `CHROMA_PERSIST_DIR` is writable by the process user. In Docker this is `/data/media/chromadb` inside the `lecturemind_data` volume.

### Configuration not taking effect

1. LLM client is reset automatically when `ConfigManager.set()` is called
2. For manual `.env` edits, sync to DB: `curl -X POST http://localhost:8000/api/config/sync-from-env/`
3. Settings read at import time (e.g. `MEDIA_ROOT`, `LOG_DIR`) require a server restart

### .env not loaded

The loader walks up from `manage.py`'s directory. Ensure `.env` is in one of:
- `server/app/.env`
- `server/.env`
- `LectureMind/.env` (project root — recommended)
