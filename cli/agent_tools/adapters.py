"""Adapters to convert canonical tools to provider-specific formats."""

from copy import deepcopy
from typing import List, Dict, Any, Iterable, Optional, Tuple
from .definitions import CLI_AGENT_TOOLS

OPENAI_COMPATIBLE_PROVIDERS = {"openai", "xai", "deepseek", "openrouter"}
ANTHROPIC_NATIVE_TOOL_NAMES = {"str_replace_based_edit_tool"}
TEXT_EDITOR_REPLACES = {"write_file", "edit_file", "read_file"}
GOOGLE_UNSUPPORTED_SCHEMA_KEYS = {
    "additionalProperties",
    "default",
    "examples",
    "exclusiveMaximum",
    "exclusiveMinimum",
    "maximum",
    "minimum",
    "multipleOf",
    "pattern",
    "title",
}


def normalize_provider(provider: Optional[str]) -> str:
    """Normalize provider names to the small set used by the tool adapters."""
    normalized = (provider or "openai").strip().lower()
    if normalized in {"anthropic", "google"}:
        return normalized
    if normalized in OPENAI_COMPATIBLE_PROVIDERS:
        return normalized
    return "openai"


def _tool_name(tool: Dict[str, Any]) -> str:
    if not isinstance(tool, dict):
        return ""
    if "function" in tool and isinstance(tool["function"], dict):
        return str(tool["function"].get("name") or "")
    return str(tool.get("name") or "")


def _is_anthropic_native_tool(tool: Dict[str, Any]) -> bool:
    tool_type = str(tool.get("type") or "")
    return tool_type.startswith("text_editor_") or _tool_name(tool) in ANTHROPIC_NATIVE_TOOL_NAMES


def _extract_tool_parts(tool: Dict[str, Any]) -> Optional[Tuple[str, str, Dict[str, Any]]]:
    """Return name, description, schema from canonical/OpenAI/Anthropic tool shapes."""
    if not isinstance(tool, dict) or _is_anthropic_native_tool(tool):
        return None

    if "function" in tool and isinstance(tool["function"], dict):
        source = tool["function"]
        parameters = source.get("parameters") or {"type": "object", "properties": {}}
    else:
        source = tool
        parameters = (
            source.get("parameters")
            or source.get("input_schema")
            or {"type": "object", "properties": {}}
        )

    name = str(source.get("name") or "")
    if not name:
        return None
    description = str(source.get("description") or "")
    return name, description, deepcopy(parameters)


def _dedupe_tools(tools: Iterable[Dict[str, Any]], *, skip_names: Optional[set[str]] = None) -> List[Dict[str, Any]]:
    seen = set(skip_names or set())
    deduped = []
    for tool in tools or []:
        name = _tool_name(tool)
        if not name or name in seen:
            continue
        seen.add(name)
        deduped.append(tool)
    return deduped


def _openai_tool_names(tools: List[Dict[str, Any]]) -> set[str]:
    return {
        tool["function"]["name"]
        for tool in tools
        if isinstance(tool, dict)
        and isinstance(tool.get("function"), dict)
        and tool["function"].get("name")
    }


def _provider_tool_names(tools: List[Any]) -> set[str]:
    names = set()
    for tool in tools or []:
        if isinstance(tool, dict):
            name = _tool_name(tool)
            if name:
                names.add(name)
    return names


def _sanitize_google_schema(value: Any) -> Any:
    """Trim JSON Schema down to fields accepted by google-generativeai."""
    if isinstance(value, list):
        return [_sanitize_google_schema(item) for item in value]
    if not isinstance(value, dict):
        return value

    sanitized = {}
    for key, raw in value.items():
        if key in GOOGLE_UNSUPPORTED_SCHEMA_KEYS:
            continue
        if key == "additional_properties":
            continue
        sanitized[key] = _sanitize_google_schema(raw)
    return sanitized


def to_openai_format(tools: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Convert canonical tools to OpenAI function calling format.
    Used by: OpenAI, xAI, DeepSeek, OpenRouter.
    """
    if tools is None:
        tools = CLI_AGENT_TOOLS
        
    openai_tools = []
    for tool in tools:
        parts = _extract_tool_parts(tool)
        if not parts:
            continue
        name, description, parameters = parts
        openai_tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters
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
    
    anthropic_tools = []
    
    # Add Claude's native text_editor tool ONLY for default CLI tools
    if is_default:
        anthropic_tools.append({
            "type": "text_editor_20250728",
            "name": "str_replace_based_edit_tool"
        })
    
    for tool in tools:
        if _is_anthropic_native_tool(tool):
            continue

        parts = _extract_tool_parts(tool)
        if not parts:
            continue
        name, description, parameters = parts
        
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
        parts = _extract_tool_parts(tool)
        if not parts:
            continue
        name, description, parameters = parts
        
        # Google's FunctionDeclaration doesn't accept "type" at top level
        # Convert OpenAI JSON Schema format to Google's expected format
        google_params = {}
        if "properties" in parameters:
            google_params["properties"] = _sanitize_google_schema(parameters["properties"])
        if "required" in parameters:
            google_params["required"] = _sanitize_google_schema(parameters["required"])
        
        # Only add if we have a valid function name
        if name:
            functions.append(genai.types.FunctionDeclaration(
                name=name,
                description=description,
                parameters=google_params if google_params else None
            ))
    return [genai.types.Tool(function_declarations=functions)] if functions else []

def get_tools_for_provider(provider: str) -> List[Any]:
    """Get tools in the correct format for the given provider."""
    # Canonicalize provider name
    provider = normalize_provider(provider)
    
    if provider == "anthropic":
        return to_anthropic_format()
    if provider == "google":
        return to_google_format()
    # All others use OpenAI format or compatible
    return to_openai_format()


def build_tools_for_provider(provider: str, extra_tools: List[Dict[str, Any]] = None) -> List[Any]:
    """Build the full provider-specific tool list without cross-provider leakage."""
    provider = normalize_provider(provider)
    base_tools = get_tools_for_provider(provider)

    if not extra_tools:
        return base_tools

    if provider == "anthropic":
        skip_names = _provider_tool_names(base_tools) | TEXT_EDITOR_REPLACES
        converted_extra = to_anthropic_format(_dedupe_tools(extra_tools, skip_names=skip_names))
        return base_tools + converted_extra

    if provider == "google":
        base_names = set(_tool_name(tool) for tool in CLI_AGENT_TOOLS)
        converted_extra = to_google_format(_dedupe_tools(extra_tools, skip_names=base_names))
        return base_tools + converted_extra

    skip_names = _openai_tool_names(base_tools)
    converted_extra = to_openai_format(_dedupe_tools(extra_tools, skip_names=skip_names))
    return base_tools + converted_extra


def get_tool_names(tools: List[Any]) -> List[str]:
    """Best-effort name extraction for tests and diagnostics."""
    names = []
    for tool in tools or []:
        if isinstance(tool, dict):
            name = _tool_name(tool)
            if name:
                names.append(name)
            continue

        declarations = getattr(tool, "function_declarations", None)
        if declarations:
            names.extend(str(getattr(decl, "name", "")) for decl in declarations if getattr(decl, "name", ""))
            continue

        proto = getattr(tool, "_proto", None)
        function_declarations = getattr(proto, "function_declarations", None)
        if function_declarations:
            names.extend(str(getattr(decl, "name", "")) for decl in function_declarations if getattr(decl, "name", ""))
    return names
