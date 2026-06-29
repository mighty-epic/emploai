from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4
from shared.security_policy import redact_json, redact_text


MAX_TIMELINE_EVENTS = 2000
_BASE64_KEYS = frozenset({"image_base64", "base64", "image_data", "data", "screenshot"})


def _truncate(text: Any, limit: int = 1200) -> str:
    value = redact_text(str(text or "")).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _safe_value(value: Any, *, limit: int = 120) -> str:
    value = redact_json(value)
    if isinstance(value, dict):
        keys = [str(key) for key in value.keys() if str(key) not in _BASE64_KEYS]
        preview = ", ".join(keys[:4]) or "object"
        return _truncate(preview, limit)
    if isinstance(value, (list, tuple, set)):
        return _truncate(f"{type(value).__name__}[{len(value)}]", limit)
    return _truncate(value, limit)


def _tool_args_preview(tool_args: Dict[str, Any]) -> str:
    parts = []
    for key, value in list((redact_json(tool_args or {}) or {}).items())[:4]:
        value_str = str(value)
        if key in _BASE64_KEYS and len(value_str) > 100:
            continue
        parts.append(f"{key}: {_safe_value(value, limit=80)}")
    return _truncate(", ".join(parts), 240)


def _tool_result_preview(tool_result: Any) -> tuple[str, str]:
    tool_result = redact_json(tool_result)
    if isinstance(tool_result, dict):
        if "error" in tool_result:
            return "error", f"Error: {_truncate(tool_result.get('error'), 220)}"
        safe_keys = [str(key) for key in tool_result.keys() if str(key) not in _BASE64_KEYS]
        return "accent", _truncate(", ".join(safe_keys[:6]) or "ok", 220)
    if isinstance(tool_result, str):
        clean = _truncate(tool_result, 220)
        if clean.startswith("Error"):
            return "error", clean
        return "accent", clean or "ok"
    return "accent", _safe_value(tool_result, limit=220) or "ok"


def build_tool_timeline_event(
    *,
    tool_name: str,
    tool_args: Dict[str, Any],
    tool_result: Any,
    duration_ms: float,
    channel: Optional[str] = None,
    source_format: Optional[str] = None,
) -> Dict[str, Any]:
    safe_args = redact_json(tool_args or {})
    safe_result = redact_json(tool_result)
    args_preview = _tool_args_preview(safe_args)
    tone, result_preview = _tool_result_preview(safe_result)
    call_preview = f"{tool_name}({args_preview})" if args_preview else f"{tool_name}()"
    content = f"{call_preview}\n-> {result_preview} ({duration_ms:.0f}ms)"
    return create_timeline_event(
        kind="tool",
        title=f"Tool · {tool_name}",
        content=content,
        tone=tone,
        channel=channel,
        source_format=source_format,
        metadata={
            "tool_name": tool_name,
            "duration_ms": round(float(duration_ms or 0.0), 2),
            "args_preview": args_preview,
            "result_preview": result_preview,
        },
    )


def build_log_timeline_event(
    *,
    message: str,
    channel: Optional[str] = None,
    source_format: Optional[str] = None,
) -> Dict[str, Any]:
    text = _truncate(message, 1200)
    tone = "neutral"
    if "[ERROR]" in text or "❌" in text or text.lower().startswith("error"):
        tone = "error"
    elif "[PAUSED]" in text or "[STOPPED]" in text or "warning" in text.lower():
        tone = "warn"
    return create_timeline_event(
        kind="runtime",
        title="Runtime",
        content=text,
        tone=tone,
        channel=channel,
        source_format=source_format,
    )


def create_timeline_event(
    *,
    kind: str,
    title: str,
    content: str,
    tone: str = "neutral",
    channel: Optional[str] = None,
    source_format: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id": uuid4().hex,
        "kind": str(kind or "note"),
        "title": _truncate(title, 180) or "Event",
        "content": _truncate(content, 4000),
        "tone": tone if tone in {"neutral", "accent", "warn", "error"} else "neutral",
        "timestamp": timestamp or datetime.now().isoformat(),
        "channel": channel,
        "source_format": source_format,
        "metadata": metadata or {},
    }


def append_timeline_event(
    session: Any,
    *,
    event: Dict[str, Any],
) -> Dict[str, Any]:
    timeline = list(getattr(session, "event_timeline", []) or [])
    timeline.append(dict(event))
    if len(timeline) > MAX_TIMELINE_EVENTS:
        timeline = timeline[-MAX_TIMELINE_EVENTS:]
    session.event_timeline = timeline
    return event
