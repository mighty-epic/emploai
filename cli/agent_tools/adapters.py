"""Adapters to convert canonical tools to provider-specific formats."""

from copy import deepcopy
from typing import List, Dict, Any, Iterable, Optional, Tuple
from .definitions import CLI_AGENT_TOOLS

OPENAI_COMPATIBLE_PROVIDERS = {"openai", "xai", "deepseek", "openrouter", "nvidia"}
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


def _is_provider_only_native_tool(tool: Dict[str, Any]) -> bool:
    tool_type = str(tool.get("type") or "")
    return tool_type.startswith("text_editor_")


def _extract_tool_parts(tool: Dict[str, Any]) -> Optional[Tuple[str, str, Dict[str, Any]]]:
    """Return name, description, schema from canonical/OpenAI/Anthropic tool shapes."""
    if not isinstance(tool, dict) or _is_provider_only_native_tool(tool):
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


def canonical_tool_names(tools: Iterable[Dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for tool in tools or []:
        parts = _extract_tool_parts(tool)
        if not parts:
            continue
        name, _description, _parameters = parts
        if name:
            names.add(name)
    return names


def validate_provider_tool_names(
    provider_tools: Iterable[Any],
    *,
    allowed_names: Iterable[str],
) -> Optional[str]:
    allowed = {str(name).strip() for name in allowed_names or [] if str(name).strip()}
    if not allowed:
        return None

    provided = [name for name in get_tool_names(list(provider_tools or [])) if name]
    invalid = sorted({name for name in provided if name not in allowed})
    if not invalid:
        return None

    return (
        "Provider tool inventory exposed unsupported tool names: "
        + ", ".join(invalid)
        + ". Allowed canonical tool names: "
        + ", ".join(sorted(allowed))
    )


def _sanitize_google_schema(value: Any) -> Any:
    """Trim JSON Schema down to fields accepted by Gemini SDK tool declarations."""
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
    Used by: OpenAI, xAI, DeepSeek, OpenRouter, NVIDIA.
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

def to_anthropic_format(
    tools: List[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Convert tools to Anthropic tool use format.
    Handles both:
    - Canonical format: {"name": ..., "description": ..., "parameters": ...}
    - OpenAI format: {"type": "function", "function": {"name": ..., ...}}
    Used by: Anthropic (Claude).
    
    Anthropic receives the same canonical callable tool names as the rest of the app.
    Provider-specific transport formatting must not change the model-visible capability set.
    """
    if tools is None:
        tools = CLI_AGENT_TOOLS
    
    anthropic_tools = []

    for tool in tools:
        if _is_provider_only_native_tool(tool):
            continue

        parts = _extract_tool_parts(tool)
        if not parts:
            continue
        name, description, parameters = parts

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
        
        if name:
            functions.append(
                {
                    "name": name,
                    "description": description,
                    "parameters": google_params if google_params else None,
                }
            )
    if not functions:
        return []

    try:
        from google.genai import types as genai_types

        return [genai_types.Tool(function_declarations=functions)]
    except ImportError:
        pass

    try:
        import google.generativeai as genai
    except ImportError:
        return []

    legacy_functions = [
        genai.types.FunctionDeclaration(
            name=function["name"],
            description=function["description"],
            parameters=function["parameters"],
        )
        for function in functions
    ]
    return [genai.types.Tool(function_declarations=legacy_functions)]

def get_tools_for_provider(provider: str, base_tools: List[Dict[str, Any]] = None) -> List[Any]:
    """Get tools in the correct format for the given provider."""
    # Canonicalize provider name
    provider = normalize_provider(provider)
    source_tools = CLI_AGENT_TOOLS if base_tools is None else base_tools

    if provider == "anthropic":
        return to_anthropic_format(source_tools)
    if provider == "google":
        return to_google_format(source_tools)
    # All others use OpenAI format or compatible
    return to_openai_format(source_tools)


def build_tools_for_provider(
    provider: str,
    extra_tools: List[Dict[str, Any]] = None,
    *,
    base_tools: List[Dict[str, Any]] = None,
) -> List[Any]:
    """Build the full provider-specific tool list without cross-provider leakage."""
    provider = normalize_provider(provider)
    provider_base_tools = get_tools_for_provider(provider, base_tools=base_tools)

    if not extra_tools:
        return provider_base_tools

    if provider == "anthropic":
        skip_names = _provider_tool_names(provider_base_tools)
        converted_extra = to_anthropic_format(_dedupe_tools(extra_tools, skip_names=skip_names))
        return provider_base_tools + converted_extra

    if provider == "google":
        base_source_tools = CLI_AGENT_TOOLS if base_tools is None else base_tools
        base_names = set(_tool_name(tool) for tool in base_source_tools)
        converted_extra = to_google_format(_dedupe_tools(extra_tools, skip_names=base_names))
        return provider_base_tools + converted_extra

    skip_names = _openai_tool_names(provider_base_tools)
    converted_extra = to_openai_format(_dedupe_tools(extra_tools, skip_names=skip_names))
    return provider_base_tools + converted_extra


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
            for decl in declarations:
                if isinstance(decl, dict):
                    name = str(decl.get("name", "") or "")
                else:
                    name = str(getattr(decl, "name", "") or "")
                if name:
                    names.append(name)
            continue

        proto = getattr(tool, "_proto", None)
        function_declarations = getattr(proto, "function_declarations", None)
        if function_declarations:
            names.extend(str(getattr(decl, "name", "")) for decl in function_declarations if getattr(decl, "name", ""))
    return names
