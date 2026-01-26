"""Configuration data models."""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class ProviderConfig:
    """Configuration for a single AI provider."""
    api_key: str = ""  # Empty - actual key stored in keyring
    org_id: str = ""
    enabled: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization.
        
        Note: api_key is NOT stored in JSON - use keyring instead.
        """
        return {
            "org_id": self.org_id,
            "enabled": self.enabled,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProviderConfig":
        """Create from dictionary."""
        return cls(
            api_key="",  # Never load from dict - use keyring
            org_id=data.get("org_id", ""),
            enabled=data.get("enabled", False),
        )


@dataclass
class AppConfig:
    """Global application configuration."""
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    default_model: str = "claude-haiku-4.5"
    default_variant: str = "standard"
    default_agent_mode: str = "manual"
    
    # Tool Safety Settings
    workspace_restriction: bool = True  # 1.A: Stay in workspace
    command_confirmation: bool = True   # 2.A: Ask before run
    command_allow_list: list[str] = field(default_factory=list) # 2.B: Commands that don't need confirmation
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "providers": {
                name: config.to_dict() 
                for name, config in self.providers.items()
            },
            "default_model": self.default_model,
            "default_variant": self.default_variant,
            "default_agent_mode": self.default_agent_mode,
            "workspace_restriction": self.workspace_restriction,
            "command_confirmation": self.command_confirmation,
            "command_allow_list": self.command_allow_list,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        """Create from dictionary."""
        providers_data = data.get("providers", {})
        providers = {
            name: ProviderConfig.from_dict(config) 
            for name, config in providers_data.items()
        }
        return cls(
            providers=providers,
            default_model=data.get("default_model", "claude-haiku-4.5"),
            default_variant=data.get("default_variant", "standard"),
            default_agent_mode=data.get("default_agent_mode", "manual"),
            workspace_restriction=data.get("workspace_restriction", True),
            command_confirmation=data.get("command_confirmation", True),
            command_allow_list=data.get("command_allow_list", []),
        )
