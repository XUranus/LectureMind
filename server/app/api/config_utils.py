"""
Configuration utilities for managing system settings.

Handles bidirectional sync between:
- .env file (source of truth for deployment)
- Database (runtime configuration)
- Environment variables (process-level overrides)

Usage:
    from api.config_utils import ConfigManager

    # Get config (checks DB first, then .env, then defaults)
    value = ConfigManager.get('llm_model')

    # Set config (updates both DB and .env)
    ConfigManager.set('llm_model', 'qwen3.6-plus')

    # Load all configs from .env to DB
    ConfigManager.sync_from_env()
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, Any
from django.conf import settings

logger = logging.getLogger('LectureMind')


class ConfigManager:
    """
    Manages system configuration with bidirectional .env and DB sync.

    Priority order (highest to lowest):
    1. Environment variables (os.environ)
    2. Database values (SystemConfig model)
    3. .env file values
    4. Default values
    """

    # Configuration keys that should be persisted to .env
    ENV_PERSIST_KEYS = {
        'llm_model',
        'llm_api_base',
        'chat_model',
        'vl_model',
        'dashscope_api_key',
        'cos_secret_id',
        'cos_secret_key',
        'cos_region',
        'cos_bucket',
    }

    # Model configuration keys
    MODEL_CONFIG_KEYS = {
        'llm_model': ('qwen2.5-7b-instruct', 'Default LLM model for task pipeline'),
        'chat_model': ('qwen3-max', 'Model for chat/agent endpoints'),
        'vl_model': ('qwen2.5-vl-72b-instruct', 'Vision-language model for slide OCR'),
        'llm_api_base': ('https://dashscope.aliyuncs.com/compatible-mode/v1', 'LLM API base URL'),
    }

    # Secret keys that should be masked
    SECRET_KEYS = {'dashscope_api_key', 'cos_secret_id', 'cos_secret_key'}

    @classmethod
    def find_env_file(cls) -> Optional[Path]:
        """Find the .env file in the project root."""
        # Start from the directory containing manage.py
        search = Path(__file__).resolve().parent.parent
        for _ in range(10):
            env_file = search / '.env'
            if env_file.exists():
                return env_file
            search = search.parent
        return None

    @classmethod
    def read_env_file(cls) -> Dict[str, str]:
        """Read all values from .env file, normalizing keys to lowercase."""
        env_file = cls.find_env_file()
        if not env_file:
            return {}

        env_vars = {}
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' not in line:
                        continue
                    key, val = line.split('=', 1)
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    # Handle inline comments
                    if ' #' in val:
                        val = val.split(' #')[0].strip().strip("'").strip('"')
                    # Normalize key to lowercase for internal use
                    env_vars[key.lower()] = val
        except Exception as e:
            logger.error(f"Failed to read .env file: {e}")

        return env_vars

    @classmethod
    def _to_env_key(cls, key: str) -> str:
        """Convert internal key to environment variable format (UPPERCASE with underscores)."""
        return key.upper()

    @classmethod
    def _from_env_key(cls, key: str) -> str:
        """Convert environment variable format to internal key (lowercase)."""
        return key.lower()

    @classmethod
    def write_env_file(cls, updates: Dict[str, str]) -> bool:
        """
        Update the .env file with new values.

        Args:
            updates: Dictionary of key-value pairs to update (keys in lowercase)

        Returns:
            True if successful, False otherwise
        """
        env_file = cls.find_env_file()
        if not env_file:
            # Try to create .env in the project root (where manage.py is)
            search = Path(__file__).resolve().parent.parent
            for _ in range(10):
                manage_py = search / 'manage.py'
                if manage_py.exists():
                    env_file = search / '.env'
                    break
                search = search.parent

        if not env_file:
            logger.error("Could not find or create .env file location")
            return False

        try:
            # Read existing content (normalize keys to uppercase for comparison)
            existing_vars = {}
            comments = []
            if env_file.exists():
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line_stripped = line.strip()
                        if not line_stripped or line_stripped.startswith('#'):
                            comments.append(line)
                            continue
                        if '=' not in line_stripped:
                            comments.append(line)
                            continue
                        key, val = line_stripped.split('=', 1)
                        key = key.strip()
                        # Normalize key to uppercase for storage
                        existing_vars[key.upper()] = line

            # Update with new values (convert keys to uppercase)
            for key, value in updates.items():
                env_key = cls._to_env_key(key)
                # Escape special characters in value
                safe_value = value.replace('"', '\\"')
                if ' ' in safe_value or '#' in safe_value:
                    safe_value = f'"{safe_value}"'
                existing_vars[env_key] = f"{env_key}={safe_value}\n"

            # Write back to file
            with open(env_file, 'w', encoding='utf-8') as f:
                # Write header comment if file is new
                if not comments:
                    f.write("# LectureMind Environment Configuration\n")
                    f.write("# Generated automatically - do not edit manually\n\n")

                # Write model configs section
                f.write("# Model Configuration\n")
                for key in ['LLM_MODEL', 'CHAT_MODEL', 'VL_MODEL', 'LLM_API_BASE']:
                    if key in existing_vars:
                        f.write(existing_vars[key])
                        del existing_vars[key]

                # Write API keys section
                f.write("\n# API Keys\n")
                for key in ['DASHSCOPE_API_KEY']:
                    if key in existing_vars:
                        f.write(existing_vars[key])
                        del existing_vars[key]

                # Write COS config section
                f.write("\n# Tencent COS Configuration\n")
                for key in ['COS_SECRET_ID', 'COS_SECRET_KEY', 'COS_REGION', 'COS_BUCKET']:
                    if key in existing_vars:
                        f.write(existing_vars[key])
                        del existing_vars[key]

                # Write any remaining vars
                if existing_vars:
                    f.write("\n# Other Configuration\n")
                    for line in existing_vars.values():
                        f.write(line)

            logger.info(f"Updated .env file: {env_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to write .env file: {e}")
            return False

    @classmethod
    def get(cls, key: str, default: str = "") -> str:
        """
        Get a configuration value.

        Priority:
        1. Environment variable (os.environ) - checks both lowercase and UPPERCASE
        2. Database (SystemConfig model)
        3. .env file
        4. Default value

        Args:
            key: Configuration key (lowercase)
            default: Default value if not found anywhere

        Returns:
            Configuration value
        """
        # Normalize key to lowercase for internal use
        key = key.lower()

        # 1. Check environment variable first (both lowercase and UPPERCASE)
        if key in os.environ:
            return os.environ[key]
        env_key = cls._to_env_key(key)
        if env_key in os.environ:
            return os.environ[env_key]

        # 2. Check database
        try:
            from api.models import SystemConfig
            try:
                return SystemConfig.objects.get(key=key).value
            except SystemConfig.DoesNotExist:
                pass
        except Exception as e:
            logger.debug(f"Could not query SystemConfig: {e}")

        # 3. Check .env file (keys are normalized to lowercase)
        env_vars = cls.read_env_file()
        if key in env_vars:
            return env_vars[key]

        # 4. Return default
        if key in cls.MODEL_CONFIG_KEYS:
            return cls.MODEL_CONFIG_KEYS[key][0]

        return default

    @classmethod
    def set(cls, key: str, value: str, description: str = "", persist_to_env: bool = True) -> bool:
        """
        Set a configuration value.

        Updates both the database and .env file (if persist_to_env is True).

        Args:
            key: Configuration key
            value: Configuration value
            description: Optional description for the config
            persist_to_env: Whether to persist to .env file

        Returns:
            True if successful, False otherwise
        """
        from api.models import SystemConfig

        # Get default description if not provided
        if not description and key in cls.MODEL_CONFIG_KEYS:
            description = cls.MODEL_CONFIG_KEYS[key][1]

        success = True

        # Update database
        try:
            obj, created = SystemConfig.objects.update_or_create(
                key=key,
                defaults={'value': value, 'description': description}
            )
            logger.info(f"Updated SystemConfig: {key}={value[:20]}..." if len(value) > 20 else f"Updated SystemConfig: {key}={value}")
        except Exception as e:
            logger.error(f"Failed to update SystemConfig: {e}")
            success = False

        # Update environment variable for current process
        os.environ[key] = value

        # Persist to .env file if requested
        if persist_to_env and key in cls.ENV_PERSIST_KEYS:
            if not cls.write_env_file({key: value}):
                success = False

        return success

    @classmethod
    def set_multiple(cls, configs: Dict[str, Dict[str, str]], persist_to_env: bool = True) -> Dict[str, bool]:
        """
        Set multiple configuration values at once.

        Args:
            configs: Dictionary mapping keys to {'value': ..., 'description': ...}
            persist_to_env: Whether to persist to .env file

        Returns:
            Dictionary mapping keys to success status
        """
        results = {}
        env_updates = {}

        from api.models import SystemConfig

        for key, config in configs.items():
            value = config.get('value', '')
            description = config.get('description', '')

            if not description and key in cls.MODEL_CONFIG_KEYS:
                description = cls.MODEL_CONFIG_KEYS[key][1]

            # Update database
            try:
                obj, created = SystemConfig.objects.update_or_create(
                    key=key,
                    defaults={'value': value, 'description': description}
                )
                results[key] = True
                os.environ[key] = value

                if persist_to_env and key in cls.ENV_PERSIST_KEYS:
                    env_updates[key] = value
            except Exception as e:
                logger.error(f"Failed to update {key}: {e}")
                results[key] = False

        # Batch update .env file
        if env_updates:
            cls.write_env_file(env_updates)

        return results

    @classmethod
    def sync_from_env(cls) -> Dict[str, bool]:
        """
        Sync all configuration from .env file to database.

        Returns:
            Dictionary mapping keys to success status
        """
        env_vars = cls.read_env_file()
        configs = {}

        for key, value in env_vars.items():
            description = ""
            if key in cls.MODEL_CONFIG_KEYS:
                description = cls.MODEL_CONFIG_KEYS[key][1]
            configs[key] = {'value': value, 'description': description}

        return cls.set_multiple(configs, persist_to_env=False)

    @classmethod
    def get_all(cls, include_secrets: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        Get all configuration values.

        Args:
            include_secrets: If False, mask secret values

        Returns:
            Dictionary mapping keys to config info
        """
        from api.models import SystemConfig

        result = {}

        # Start with defaults
        for key, (default_val, desc) in cls.MODEL_CONFIG_KEYS.items():
            result[key] = {
                'value': default_val,
                'description': desc,
                'source': 'default',
                'is_secret': key in cls.SECRET_KEYS,
            }

        # Override with .env values
        env_vars = cls.read_env_file()
        for key, value in env_vars.items():
            if key in result:
                result[key]['value'] = value
                result[key]['source'] = '.env'

        # Override with database values
        try:
            for obj in SystemConfig.objects.all():
                if obj.key in result:
                    result[obj.key]['value'] = obj.value
                    result[obj.key]['source'] = 'database'
                    if obj.description:
                        result[obj.key]['description'] = obj.description
                else:
                    result[obj.key] = {
                        'value': obj.value,
                        'description': obj.description,
                        'source': 'database',
                        'is_secret': obj.key in cls.SECRET_KEYS,
                    }
        except Exception as e:
            logger.debug(f"Could not query SystemConfig: {e}")

        # Override with environment variables
        for key in result:
            if key in os.environ:
                result[key]['value'] = os.environ[key]
                result[key]['source'] = 'environment'

        # Mask secrets if requested
        if not include_secrets:
            for key, info in result.items():
                if info.get('is_secret') and info['value']:
                    value = info['value']
                    if len(value) > 4:
                        info['value'] = "*" * (len(value) - 4) + value[-4:]
                    else:
                        info['value'] = "****"

        return result

    @classmethod
    def reset_llm_client(cls):
        """Reset the LLM client singleton to pick up new configuration."""
        try:
            import api.llm_client as _llm_mod
            _llm_mod._default_client = None
            logger.info("Reset LLM client singleton")
        except Exception as e:
            logger.debug(f"Could not reset LLM client: {e}")
