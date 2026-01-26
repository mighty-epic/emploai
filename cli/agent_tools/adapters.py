"""Adapters to convert canonical tools to provider-specific formats."""

from typing import List, Dict, Any
from .definitions import CLI_AGENT_TOOLS

def to_openai_format(tools: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Convert canonical tools to OpenAI function calling format.
    Used by: OpenAI, xAI, Gemini, DeepSeek, OpenRouter.
    """
    if tools is None:
        tools = CLI_AGENT_TOOLS
        
    openai_tools = []
    for tool in tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"]
            }
        })
    return openai_tools

def to_anthropic_format(tools: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Convert canonical tools to Anthropic tool use format.
    Used by: Anthropic (Claude).
    """
    if tools is None:
        tools = CLI_AGENT_TOOLS
        
    anthropic_tools = []
    for tool in tools:
        anthropic_tools.append({
            "name": tool["name"],
            "description": tool["description"],
            "input_schema": tool["parameters"]
        })
    return anthropic_tools

def get_tools_for_provider(provider: str) -> List[Dict[str, Any]]:
    """Get tools in the correct format for the given provider."""
    # Canonicalize provider name
    provider = provider.lower()
    
    if provider == "anthropic":
        return to_anthropic_format()
    # All others use OpenAI format or compatible
    return to_openai_format()
