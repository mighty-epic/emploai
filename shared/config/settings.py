"""
Global configuration settings for the agentic system.
"""

from dataclasses import dataclass
from typing import Dict, Any
import os


@dataclass
class MAKERConfig:
    """MAKER voting configuration."""
    # Default K value for first-to-ahead-by-K voting
    default_k: int = 2
    
    # K adjustments based on context
    k_low_risk: int = 1
    k_medium_risk: int = 2
    k_high_risk: int = 4
    
    # Maximum proposals to sample before giving up
    max_proposals: int = 20
    
    # Minimum proposals before allowing a decision
    min_proposals: int = 3


@dataclass
class RedFlagConfig:
    """Red-flagging configuration."""
    # Confidence thresholds
    min_visual_confidence: float = 0.7
    min_ocr_confidence: float = 0.8
    
    # Risky action patterns
    irreversible_keywords: list = None
    payment_keywords: list = None
    delete_keywords: list = None
    
    def __post_init__(self):
        if self.irreversible_keywords is None:
            self.irreversible_keywords = [
                "send", "submit", "confirm", "delete", "remove",
                "pay", "purchase", "order", "checkout"
            ]
        if self.payment_keywords is None:
            self.payment_keywords = [
                "pay", "payment", "checkout", "purchase", "buy",
                "credit card", "billing"
            ]
        if self.delete_keywords is None:
            self.delete_keywords = [
                "delete", "remove", "trash", "discard", "clear"
            ]


@dataclass
class ObservationConfig:
    """Observation layer configuration."""
    # Screenshot settings
    screenshot_format: str = "png"
    screenshot_quality: int = 90
    
    # Element detection
    max_elements: int = 500
    min_element_size: int = 5  # pixels
    
    # OmniParser settings
    omniparser_model: str = "default"
    use_gpu: bool = True


@dataclass
class HandsConfig:
    """Hands layer configuration."""
    # Timing
    default_click_delay: float = 0.1  # seconds
    default_type_delay: float = 0.05  # seconds between keystrokes
    
    # Safety
    action_timeout: float = 10.0  # seconds
    verify_focus_before_action: bool = True
    
    # Coordinate handling
    auto_dpi_scaling: bool = True


@dataclass
class OrchestratorConfig:
    """Orchestrator configuration."""
    # LLM settings
    model: str = "gpt-4"
    temperature: float = 0.3
    max_tokens: int = 2000
    
    # Plan verification
    verify_after_each_step: bool = True
    max_consecutive_failures: int = 3
    
    # Micro-agent settings
    micro_agent_model: str = "gpt-4"
    micro_agent_temperature: float = 0.7  # Higher for diversity
    num_micro_agents: int = 5


@dataclass
class SystemConfig:
    """Top-level system configuration."""
    maker: MAKERConfig = None
    red_flags: RedFlagConfig = None
    observation: ObservationConfig = None
    hands: HandsConfig = None
    orchestrator: OrchestratorConfig = None
    
    # Paths
    log_dir: str = "./logs"
    screenshot_dir: str = "./screenshots"
    
    # Debug
    debug_mode: bool = True
    save_all_observations: bool = True
    
    def __post_init__(self):
        self.maker = self.maker or MAKERConfig()
        self.red_flags = self.red_flags or RedFlagConfig()
        self.observation = self.observation or ObservationConfig()
        self.hands = self.hands or HandsConfig()
        self.orchestrator = self.orchestrator or OrchestratorConfig()


# Default global config
DEFAULT_CONFIG = SystemConfig()
