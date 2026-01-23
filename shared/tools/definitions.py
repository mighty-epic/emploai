"""
TOOL DEFINITIONS
Defines all tools available to the LLM agents.

These are the function schemas that get passed to the LLM for tool calling.
"""

from typing import Dict, List, Any, Optional
from enum import Enum


# ============================================================================
# OBSERVATION TOOLS - Used to perceive the environment
# ============================================================================

OBSERVATION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_screen_state",
            "description": "Get the current screen state including all visible UI elements, focused element, and window info. Use this before deciding on any action.",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_screenshot": {
                        "type": "boolean",
                        "description": "Whether to include a screenshot path in the response"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_element",
            "description": "Find a specific UI element by text, role, or other attributes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text content to search for"
                    },
                    "role": {
                        "type": "string",
                        "description": "Element role (button, textbox, link, etc.)"
                    },
                    "label": {
                        "type": "string",
                        "description": "Accessible label to search for"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_focused_element",
            "description": "Get information about the currently focused UI element.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "capture_screenshot",
            "description": "Capture a screenshot of the current screen state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {
                        "type": "object",
                        "description": "Optional region to capture (x, y, width, height)"
                    }
                },
                "required": []
            }
        }
    },
]


# ============================================================================
# ACTION TOOLS - Used to interact with the environment
# ============================================================================

ACTION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "click_element",
            "description": "Click on a UI element. Use element_id from observation, or provide text/role to find it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_id": {
                        "type": "string",
                        "description": "The element ID from observation"
                    },
                    "text": {
                        "type": "string",
                        "description": "Text of element to click (if element_id not known)"
                    },
                    "role": {
                        "type": "string",
                        "description": "Role of element to click (button, link, etc.)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text into the currently focused element or a specified element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to type"
                    },
                    "element_id": {
                        "type": "string",
                        "description": "Optional element to focus before typing"
                    },
                    "clear_first": {
                        "type": "boolean",
                        "description": "Whether to clear existing text first"
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Press a keyboard key or key combination.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Key to press (enter, tab, escape, etc.)"
                    },
                    "modifiers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Modifier keys (ctrl, alt, shift)"
                    }
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scroll",
            "description": "Scroll the current view.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down", "left", "right"],
                        "description": "Scroll direction"
                    },
                    "amount": {
                        "type": "integer",
                        "description": "Scroll amount (1-10)"
                    }
                },
                "required": ["direction"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "navigate",
            "description": "Navigate to a URL (browser only).",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to navigate to"
                    }
                },
                "required": ["url"]
            }
        }
    },
]


# ============================================================================
# SYSTEM TOOLS - Used for control flow and verification
# ============================================================================

SYSTEM_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "wait",
            "description": "Wait for a specified duration or condition.",
            "parameters": {
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "number",
                        "description": "Seconds to wait"
                    },
                    "for_element": {
                        "type": "string",
                        "description": "Wait until this element appears"
                    },
                    "for_url_contains": {
                        "type": "string",
                        "description": "Wait until URL contains this string"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "verify_state",
            "description": "Verify that the current state matches expectations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "element_exists": {
                        "type": "string",
                        "description": "Verify this element exists"
                    },
                    "url_contains": {
                        "type": "string",
                        "description": "Verify URL contains this string"
                    },
                    "text_visible": {
                        "type": "string",
                        "description": "Verify this text is visible"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "report_completion",
            "description": "Report that the current step or task is complete.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["success", "failure", "blocked"],
                        "description": "Completion status"
                    },
                    "message": {
                        "type": "string",
                        "description": "Completion message or error details"
                    }
                },
                "required": ["status"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "request_human_help",
            "description": "Request human intervention for something the agent cannot handle.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Why human help is needed"
                    },
                    "context": {
                        "type": "string",
                        "description": "Current context/state"
                    }
                },
                "required": ["reason"]
            }
        }
    },
]


# ============================================================================
# ORCHESTRATOR-ONLY TOOLS - Used by high-level planner
# ============================================================================

ORCHESTRATOR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "decompose_task",
            "description": "Break down a complex task into atomic steps.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "The task to decompose"
                    },
                    "context": {
                        "type": "string",
                        "description": "Current screen/application context"
                    }
                },
                "required": ["task"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "issue_micro_step",
            "description": "Issue a single atomic step to micro-agents for execution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "step_description": {
                        "type": "string",
                        "description": "Description of the atomic step"
                    },
                    "target_element": {
                        "type": "string",
                        "description": "Target element if known"
                    },
                    "expected_outcome": {
                        "type": "string",
                        "description": "What should happen after this step"
                    }
                },
                "required": ["step_description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "adapt_plan",
            "description": "Modify the current plan based on unexpected state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Why adaptation is needed"
                    },
                    "new_steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New steps to add to the plan"
                    },
                    "remove_steps": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Indices of steps to remove"
                    }
                },
                "required": ["reason"]
            }
        }
    },
]


# ============================================================================
# TOOL COLLECTIONS
# ============================================================================

ALL_TOOLS = OBSERVATION_TOOLS + ACTION_TOOLS + SYSTEM_TOOLS

MICRO_AGENT_TOOLS = OBSERVATION_TOOLS + ACTION_TOOLS + [
    t for t in SYSTEM_TOOLS if t["function"]["name"] in ["wait", "report_completion"]
]

ORCHESTRATOR_ALL_TOOLS = OBSERVATION_TOOLS + SYSTEM_TOOLS + ORCHESTRATOR_TOOLS


def get_tool_names(tools: List[Dict]) -> List[str]:
    """Get list of tool names from tool definitions."""
    return [t["function"]["name"] for t in tools]
