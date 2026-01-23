"""
Action Schema
Defines atomic actions that the hands layer can execute.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Literal
from enum import Enum


class ActionType(Enum):
    """Types of atomic actions."""
    # Mouse actions
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    MOUSE_DOWN = "mouse_down"
    MOUSE_UP = "mouse_up"
    MOUSE_MOVE = "mouse_move"
    SCROLL = "scroll"
    DRAG = "drag"
    
    # Keyboard actions
    TYPE_TEXT = "type_text"
    PRESS_KEY = "press_key"
    KEY_DOWN = "key_down"
    KEY_UP = "key_up"
    HOTKEY = "hotkey"
    
    # Wait actions
    WAIT_TIME = "wait_time"
    WAIT_ELEMENT = "wait_element"
    WAIT_URL = "wait_url"
    
    # Window actions
    FOCUS_WINDOW = "focus_window"
    MINIMIZE_WINDOW = "minimize_window"
    MAXIMIZE_WINDOW = "maximize_window"
    CLOSE_WINDOW = "close_window"
    
    # Browser-specific
    NAVIGATE = "navigate"
    GO_BACK = "go_back"
    GO_FORWARD = "go_forward"
    REFRESH = "refresh"


@dataclass
class ActionTarget:
    """
    Target specification for an action.
    Can be element-based or coordinate-based.
    """
    # Element-based targeting (preferred)
    element_id: Optional[str] = None
    
    # Coordinate-based targeting (fallback)
    x: Optional[float] = None
    y: Optional[float] = None
    
    # Text-based targeting (for finding elements)
    text: Optional[str] = None
    role: Optional[str] = None
    
    def is_element_target(self) -> bool:
        return self.element_id is not None
    
    def is_coordinate_target(self) -> bool:
        return self.x is not None and self.y is not None
    
    def is_text_target(self) -> bool:
        return self.text is not None


@dataclass
class AtomicAction:
    """
    A single atomic action to be executed.
    This is what the brain produces and hands consume.
    """
    # Action specification
    action_type: ActionType
    target: Optional[ActionTarget] = None
    
    # Action parameters
    text: Optional[str] = None  # For TYPE_TEXT
    key: Optional[str] = None  # For PRESS_KEY
    keys: Optional[List[str]] = None  # For HOTKEY
    url: Optional[str] = None  # For NAVIGATE
    scroll_amount: int = 0  # For SCROLL (positive = down, negative = up)
    wait_seconds: float = 0  # For WAIT_TIME
    
    # Execution hints
    rationale: str = ""  # Why this action was chosen
    confidence: float = 1.0  # How confident the proposer is
    risk_level: str = "low"  # "low", "medium", "high"
    is_reversible: bool = True
    
    # Metadata
    proposer_id: Optional[str] = None  # Which micro-agent proposed this
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "action_type": self.action_type.value,
            "target": {
                "element_id": self.target.element_id,
                "x": self.target.x,
                "y": self.target.y,
                "text": self.target.text,
                "role": self.target.role
            } if self.target else None,
            "text": self.text,
            "key": self.key,
            "keys": self.keys,
            "url": self.url,
            "scroll_amount": self.scroll_amount,
            "wait_seconds": self.wait_seconds,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "risk_level": self.risk_level,
            "is_reversible": self.is_reversible,
            "proposer_id": self.proposer_id,
            "metadata": self.metadata
        }


@dataclass
class ActionResult:
    """
    Result of executing an atomic action.
    Returned by the hands layer.
    """
    success: bool
    action: AtomicAction
    
    # Execution details
    actual_target_coords: Optional[tuple] = None  # Actual (x, y) clicked
    execution_time_ms: float = 0
    
    # Error info
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    
    # Evidence
    screenshot_before: Optional[str] = None
    screenshot_after: Optional[str] = None
    focus_changed: bool = False
    url_changed: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "action": self.action.to_dict(),
            "actual_target_coords": self.actual_target_coords,
            "execution_time_ms": self.execution_time_ms,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "focus_changed": self.focus_changed,
            "url_changed": self.url_changed
        }


@dataclass
class ActionProposal:
    """
    A proposed action from a micro-agent, before voting.
    """
    action: AtomicAction
    rationale: str
    proposer_id: str
    
    # Voting metadata
    votes: int = 0
    red_flags: List[str] = field(default_factory=list)
    is_filtered: bool = False  # True if red-flagged out
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.to_dict(),
            "rationale": self.rationale,
            "proposer_id": self.proposer_id,
            "votes": self.votes,
            "red_flags": self.red_flags,
            "is_filtered": self.is_filtered
        }
