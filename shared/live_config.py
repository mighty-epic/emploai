"""
Live Config System - Edit configuration without restarting
Similar to Moltbot's gateway.config.patch
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class ConfigChange:
    """Record of a configuration change."""
    timestamp: datetime
    user_id: int
    path: str  # Dot-notation path (e.g., "telegram.reply_mode")
    old_value: Any
    new_value: Any
    note: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'user_id': self.user_id,
            'path': self.path,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'note': self.note
        }


class LiveConfig:
    """
    Live configuration manager.
    Allows editing config values at runtime and persisting them.
    """
    
    def __init__(self, config_file: Optional[Path] = None):
        """
        Initialize live config manager.
        
        Args:
            config_file: Path to config JSON file (default: config.json)
        """
        self.config_file = config_file or Path("config.json")
        self.config: Dict[str, Any] = self._load_config()
        self.changes: List[ConfigChange] = []
        self._defaults = self._get_defaults()
        self._last_mtime_ns: Optional[int] = self._config_mtime_ns()

    def _config_mtime_ns(self) -> Optional[int]:
        try:
            return self.config_file.stat().st_mtime_ns
        except OSError:
            return None

    def refresh_if_needed(self):
        """Reload config from disk if the backing file changed."""
        current_mtime_ns = self._config_mtime_ns()
        if current_mtime_ns == self._last_mtime_ns:
            return
        self.config = self._load_config()
        self._last_mtime_ns = current_mtime_ns
    
    def _get_defaults(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            'telegram': {
                'reply_mode': 'full',  # full, minimal, silent
                'show_thinking': False,
                'inline_buttons': True,
                'rate_limit_per_min': 30,
                'rate_limit_per_hour': 200
            },
            'heartbeat': {
                'enabled': False,
                'interval_seconds': 1800,  # 30 minutes
                'quiet_hours_start': 23,  # 11 PM
                'quiet_hours_end': 8      # 8 AM
            },
            'memory': {
                'auto_save_daily_logs': True,
                'max_daily_log_days': 30,
                'enable_semantic_search': False  # TODO: Implement
            },
            'agent': {
                'default_model': 'claude-sonnet-4-5',
                'default_mode': 'auto',
                'max_turns': 100,
                'context_compression_threshold': 0.5
            },
            'skills': {
                'auto_trigger': True,
                'show_notifications': True
            },
            'security': {
                'allowed_user_ids': [],
                'max_file_size_mb': 10,
                'allowed_file_types': ['txt', 'md', 'py', 'js', 'json', 'yaml', 'yml']
            },
            'voice': {
                'selection_source': 'default',
                'default_engine': 'english_local',
                'packs': {
                    'english_local': {
                        'requested': True,
                        'display_name': 'English voice pack',
                        'placeholder': False
                    },
                    'hebrew_local': {
                        'requested': False,
                        'display_name': 'Hebrew voice pack',
                        'placeholder': False
                    }
                }
            },
            'channels': {
                'telegram': {
                    'enabled': True
                },
                'app': {
                    'enabled': False,
                    'host': '0.0.0.0',
                    'port': 8787,
                    'auth_mode': 'token',
                    'push_notifications': False
                },
                'desktop': {
                    'enabled': True,
                    'host': '127.0.0.1',
                    'port': 8787,
                    'auto_start': True,
                    'keep_runtime_on_app_close': False,
                    'attach_timeout_seconds': 20
                }
            }
        }
    
    def _load_config(self) -> Dict[str, Any]:
        """Load config from file or create with defaults."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                logger.info(f"Loaded config from {self.config_file}")
                return config
            except Exception as e:
                logger.error(f"Error loading config: {e}")
        
        # Return defaults if no file
        return self._get_defaults()
    
    def save_config(self):
        """Save current config to file."""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2)
            logger.info(f"Saved config to {self.config_file}")
            self._last_mtime_ns = self._config_mtime_ns()
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def get(self, path: str, default: Any = None) -> Any:
        """
        Get a config value by dot-notation path.
        
        Example: get("telegram.reply_mode") -> "full"
        """
        self.refresh_if_needed()
        parts = path.split('.')
        value = self.config
        
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        
        return value
    
    def set(self, path: str, value: Any, user_id: int = 0, note: Optional[str] = None):
        """
        Set a config value by dot-notation path.
        
        Example: set("telegram.reply_mode", "minimal")
        """
        self.refresh_if_needed()
        parts = path.split('.')
        old_value = self.get(path)
        
        # Navigate to the parent
        current = self.config
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        # Set the value
        current[parts[-1]] = value
        
        # Record change
        change = ConfigChange(
            timestamp=datetime.now(),
            user_id=user_id,
            path=path,
            old_value=old_value,
            new_value=value,
            note=note
        )
        self.changes.append(change)
        
        logger.info(f"Config changed: {path} = {value} (was {old_value})")
    
    def patch(self, updates: Dict[str, Any], user_id: int = 0, note: Optional[str] = None):
        """
        Patch multiple config values at once.
        
        Example:
            patch({
                "telegram.reply_mode": "minimal",
                "heartbeat.enabled": True
            })
        """
        for path, value in updates.items():
            self.set(path, value, user_id, note)
    
    def reset_to_defaults(self):
        """Reset all config to defaults."""
        self.config = self._get_defaults()
        self._last_mtime_ns = self._config_mtime_ns()
        logger.info("Config reset to defaults")
    
    def get_section(self, section: str) -> Optional[Dict]:
        """Get an entire config section."""
        self.refresh_if_needed()
        return self.config.get(section)
    
    def list_all(self) -> Dict[str, Any]:
        """Get all config as a flat dict with dot-notation keys."""
        self.refresh_if_needed()
        def flatten(d: Dict, prefix: str = '') -> Dict:
            items = {}
            for k, v in d.items():
                new_key = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    items.update(flatten(v, new_key))
                else:
                    items[new_key] = v
            return items
        
        return flatten(self.config)
    
    def get_change_history(self, limit: int = 10) -> List[Dict]:
        """Get recent config changes."""
        return [c.to_dict() for c in self.changes[-limit:]]
    
    def export_for_env(self) -> str:
        """Export config as .env format."""
        lines = []
        for key, value in self.list_all().items():
            env_key = key.upper().replace('.', '_')
            if isinstance(value, bool):
                env_value = "true" if value else "false"
            elif isinstance(value, (list, dict)):
                env_value = json.dumps(value)
            else:
                env_value = str(value)
            
            lines.append(f"{env_key}={env_value}")
        
        return '\n'.join(lines)
    
    def import_from_env(self):
        """Import config values from environment variables."""
        # Map env vars back to config paths
        for key, value in os.environ.items():
            # Convert ENV_VAR_NAME to config.path
            config_path = key.lower().replace('_', '.')
            
            # Try to parse the value
            try:
                if value.lower() in ('true', 'false'):
                    parsed_value = value.lower() == 'true'
                elif value.startswith('[') or value.startswith('{'):
                    parsed_value = json.loads(value)
                else:
                    # Try int, then float, then keep as string
                    try:
                        parsed_value = int(value)
                    except ValueError:
                        try:
                            parsed_value = float(value)
                        except ValueError:
                            parsed_value = value
                
                # Only set if path exists in defaults
                if self.get(config_path) is not None:
                    self.set(config_path, parsed_value, user_id=0, note="imported from env")
            except Exception as e:
                logger.debug(f"Skipping env var {key}: {e}")


# Global instance
_live_config: Optional[LiveConfig] = None


def get_live_config(config_file: Optional[Path] = None) -> LiveConfig:
    """Get or create the global live config instance."""
    global _live_config
    resolved_config_file = (config_file or Path("config.json")).resolve()
    if _live_config is None or _live_config.config_file.resolve() != resolved_config_file:
        _live_config = LiveConfig(resolved_config_file)
    else:
        _live_config.refresh_if_needed()
    return _live_config
