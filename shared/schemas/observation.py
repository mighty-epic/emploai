"""
Observation Schema
Normalized format for screen state observations from any source.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class ElementRole(Enum):
    """Semantic roles for UI elements."""
    BUTTON = "button"
    LINK = "link"
    TEXTBOX = "textbox"
    SEARCHBOX = "searchbox"
    DROPDOWN = "dropdown"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    LABEL = "label"
    HEADING = "heading"
    IMAGE = "image"
    ICON = "icon"
    LIST = "list"
    LISTITEM = "listitem"
    MENU = "menu"
    MENUITEM = "menuitem"
    TAB = "tab"
    TREE = "tree"
    TREEITEM = "treeitem"
    GRID = "grid"
    GRIDCELL = "gridcell"
    MODAL = "modal"
    GENERIC = "generic"


@dataclass
class BoundingBox:
    """Bounding box for an element."""
    x: float
    y: float
    width: float
    height: float
    
    @property
    def center(self) -> tuple:
        """Get center point of bounding box."""
        return (self.x + self.width / 2, self.y + self.height / 2)
    
    @property
    def area(self) -> float:
        """Get area of bounding box."""
        return self.width * self.height
    
    def contains_point(self, px: float, py: float) -> bool:
        """Check if point is inside bounding box."""
        return (self.x <= px <= self.x + self.width and
                self.y <= py <= self.y + self.height)


@dataclass
class ElementDescriptor:
    """
    Normalized descriptor for a UI element.
    Used by both structured and vision-based observation.
    """
    # Identity
    id: str  # Unique ID within this observation
    
    # Semantics
    role: str  # One of ElementRole values
    text: str = ""  # Visible text content
    label: str = ""  # Accessible name/label
    
    # Geometry
    bbox: Optional[BoundingBox] = None
    
    # State
    is_enabled: bool = True
    is_focused: bool = False
    is_selected: bool = False
    is_visible: bool = True
    
    # Confidence (1.0 for structured, < 1.0 for vision)
    confidence: float = 1.0
    
    # Source-specific metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "role": self.role,
            "text": self.text,
            "label": self.label,
            "bbox": {
                "x": self.bbox.x,
                "y": self.bbox.y,
                "width": self.bbox.width,
                "height": self.bbox.height
            } if self.bbox else None,
            "is_enabled": self.is_enabled,
            "is_focused": self.is_focused,
            "is_selected": self.is_selected,
            "is_visible": self.is_visible,
            "confidence": self.confidence,
            "metadata": self.metadata
        }


@dataclass
class ObservationSnapshot:
    """
    Complete observation of screen state at a point in time.
    This is the output of the observation layer.
    """
    # Source identification
    source: str  # "selenium", "pywinauto", "omniparser", "hybrid"
    timestamp: float  # Unix timestamp
    
    # Context
    active_window_title: str = ""
    url: Optional[str] = None  # For browser observations
    
    # Elements
    elements: List[ElementDescriptor] = field(default_factory=list)
    focused_element_id: Optional[str] = None
    
    # Raw data
    screenshot_path: Optional[str] = None
    annotated_screenshot_path: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_element_by_id(self, element_id: str) -> Optional[ElementDescriptor]:
        """Find element by ID."""
        for el in self.elements:
            if el.id == element_id:
                return el
        return None
    
    def get_elements_by_role(self, role: str) -> List[ElementDescriptor]:
        """Find all elements with a specific role."""
        return [el for el in self.elements if el.role == role]
    
    def get_focused_element(self) -> Optional[ElementDescriptor]:
        """Get the focused element if any."""
        if self.focused_element_id:
            return self.get_element_by_id(self.focused_element_id)
        for el in self.elements:
            if el.is_focused:
                return el
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "source": self.source,
            "timestamp": self.timestamp,
            "active_window_title": self.active_window_title,
            "url": self.url,
            "elements": [el.to_dict() for el in self.elements],
            "focused_element_id": self.focused_element_id,
            "screenshot_path": self.screenshot_path,
            "annotated_screenshot_path": self.annotated_screenshot_path,
            "metadata": self.metadata
        }
