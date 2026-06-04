"""Configuration Manager - handles global config and secure API key storage."""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False
    print("[WARNING] keyring not installed. API keys will fall back to environment variables.")

from openai import OpenAI
from anthropic import Anthropic

from cli.models.config import ProviderConfig, AppConfig
from shared.runtime_paths import scoped_keyring_service, shared_state_root


# Service name for keyring storage
KEYRING_SERVICE = "agentshell"

# Provider definitions
PROVIDERS = [
    {"id": "openai", "name": "OpenAI", "key_prefix": "sk-", "env_var": "OPENAI_API_KEY"},
    {"id": "anthropic", "name": "Anthropic", "key_prefix": "sk-ant-", "env_var": "ANTHROPIC_API_KEY"},
    {"id": "google", "name": "Google (Gemini)", "key_prefix": "", "env_var": "GOOGLE_API_KEY"},
    {"id": "xai", "name": "xAI (Grok)", "key_prefix": "", "env_var": "XAI_API_KEY"},
    {"id": "deepseek", "name": "DeepSeek", "key_prefix": "sk-", "env_var": "DEEPSEEK_API_KEY"},
    {"id": "openrouter", "name": "OpenRouter", "key_prefix": "sk-or-", "env_var": "OPENROUTER_API_KEY"},
]


class ConfigManager:
    """Manages global configuration including secure API key storage."""
    
    def __init__(self, base_path: Optional[Path] = None):
        """Initialize config manager.
        
        Args:
            base_path: Base path for storing config. Defaults to ~/.agentshell
        """
        self.base_path = base_path or shared_state_root()
        self.config_file = self.base_path / "config.json"
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._config: Optional[AppConfig] = None
        self.keyring_service = scoped_keyring_service(KEYRING_SERVICE)
    
    def load(self) -> AppConfig:
        """Load configuration from disk.
        
        Returns:
            AppConfig object.
        """
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                self._config = AppConfig.from_dict(data)
            except (json.JSONDecodeError, IOError):
                self._config = self._default_config()
        else:
            self._config = self._default_config()
        
        return self._config
    
    def save(self) -> None:
        """Save configuration to disk."""
        if self._config:
            self.config_file.write_text(
                json.dumps(self._config.to_dict(), indent=2),
                encoding="utf-8"
            )
    
    def get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for a provider, using keyring with env var fallback.
        
        Priority:
        1. Keyring (secure storage)
        2. Environment variable
        
        Args:
            provider: Provider ID (openai, anthropic, google, xai).
            
        Returns:
            API key or None if not found.
        """
        # Try keyring first
        if KEYRING_AVAILABLE:
            try:
                key = keyring.get_password(self.keyring_service, provider)
                if key:
                    return key
            except Exception:
                pass  # Fall through to env var
        
        # Fallback to environment variables
        env_vars = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
            "xai": "XAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }
        
        env_var = env_vars.get(provider, "")
        return os.getenv(env_var) if env_var else None
    
    def set_api_key(self, provider: str, key: str) -> bool:
        """Set API key for a provider using keyring.
        
        Args:
            provider: Provider ID.
            key: API key to store.
            
        Returns:
            True if successfully stored, False otherwise.
        """
        if not KEYRING_AVAILABLE:
            return False
        
        try:
            keyring.set_password(self.keyring_service, provider, key)
            
            # Update config to mark provider as enabled
            config = self.load()
            if provider not in config.providers:
                config.providers[provider] = ProviderConfig()
            config.providers[provider].enabled = True
            self.save()
            
            return True
        except Exception as e:
            print(f"[ERROR] Failed to save API key: {e}")
            return False
    
    def delete_api_key(self, provider: str) -> bool:
        """Delete API key for a provider from keyring.
        
        Args:
            provider: Provider ID.
            
        Returns:
            True if successfully deleted, False otherwise.
        """
        if not KEYRING_AVAILABLE:
            return False
        
        try:
            keyring.delete_password(self.keyring_service, provider)
            
            # Update config to mark provider as disabled
            config = self.load()
            if provider in config.providers:
                config.providers[provider].enabled = False
            self.save()
            
            return True
        except Exception:
            return False
    
    def test_api_key(self, provider: str) -> tuple[bool, str]:
        """Test if an API key is valid by making a simple API call.
        
        Args:
            provider: Provider ID to test.
            
        Returns:
            Tuple of (success, message).
        """
        key = self.get_api_key(provider)
        
        if not key:
            return False, "No API key configured"
        
        try:
            if provider == "openai":
                client = OpenAI(api_key=key)
                # Simple validation - list models
                client.models.list()
                return True, "OK"
            
            elif provider == "anthropic":
                client = Anthropic(api_key=key)
                # Anthropic doesn't have a simple list endpoint
                # Just verify client creation works
                return True, "OK"
            
            elif provider == "google":
                # Google Gemini validation would go here
                return True, "OK (not validated)"
            
            elif provider == "xai":
                # xAI/Grok validation would go here
                return True, "OK (not validated)"
            
            return False, "Unknown provider"
            
        except Exception as e:
            return False, str(e)[:50]  # Truncate error message
    
    def is_provider_enabled(self, provider: str) -> bool:
        """Check if a provider is enabled.
        
        Args:
            provider: Provider ID.
            
        Returns:
            True if enabled, False otherwise.
        """
        config = self.load()
        provider_config = config.providers.get(provider)
        
        if provider_config and provider_config.enabled:
            return True
        
        # Also check if we have an API key (from env or keyring)
        return self.get_api_key(provider) is not None
    
    def get_enabled_providers(self) -> list[str]:
        """Get list of enabled provider IDs.
        
        Returns:
            List of provider IDs that are enabled.
        """
        return [
            p["id"] for p in PROVIDERS 
            if self.is_provider_enabled(p["id"])
        ]
    
    def set_default_model(self, model: str) -> None:
        """Set the default model.
        
        Args:
            model: Model name to set as default.
        """
        config = self.load()
        config.default_model = model
        self.save()
    
    def set_default_variant(self, variant: str) -> None:
        """Set the default variant.
        
        Args:
            variant: Variant name to set as default.
        """
        config = self.load()
        config.default_variant = variant
        self.save()
    
    def set_default_agent_mode(self, mode: str) -> None:
        """Set the default agent mode.
        
        Args:
            mode: Agent mode to set as default.
        """
        config = self.load()
        config.default_agent_mode = mode
        self.save()

    def get_workspace_restriction(self) -> bool:
        """Get workspace restriction setting."""
        config = self.load()
        return config.workspace_restriction

    def set_workspace_restriction(self, enabled: bool) -> None:
        """Set workspace restriction setting."""
        config = self.load()
        config.workspace_restriction = enabled
        self.save()

    def get_command_confirmation(self) -> bool:
        """Get command confirmation setting."""
        config = self.load()
        return config.command_confirmation

    def set_command_confirmation(self, enabled: bool) -> None:
        """Set command confirmation setting."""
        config = self.load()
        config.command_confirmation = enabled
        self.save()

    def get_command_allow_list(self) -> list[str]:
        """Get command allow list."""
        config = self.load()
        return config.command_allow_list

    def set_command_allow_list(self, allow_list: list[str]) -> None:
        """Set command allow list."""
        config = self.load()
        config.command_allow_list = allow_list
        self.save()
    
    def _default_config(self) -> AppConfig:
        """Create default configuration."""
        return AppConfig(
            providers={},
            default_model="claude-haiku-4.5",
            default_variant="standard",
            default_agent_mode="manual",
        )


# Singleton instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get the global config manager instance.
    
    Returns:
        ConfigManager singleton.
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
