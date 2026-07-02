"""
Runtime hook system.

Provides an extensible event system for custom behaviors.
"""

import logging
from enum import Enum
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass
from datetime import datetime


logger = logging.getLogger(__name__)


class HookType(Enum):
    """Types of hooks available in the system."""
    # Message lifecycle
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_PREPROCESS = "message_preprocess"
    MESSAGE_PROCESSED = "message_processed"
    MESSAGE_REPLY = "message_reply"
    
    # Command lifecycle
    COMMAND_PRE = "command_pre"
    COMMAND_POST = "command_post"
    
    # Agent lifecycle
    AGENT_START = "agent_start"
    AGENT_STOP = "agent_stop"
    AGENT_ERROR = "agent_error"
    
    # Tool execution
    TOOL_PRE = "tool_pre"
    TOOL_POST = "tool_post"
    
    # Custom
    CUSTOM = "custom"


@dataclass
class HookEvent:
    """Event data passed to hook handlers."""
    hook_type: HookType
    timestamp: datetime
    user_id: int
    data: Dict[str, Any]
    
    @classmethod
    def create(cls, hook_type: HookType, user_id: int, **data) -> "HookEvent":
        return cls(
            hook_type=hook_type,
            timestamp=datetime.now(),
            user_id=user_id,
            data=data
        )


@dataclass
class HookResult:
    """Result from a hook handler."""
    success: bool
    modified_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    stop_processing: bool = False  # If True, stop further hooks


HookHandler = Callable[[HookEvent], HookResult]


class HookManager:
    """
    Manages hooks for local agent surfaces.
    
    Hooks allow extending the agent's behavior without modifying core code.
    They can:
    - Modify messages before processing
    - Add custom commands
    - Log events
    - Integrate with external systems
    - Enforce policies
    """
    
    def __init__(self):
        # Store tuples of (priority, order, handler) for sorting
        self._handlers: Dict[HookType, List[tuple[int, int, HookHandler]]] = {
            hook_type: [] for hook_type in HookType
        }
        self._enabled = True
        logger.info("HookManager initialized")
    
    def register(self, hook_type: HookType, handler: HookHandler, 
                 priority: int = 0) -> None:
        """
        Register a hook handler.
        
        Args:
            hook_type: Type of hook to register for
            handler: Function to call when hook is triggered
            priority: Higher priority handlers run first (default: 0)
        """
        # Insert based on priority
        handlers = self._handlers[hook_type]
        
        # Store with priority for sorting
        handler_with_meta: tuple[int, int, HookHandler] = (priority, len(handlers), handler)
        handlers.append(handler_with_meta)
        # Sort by priority (descending), then by registration order
        handlers.sort(key=lambda x: (-x[0], x[1]))
        
        logger.debug(f"Registered {handler.__name__} for {hook_type.value} (priority: {priority})")
    
    def unregister(self, hook_type: HookType, handler: HookHandler) -> bool:
        """Unregister a hook handler."""
        handlers = self._handlers[hook_type]
        for i, (priority, order, h) in enumerate(handlers):
            if h == handler:
                handlers.pop(i)
                logger.debug(f"Unregistered {handler.__name__} from {hook_type.value}")
                return True
        return False
    
    def trigger(self, hook_type: HookType, event: HookEvent) -> Dict[str, Any]:
        """
        Trigger a hook, calling all registered handlers.
        
        Args:
            hook_type: Type of hook to trigger
            event: Event data to pass to handlers
            
        Returns:
            Dict with results from all handlers and any modified data
        """
        if not self._enabled:
            return {"success": True, "original_data": event.data}
        
        results = []
        current_data = event.data.copy()
        
        handlers = self._handlers.get(hook_type, [])
        for priority, order, handler in handlers:
            try:
                # Update event with current data
                event.data = current_data
                
                result = handler(event)
                results.append({
                    "handler": handler.__name__,
                    "success": result.success,
                    "error": result.error
                })
                
                # Apply modified data if provided
                if result.modified_data:
                    current_data.update(result.modified_data)
                
                # Stop processing if requested
                if result.stop_processing:
                    logger.debug(f"Hook {handler.__name__} stopped processing for {hook_type.value}")
                    break
                    
            except Exception as e:
                logger.error(f"Hook handler {handler.__name__} failed: {e}")
                results.append({
                    "handler": handler.__name__,
                    "success": False,
                    "error": str(e)
                })
        
        return {
            "success": all(r["success"] for r in results),
            "results": results,
            "final_data": current_data
        }
    
    def disable(self):
        """Disable all hooks."""
        self._enabled = False
        logger.info("Hooks disabled")
    
    def enable(self):
        """Enable hooks."""
        self._enabled = True
        logger.info("Hooks enabled")
    
    def list_handlers(self, hook_type: Optional[HookType] = None) -> Dict[str, List[str]]:
        """List all registered handlers."""
        if hook_type:
            return {
                hook_type.value: [
                    h[2].__name__ for h in self._handlers[hook_type]
                ]
            }
        
        return {
            hook_type.value: [h[2].__name__ for h in handlers]
            for hook_type, handlers in self._handlers.items()
            if handlers
        }


# Global hook manager instance
_global_hook_manager: Optional[HookManager] = None


def get_hook_manager() -> HookManager:
    """Get or create the global hook manager."""
    global _global_hook_manager
    if _global_hook_manager is None:
        _global_hook_manager = HookManager()
    return _global_hook_manager


# Convenience decorators for common hook types

def on_message_received(func: HookHandler) -> HookHandler:
    """Decorator to register a handler for MESSAGE_RECEIVED hooks."""
    get_hook_manager().register(HookType.MESSAGE_RECEIVED, func)
    return func

def on_message_preprocess(func: HookHandler) -> HookHandler:
    """Decorator to register a handler for MESSAGE_PREPROCESS hooks."""
    get_hook_manager().register(HookType.MESSAGE_PREPROCESS, func)
    return func

def on_message_processed(func: HookHandler) -> HookHandler:
    """Decorator to register a handler for MESSAGE_PROCESSED hooks."""
    get_hook_manager().register(HookType.MESSAGE_PROCESSED, func)
    return func

def on_command_pre(func: HookHandler) -> HookHandler:
    """Decorator to register a handler for COMMAND_PRE hooks."""
    get_hook_manager().register(HookType.COMMAND_PRE, func)
    return func

def on_command_post(func: HookHandler) -> HookHandler:
    """Decorator to register a handler for COMMAND_POST hooks."""
    get_hook_manager().register(HookType.COMMAND_POST, func)
    return func

def on_tool_pre(func: HookHandler) -> HookHandler:
    """Decorator to register a handler for TOOL_PRE hooks."""
    get_hook_manager().register(HookType.TOOL_PRE, func)
    return func

def on_tool_post(func: HookHandler) -> HookHandler:
    """Decorator to register a handler for TOOL_POST hooks."""
    get_hook_manager().register(HookType.TOOL_POST, func)
    return func
