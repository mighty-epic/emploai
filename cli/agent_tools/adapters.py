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
    Convert tools to Anthropic tool use format.
    Handles both:
    - Canonical format: {"name": ..., "description": ..., "parameters": ...}
    - OpenAI format: {"type": "function", "function": {"name": ..., ...}}
    Used by: Anthropic (Claude).
    
    When using default CLI tools, replaces custom write_file/edit_file/read_file
    with Claude's native text_editor_20250728 tool for reliable file operations.
    """
    is_default = tools is None
    if tools is None:
        tools = CLI_AGENT_TOOLS
    
    # Tools that Claude's native text_editor replaces
    TEXT_EDITOR_REPLACES = {"write_file", "edit_file", "read_file"}
        
    anthropic_tools = []
    
    # Add Claude's native text_editor tool ONLY for default CLI tools
    if is_default:
        anthropic_tools.append({
            "type": "text_editor_20250728",
            "name": "str_replace_based_edit_tool"
        })
    
    for tool in tools:
        # Check if it's OpenAI format (has "function" key)
        if "function" in tool:
            func = tool["function"]
            name = func.get("name", "")
            description = func.get("description", "")
            parameters = func.get("parameters", {"type": "object", "properties": {}})
        else:
            # Canonical format
            name = tool.get("name", "")
            description = tool.get("description", "")
            parameters = tool.get("parameters", {"type": "object", "properties": {}})
        
        # Skip tools replaced by native text_editor when using default CLI tools
        if is_default and name in TEXT_EDITOR_REPLACES:
            continue
        
        anthropic_tools.append({
            "name": name,
            "description": description,
            "input_schema": parameters
        })
    return anthropic_tools

def to_google_format(tools: List[Dict[str, Any]] = None) -> List[Any]:
    """
    Convert tools to Google Gemini tool format.
    Handles both:
    - Canonical format: {"name": ..., "description": ..., "parameters": ...}
    - OpenAI format: {"type": "function", "function": {"name": ..., ...}}
    
    Note: Google's FunctionDeclaration doesn't accept "type" at the top level
    of parameters, so we strip it.
    """
    if tools is None:
        tools = CLI_AGENT_TOOLS
        
    try:
        import google.generativeai as genai
    except ImportError:
        return []

    functions = []
    for tool in tools:
        # Check if it's OpenAI format (has "function" key)
        if "function" in tool:
            func = tool["function"]
            name = func.get("name", "")
            description = func.get("description", "")
            parameters = func.get("parameters", {})
        else:
            # Canonical format
            name = tool.get("name", "")
            description = tool.get("description", "")
            parameters = tool.get("parameters", {})
        
        # Google's FunctionDeclaration doesn't accept "type" at top level
        # Convert OpenAI JSON Schema format to Google's expected format
        google_params = {}
        if "properties" in parameters:
            google_params["properties"] = parameters["properties"]
        if "required" in parameters:
            google_params["required"] = parameters["required"]
        
        # Only add if we have a valid function name
        if name:
            functions.append(genai.types.FunctionDeclaration(
                name=name,
                description=description,
                parameters=google_params if google_params else None
            ))
    return [genai.types.Tool(function_declarations=functions)] if functions else []

def get_tools_for_provider(provider: str) -> List[Dict[str, Any]]:
    """Get tools in the correct format for the given provider."""
    # Canonicalize provider name
    provider = provider.lower()
    
    if provider == "anthropic":
        return to_anthropic_format()
    if provider == "google":
        return to_google_format()
    # All others use OpenAI format or compatible
    return to_openai_format()
