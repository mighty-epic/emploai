"""Unified tool-calling loop for multiple LLM providers."""

import base64
import io
import json
import time
from dataclasses import dataclass
from typing import List, Dict, Any, Callable, Optional, Tuple
from cli.tui_constants import ChatMessage, SYSTEM_PROMPT, RESPONSE_MAX_TOKENS
from .adapters import (
    build_tools_for_provider,
    canonical_tool_names,
    get_tool_names,
    normalize_provider,
    validate_provider_tool_names,
)
from .definitions import CLI_AGENT_TOOLS, TOOL_RUN_COMMAND
from .final_quality_guard import (
    FinalQualityVerdict,
    final_quality_guard_enabled,
    final_quality_guard_mode,
    judge_final_quality_with_nli,
    max_auto_continues,
)
from cli.agent_tools.gemini_client import is_openai_compatible_client
from shared.provider_errors import (
    PROVIDER_INPUT_REJECTED,
    PROVIDER_SAFETY_REJECTION,
    normalize_provider_error,
    provider_blocker_message,
)
from shared.security_policy import redact_json, redact_text

# Try to import verbose tool logger (only available in telegram_bot context)
VERBOSE_LOGGING = False
try:
    from telegram_bot.tool_logger import log_tool_call, log_tool_result, log_conversation_turn, log_model_response
    VERBOSE_LOGGING = True
except ImportError:
    try:
        # Alternative import path when running from telegram_bot directory
        from tool_logger import log_tool_call, log_tool_result, log_conversation_turn, log_model_response
        VERBOSE_LOGGING = True
    except ImportError:
        pass

@dataclass
class LoopResult:
    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


def _extract_image_payload(result: Any) -> Optional[str]:
    if not isinstance(result, dict):
        return None
    for key in ("image_base64", "base64", "image_data", "data", "screenshot"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _vision_question_for_result(tool_name: str, args: Dict[str, Any], result: Any) -> str:
    if isinstance(result, dict):
        explicit = str(result.get("question") or "").strip()
        if explicit:
            return explicit
    explicit_arg = str((args or {}).get("question") or "").strip()
    if explicit_arg:
        return explicit_arg

    if tool_name == "describe_screen":
        return (
            "Describe the current visible desktop state, the main active window or dialog, "
            "any error or confirmation message, and the controls or content most relevant to the current task."
        )
    if tool_name == "browser_screenshot":
        return (
            "Describe the visible browser page state, major heading or content, any dialogs, login prompts, or errors, "
            "and whether the intended page, file, or result appears visibly open and ready."
        )
    return "Describe the visible state relevant to the current task."


def _vision_sidecar_prompt(tool_name: str, question: str) -> str:
    surface = "browser page" if tool_name == "browser_screenshot" else "desktop screen"
    return (
        "You are a vision sidecar for an autonomous agent. "
        f"Look only at the provided {surface} image and answer the question precisely. "
        "Do not guess hidden state, unreadable text, or off-screen content. "
        "If you are uncertain, say what is uncertain. "
        "Mention visible errors, dialogs, active window/page state, and whether the intended target appears visible when relevant. "
        "Keep the answer concise and concrete.\n\n"
        f"Question: {question}"
    )


def _extract_anthropic_text(response: Any) -> str:
    parts: List[str] = []
    for block in list(getattr(response, "content", []) or []):
        block_type = getattr(block, "type", "")
        text = getattr(block, "text", None)
        if block_type == "text" and text:
            parts.append(str(text))
    return "\n".join(part for part in parts if part).strip()


def _extract_openai_response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return str(text).strip()

    output = list(getattr(response, "output", []) or [])
    parts: List[str] = []
    for item in output:
        for content_item in list(getattr(item, "content", []) or []):
            if getattr(content_item, "type", "") in {"output_text", "text"} and getattr(content_item, "text", None):
                parts.append(str(content_item.text))
    return "\n".join(part for part in parts if part).strip()


def _analyze_image_sidecar(
    *,
    provider: str,
    model_id: str,
    client: Any,
    api_type: str,
    tool_name: str,
    image_data: str,
    question: str,
    log: Callable[..., None],
) -> str:
    prompt = _vision_sidecar_prompt(tool_name, question)
    try:
        if provider == "anthropic":
            response = client.messages.create(
                model=model_id,
                max_tokens=300,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_data,
                                },
                            },
                        ],
                    }
                ],
            )
            text = _extract_anthropic_text(response)
            if text:
                return text
        elif provider == "google":
            if is_openai_compatible_client(client):
                response = client.chat.completions.create(
                    model=model_id,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
                            ],
                        }
                    ],
                    max_tokens=300,
                )
                choice = response.choices[0].message if getattr(response, "choices", None) else None
                text = str(getattr(choice, "content", "") or "").strip()
                if text:
                    return text
                return "Vision analysis unavailable for this image."
            from PIL import Image

            image = Image.open(io.BytesIO(base64.b64decode(image_data)))
            model = client.GenerativeModel(model_name=model_id)
            response = model.generate_content([prompt, image])
            text = str(getattr(response, "text", "") or "").strip()
            if text:
                return text
        else:
            if api_type == "responses" and hasattr(client, "responses"):
                response = client.responses.create(
                    model=model_id,
                    input=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": prompt},
                                {"type": "input_image", "image_url": f"data:image/png;base64,{image_data}"},
                            ],
                        }
                    ],
                    max_output_tokens=300,
                )
                text = _extract_openai_response_text(response)
                if text:
                    return text
            if hasattr(client, "chat") and hasattr(client.chat, "completions"):
                response = client.chat.completions.create(
                    model=model_id,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
                            ],
                        }
                    ],
                    max_tokens=300,
                )
                choice = response.choices[0].message if getattr(response, "choices", None) else None
                text = str(getattr(choice, "content", "") or "").strip()
                if text:
                    return text
    except Exception as exc:
        info = normalize_provider_error(exc, payload_kind="image")
        log(f"  ↪ Vision sidecar failed for {tool_name}: {info.error_type}")
        if info.error_type in {PROVIDER_SAFETY_REJECTION, PROVIDER_INPUT_REJECTED}:
            return (
                "Vision analysis was rejected by the provider. "
                "The screenshot/image was not sent back into model context; use OCR, DOM text, "
                "or another non-image observation route if more verification is needed."
            )

    return (
        "Vision analysis unavailable for this image. "
        "Use the screenshot as proof/artifact only and rely on other observation tools if you still need more certainty."
    )


def _responses_tool_shape(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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


def _responses_input_from_messages(messages: List[Dict[str, Any]]) -> tuple[str, List[Dict[str, Any]]]:
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

    return "\n\n".join(part for part in instructions_parts if part), input_items


def _joined_system_text(system_parts: List[str]) -> Optional[str]:
    joined = "\n\n".join(part for part in system_parts if str(part or "").strip()).strip()
    return joined or None


def _response_item_to_dict(item: Any) -> Any:
    if item is None:
        return None
    if isinstance(item, dict):
        return item
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    model_dump = getattr(item, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    return item


def _truncate_text(value: str, *, max_chars: int) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 32] + f"\n...[truncated {len(text) - max_chars + 32} chars]"


def _truncate_lines(value: str, *, max_lines: int, max_chars: int) -> str:
    text = str(value or "")
    lines = text.splitlines()
    trimmed_lines = lines[:max_lines]
    trimmed = "\n".join(trimmed_lines)
    if len(lines) > max_lines:
        trimmed += f"\n...[truncated {len(lines) - max_lines} lines]"
    return _truncate_text(trimmed, max_chars=max_chars)


def _summarize_tool_result_for_model(tool_name: str, result: Any) -> str:
    if isinstance(result, dict):
        safe = redact_json(dict(result))
        for key in ("image_base64", "base64", "image_data", "data"):
            if key in safe and isinstance(safe[key], str) and len(safe[key]) > 500:
                safe[key] = f"[IMAGE_DATA elided: {len(safe[key])} chars]"

        if tool_name == "describe_screen":
            summary = {
                "image_captured": bool(safe.get("image_captured")),
                "description": _truncate_text(str(safe.get("description") or ""), max_chars=600),
                "metadata": safe.get("metadata"),
            }
            if safe.get("question"):
                summary["question"] = _truncate_text(str(safe.get("question") or ""), max_chars=240)
            if safe.get("vision_question"):
                summary["vision_question"] = _truncate_text(str(safe.get("vision_question") or ""), max_chars=320)
            if safe.get("vision_summary"):
                summary["vision_summary"] = _truncate_text(str(safe.get("vision_summary") or ""), max_chars=1400)
            return json.dumps(summary, ensure_ascii=False)

        if tool_name == "browser_screenshot":
            summary = {
                "backend": safe.get("backend"),
                "mode": safe.get("mode"),
                "title": safe.get("title"),
                "url": safe.get("url"),
                "tab_id": safe.get("tab_id"),
                "window_id": safe.get("window_id"),
                "wait_reason": safe.get("wait_reason"),
                "note": "Screenshot stored as proof/artifact only. Pixel content is not injected back into the model; use browser_read_text for exact text.",
            }
            if safe.get("question"):
                summary["question"] = _truncate_text(str(safe.get("question") or ""), max_chars=240)
            if safe.get("vision_question"):
                summary["vision_question"] = _truncate_text(str(safe.get("vision_question") or ""), max_chars=320)
            if safe.get("vision_summary"):
                summary["vision_summary"] = _truncate_text(str(safe.get("vision_summary") or ""), max_chars=1400)
            return json.dumps(summary, ensure_ascii=False)

        if tool_name == "browser_read_text":
            summary = {
                "backend": safe.get("backend"),
                "mode": safe.get("mode"),
                "title": safe.get("title"),
                "url": safe.get("url"),
                "selector": safe.get("selector"),
                "truncated": bool(safe.get("truncated")),
                "text": _truncate_text(str(safe.get("text") or ""), max_chars=3500),
            }
            return json.dumps(summary, ensure_ascii=False)

        if tool_name in {"browser_snapshot", "observe_browser"} and isinstance(safe.get("formatted"), str):
            safe["formatted"] = _truncate_lines(safe["formatted"], max_lines=40, max_chars=3500)
            safe["semantics"] = "Interactive structure and refs only. Use browser_read_text for full visible page text or exact rendered values."
            return json.dumps(safe, ensure_ascii=False)

        return _truncate_text(json.dumps(safe, ensure_ascii=False, default=str), max_chars=5000)

    if isinstance(result, str):
        result = redact_text(result)
        if tool_name == "ocr_screen":
            return _truncate_lines(result, max_lines=60, max_chars=3500)
        if tool_name in {"browser_snapshot", "observe_browser"}:
            return _truncate_lines(result, max_lines=40, max_chars=3500)
        if tool_name == "observe_desktop":
            return _truncate_lines(result, max_lines=30, max_chars=2500)
        return _truncate_text(result, max_chars=4000)

    return _truncate_text(json.dumps(redact_json(result), ensure_ascii=False, default=str), max_chars=4000)


def _fallback_final_from_tool_trace(tool_trace: List[Dict[str, Any]]) -> str:
    if not tool_trace:
        return ""
    last = tool_trace[-1]
    tool_name = str(last.get("tool") or "tool").strip() or "tool"
    result = last.get("result")
    result_text = ""
    if isinstance(result, str):
        raw = result.strip()
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            for key in ("vision_summary", "description", "summary", "text", "message", "output", "error"):
                value = str(parsed.get(key) or "").strip()
                if value:
                    result_text = value
                    break
        if not result_text:
            result_text = raw
    elif isinstance(result, dict):
        for key in ("vision_summary", "description", "summary", "text", "message", "output", "error"):
            value = str(result.get(key) or "").strip()
            if value:
                result_text = value
                break
        if not result_text:
            result_text = json.dumps(result, ensure_ascii=False, default=str)
    else:
        result_text = str(result or "").strip()

    if result_text:
        if tool_name == "describe_screen":
            return f"I looked at the screen. {_truncate_text(result_text, max_chars=900)}"
        return f"I used `{tool_name}`. {_truncate_text(result_text, max_chars=900)}"
    return f"I used `{tool_name}`, but it did not return any displayable output."


_RUNTIME_EPHEMERAL_SYSTEM_PREFIXES = (
    "# MANAGED TASK BOARD RUNTIME",
    "# ACTIVE MANAGED TASK BOARD",
    "TASK BOARD BLOCKED WAITING USER:",
    "CURRENT TASK CONTRACT (fresh before this model turn):",
    "LIVE DESKTOP WINDOW SNAPSHOT (fresh before this model turn):",
    "CHAT ARTIFACT INDEX (current chat only):",
    "RELEVANT CHAT ARTIFACT EXCERPTS:",
)


def _max_auto_continues_for_request(user_request: str) -> int:
    base = max_auto_continues()
    text = str(user_request or "").lower()
    coding_markers = (
        "code",
        "coding",
        "script",
        "app",
        "application",
        "electron",
        "website",
        "web app",
        "server",
        "build",
        "compile",
        "run",
        "launch",
        "start",
        "install",
        "npm",
        "node",
        "package",
        "test",
        "debug",
        "implement",
        "fix",
    )
    if any(marker in text for marker in coding_markers):
        return max(base, 5)
    return base


def _is_continuation_request_text(text: str) -> bool:
    normalized = " ".join(
        str(text or "")
        .strip()
        .lower()
        .replace(".", " ")
        .replace("!", " ")
        .replace("?", " ")
        .split()
    )
    return normalized in {
        "continue",
        "keep going",
        "go on",
        "carry on",
        "resume",
        "proceed",
        "try again",
        "continue please",
        "keep going please",
    }


def _is_ephemeral_runtime_context(message: Dict[str, Any]) -> bool:
    if message.get("role") != "system":
        return False
    content = message.get("content")
    if not isinstance(content, str):
        return False
    stripped = content.lstrip()
    return any(stripped.startswith(prefix) for prefix in _RUNTIME_EPHEMERAL_SYSTEM_PREFIXES)


def _drop_prior_ephemeral_runtime_context(messages: List[Dict[str, Any]]) -> None:
    if not messages:
        return
    retained: List[Dict[str, Any]] = []
    for index, message in enumerate(messages):
        if index > 0 and _is_ephemeral_runtime_context(message):
            continue
        retained.append(message)
    if len(retained) != len(messages):
        messages[:] = retained


def _message_text(message: Dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return " ".join(part for part in parts if part).strip()
    return ""


def _latest_user_text(messages: List[Dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        text = _message_text(message)
        if text:
            return text
    return ""


def _quality_guard_objective_from_messages(messages: List[Dict[str, Any]]) -> str:
    latest = _latest_user_text(messages)
    if latest and not _is_continuation_request_text(latest):
        return latest
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        text = _message_text(message).strip()
        if text and not _is_continuation_request_text(text):
            return text
    return latest


def _quality_guard_should_verify_request(user_request: str) -> bool:
    from shared.task_intent import request_requires_tool_evidence

    return request_requires_tool_evidence(user_request)


def _nvidia_forced_tool_choice(
    *,
    provider: str,
    user_request: str,
    provider_tool_names: set[str],
    tool_trace: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Force explicitly named NVIDIA tools without changing normal auto tool use."""
    if provider != "nvidia" or not str(user_request or "").strip():
        return None

    request_text = f" {str(user_request).lower()} "
    requested: List[Tuple[int, str]] = []
    for name in sorted(provider_tool_names):
        normalized_name = str(name or "").strip()
        if not normalized_name:
            continue
        aliases = {
            normalized_name.lower(),
            normalized_name.replace("_", " ").lower(),
            normalized_name.replace("_", "-").lower(),
        }
        positions = [request_text.find(f" {alias} ") for alias in aliases if alias]
        positions = [position for position in positions if position >= 0]
        if positions:
            requested.append((min(positions), normalized_name))

    if not requested:
        return None

    completed_tools = {
        str(entry.get("tool") or "").strip()
        for entry in tool_trace
        if isinstance(entry, dict)
    }
    for _position, name in sorted(requested):
        if name not in completed_tools:
            return {"type": "function", "function": {"name": name}}
    return None


def _coerce_final_quality_verdict(value: Any) -> FinalQualityVerdict:
    if isinstance(value, FinalQualityVerdict):
        return value
    if isinstance(value, dict):
        action = str(value.get("action") or "allow").strip().lower()
        if action == "retry":
            action = "continue"
        if action == "true_blocker":
            action = "allow"
        return FinalQualityVerdict(
            action=action if action in {"allow", "continue"} else "allow",
            reason=str(value.get("reason") or value.get("failed_obligation") or "planner_verdict").strip(),
            scores=dict(value.get("scores") or {}),
            continuation_instruction=str(value.get("continuation_instruction") or value.get("retry_instruction") or "").strip(),
        )
    return FinalQualityVerdict(action="allow", reason="invalid_verdict")

def run_tool_loop(
    provider: str,
    model_id: str,
    client: Any,
    messages: List[Dict[str, Any]],
    tool_executor: Any,
    callbacks: Dict[str, Callable],
    variant: str = "standard",
    extra_tools: List[Dict[str, Any]] = None,
    custom_system_prompt: str = None,
    api_type: str = "chat",
    base_tools: List[Dict[str, Any]] = None,
) -> LoopResult:
    """
    Executes a multi-turn conversation loop where the model can call tools.
    Simplified to use only OpenAI-compatible streaming protocol for all providers.
    """
    log = callbacks.get("log", lambda *args: None)
    log_inline = callbacks.get("log_inline", lambda *args: None)
    append_stream = callbacks.get("append_stream", lambda *args: None)
    append_reasoning = callbacks.get("append_reasoning", lambda *args: None)
    begin_stream = callbacks.get("begin_stream", lambda *args: None)
    finish_stream = callbacks.get("finish_stream", lambda *args: None)
    provider = normalize_provider(provider)
    google_uses_openai_compat = provider == "google" and is_openai_compatible_client(client)
    tool_provider = "openai" if google_uses_openai_compat else provider
    
    max_turns = 100
    total_usage = {"input": 0, "output": 0}
    final_response = ""
    assistant_text = ""
    original_user_request = _quality_guard_objective_from_messages(messages)
    tool_trace: List[Dict[str, Any]] = []
    auto_continue_count = 0
    empty_post_tool_continue_count = 0
    empty_post_tool_continue_limit = 1
    quality_guard_enabled = final_quality_guard_enabled()
    quality_guard_mode = final_quality_guard_mode()
    if quality_guard_enabled and not _quality_guard_should_verify_request(original_user_request):
        quality_guard_enabled = False
    auto_continue_limit = _max_auto_continues_for_request(original_user_request) if quality_guard_enabled else 0
    must_use_tool_after_retry = False
    retry_tool_trace_len = 0
    
    # 0. System Prompt Injection
    effective_system = custom_system_prompt or SYSTEM_PROMPT
    if messages:
        if messages[0]["role"] == "system":
            messages[0]["content"] = effective_system
        else:
            messages.insert(0, {"role": "system", "content": effective_system})
    else:
        messages.append({"role": "system", "content": effective_system})

    for turn in range(max_turns):
        _drop_prior_ephemeral_runtime_context(messages)
        before_model_turn_cb = callbacks.get("before_model_turn")
        if before_model_turn_cb:
            injected_messages = before_model_turn_cb(turn, messages)
            if isinstance(injected_messages, dict):
                injected_messages = [injected_messages]
            if injected_messages:
                for injected in injected_messages:
                    if isinstance(injected, dict) and injected.get("role") and injected.get("content") is not None:
                        messages.append(injected)

        # Check for interruption at start of turn
        if tool_executor.check_interruption and tool_executor.check_interruption():
            # Get the interrupting message if available
            interrupt_msg = None
            if hasattr(tool_executor, 'get_interrupt_message') and tool_executor.get_interrupt_message:
                interrupt_msg = tool_executor.get_interrupt_message()
            
            if interrupt_msg:
                # Inject the user's interrupt message into messages
                messages.append({"role": "user", "content": f"[USER INTERRUPT] {interrupt_msg}"})
                # Reset the interrupt flag so we can continue processing
                if hasattr(tool_executor, 'clear_interrupt') and tool_executor.clear_interrupt:
                    tool_executor.clear_interrupt()
            else:
                # No message, just stop
                final_response = assistant_text + "\n\n[Interrupted by user]"
                break
            
        tools = build_tools_for_provider(tool_provider, extra_tools, base_tools=base_tools)
        provider_tool_names = set(get_tool_names(tools))
        forced_tool_choice = _nvidia_forced_tool_choice(
            provider=provider,
            user_request=original_user_request,
            provider_tool_names=provider_tool_names,
            tool_trace=tool_trace,
        )
        canonical_source_tools = list(base_tools) if base_tools is not None else list(CLI_AGENT_TOOLS)
        canonical_names = canonical_tool_names(canonical_source_tools)
        canonical_names.update(canonical_tool_names(extra_tools or []))
        tool_validation_error = validate_provider_tool_names(tools, allowed_names=canonical_names)
        if tool_validation_error:
            finish_stream()
            return LoopResult(content=f"Error in tool inventory: {tool_validation_error}")
            
        assistant_text = ""
        # Because streaming tool calls are chunks, we must accumulate them
        # Format: {index: {"name": str, "args": str, "id": str}}
        tool_call_chunks = {}
        
        interrupted_stream = False
        visible_stream_started = False
        buffered_stream_events: List[Tuple[str, str]] = []

        def _start_visible_stream() -> None:
            nonlocal visible_stream_started
            if not visible_stream_started:
                begin_stream()
                visible_stream_started = True

        def _emit_stream(text: str) -> None:
            if not text:
                return
            if quality_guard_enabled:
                buffered_stream_events.append(("assistant_delta", str(text)))
                return
            _start_visible_stream()
            append_stream(text)

        def _emit_reasoning(text: str) -> None:
            if not str(text or "").strip():
                return
            if quality_guard_enabled:
                buffered_stream_events.append(("reasoning_delta", str(text)))
                return
            append_reasoning(text)

        def _flush_buffered_stream_events() -> None:
            if not buffered_stream_events:
                return
            _start_visible_stream()
            for event_type, text in buffered_stream_events:
                if event_type == "reasoning_delta":
                    append_reasoning(text)
                else:
                    append_stream(text)
            buffered_stream_events.clear()

        def _discard_buffered_stream_events() -> None:
            buffered_stream_events.clear()

        def _finish_visible_stream() -> None:
            if visible_stream_started:
                finish_stream()

        if not quality_guard_enabled:
            _start_visible_stream()

        try:
            if provider == "anthropic":
                # Convert ALL messages in history to Anthropic format
                system_parts = []
                anthropic_messages = []
                
                for m in messages:
                    role = m.get("role")
                    content = m.get("content")
                    
                    if role == "system":
                        if content:
                            system_parts.append(str(content))
                        continue
                    
                    if role == "tool":
                        # Orphaned tool result - wrap in user message
                        # (Anthropic requires tool results to follow assistant tool_use)
                        anthropic_messages.append({
                            "role": "user",
                            "content": [{
                                "type": "tool_result", 
                                "tool_use_id": m.get("tool_call_id"), 
                                "content": content
                            }]
                        })
                    elif role == "assistant" and m.get("tool_calls"):
                        # Convert assistant tool_calls to blocks
                        content_list = []
                        if content:
                            content_list.append({"type": "text", "text": content})
                        for tc in m["tool_calls"]:
                            try:
                                args_obj = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                            except:
                                args_obj = {}
                            content_list.append({
                                "type": "tool_use",
                                "id": tc["id"],
                                "name": tc["function"]["name"],
                                "input": args_obj
                            })
                        anthropic_messages.append({"role": "assistant", "content": content_list})
                    elif role == "user" and isinstance(content, list) and any(c.get("type") == "tool_result" for c in content if isinstance(c, dict)):
                        # Already in anthropic format (internal turn results)
                        anthropic_messages.append(m)
                    else:
                        # Standard message
                        anthropic_messages.append({"role": role, "content": content})

                with client.messages.stream(
                    model=model_id,
                    max_tokens=4096,
                    system=_joined_system_text(system_parts),
                    messages=anthropic_messages,
                    tools=tools if tools else None
                ) as stream:
                    # Track current content block for tool calls
                    current_tool_block = None
                    current_tool_index = None
                    
                    for event in stream:
                        if tool_executor.check_interruption and tool_executor.check_interruption():
                             interrupted_stream = True
                             break
                        
                        # Track content block starts (including tool_use)
                        if event.type == "content_block_start":
                            if hasattr(event, 'content_block') and event.content_block.type == "tool_use":
                                # New tool call starting
                                current_tool_index = event.index
                                current_tool_block = event.content_block
                                tool_call_chunks[current_tool_index] = {
                                    "id": current_tool_block.id,
                                    "name": current_tool_block.name,
                                    "args": ""
                                }
                        elif event.type == "content_block_delta":
                            if event.delta.type == "text_delta":
                                assistant_text += event.delta.text
                                _emit_stream(event.delta.text)
                            elif event.delta.type == "input_json_delta":
                                # Tool call argument delta - use tracked index
                                if current_tool_index is not None and current_tool_index in tool_call_chunks:
                                    tool_call_chunks[current_tool_index]["args"] += event.delta.partial_json
                        elif event.type == "content_block_stop":
                            # Content block finished
                            pass
            elif provider == "google" and not google_uses_openai_compat:
                # Google Gemini Branch
                import google.generativeai as genai
                
                # Convert history for Gemini
                gemini_history = []
                system_parts = []
                for m in messages[:-1]:
                    role = m.get("role")
                    content = m.get("content")
                    if role == "system":
                        if content:
                            system_parts.append(str(content))
                        continue
                    
                    # Gemini roles are 'user' and 'model'
                    gemini_role = "user" if role in ["user", "tool"] else "model"
                    
                    if isinstance(content, list):
                        parts = []
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                parts.append(part.get("text", ""))
                        content = " ".join(parts)
                    
                    gemini_history.append({"role": gemini_role, "parts": [str(content)]})
                
                # Create model
                model = client.GenerativeModel(
                    model_name=model_id,
                    system_instruction=_joined_system_text(system_parts),
                    tools=tools if tools else None
                )
                
                chat = model.start_chat(history=gemini_history)
                
                last_msg = messages[-1]["content"]
                if isinstance(last_msg, list):
                    last_msg = " ".join([p.get("text", "") for p in last_msg if isinstance(p, dict) and p.get("type") == "text"])
                
                response_stream = chat.send_message(last_msg, stream=True)
                
                for chunk in response_stream:
                    if tool_executor.check_interruption and tool_executor.check_interruption():
                         interrupted_stream = True
                         break
                    
                    if chunk.text:
                        assistant_text += chunk.text
                        _emit_stream(chunk.text)
                    
                    # Tool handling for Gemini
                    if hasattr(chunk, "candidates") and chunk.candidates:
                        for cand in chunk.candidates:
                            if hasattr(cand.content, "parts"):
                                for part in cand.content.parts:
                                    if hasattr(part, "function_call") and part.function_call:
                                        fn = part.function_call
                                        idx = len(tool_call_chunks)
                                        # Use a special ID format for Gemini
                                        tid = f"gemini_{int(time.time())}_{idx}"
                                        tool_call_chunks[idx] = {
                                            "id": tid,
                                            "name": fn.name,
                                            "args": json.dumps(dict(fn.args))
                                        }
            elif provider == "openai" and api_type == "responses":
                instructions, response_input = _responses_input_from_messages(messages)
                response_tools = _responses_tool_shape(tools)
                kwargs = {
                    "model": model_id,
                    "input": response_input,
                    "stream": True,
                    "tools": response_tools,
                    "tool_choice": "auto",
                    "instructions": instructions or None,
                }

                if variant in ["low", "medium", "high", "xhigh"]:
                    kwargs["reasoning"] = {"effort": variant if variant != "xhigh" else "high"}

                response_stream = client.responses.create(**kwargs)
                completed_response = None

                for event in response_stream:
                    if tool_executor.check_interruption and tool_executor.check_interruption():
                        interrupted_stream = True
                        break

                    event_type = getattr(event, "type", "")
                    if event_type == "response.output_text.delta":
                        delta_text = getattr(event, "delta", "") or ""
                        if delta_text:
                            assistant_text += delta_text
                            _emit_stream(delta_text)
                    elif "reasoning" in event_type:
                        reasoning_delta = getattr(event, "delta", "") or getattr(event, "text", "") or ""
                        if reasoning_delta:
                            _emit_reasoning(str(reasoning_delta))
                    elif event_type == "response.output_item.added":
                        item = getattr(event, "item", None)
                        if getattr(item, "type", "") == "function_call":
                            idx = int(getattr(event, "output_index", len(tool_call_chunks)) or 0)
                            tool_call_chunks[idx] = {
                                "id": getattr(item, "call_id", None) or getattr(item, "id", None) or f"call_{idx}",
                                "name": getattr(item, "name", "") or "",
                                "args": getattr(item, "arguments", "") or "",
                            }
                    elif event_type == "response.function_call_arguments.delta":
                        idx = int(getattr(event, "output_index", len(tool_call_chunks)) or 0)
                        if idx not in tool_call_chunks:
                            tool_call_chunks[idx] = {
                                "id": getattr(event, "item_id", None) or f"call_{idx}",
                                "name": "",
                                "args": "",
                            }
                        snapshot = getattr(event, "snapshot", None)
                        delta_text = getattr(event, "delta", "") or ""
                        tool_call_chunks[idx]["args"] = str(snapshot if snapshot is not None else (tool_call_chunks[idx]["args"] + delta_text))
                    elif event_type == "response.completed":
                        completed_response = getattr(event, "response", None)
                        usage = getattr(completed_response, "usage", None)
                        if usage is not None:
                            total_usage["input"] += int(getattr(usage, "input_tokens", 0) or 0)
                            total_usage["output"] += int(getattr(usage, "output_tokens", 0) or 0)

                if completed_response is not None:
                    for idx, item in enumerate(list(getattr(completed_response, "output", []) or [])):
                        if getattr(item, "type", "") == "function_call":
                            tool_call_chunks[idx] = {
                                "id": getattr(item, "call_id", None) or getattr(item, "id", None) or f"call_{idx}",
                                "name": getattr(item, "name", "") or "",
                                "args": getattr(item, "arguments", "") or "",
                            }

                    if not assistant_text:
                        output_text = getattr(completed_response, "output_text", None)
                        if output_text:
                            assistant_text = str(output_text)
                            _emit_stream(assistant_text)
            else:
                # OpenAI-compatible streaming logic, including Gemini's official
                # OpenAI-compatible endpoint.
                kwargs = {
                    "model": model_id,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": forced_tool_choice or "auto",
                    "stream": True,
                }
                if provider not in {"google", "nvidia"}:
                    kwargs["stream_options"] = {"include_usage": True}
                
                if (
                    variant in ["low", "medium", "high", "xhigh"]
                    and provider == "openai"
                    and api_type != "responses"
                ):
                    kwargs["reasoning_effort"] = variant if variant != "xhigh" else "high"
                elif provider == "google" and variant in {"low", "medium", "high"}:
                    kwargs["reasoning_effort"] = variant

                response_stream = client.chat.completions.create(**kwargs)
                
                for chunk in response_stream:
                    if tool_executor.check_interruption and tool_executor.check_interruption():
                         interrupted_stream = True
                         break

                    if not chunk.choices:
                        if hasattr(chunk, "usage") and chunk.usage:
                            total_usage["input"] += chunk.usage.prompt_tokens
                            total_usage["output"] += chunk.usage.completion_tokens
                        continue
                        
                    delta = chunk.choices[0].delta
                    
                    if hasattr(delta, "content") and delta.content:
                        assistant_text += delta.content
                        _emit_stream(delta.content)
                    
                    reasoning = getattr(delta, "reasoning_content", None)
                    if reasoning:
                        _emit_reasoning(reasoning)
                        _emit_stream(f"[dim]{reasoning}[/dim]")

                    if hasattr(delta, "tool_calls") and delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_call_chunks:
                                tool_call_chunks[idx] = {"id": tc.id, "name": "", "args": ""}
                            
                            if tc.function:
                                if tc.function.name:
                                    tool_call_chunks[idx]["name"] += tc.function.name
                                if tc.function.arguments:
                                    tool_call_chunks[idx]["args"] += tc.function.arguments
            
            if interrupted_stream:
                log("  🛑 Stream interrupted by user.")
                if assistant_text:
                    assistant_text += "\n\n[USER INTERRUPT: Output Truncated]"
                else:
                    assistant_text = "[USER INTERRUPT: Output Truncated]"

        except Exception as e:
            _finish_visible_stream()
            info = normalize_provider_error(e, payload_kind="text")
            return LoopResult(
                content=provider_blocker_message(info),
            )
        
        # Format tool calls for history
        formatted_tc = []
        for idx in sorted(tool_call_chunks.keys()):
            chunks = tool_call_chunks[idx]
            if chunks["name"]:
                formatted_tc.append({
                    "id": chunks["id"],
                    "type": "function",
                    "function": {"name": chunks["name"], "arguments": chunks["args"]}
                })

        # --- ASSISTANT MESSAGE APPEND ---
        if provider == "anthropic":
            # For Anthropic, if there are tool calls, content must be a list
            content_list = []
            if assistant_text:
                content_list.append({"type": "text", "text": assistant_text})
            
            for tc in formatted_tc:
                try:
                    args_obj = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                except Exception:
                    args_obj = {}
                content_list.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "input": args_obj
                })
            
            # If no text AND no tools, Anthropic might complain, but tool loop logic handles break
            if content_list:
                messages.append({"role": "assistant", "content": content_list})
            elif assistant_text:
                messages.append({"role": "assistant", "content": assistant_text})
        else:
            # OpenAI / Generic
            if assistant_text or formatted_tc:
                msg_obj = {"role": "assistant", "content": assistant_text or None}
                if formatted_tc:
                    msg_obj["tool_calls"] = formatted_tc
                messages.append(msg_obj)

        if not formatted_tc:
            final_response = assistant_text
            has_deferred = (
                hasattr(tool_executor, "has_deferred_interrupts")
                and tool_executor.has_deferred_interrupts
                and tool_executor.has_deferred_interrupts()
            )
            if has_deferred and hasattr(tool_executor, "activate_deferred_interrupts") and tool_executor.activate_deferred_interrupts:
                if tool_executor.activate_deferred_interrupts():
                    log("  ↪ Applying deferred steering after current turn.")
                    _discard_buffered_stream_events()
                    _finish_visible_stream()
                    continue
            if interrupted_stream:
                _discard_buffered_stream_events()
                _finish_visible_stream()
                continue 
            if not assistant_text.strip() and tool_trace:
                if empty_post_tool_continue_count < empty_post_tool_continue_limit:
                    empty_post_tool_continue_count += 1
                    final_response = ""
                    _discard_buffered_stream_events()
                    _finish_visible_stream()
                    latest_tool = tool_trace[-1]
                    instruction = (
                        "[Hidden runtime continuation: your previous turn ended with no user-visible assistant reply after tool use.] "
                        "Answer the user's original request now using the latest tool result. "
                        "Do not call another tool unless the latest tool result is genuinely insufficient. "
                        f"Latest tool: {latest_tool.get('tool')}. "
                        f"Latest result summary: {_truncate_text(str(latest_tool.get('result') or ''), max_chars=2000)}"
                    )
                    messages.append({"role": "user", "content": instruction})
                    on_auto_continue_cb = callbacks.get("on_auto_continue")
                    if on_auto_continue_cb:
                        try:
                            on_auto_continue_cb(
                                {
                                    "reason": "empty_post_tool_final",
                                    "action": "continue",
                                    "scores": {},
                                    "auto_continue_count": empty_post_tool_continue_count,
                                    "auto_continue_limit": empty_post_tool_continue_limit,
                                }
                            )
                        except Exception:
                            pass
                    log(
                        "  ↪ Empty post-tool answer forced continuation "
                        f"({empty_post_tool_continue_count}/{empty_post_tool_continue_limit})."
                    )
                    continue
                final_response = _fallback_final_from_tool_trace(tool_trace)
                _flush_buffered_stream_events()
                _finish_visible_stream()
                break
            if (
                must_use_tool_after_retry
                and len(tool_trace) <= retry_tool_trace_len
                and auto_continue_count < auto_continue_limit
            ):
                auto_continue_count += 1
                final_response = ""
                _discard_buffered_stream_events()
                _finish_visible_stream()
                instruction = (
                    "[Hidden runtime continuation: your previous answer was not shown to the user.] "
                    "A verifier already required more evidence, but you attempted to final-answer without using a tool. "
                    "Call an appropriate tool now. Continue the user's original task from the current state, "
                    "take a materially useful action, and verify the result before final-answering."
                )
                messages.append({"role": "user", "content": instruction})
                on_auto_continue_cb = callbacks.get("on_auto_continue")
                if on_auto_continue_cb:
                    try:
                        on_auto_continue_cb(
                            {
                                "reason": "retry_requires_tool",
                                "action": "continue",
                                "scores": {},
                                "auto_continue_count": auto_continue_count,
                                "auto_continue_limit": auto_continue_limit,
                            }
                        )
                    except Exception:
                        pass
                log(
                    "  ↪ Final quality guard forced tool use "
                    f"(retry_requires_tool; {auto_continue_count}/{auto_continue_limit})."
                )
                continue
            if (
                quality_guard_enabled
                and auto_continue_count < auto_continue_limit
                and assistant_text
            ):
                judge_final_candidate_cb = callbacks.get("judge_final_candidate")
                raw_final_quality_verdict = None
                if judge_final_candidate_cb:
                    try:
                        raw_final_quality_verdict = judge_final_candidate_cb(
                            {
                                "user_request": original_user_request,
                                "assistant_final": assistant_text,
                                "tool_trace": list(tool_trace),
                                "auto_continue_count": auto_continue_count,
                                "auto_continue_limit": auto_continue_limit,
                            }
                        )
                        verdict = _coerce_final_quality_verdict(
                            raw_final_quality_verdict
                        )
                    except Exception as exc:
                        verdict = FinalQualityVerdict(action="allow", reason=f"planner_unavailable:{exc}")
                elif quality_guard_mode == "nli":
                    verdict = judge_final_quality_with_nli(
                        user_request=original_user_request,
                        assistant_final=assistant_text,
                        tool_trace=tool_trace,
                    )
                else:
                    verdict = FinalQualityVerdict(action="allow", reason="no_final_quality_verifier")
                on_auto_continue_cb = callbacks.get("on_auto_continue")
                if on_auto_continue_cb:
                    try:
                        auto_continue_payload = {
                            "reason": verdict.reason,
                            "action": verdict.action,
                            "scores": verdict.scores,
                            "auto_continue_count": auto_continue_count + 1,
                            "auto_continue_limit": auto_continue_limit,
                            "candidate_final_preview": _truncate_text(assistant_text, max_chars=2000),
                        }
                        if isinstance(raw_final_quality_verdict, dict):
                            for key in (
                                "failed_obligation",
                                "evidence_gap",
                                "retry_instruction",
                                "continuation_instruction",
                                "must_use_tool",
                            ):
                                if key in raw_final_quality_verdict:
                                    auto_continue_payload[key] = _truncate_text(
                                        str(raw_final_quality_verdict.get(key) or ""),
                                        max_chars=2000,
                                    )
                        on_auto_continue_cb(auto_continue_payload)
                    except Exception:
                        pass
                if verdict.action == "continue" and verdict.continuation_instruction:
                    auto_continue_count += 1
                    final_response = ""
                    _discard_buffered_stream_events()
                    _finish_visible_stream()
                    messages.append({"role": "user", "content": verdict.continuation_instruction})
                    must_use_tool_after_retry = True
                    retry_tool_trace_len = len(tool_trace)
                    log(
                        "  ↪ Final quality guard forced continuation "
                        f"({verdict.reason}; {auto_continue_count}/{auto_continue_limit})."
                    )
                    continue
            _flush_buffered_stream_events()
            _finish_visible_stream()
            break

        # --- EXECUTE TOOLS ---
        _flush_buffered_stream_events()
        _finish_visible_stream()
        must_use_tool_after_retry = False
        interrupted_batch = False
        batch_results = []
        post_tool_messages: List[Dict[str, Any]] = []
        
        for i, tc in enumerate(formatted_tc):
            if tool_executor.check_interruption and tool_executor.check_interruption():
                log(f"  🛑 Interruption detected. Skipping remaining tool calls.")
                interrupted_batch = True
                
            name = tc["function"]["name"]
            
            if interrupted_batch:
                batch_results.append({
                    "id": tc["id"],
                    "name": name,
                    "content": json.dumps({"error": "Operation cancelled by user interrupt.", "interrupted": True})
                })
                continue

            if name not in provider_tool_names:
                result = {
                    "error": (
                        f"Model requested undeclared tool '{name}'. "
                        "This tool was not in the callable provider inventory for this turn, "
                        "so it was not executed. Choose one of the actually available tools."
                    ),
                    "error_type": "invalid_provider_tool_call",
                    "tool_name": name,
                    "available_tools": sorted(provider_tool_names),
                    "retry": True,
                }
                log(f"  [TOOL BLOCKED] {name} is not in the provider tool inventory.")
                tool_trace.append(
                    {
                        "tool": name,
                        "args": {},
                        "result": _summarize_tool_result_for_model(name, result),
                    }
                )
                tool_trace = tool_trace[-32:]
                on_tool_use_cb = callbacks.get("on_tool_use")
                if on_tool_use_cb:
                    try:
                        tool_messages = on_tool_use_cb(name, {}, result, 0.0)
                        if isinstance(tool_messages, dict):
                            post_tool_messages.append(tool_messages)
                        elif isinstance(tool_messages, list):
                            for item in tool_messages:
                                if isinstance(item, dict):
                                    post_tool_messages.append(item)
                    except Exception:
                        pass
                batch_results.append({
                    "id": tc["id"],
                    "name": name,
                    "raw_result": result,
                    "content": json.dumps(result),
                    "image_data": None,
                })
                continue
            
            try:
                args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
            except json.JSONDecodeError:
                args = {} 
            
            # Verbose logging for tool call
            if VERBOSE_LOGGING:
                log_tool_call(name, args, provider)
            else:
                log_args = args.copy() if args else {}
                if 'content' in log_args and len(str(log_args.get('content', ''))) > 100:
                    log_args['content'] = str(log_args['content'])[:100] + "..."
                log(f"  [TOOL] {name}({log_args})")
            
            start_time = time.time()
            try:
                result = tool_executor.execute(name, args)
                if isinstance(result, dict) and result.get("interrupted"):
                    interrupted_batch = True
            except Exception as e:
                result = {"error": f"Tool execution failed: {str(e)}"}
                log(f"  ❌ ERROR: {str(e)}")
            
            duration_ms = (time.time() - start_time) * 1000
            
            # Verbose logging for tool result
            if VERBOSE_LOGGING:
                log_tool_result(name, result, duration_ms)

            model_ready_result = result
            image_payload = _extract_image_payload(result)
            if image_payload and isinstance(result, dict):
                vision_question = _vision_question_for_result(name, args, result)
                vision_summary = _analyze_image_sidecar(
                    provider=provider,
                    model_id=model_id,
                    client=client,
                    api_type=api_type,
                    tool_name=name,
                    image_data=image_payload,
                    question=vision_question,
                    log=log,
                )
                model_ready_result = dict(result)
                model_ready_result["vision_question"] = vision_question
                model_ready_result["vision_summary"] = vision_summary

            tool_trace.append(
                {
                    "tool": name,
                    "args": args,
                    "result": _summarize_tool_result_for_model(name, model_ready_result),
                }
            )
            tool_trace = tool_trace[-32:]

            # Notify external callback (e.g. Telegram verbose mode)
            on_tool_use_cb = callbacks.get("on_tool_use")
            if on_tool_use_cb:
                tool_messages = on_tool_use_cb(name, args, model_ready_result, duration_ms)
                if isinstance(tool_messages, dict):
                    post_tool_messages.append(tool_messages)
                elif isinstance(tool_messages, list):
                    for item in tool_messages:
                        if isinstance(item, dict):
                            post_tool_messages.append(item)

            # Group result
            batch_results.append({
                "id": tc["id"],
                "name": name,
                "raw_result": model_ready_result,
                "content": json.dumps(model_ready_result) if not isinstance(model_ready_result, str) else model_ready_result,
                "image_data": None,
            })

        # --- TOOL RESULTS APPEND ---
        # Helper to strip base64 data from content (it's passed via vision API separately)
        if provider == "anthropic":
            # Anthropic expects tool results in a SINGLE user message as a list
            result_content = []
            for res in batch_results:
                clean_content = _summarize_tool_result_for_model(res["name"], res.get("raw_result"))
                
                result_content.append({
                    "type": "tool_result",
                    "tool_use_id": res["id"],
                    "content": clean_content
                })
            
            if result_content:
                messages.append({"role": "user", "content": result_content})
        else:
            # OpenAI style - one message per tool
            for res in batch_results:
                clean_content = _summarize_tool_result_for_model(res["name"], res.get("raw_result"))
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": res["id"],
                    "name": res["name"],
                    "content": clean_content
                })
        if hasattr(tool_executor, "activate_deferred_interrupts") and tool_executor.activate_deferred_interrupts:
            activated_deferred = tool_executor.activate_deferred_interrupts()
            if activated_deferred:
                log("  ↪ Applying deferred steering after tool boundary.")

        if post_tool_messages:
            messages.extend(post_tool_messages)

    return LoopResult(
        content=final_response,
        input_tokens=total_usage["input"],
        output_tokens=total_usage["output"],
        total_tokens=total_usage["input"] + total_usage["output"]
    )
