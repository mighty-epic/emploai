from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from cli.tui_constants import MODEL_CONFIGS


def resolve_openai_api_type(
    model_name: Optional[str] = None,
    *,
    model_id: Optional[str] = None,
    explicit_api_type: Optional[str] = None,
) -> str:
    if explicit_api_type:
        return str(explicit_api_type).strip() or "chat"

    if model_name:
        config = MODEL_CONFIGS.get(str(model_name).strip(), {})
        api_type = str(config.get("api", "") or "").strip()
        if api_type:
            return api_type

    if model_id:
        normalized_model_id = str(model_id).strip()
        for config in MODEL_CONFIGS.values():
            if str(config.get("id", "")).strip() == normalized_model_id:
                api_type = str(config.get("api", "") or "").strip()
                if api_type:
                    return api_type

    return "chat"


def _responses_tool_shape(tools: Optional[Sequence[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
            function = tool["function"]
            normalized.append(
                {
                    "type": "function",
                    "name": function.get("name"),
                    "description": function.get("description"),
                    "parameters": function.get("parameters"),
                }
            )
        else:
            normalized.append(tool)
    return normalized


def _responses_input_from_messages(messages: Sequence[Dict[str, Any]]) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    instructions_parts: List[str] = []
    input_items: List[Dict[str, Any]] = []

    for message in messages:
        role = str(message.get("role") or "")
        content = message.get("content")

        if role == "system":
            if content:
                instructions_parts.append(str(content))
            continue

        if role == "tool":
            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": message.get("tool_call_id"),
                    "output": str(content or ""),
                }
            )
            continue

        tool_calls = list(message.get("tool_calls") or [])
        if role == "assistant" and tool_calls:
            if content:
                input_items.append({"role": "assistant", "content": str(content)})
            for tool_call in tool_calls:
                function = tool_call.get("function") or {}
                input_items.append(
                    {
                        "type": "function_call",
                        "call_id": tool_call.get("id"),
                        "name": function.get("name"),
                        "arguments": function.get("arguments") or "",
                    }
                )
            continue

        if role in {"user", "assistant"}:
            input_items.append({"role": role, "content": str(content or "")})

    instructions = "\n\n".join(part for part in instructions_parts if part) or None
    return instructions, input_items


def _responses_to_chat_completion_like(response: Any) -> Any:
    tool_calls: List[Any] = []
    for item in list(getattr(response, "output", []) or []):
        if getattr(item, "type", "") != "function_call":
            continue
        tool_calls.append(
            SimpleNamespace(
                id=getattr(item, "call_id", None) or getattr(item, "id", None),
                function=SimpleNamespace(
                    name=getattr(item, "name", "") or "",
                    arguments=getattr(item, "arguments", "") or "",
                ),
            )
        )

    message = SimpleNamespace(
        content=getattr(response, "output_text", None) or None,
        tool_calls=tool_calls or None,
    )
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice], _responses_raw=response)


def create_openai_completion(
    client: Any,
    *,
    model_name: Optional[str] = None,
    model_id: str,
    messages: Sequence[Dict[str, Any]],
    tools: Optional[Sequence[Dict[str, Any]]] = None,
    tool_choice: Optional[str] = None,
    max_tokens: Optional[int] = None,
    explicit_api_type: Optional[str] = None,
) -> Any:
    api_type = resolve_openai_api_type(
        model_name,
        model_id=model_id,
        explicit_api_type=explicit_api_type,
    )

    if api_type == "responses":
        instructions, response_input = _responses_input_from_messages(messages)
        kwargs: Dict[str, Any] = {
            "model": model_id,
            "input": response_input,
        }

        response_tools = _responses_tool_shape(tools)
        if response_tools:
            kwargs["tools"] = response_tools
            kwargs["tool_choice"] = tool_choice or "auto"
        if instructions:
            kwargs["instructions"] = instructions
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens

        response = client.responses.create(**kwargs)
        return _responses_to_chat_completion_like(response)

    kwargs = {
        "model": model_id,
        "messages": list(messages),
    }
    if tools:
        kwargs["tools"] = list(tools)
        kwargs["tool_choice"] = tool_choice or "auto"
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return client.chat.completions.create(**kwargs)
