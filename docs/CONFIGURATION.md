# LectureMind Configuration System

This document describes the configuration system for LectureMind, which supports bidirectional sync between the web UI, database, and `.env` file.

## Overview

The configuration system provides a unified way to manage system settings across:
- **.env file**: Source of truth for deployment and persistence
- **Database**: Runtime configuration storage
- **Environment variables**: Process-level overrides
- **Web UI**: User-friendly configuration interface

## Model Configuration

The following model configurations are supported:

| Key | Description | Default |
|-----|-------------|---------|
| `llm_model` | Default LLM model for task pipeline | `qwen2.5-7b-instruct` |
| `chat_model` | Model for chat/agent endpoints | `qwen3-max` |
| `vl_model` | Vision-language model for slide OCR | `qwen2.5-vl-72b-instruct` |
| `llm_api_base` | LLM API base URL | `https://dashscope.aliyuncs.com/compatible-mode/v1` |

## API Configuration

| Key | Description | Default |
|-----|-------------|---------|
| `dashscope_api_key` | DashScope API key for LLM and ASR | (empty) |
| `cos_secret_id` | Tencent COS SecretId | (empty) |
| `cos_secret_key` | Tencent COS SecretKey | (empty) |
| `cos_region` | Tencent COS region | (empty) |
| `cos_bucket` | Tencent COS bucket name | (empty) |

## Configuration Priority

When reading configuration values, the system checks in this order (highest to lowest priority):

1. **Environment variables** (`os.environ`)
2. **Database** (`SystemConfig` model)
3. **.env file**
4. **Default values**

## Configuration Methods

### 1. Via .env File

Create or edit the `.env` file in the project root (same directory as `manage.py`):

```bash
# Model Configuration
llm_model=qwen2.5-7b-instruct
chat_model=qwen3-max
vl_model=qwen2.5-vl-72b-instruct
llm_api_base=https://dashscope.aliyuncs.com/compatible-mode/v1

# API Keys
dashscope_api_key=your-api-key-here

# Tencent COS Configuration
cos_secret_id=your-secret-id
cos_secret_key=your-secret-key
cos_region=ap-guangzhou
cos_bucket=your-bucket-name
```

### 2. Via Web UI

Access the system configuration through the web UI:

- **GET** `/api/config/` - List all configurations
- **POST** `/api/config/update/` - Update configuration values
- **POST** `/api/config/sync-from-env/` - Sync from .env to database

Example API calls:

```bash
# Get all configurations
curl http://localhost:8000/api/config/

# Update configuration (persists to both DB and .env)
curl -X POST http://localhost:8000/api/config/update/ \
  -H "Content-Type: application/json" \
  -d '{
    "key": "chat_model",
    "value": "qwen3.6-plus",
    "description": "Model for chat/agent endpoints"
  }'

# Batch update multiple configurations
curl -X POST http://localhost:8000/api/config/update/ \
  -H "Content-Type: application/json" \
  -d '[
    {"key": "llm_model", "value": "qwen-turbo"},
    {"key": "chat_model", "value": "qwen3-max"}
  ]'

# Sync from .env file to database
curl -X POST http://localhost:8000/api/config/sync-from-env/
```

### 3. Via Python Code

```python
from api.config_utils import ConfigManager

# Get configuration value
llm_model = ConfigManager.get('llm_model', 'default-model')

# Set configuration (persists to both DB and .env)
ConfigManager.set('chat_model', 'qwen3.6-plus')

# Set multiple configurations
configs = {
    'llm_model': {'value': 'qwen-turbo', 'description': 'Task pipeline model'},
    'chat_model': {'value': 'qwen3-max', 'description': 'Chat model'},
}
ConfigManager.set_multiple(configs)

# Sync from .env to database
ConfigManager.sync_from_env()

# Get all configurations
all_config = ConfigManager.get_all()
```

## How It Works

### Writing Configuration

When you update configuration via the Web UI or Python API:

1. The value is saved to the database (`SystemConfig` model)
2. The value is written to the `.env` file (for persistence)
3. The value is set in the current process's environment variables
4. The LLM client singleton is reset to pick up new configuration

### Reading Configuration

When the system reads a configuration value:

1. First checks environment variables (allows runtime overrides)
2. Then checks the database (runtime configuration)
3. Then checks the `.env` file (persistent configuration)
4. Finally falls back to default values

### .env File Structure

The `.env` file is automatically organized into sections:

```bash
# LectureMind Environment Configuration

# Model Configuration
llm_model=qwen2.5-7b-instruct
chat_model=qwen3-max
vl_model=qwen2.5-vl-72b-instruct
llm_api_base=https://dashscope.aliyuncs.com/compatible-mode/v1

# API Keys
dashscope_api_key=your-api-key

# Tencent COS Configuration
cos_secret_id=your-secret-id
cos_secret_key=your-secret-key
cos_region=ap-guangzhou
cos_bucket=your-bucket
```

## Security

### Secret Masking

Secret values (API keys, secrets) are masked in API responses:
- Values longer than 4 characters: show only last 4 characters
- Shorter values: show as `****`

Secret keys include:
- `dashscope_api_key`
- `cos_secret_id`
- `cos_secret_key`

### Best Practices

1. **Never commit `.env` file** to version control
2. **Use different API keys** for development and production
3. **Rotate secrets regularly**
4. **Limit access** to the `.env` file on production servers

## Migration from Old System

If you were using the previous configuration system:

1. Your existing database values will continue to work
2. New configurations will be persisted to `.env`
3. Run the sync endpoint to populate database from `.env`:
   ```bash
   curl -X POST http://localhost:8000/api/config/sync-from-env/
   ```

## Troubleshooting

### Configuration Not Persisting

1. Check that the `.env` file is writable
2. Verify the file path is correct
3. Check logs for write errors

### Configuration Not Taking Effect

1. The LLM client singleton is automatically reset on updates
2. For manual reset: `ConfigManager.reset_llm_client()`
3. Restart the Django server if needed

### .env File Not Found

The system searches for `.env` file starting from the directory containing `manage.py` and walking up the directory tree. Ensure your `.env` file is in one of these locations:
- Same directory as `manage.py`
- Parent directory of `manage.py`
- Project root directory

## API Reference

### ConfigManager

```python
class ConfigManager:
    @classmethod
    def get(cls, key: str, default: str = "") -> str
    @classmethod
    def set(cls, key: str, value: str, description: str = "", persist_to_env: bool = True) -> bool
    @classmethod
    def set_multiple(cls, configs: Dict[str, Dict[str, str]], persist_to_env: bool = True) -> Dict[str, bool]
    @classmethod
    def get_all(cls, include_secrets: bool = False) -> Dict[str, Dict[str, Any]]
    @classmethod
    def sync_from_env(cls) -> Dict[str, bool]
    @classmethod
    def reset_llm_client(cls)
```

### REST API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/config/` | List all configurations (secrets masked) |
| POST | `/api/config/update/` | Update configuration values |
| POST | `/api/config/sync-from-env/` | Sync .env file to database |
