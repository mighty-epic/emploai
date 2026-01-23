"""
Schemas for Dual Agent Communication
Defines the structured formats for requests and responses between Memory Agent and Executor.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Literal
from enum import Enum
import time


class RequestType(Enum):
    """Types of requests Memory Agent can make."""
    OBSERVE = "observe"
    ACTION = "action"
    STEP = "step"


class ObservationMethod(Enum):
    """Methods for observation based on context."""
    BROWSER = "browser"      # Selenium + screenshot
    DESKTOP = "desktop"      # pywinauto + OCR + screenshot
    GENERAL = "general"      # All methods


class ActionType(Enum):
    """Atomic action types."""
    CLICK = "click"
    TYPE = "type"
    PRESS_KEY = "press_key"
    SCROLL = "scroll"
    NAVIGATE = "navigate"
    FOCUS_WINDOW = "focus_window"


@dataclass
class ObserveRequest:
    """Request for observation from Executor."""
    method: ObservationMethod
    focus_area: Optional[str] = None  # e.g., "search results", "top menu"
    question: Optional[str] = None     # Specific thing to look for


@dataclass
class ActionRequest:
    """Request for action from Executor."""
    action_type: ActionType
    target: Optional[str] = None       # Element description or ID
    value: Optional[str] = None        # Text to type, key to press, URL to navigate
    coordinates: Optional[tuple] = None  # Fallback (x, y) if target not found


@dataclass
class StepRequest:
    """High-level step request for Executor to fulfill."""
    description: str


@dataclass
class ExecutorRequest:
    """Complete request sent to Executor."""
    request_type: RequestType
    observe: Optional[ObserveRequest] = None
    action: Optional[ActionRequest] = None
    step: Optional[StepRequest] = None
    
    def to_prompt(self) -> str:
        """Convert to prompt string for Executor."""
        if self.request_type == RequestType.STEP:
            return f"STEP: {self.step.description}"
        elif self.request_type == RequestType.OBSERVE:
            obs = self.observe
            method_str = obs.method.value if obs else "general"
            prompt = f"OBSERVE using {method_str} method."
            if obs and obs.focus_area:
                prompt += f" Focus on: {obs.focus_area}."
            if obs and obs.question:
                prompt += f" Answer: {obs.question}"
            return prompt
        else:
            act = self.action
            if act.action_type == ActionType.CLICK:
                return f"ACTION: Click on '{act.target}'"
            elif act.action_type == ActionType.TYPE:
                return f"ACTION: Type '{act.value}' into '{act.target or 'focused element'}'"
            elif act.action_type == ActionType.PRESS_KEY:
                return f"ACTION: Press key '{act.value}'"
            elif act.action_type == ActionType.SCROLL:
                return f"ACTION: Scroll {act.value}"
            elif act.action_type == ActionType.NAVIGATE:
                return f"ACTION: Navigate to '{act.value}'"
            elif act.action_type == ActionType.FOCUS_WINDOW:
                return f"ACTION: Focus window '{act.target}'"
            return f"ACTION: {act.action_type.value}"


@dataclass
class ObservationResult:
    """Structured observation result from Executor."""
    success: bool
    method_used: str
    screen_title: str = ""
    url: Optional[str] = None
    key_elements: List[Dict[str, Any]] = field(default_factory=list)
    focused_element: Optional[str] = None
    blockers: List[str] = field(default_factory=list)
    screenshot_path: Optional[str] = None
    raw_text: Optional[str] = None  # OCR text
    error: Optional[str] = None


@dataclass
class ActionResult:
    """Result of action execution from Executor."""
    success: bool
    action_taken: str
    failure_reason: Optional[str] = None
    element_found: bool = True
    coordinates_used: Optional[tuple] = None
    error: Optional[str] = None


@dataclass 
class ExecutorResponse:
    """Complete response from Executor."""
    request_type: RequestType
    observation: Optional[ObservationResult] = None
    action: Optional[ActionResult] = None
    impossible: bool = False
    impossible_reason: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class StepInfo:
    """Information about a task step."""
    step_number: int
    description: str
    status: Literal["pending", "in_progress", "complete", "failed"] = "pending"
    attempts: int = 0
    max_attempts: int = 3


@dataclass
class ActionHistoryEntry:
    """Entry in the prunable action history."""
    thought: str
    request: ExecutorRequest
    result: ExecutorResponse
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for context."""
        return {
            "thought": self.thought,
            "request": self.request.to_prompt(),
            "result_success": self.result.observation.success if self.result.observation else (
                self.result.action.success if self.result.action else False
            ),
            "result_summary": self._summarize_result()
        }
    
    def _summarize_result(self) -> str:
        if self.result.impossible:
            return f"IMPOSSIBLE: {self.result.impossible_reason}"
        if self.result.observation:
            obs = self.result.observation
            return f"Observed: {obs.screen_title}, {len(obs.key_elements)} elements"
        if self.result.action:
            act = self.result.action
            if act.success:
                return f"Action succeeded: {act.action_taken}"
            return f"Action failed: {act.failure_reason}"
        return "Unknown result"


@dataclass
class MemoryContext:
    """Complete context held by Memory Agent."""
    task: str
    step_list: List[StepInfo] = field(default_factory=list)
    action_history: List[ActionHistoryEntry] = field(default_factory=list)
    current_step_index: int = 0
    
    def get_current_step(self) -> Optional[StepInfo]:
        if 0 <= self.current_step_index < len(self.step_list):
            return self.step_list[self.current_step_index]
        return None
    
    def advance_step(self):
        if self.current_step_index < len(self.step_list):
            self.step_list[self.current_step_index].status = "complete"
        self.current_step_index += 1
        if self.current_step_index < len(self.step_list):
            self.step_list[self.current_step_index].status = "in_progress"
    
    def prune_if_needed(self, max_tokens: int, current_tokens: int):
        """Prune oldest action history if context exceeds 25% of max."""
        threshold = max_tokens * 0.25
        while current_tokens > threshold and len(self.action_history) > 5:
            # Keep at least 5 most recent entries
            self.action_history.pop(0)
            # Rough estimate: each entry ~200 tokens
            current_tokens -= 200
    
    def to_context_string(self) -> str:
        """Convert to string for LLM context."""
        lines = [
            f"TASK: {self.task}",
            "",
            "STEP LIST:"
        ]
        for step in self.step_list:
            status_icon = {
                "pending": "⬜",
                "in_progress": "🔄",
                "complete": "✅",
                "failed": "❌"
            }.get(step.status, "?")
            lines.append(f"  {status_icon} Step {step.step_number}: {step.description} [{step.status}]")
        
        if self.action_history:
            lines.append("")
            lines.append("RECENT ACTIONS:")
            # Show last 10 actions
            for entry in self.action_history[-10:]:
                d = entry.to_dict()
                lines.append(f"  - Thought: {d['thought'][:50]}...")
                lines.append(f"    Request: {d['request']}")
                lines.append(f"    Result: {d['result_summary']}")
        
        return "\n".join(lines)
