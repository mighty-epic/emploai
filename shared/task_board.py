from __future__ import annotations

import copy
import json
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from cli.tui_constants import MODEL_CONFIGS
from shared.openai_api import create_openai_completion


TASK_BOARD_METHOD_FAILURE_THRESHOLD = 3
TASK_BOARD_MODEL_TURN_THRESHOLD = 30
TASK_BOARD_COMPLETED_HISTORY_LIMIT = 5
TASK_BOARD_INTERNAL_TOOL_NAME = "task_board_report_failure"

_TASK_STATES = {
    "idle",
    "candidate",
    "active",
    "reassessing",
    "blocked_waiting_user",
    "completed_collapsed",
    "history_collapsed",
}
_TASK_STATUSES = {"active", "completed", "blocked", "paused", "interrupted"}
_DISPLAY_MODES = {"active", "completed_collapsed", "history_collapsed"}
_SUBGOAL_STATUSES = {"open", "in_progress", "done", "blocked"}
_VERIFICATION_STATUSES = {"open", "done"}
_BLOCKER_TYPES = {"none", "credentials", "2fa", "account_choice"}

_TOOL_FAMILY_MAP: Dict[str, str] = {
    # Browser DOM / Selenium / extension-backed Chrome
    "open_browser": "browser_dom",
    "observe_browser": "browser_dom",
    "browser_snapshot": "browser_dom",
    "browser_read_text": "browser_dom",
    "browser_click_ref": "browser_dom",
    "browser_type": "browser_dom",
    "browser_press_key": "browser_dom",
    "browser_scroll": "browser_dom",
    "browser_screenshot": "browser_dom",
    "browser_navigate": "browser_dom",
    "browser_wait_for": "browser_dom",
    "browser_list_tabs": "browser_dom",
    "browser_activate_tab": "browser_dom",
    "browser_extension_toggle": "browser_dom",
    "switch_tab": "browser_dom",
    "close_tab": "browser_dom",
    "go_back": "browser_dom",
    "go_forward": "browser_dom",
    # Desktop GUI / vision / atomic actions
    "describe_screen": "desktop_gui",
    "ocr_screen": "desktop_gui",
    "observe_desktop": "desktop_gui",
    "focus_window": "desktop_gui",
    "minimize_window": "desktop_gui",
    "maximize_window": "desktop_gui",
    "close_window": "desktop_gui",
    "click": "desktop_gui",
    "right_click": "desktop_gui",
    "double_click": "desktop_gui",
    "type_text": "desktop_gui",
    "press_key": "desktop_gui",
    "hotkey": "desktop_gui",
    "scroll": "desktop_gui",
    "drag_and_drop": "desktop_gui",
    "open_file": "system_app_or_terminal",
    # Workspace / code
    "read_file": "workspace_code",
    "write_file": "workspace_code",
    "append_file": "workspace_code",
    "edit_file": "workspace_code",
    "list_dir": "workspace_code",
    "find_file": "workspace_code",
    "grep_search": "workspace_code",
    "change_directory": "workspace_code",
    # Web research
    "web_search": "web_research",
    "fetch_url": "web_research",
    # Terminal / apps / system
    "open_app": "system_app_or_terminal",
    "launch_app": "system_app_or_terminal",
    "run_command": "system_app_or_terminal",
    "run_background_command": "system_app_or_terminal",
    "command_status": "system_app_or_terminal",
    "send_input": "system_app_or_terminal",
    "kill_command": "system_app_or_terminal",
    "get_clipboard": "system_app_or_terminal",
    "set_clipboard": "system_app_or_terminal",
}

_PLANNER_PREFERRED_MODELS = [
    "gpt-4o-mini",
    "claude-haiku-4.5",
    "claude-haiku-4",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "deepseek-chat",
    "grok-4.1-fast-non-reasoning",
    "grok-4-fast-non-reasoning",
    "orb-gpt-4o",
]

_FAMILY_SIBLING_METHODS: Dict[str, List[str]] = {
    "browser_dom": [
        "Refresh the DOM view with browser_snapshot or observe_browser and use a ref-based browser action after re-observing the page.",
        "Use browser_read_text or browser_wait_for(text_contains=...) when the missing proof is static page text, a heading, or an exact rendered value.",
        "Do not switch to describe_screen or ocr_screen for a headless isolated browser page. Use desktop vision only when the browser is intentionally headed and visibly on screen.",
    ],
    "desktop_gui": [
        "Re-observe with describe_screen and relocate the target before trying another physical action.",
        "Use ocr_screen for exact text coordinates instead of repeating the same visual click path.",
        "Prefer keyboard navigation or hotkeys before another pixel-based click.",
    ],
    "system_app_or_terminal": [
        "Try an alternate app-launch path or a direct command-line launch instead of repeating the same opener.",
        "If the native app path fails again, switch to the browser version if that path is allowed.",
    ],
    "workspace_code": [
        "Inspect the adjacent files or verify the state from the filesystem before repeating the same edit path.",
        "Switch from direct edits to a read-then-edit verification flow for the next attempt.",
    ],
    "web_research": [
        "Switch to a different source or a fetch_url plus web_search combination instead of repeating the same page.",
        "Change the query or site focus before re-running the same research step.",
    ],
}

_BLOCKER_LABELS = {
    "credentials": "The task needs credentials from the user before it can continue.",
    "2fa": "The task is waiting on a user-provided 2FA or verification code.",
    "account_choice": "The task needs the user to choose an account or identity before it can continue.",
}


TASK_BOARD_FAILURE_REPORT_TOOL: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": TASK_BOARD_INTERNAL_TOOL_NAME,
        "description": (
            "Report that the current concrete method has failed repeatedly and the runtime should reassess the task board. "
            "Use this only after the same method has genuinely failed three times or a true user-dependent blocker was reached."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "method_key": {
                    "type": "string",
                    "description": "Stable runtime-facing key for the failing method.",
                },
                "method_label": {
                    "type": "string",
                    "description": "Human-readable label for the failing method.",
                },
                "failure_summary": {
                    "type": "string",
                    "description": "Short summary of what failed and why the current method is exhausted.",
                },
                "attempt_count": {
                    "type": "integer",
                    "description": "How many times this same method has already been tried.",
                },
                "state_changed": {
                    "type": "boolean",
                    "description": "Whether the page/app state materially changed between retries.",
                },
                "suspected_blocker_type": {
                    "type": "string",
                    "enum": ["none", "credentials", "2fa", "account_choice"],
                    "description": "Only use a blocker type when the task truly requires the user's input to continue.",
                },
            },
            "required": [
                "method_key",
                "method_label",
                "failure_summary",
                "attempt_count",
                "state_changed",
                "suspected_blocker_type",
            ],
        },
    },
}

# Backwards-compatible alias so older imports do not break while the runtime moves to the
# new hardcoded failure-report flow.
TASK_BOARD_UPDATE_TOOL = TASK_BOARD_FAILURE_REPORT_TOOL


def _now_iso() -> str:
    return datetime.now().isoformat()


def _collapse_text(value: str, *, limit: int = 220) -> str:
    cleaned = " ".join(str(value or "").strip().split())
    cleaned = cleaned.strip(" .,:;!-")
    if not cleaned:
        return ""
    if len(cleaned) > limit:
        cleaned = cleaned[: limit - 3].rstrip() + "..."
    return cleaned[:1].upper() + cleaned[1:]


def _normalize_status(value: str, *, default: str, allowed: set[str]) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in allowed else default


def _task_id() -> str:
    return f"task_{uuid.uuid4().hex[:10]}"


def ensure_task_board_state(session: Any) -> None:
    if getattr(session, "task_history", None) is None:
        session.task_history = []
    if not hasattr(session, "active_task_id"):
        session.active_task_id = None
    if not hasattr(session, "task_board_armed_next_turn"):
        session.task_board_armed_next_turn = False
    if not hasattr(session, "_task_board_candidate"):
        session._task_board_candidate = None
    if not hasattr(session, "_task_board_turn_state"):
        session._task_board_turn_state = None


def get_task_board_armed_next_turn(session: Any) -> bool:
    ensure_task_board_state(session)
    return bool(getattr(session, "task_board_armed_next_turn", False))


def set_task_board_armed_next_turn(session: Any, armed: bool) -> bool:
    ensure_task_board_state(session)
    session.task_board_armed_next_turn = bool(armed)
    return session.task_board_armed_next_turn


def _current_turn_state(session: Any) -> Optional[Dict[str, Any]]:
    ensure_task_board_state(session)
    state = getattr(session, "_task_board_turn_state", None)
    return state if isinstance(state, dict) else None


def _set_turn_state(session: Any, state: Optional[Dict[str, Any]]) -> None:
    ensure_task_board_state(session)
    session._task_board_turn_state = state


def _clean_request_text(user_message: str) -> str:
    cleaned = _collapse_text(user_message, limit=320)
    if not cleaned:
        return "Carry out the requested task"
    cleaned = re.sub(
        r"^(?:please\s+|can you\s+|could you\s+|i want you to\s+|i need you to\s+|help me\s+)",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = _collapse_text(cleaned, limit=220)
    return cleaned or "Carry out the requested task"


def _is_continuation_message(user_message: str) -> bool:
    cleaned = str(user_message or "").strip().lower()
    if not cleaned:
        return False
    continuations = {
        "continue",
        "go on",
        "keep going",
        "carry on",
        "resume",
        "proceed",
        "next",
        "do it",
        "do that",
        "keep working",
    }
    return cleaned in continuations


def _split_request_into_steps(user_message: str) -> List[str]:
    cleaned = _clean_request_text(user_message)
    if not cleaned:
        return []

    parts = re.split(r"\b(?:and then|then|after that|afterwards|next)\b", cleaned, flags=re.IGNORECASE)
    if len(parts) == 1 and cleaned.lower().count(" and ") in {1, 2}:
        parts = re.split(r"\band\b", cleaned, flags=re.IGNORECASE)

    items = [_collapse_text(part, limit=120) for part in parts if _collapse_text(part, limit=120)]
    deduped: List[str] = []
    for item in items:
        if item not in deduped:
            deduped.append(item)

    if len(deduped) <= 1:
        return [
            "Inspect the current state and constraints",
            cleaned,
            "Verify the requested result",
        ]

    if not any(word in deduped[-1].lower() for word in ("verify", "confirm", "check", "validate", "ensure")):
        deduped.append("Verify the requested result")

    return deduped[:6]


def _default_sub_goals(user_message: str) -> List[Dict[str, Any]]:
    sub_goals: List[Dict[str, Any]] = []
    for index, title in enumerate(_split_request_into_steps(user_message), start=1):
        sub_goals.append(
            {
                "id": f"sg_{index}",
                "title": title,
                "status": "open",
                "completion_reason": None,
                "completion_evidence": None,
            }
        )
    if not sub_goals:
        sub_goals.append(
            {
                "id": "sg_1",
                "title": "Carry out the requested task",
                "status": "open",
                "completion_reason": None,
                "completion_evidence": None,
            }
        )
    return sub_goals


def _progress_counts(board: Dict[str, Any]) -> tuple[int, int]:
    sub_goals = board.get("sub_goals") or []
    total = len(sub_goals)
    done = sum(1 for item in sub_goals if str(item.get("status", "")).lower() == "done")
    return done, total


def _set_progress_summary(board: Dict[str, Any]) -> None:
    done, total = _progress_counts(board)
    board["completed_sub_goals"] = done
    board["total_sub_goals"] = total
    board["progress_summary"] = f"{done}/{total} sub-goals complete" if total else "No sub-goals yet"


def _normalize_sub_goal(payload: Dict[str, Any], index: int) -> Dict[str, Any]:
    title = _collapse_text(str(payload.get("title") or ""), limit=140) or f"Step {index}"
    return {
        "id": str(payload.get("id") or f"sg_{index}"),
        "title": title,
        "status": _normalize_status(payload.get("status", "open"), default="open", allowed=_SUBGOAL_STATUSES),
        "completion_reason": _collapse_text(str(payload.get("completion_reason") or ""), limit=180) or None,
        "completion_evidence": _collapse_text(str(payload.get("completion_evidence") or ""), limit=180) or None,
    }


def _append_unique(items: List[str], value: Optional[str], *, limit: int = 10) -> None:
    cleaned = _collapse_text(str(value or ""), limit=220)
    if not cleaned:
        return
    if cleaned in items:
        items.remove(cleaned)
    items.append(cleaned)
    del items[:-limit]


def _board_log(board: Dict[str, Any], kind: str, text: Optional[str]) -> None:
    cleaned = _collapse_text(str(text or ""), limit=260)
    if not cleaned:
        return
    markers = board.setdefault("progress_markers", [])
    markers.append({"timestamp": _now_iso(), "kind": kind, "text": cleaned})
    del markers[:-40]
    board["latest_summary"] = cleaned


def _find_board_index(session: Any, task_id: Optional[str]) -> Optional[int]:
    if not task_id:
        return None
    ensure_task_board_state(session)
    for index, item in enumerate(session.task_history):
        if str(item.get("task_id") or "") == str(task_id):
            return index
    return None


def get_active_task_board(session: Any) -> Optional[Dict[str, Any]]:
    ensure_task_board_state(session)
    index = _find_board_index(session, getattr(session, "active_task_id", None))
    if index is None:
        return None
    board = session.task_history[index]
    if str(board.get("display_mode") or "") != "active":
        return None
    if str(board.get("status") or "") != "active":
        return None
    return board


def get_latest_task_board(session: Any) -> Optional[Dict[str, Any]]:
    ensure_task_board_state(session)
    if not session.task_history:
        return None
    return session.task_history[-1]


def get_display_task_board(session: Any) -> Optional[Dict[str, Any]]:
    return get_active_task_board(session)


def completed_task_boards(session: Any) -> List[Dict[str, Any]]:
    ensure_task_board_state(session)
    items = [
        board
        for board in session.task_history
        if str(board.get("display_mode") or "") in {"completed_collapsed", "history_collapsed"}
    ]
    items.sort(key=lambda item: str(item.get("collapsed_completed_at") or item.get("completed_at") or item.get("updated_at") or ""), reverse=True)
    return items[:TASK_BOARD_COMPLETED_HISTORY_LIMIT]


def completed_task_board_views(session: Any) -> List[Dict[str, Any]]:
    return [task_board_view(board) for board in completed_task_boards(session)]


def _prune_completed_boards(session: Any) -> None:
    ensure_task_board_state(session)
    completed_indexes = [
        index
        for index, board in enumerate(session.task_history)
        if str(board.get("display_mode") or "") in {"completed_collapsed", "history_collapsed"}
    ]
    if len(completed_indexes) <= TASK_BOARD_COMPLETED_HISTORY_LIMIT:
        return
    removable = completed_indexes[: len(completed_indexes) - TASK_BOARD_COMPLETED_HISTORY_LIMIT]
    for index in reversed(removable):
        del session.task_history[index]


def _family_for_tool(tool_name: str) -> Optional[str]:
    normalized = str(tool_name or "").strip()
    if not normalized or normalized == TASK_BOARD_INTERNAL_TOOL_NAME:
        return None
    return _TOOL_FAMILY_MAP.get(normalized)


def _is_qualifying_tool(tool_name: str) -> bool:
    return _family_for_tool(tool_name) is not None


def _tool_args_preview(tool_args: Dict[str, Any], *, limit: int = 3) -> List[str]:
    focus_keys = [
        "ref",
        "path",
        "url",
        "selector",
        "title_contains",
        "text_contains",
        "tab_id",
        "index",
        "key",
        "x",
        "y",
    ]
    details: List[str] = []
    for key in focus_keys:
        if key not in tool_args:
            continue
        value = tool_args.get(key)
        if value is None or value == "":
            continue
        details.append(f"{key}={value}")
        if len(details) >= limit:
            break
    return details


def _method_identity(tool_name: str, tool_args: Dict[str, Any]) -> tuple[str, str]:
    details = _tool_args_preview(tool_args)
    key = f"{tool_name}|{'|'.join(details)}" if details else tool_name
    display = f"{tool_name} ({', '.join(details)})" if details else tool_name
    return key, display


def _is_failure_result(result: Any) -> bool:
    if isinstance(result, dict):
        return bool(result.get("error"))
    if not isinstance(result, str):
        return False
    lowered = result.strip().lower()
    return lowered.startswith(
        (
            "error",
            "browser error",
            "click error",
            "type error",
            "clear error",
            "execution failed",
        )
    ) or " tool execution failed" in lowered


def _result_preview(result: Any) -> str:
    if isinstance(result, dict):
        if result.get("error"):
            return _collapse_text(str(result.get("error")), limit=180)
        if result.get("message"):
            return _collapse_text(str(result.get("message")), limit=180)
        try:
            return _collapse_text(json.dumps(result, ensure_ascii=True), limit=180)
        except Exception:
            return "Structured tool result"
    return _collapse_text(str(result or ""), limit=180)


def _tool_event(tool_name: str, tool_args: Dict[str, Any], tool_result: Any) -> Dict[str, Any]:
    family = _family_for_tool(tool_name)
    method_key, method_label = _method_identity(tool_name, tool_args)
    return {
        "timestamp": _now_iso(),
        "tool_name": tool_name,
        "family": family,
        "method_key": method_key,
        "method_label": method_label,
        "args_preview": _tool_args_preview(tool_args),
        "success": not _is_failure_result(tool_result),
        "result_preview": _result_preview(tool_result),
    }


def _default_next_method() -> str:
    return "Continue with the current verified path, one sub-goal at a time, and verify the state after each change."


def _resolve_focus(sub_goals: List[Dict[str, Any]], current_focus: Optional[str]) -> Optional[str]:
    target = str(current_focus or "").strip()
    if not target:
        for item in sub_goals:
            if item.get("status") in {"open", "in_progress", "blocked"}:
                return str(item.get("id") or item.get("title"))
        return str(sub_goals[-1].get("id")) if sub_goals else None

    for item in sub_goals:
        if target == str(item.get("id")) or target.lower() == str(item.get("title") or "").strip().lower():
            return str(item.get("id") or item.get("title"))
    return _resolve_focus(sub_goals, None)


def _merge_sub_goals(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    title_to_existing = {
        str(item.get("title") or "").strip().lower(): item
        for item in existing
        if str(item.get("title") or "").strip()
    }
    merged: List[Dict[str, Any]] = []
    for index, item in enumerate(incoming, start=1):
        normalized = _normalize_sub_goal(item, index)
        existing_item = title_to_existing.get(normalized["title"].strip().lower())
        if existing_item:
            normalized["id"] = str(existing_item.get("id") or normalized["id"])
        merged.append(normalized)
    return merged or existing


def _complete_remaining_sub_goals(board: Dict[str, Any], completion_summary: Optional[str]) -> None:
    summary_text = _collapse_text(str(completion_summary or ""), limit=180) or "Closed with verified task completion."
    for item in board.get("sub_goals") or []:
        if str(item.get("status") or "").lower() == "done":
            continue
        item["status"] = "done"
        if not item.get("completion_reason"):
            item["completion_reason"] = "Closed with verified task completion."
        if not item.get("completion_evidence"):
            item["completion_evidence"] = summary_text


def _is_verification_like_sub_goal(item: Dict[str, Any]) -> bool:
    title = str(item.get("title") or "").strip().lower()
    return any(token in title for token in ("verify", "confirm", "check", "validate", "ensure"))


def _assistant_completion_summary(assistant_text: str) -> str:
    return _collapse_text(assistant_text, limit=260) or "Task completed."


def _planner_system_prompt() -> str:
    return (
        "You are EmploAI's task planner and progress monitor. "
        "You do not execute tools. You maintain a stable, high-level task board for a long-running computer task.\n"
        "Rules:\n"
        "- Keep the main goal stable unless the user request itself changed.\n"
        "- Do not prescribe low-level click-by-click methods. Split the task into durable sub-goals.\n"
        "- Preserve already-completed progress when it still fits.\n"
        "- Use only these sub-goal statuses: open, in_progress, done, blocked.\n"
        "- Blocked should be rare and should reflect a real user-dependent blocker only when the evidence supports it.\n"
        "- Return strict JSON only with this shape:\n"
        "{\"sub_goals\":[{\"title\":\"...\",\"status\":\"open\",\"completion_reason\":\"...\",\"completion_evidence\":\"...\"}],\"current_focus\":\"...\",\"plan_notes\":\"...\"}"
    )


def _planner_payload(
    session: Any,
    *,
    mode: str,
    board: Optional[Dict[str, Any]],
    recent_events: List[Dict[str, Any]],
    failure_report: Optional[Dict[str, Any]] = None,
    assistant_text: Optional[str] = None,
    reassessment_reason: Optional[str] = None,
) -> Dict[str, Any]:
    browser_context = getattr(session, "browser_task_context", None)
    environment = {
        "workspace": str(getattr(session, "workspace", "")),
        "system_info": _collapse_text(str(getattr(session, "system_info", "")), limit=1800),
        "browser_backend": getattr(browser_context, "backend", None) if browser_context else None,
        "real_chrome_required": bool(getattr(browser_context, "requires_real_chrome", False)) if browser_context else False,
        "model": str(getattr(session, "current_model", "")),
    }
    return {
        "mode": mode,
        "user_request": _clean_request_text(str(getattr(session, "last_user_message", "") or "")),
        "main_goal": str((board or {}).get("main_goal") or _clean_request_text(str(getattr(session, "last_user_message", "") or ""))),
        "environment": environment,
        "last_verified_state": (board or {}).get("verification_summary") or (board or {}).get("completion_summary"),
        "recent_tool_events": recent_events[-10:],
        "current_board": {
            "state": (board or {}).get("state"),
            "status": (board or {}).get("status"),
            "sub_goals": copy.deepcopy((board or {}).get("sub_goals") or []),
            "current_focus": (board or {}).get("current_focus"),
            "next_method": (board or {}).get("next_method"),
            "successful_methods": list((board or {}).get("successful_methods") or []),
            "failed_methods": list((board or {}).get("failed_methods") or []),
        } if board else None,
        "reassessment_reason": reassessment_reason,
        "failure_report": failure_report,
        "assistant_turn_summary": _collapse_text(str(assistant_text or ""), limit=400) or None,
    }


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    cleaned = str(text or "").strip()
    if not cleaned:
        return None
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


def _planner_model_supported(session: Any, model_name: str) -> bool:
    config = MODEL_CONFIGS.get(model_name, {})
    provider = str(config.get("provider", "unknown"))
    api = str(config.get("api", "chat"))
    if provider == "google":
        return getattr(session, "gemini_openai_client", None) is not None
    return provider in {"openai", "anthropic", "xai", "deepseek", "openrouter"} and api != "responses"


def _select_planner_model(session: Any) -> Optional[str]:
    configured = str(getattr(session, "planner_model", "") or "").strip()
    available = set(getattr(session, "get_available_models", lambda *_args, **_kwargs: [])(list(MODEL_CONFIGS.keys())))
    if configured and configured in available and _planner_model_supported(session, configured):
        return configured

    for candidate in _PLANNER_PREFERRED_MODELS:
        if candidate in available and _planner_model_supported(session, candidate):
            return candidate

    current = str(getattr(session, "current_model", "") or "").strip()
    if current and current in available and _planner_model_supported(session, current):
        return current
    return None


def _planner_fallback(board: Optional[Dict[str, Any]], *, user_message: str, assistant_text: Optional[str], reassessment_reason: Optional[str]) -> Dict[str, Any]:
    existing = copy.deepcopy((board or {}).get("sub_goals") or [])
    if not existing:
        existing = _default_sub_goals(user_message)
    normalized = [_normalize_sub_goal(item, index) for index, item in enumerate(existing, start=1)]

    if assistant_text:
        preview = _collapse_text(assistant_text, limit=180)
        if preview and normalized:
            current_focus = _resolve_focus(normalized, (board or {}).get("current_focus"))
            for item in normalized:
                item_id = str(item.get("id") or "")
                if item_id == str(current_focus or "") and item.get("status") == "open":
                    item["status"] = "in_progress"
                    item["completion_evidence"] = preview
                    break

    current_focus = _resolve_focus(normalized, (board or {}).get("current_focus"))
    return {
        "sub_goals": normalized,
        "current_focus": current_focus,
        "plan_notes": _collapse_text(reassessment_reason or assistant_text or "", limit=220) or None,
    }


def _planner_create_completion(model_name: str, provider: str, client: Any, prompt_payload: Dict[str, Any]) -> Optional[str]:
    system_prompt = _planner_system_prompt()
    user_prompt = json.dumps(prompt_payload, ensure_ascii=True, indent=2)
    model_id = MODEL_CONFIGS.get(model_name, {}).get("id", model_name)

    if provider in {"openai", "xai", "deepseek", "openrouter", "google"}:
        response = create_openai_completion(
            client,
            model_name=model_name,
            model_id=model_id,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=700,
        )
        content = response.choices[0].message.content if response.choices else ""
        return str(content or "")

    if provider == "anthropic":
        response = client.messages.create(
            model=model_id,
            max_tokens=700,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        parts = getattr(response, "content", None) or []
        if not parts:
            return None
        text_parts = [getattr(part, "text", "") for part in parts if getattr(part, "text", "")]
        return "\n".join(text_parts).strip() or None

    return None


def _planner_refresh(
    session: Any,
    *,
    board: Optional[Dict[str, Any]],
    mode: str,
    recent_events: List[Dict[str, Any]],
    failure_report: Optional[Dict[str, Any]] = None,
    assistant_text: Optional[str] = None,
    reassessment_reason: Optional[str] = None,
) -> Dict[str, Any]:
    payload = _planner_payload(
        session,
        mode=mode,
        board=board,
        recent_events=recent_events,
        failure_report=failure_report,
        assistant_text=assistant_text,
        reassessment_reason=reassessment_reason,
    )

    model_name = _select_planner_model(session)
    raw_text: Optional[str] = None
    if model_name:
        try:
            client, provider = session.get_client_for_specific_model(model_name)
            if client is not None:
                raw_text = _planner_create_completion(model_name, provider, client, payload)
        except Exception:
            raw_text = None

    parsed = _extract_json_object(raw_text or "")
    if not parsed:
        return _planner_fallback(
            board,
            user_message=str(getattr(session, "last_user_message", "") or (board or {}).get("source_message") or ""),
            assistant_text=assistant_text,
            reassessment_reason=reassessment_reason,
        )

    incoming_sub_goals = parsed.get("sub_goals")
    if not isinstance(incoming_sub_goals, list) or not incoming_sub_goals:
        return _planner_fallback(
            board,
            user_message=str(getattr(session, "last_user_message", "") or (board or {}).get("source_message") or ""),
            assistant_text=assistant_text,
            reassessment_reason=reassessment_reason,
        )

    sub_goals = _merge_sub_goals((board or {}).get("sub_goals") or [], incoming_sub_goals)
    current_focus = _resolve_focus(sub_goals, parsed.get("current_focus") or (board or {}).get("current_focus"))
    return {
        "sub_goals": sub_goals,
        "current_focus": current_focus,
        "plan_notes": _collapse_text(str(parsed.get("plan_notes") or ""), limit=220) or None,
    }


def _apply_planner_result(board: Dict[str, Any], plan: Dict[str, Any]) -> None:
    incoming_sub_goals = plan.get("sub_goals")
    if isinstance(incoming_sub_goals, list) and incoming_sub_goals:
        board["sub_goals"] = _merge_sub_goals(board.get("sub_goals") or [], incoming_sub_goals)
    board["current_focus"] = _resolve_focus(board.get("sub_goals") or [], plan.get("current_focus") or board.get("current_focus"))
    plan_notes = _collapse_text(str(plan.get("plan_notes") or ""), limit=220) or None
    if plan_notes:
        board["plan_notes"] = plan_notes


def _select_next_method(board: Dict[str, Any], *, family: Optional[str], failure_report: Dict[str, Any]) -> str:
    used = set(board.setdefault("used_runtime_methods", []))
    for candidate in _FAMILY_SIBLING_METHODS.get(str(family or ""), []):
        if candidate not in used:
            board["used_runtime_methods"].append(candidate)
            return candidate

    failure_summary = _collapse_text(str(failure_report.get("failure_summary") or ""), limit=220)
    method_label = _collapse_text(str(failure_report.get("method_label") or ""), limit=140) or "the current method"
    if family == "browser_dom":
        if "extension" in failure_summary.lower() or "real chrome" in failure_summary.lower() or "user chrome" in failure_summary.lower():
            fallback = "Switch to describe_screen plus atomic desktop actions for the user's live browser, and use ocr_screen only if exact coordinates are needed."
        else:
            fallback = "Re-observe the page and switch from DOM-first browser actions to visual discovery before another click or type attempt."
    elif family == "system_app_or_terminal" and any(token in method_label.lower() for token in ("launch", "open_app", "spotify", "chrome")):
        fallback = "Try an alternate app-launch path first, then use the browser version if the native app path is unavailable."
    elif family == "desktop_gui":
        fallback = "Switch to a fresh visual observation path and prefer keyboard navigation or OCR-guided coordinates instead of repeating the same desktop action."
    elif family == "workspace_code":
        fallback = "Inspect the surrounding files or run a verifying command before repeating the same code-edit path."
    elif family == "web_research":
        fallback = "Change the research source or query before retrying the same page."
    else:
        fallback = "Choose a materially different verified path and continue from the same goal without asking the user."

    board["used_runtime_methods"].append(fallback)
    return fallback


def _activation_summary(board: Dict[str, Any]) -> str:
    return _collapse_text(
        f"Managed task tracking started for a long-running multi-tool task. {board.get('progress_summary')}",
        limit=260,
    )


def _reassess_board_runtime(
    session: Any,
    board: Dict[str, Any],
    *,
    reason: str,
    failure_report: Optional[Dict[str, Any]] = None,
    recent_events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    board["state"] = "reassessing"
    board["status"] = "active"
    board["display_mode"] = "active"
    board["pending_reassessment_reason"] = _collapse_text(reason, limit=220) or "Reassessment requested."
    board["reassessment_count"] = int(board.get("reassessment_count") or 0) + 1
    board["last_reassessment_at"] = _now_iso()
    board["last_reassessment_turn_count"] = int(board.get("model_turn_count") or 0)

    plan = _planner_refresh(
        session,
        board=board,
        mode="reassess",
        recent_events=recent_events or list(board.get("recent_tool_events") or []),
        failure_report=failure_report,
        reassessment_reason=board["pending_reassessment_reason"],
    )
    _apply_planner_result(board, plan)

    family = str((failure_report or {}).get("family") or "")
    if not family:
        family = str((failure_report or {}).get("method_key") or "").split("|", 1)[0]
        family = _family_for_tool(family) or family
    board["next_method"] = _select_next_method(board, family=family or None, failure_report=failure_report or {})
    board["state"] = "active"
    board["pending_reassessment_reason"] = None
    board["updated_at"] = _now_iso()
    _set_progress_summary(board)
    summary = _collapse_text(
        f"Task reassessed. {board.get('progress_summary')} Next method: {board.get('next_method')}",
        limit=260,
    )
    _board_log(board, "reassess", summary)
    return {
        "summary": summary,
        "prompt_messages": [
            {
                "role": "system",
                "content": (
                    "The managed task board was reassessed by the runtime.\n"
                    f"Goal: {board.get('main_goal')}\n"
                    f"Current focus: {board.get('current_focus') or 'unset'}\n"
                    f"Next method: {board.get('next_method')}\n"
                    "Continue from this revised board immediately. Do not ask the user unless the blocker is credentials, 2FA, or account choice."
                ),
            }
        ],
    }


def _archive_board(board: Dict[str, Any], *, status: str, summary: str, blocked_reason: Optional[str] = None) -> None:
    archived_at = _now_iso()
    normalized_status = _normalize_status(status, default="interrupted", allowed=_TASK_STATUSES)
    summary_text = _collapse_text(summary, limit=260) or "Managed task archived."
    title_prefix = {
        "completed": "[x]",
        "blocked": "[!]",
        "interrupted": "[■]",
    }.get(normalized_status, "[x]")

    if normalized_status == "completed":
        _complete_remaining_sub_goals(board, summary_text)
        board["verification_status"] = "done"
    else:
        board["verification_status"] = _normalize_status(
            board.get("verification_status", "open"),
            default="open",
            allowed=_VERIFICATION_STATUSES,
        )

    board["state"] = "history_collapsed"
    board["status"] = normalized_status
    board["display_mode"] = "history_collapsed"
    board["completed_at"] = archived_at
    board["completion_summary"] = summary_text
    board["verification_summary"] = summary_text
    board["collapsed_title"] = f"{title_prefix} {board.get('main_goal')}"
    board["collapsed_completed_at"] = archived_at
    board["collapsed_completion_summary"] = summary_text
    board["pending_reassessment_reason"] = None
    board["blocked_reason"] = blocked_reason
    board["updated_at"] = archived_at
    _set_progress_summary(board)
    _board_log(board, normalized_status, summary_text)


def _collapse_completed_board(board: Dict[str, Any], completion_summary: str) -> None:
    _archive_board(board, status="completed", summary=completion_summary)


def archive_active_task_board(
    session: Any,
    *,
    status: str,
    summary: str,
    blocked_reason: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    board = get_active_task_board(session)
    if not board:
        return None
    _archive_board(board, status=status, summary=summary, blocked_reason=blocked_reason)
    session.active_task_id = None
    _prune_completed_boards(session)
    return board


def recover_stale_task_board(
    session: Any,
    *,
    summary: str = "The previous managed task ended before it could be closed cleanly.",
) -> Optional[Dict[str, Any]]:
    board = get_active_task_board(session)
    if not board:
        return None
    if bool(getattr(session, "is_processing", False)):
        return None
    return archive_active_task_board(session, status="interrupted", summary=summary)


def create_task_board(
    session: Any,
    *,
    user_message: Optional[str] = None,
    origin: str = "runtime_activation",
    channel: Optional[str] = None,
) -> Dict[str, Any]:
    ensure_task_board_state(session)
    task_text = user_message or getattr(session, "last_user_message", "") or "Carry out the requested task"
    created_at = _now_iso()
    board = {
        "task_id": _task_id(),
        "state": "active",
        "status": "active",
        "display_mode": "active",
        "origin": origin,
        "origin_channel": channel,
        "created_at": created_at,
        "updated_at": created_at,
        "completed_at": None,
        "main_goal": _clean_request_text(task_text),
        "goal_locked": True,
        "source_message": task_text,
        "last_user_request": task_text,
        "sub_goals": _default_sub_goals(task_text),
        "current_focus": "sg_1",
        "next_method": _default_next_method(),
        "successful_methods": [],
        "failed_methods": [],
        "used_runtime_methods": [],
        "observed_failures": {},
        "recent_tool_events": [],
        "turn_count": 0,
        "model_turn_count": 0,
        "tool_call_count": 0,
        "qualifying_tool_calls": 0,
        "reassessment_count": 0,
        "pending_reassessment_reason": None,
        "last_reassessment_at": None,
        "last_reassessment_turn_count": 0,
        "progress_markers": [],
        "latest_summary": None,
        "plan_notes": None,
        "completion_summary": None,
        "verification_status": "open",
        "verification_summary": None,
        "collapsed_title": None,
        "collapsed_completed_at": None,
        "collapsed_completion_summary": None,
        "last_failure_signature": None,
    }
    _set_progress_summary(board)
    _board_log(board, "created", f"Task tracking started for: {board['main_goal']}")
    session.task_history.append(board)
    session.active_task_id = board["task_id"]
    _prune_completed_boards(session)
    return board


def task_board_view(board: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not board:
        return None
    done, total = _progress_counts(board)
    raw_state = str(board.get("state", "active") or "active")
    raw_display_mode = str(board.get("display_mode", "active") or "active")
    if raw_state == "completed_collapsed":
        raw_state = "history_collapsed"
    if raw_display_mode == "completed_collapsed":
        raw_display_mode = "history_collapsed"
    return {
        "task_id": str(board.get("task_id") or ""),
        "status": _normalize_status(board.get("status", "active"), default="active", allowed=_TASK_STATUSES),
        "state": _normalize_status(raw_state, default="active", allowed=_TASK_STATES),
        "display_mode": _normalize_status(raw_display_mode, default="active", allowed=_DISPLAY_MODES),
        "main_goal": str(board.get("main_goal") or ""),
        "goal_locked": bool(board.get("goal_locked", True)),
        "sub_goals": [copy.deepcopy(item) for item in board.get("sub_goals") or []],
        "current_focus": board.get("current_focus"),
        "next_method": board.get("next_method"),
        "pending_reassessment_reason": board.get("pending_reassessment_reason"),
        "progress_summary": board.get("progress_summary"),
        "completed_sub_goals": done,
        "total_sub_goals": total,
        "turn_count": int(board.get("turn_count") or 0),
        "model_turn_count": int(board.get("model_turn_count") or 0),
        "tool_call_count": int(board.get("tool_call_count") or 0),
        "reassessment_count": int(board.get("reassessment_count") or 0),
        "latest_summary": board.get("latest_summary"),
        "completion_summary": board.get("completion_summary"),
        "verification_status": _normalize_status(
            board.get("verification_status", "open"),
            default="open",
            allowed=_VERIFICATION_STATUSES,
        ),
        "verification_summary": board.get("verification_summary"),
        "collapsed_title": board.get("collapsed_title"),
        "collapsed_completed_at": board.get("collapsed_completed_at"),
        "collapsed_completion_summary": board.get("collapsed_completion_summary"),
        "created_at": board.get("created_at"),
        "updated_at": board.get("updated_at"),
        "completed_at": board.get("completed_at"),
    }


def format_task_board_for_user(board: Optional[Dict[str, Any]]) -> str:
    if not board:
        return "No active managed task."

    view = task_board_view(board) or {}
    lines = [
        f"Goal: {view.get('main_goal', '(unknown)')}",
        f"Status: {view.get('status', 'active')}",
        f"Progress: {view.get('progress_summary', '0/0 sub-goals complete')}",
    ]
    current_focus = str(view.get("current_focus") or "").strip()
    if current_focus:
        lines.append(f"Current focus: {current_focus}")
    lines.append("")
    lines.append("Sub-goals:")
    for item in view.get("sub_goals") or []:
        status = str(item.get("status") or "open")
        marker = "[x]" if status == "done" else "[>]" if status == "in_progress" else "[!]" if status == "blocked" else "[ ]"
        line = f"{marker} {item.get('title', 'Untitled step')}"
        if item.get("completion_reason"):
            line += f" - {item['completion_reason']}"
        lines.append(line)
    verification_status = str(view.get("verification_status") or "open")
    verification_marker = "[x]" if verification_status == "done" else "[ ]"
    verification_line = f"{verification_marker} Verify the requested result and close the task"
    verification_summary = _collapse_text(str(view.get("verification_summary") or ""), limit=180)
    if verification_summary:
        verification_line += f" - {verification_summary}"
    lines.append(verification_line)
    if view.get("next_method"):
        lines.append("")
        lines.append(f"Next method: {view['next_method']}")
    if view.get("pending_reassessment_reason"):
        lines.append("")
        lines.append(f"Pending reassessment: {view['pending_reassessment_reason']}")
    if view.get("latest_summary"):
        lines.append("")
        lines.append(f"Latest update: {view['latest_summary']}")
    return "\n".join(lines)


def build_task_board_prompt(session: Any) -> str:
    board = get_active_task_board(session)
    if not board:
        return (
            "# MANAGED TASK BOARD RUNTIME\n"
            "- The managed task board is runtime-owned. You do NOT create or edit it directly.\n"
            "- The board appears only for long-running multi-tool tasks after the runtime confirms the task crossed the activation threshold.\n"
            "- Do NOT ask the user to continue just because a method failed. Keep working unless a true user-dependent blocker exists.\n"
            "- No managed task board is active right now, so task-board-only tools are unavailable for this turn.\n"
            "- For normal failures, keep trying materially different methods and let the runtime manage the board.\n"
            "- The runtime will create, reassess, and complete the board; you should focus on executing the task and reporting proof."
        )

    verification_status = _normalize_status(
        board.get("verification_status", "open"),
        default="open",
        allowed=_VERIFICATION_STATUSES,
    )
    state = str(board.get("state") or "active")
    blocker_line = (
        f"- User-dependent blocker: {_BLOCKER_LABELS.get(str(board.get('blocked_reason') or ''), str(board.get('blocked_reason') or ''))}"
        if state == "blocked_waiting_user"
        else "- User-dependent blocker: none"
    )
    return "\n".join(
        [
            "# ACTIVE MANAGED TASK BOARD",
            f"- Task ID: {board.get('task_id')}",
            f"- State: {state}",
            f"- Main goal: {board.get('main_goal')}",
            f"- Progress: {board.get('progress_summary')}",
            f"- Current focus: {board.get('current_focus') or '(unset)'}",
            f"- Next method: {board.get('next_method') or '(unset)'}",
            *[
                f"- Sub-goal {index + 1}: [{item.get('status', 'open')}] {item.get('title', '')}"
                for index, item in enumerate(board.get("sub_goals") or [])
            ],
            (
                f"- Final verifier gate: [{verification_status}] Verify the requested result and close the task"
                + (
                    f" - {board.get('verification_summary')}"
                    if board.get("verification_summary")
                    else ""
                )
            ),
            blocker_line,
            (
                f"- Reassessment reason: {board.get('pending_reassessment_reason')}"
                if board.get("pending_reassessment_reason")
                else "- Reassessment reason: none"
            ),
            f"- Do not try to edit this board. Only use {TASK_BOARD_INTERNAL_TOOL_NAME} when the same method has truly failed three times, or when the task needs credentials, 2FA, or account choice from the user.",
            "- Ask the user only for those true user-dependent blockers. For all other failures, continue autonomously.",
        ]
    )


def note_user_turn(session: Any, user_message: str) -> Optional[str]:
    session._task_board_candidate = None

    board = get_active_task_board(session)
    cleaned_message = str(user_message or "").strip()
    armed_next_turn = get_task_board_armed_next_turn(session)
    if armed_next_turn:
        set_task_board_armed_next_turn(session, False)
    turn_state: Dict[str, Any] = {
        "user_message": user_message,
        "qualifying_tool_calls": 0,
        "qualifying_tool_events": [],
        "board_task_id_at_start": str(board.get("task_id") or "") if board else None,
        "user_changed_active_board": False,
        "board_armed_next_turn": armed_next_turn,
    }

    if board is None and armed_next_turn:
        board = create_task_board(
            session,
            user_message=user_message,
            origin="armed_next_turn",
        )
        plan = _planner_refresh(
            session,
            board=board,
            mode="activation",
            recent_events=[],
        )
        _apply_planner_result(board, plan)
        board["next_method"] = _default_next_method()
        board["updated_at"] = _now_iso()
        _set_progress_summary(board)
        summary = _activation_summary(board)
        _board_log(board, "created", summary)
        _set_turn_state(session, turn_state)
        return summary

    if not board:
        _set_turn_state(session, turn_state)
        return None

    source_message = str(board.get("source_message") or "").strip()
    if cleaned_message and cleaned_message != source_message and not _is_continuation_message(cleaned_message):
        turn_state["user_changed_active_board"] = True
        board["source_message"] = user_message
        board["last_user_request"] = user_message
        board["main_goal"] = _clean_request_text(user_message)
        board["updated_at"] = _now_iso()
        result = _reassess_board_runtime(
            session,
            board,
            reason=f"User updated the active task request: {_collapse_text(user_message, limit=180)}",
            recent_events=list(board.get("recent_tool_events") or []),
        )
        _set_turn_state(session, turn_state)
        return result.get("summary")

    _set_turn_state(session, turn_state)
    board["turn_count"] = int(board.get("turn_count") or 0) + 1
    board["last_user_request"] = user_message
    board["updated_at"] = _now_iso()
    return None


def request_task_board_reassessment(session: Any, reason: str) -> Optional[Dict[str, Any]]:
    board = get_active_task_board(session)
    if not board:
        return None
    cleaned = _collapse_text(reason, limit=220) or "Manual reassessment requested."
    _reassess_board_runtime(
        session,
        board,
        reason=cleaned,
        recent_events=list(board.get("recent_tool_events") or []),
    )
    return task_board_view(board)


class SimpleNamespaceTaskBoard:
    def __init__(self, board: Dict[str, Any]) -> None:
        self._board = board

    def __getattr__(self, item: str) -> Any:
        if item == "task_history":
            return [self._board]
        if item == "active_task_id":
            return self._board.get("task_id")
        raise AttributeError(item)


def before_model_turn_messages(session: Any) -> List[Dict[str, str]]:
    board = get_active_task_board(session)
    if not board:
        return []

    board["model_turn_count"] = int(board.get("model_turn_count") or 0) + 1
    since_last_reassessment = board["model_turn_count"] - int(board.get("last_reassessment_turn_count") or 0)
    if since_last_reassessment >= TASK_BOARD_MODEL_TURN_THRESHOLD and str(board.get("state") or "") == "active":
        _reassess_board_runtime(
            session,
            board,
            reason=(
                f"{TASK_BOARD_MODEL_TURN_THRESHOLD} model turns have passed without closing the task. "
                "Reassess the method and revise the sub-goals before continuing."
            ),
            recent_events=list(board.get("recent_tool_events") or []),
        )

    messages = [
        {
            "role": "system",
            "content": build_task_board_prompt(SimpleNamespaceTaskBoard(board)),
        }
    ]
    if str(board.get("state") or "") == "blocked_waiting_user":
        blocked_reason = _BLOCKER_LABELS.get(str(board.get("blocked_reason") or ""), "A user-dependent blocker is active.")
        messages.append(
            {
                "role": "system",
                "content": (
                    "TASK BOARD BLOCKED WAITING USER:\n"
                    f"- {blocked_reason}\n"
                    "- Ask only for the missing user-dependent input, then continue once it is provided."
                ),
            }
        )
    return messages


def handle_tool_result(
    session: Any,
    *,
    tool_name: str,
    tool_args: Dict[str, Any],
    tool_result: Any,
    channel: Optional[str] = None,
) -> Dict[str, Any]:
    if tool_name == TASK_BOARD_INTERNAL_TOOL_NAME:
        return {
            "summary": None,
            "prompt_messages": [],
            "board": get_active_task_board(session),
            "completed_boards": completed_task_board_views(session),
            "created": False,
        }

    board = get_active_task_board(session)
    prompt_messages: List[Dict[str, str]] = []
    turn_state = _current_turn_state(session)

    if not _is_qualifying_tool(tool_name):
        return {
            "summary": None,
            "prompt_messages": [],
            "board": board,
            "completed_boards": completed_task_board_views(session),
            "created": False,
        }

    event = _tool_event(tool_name, tool_args, tool_result)
    source_message = getattr(session, "last_user_message", None) or (turn_state or {}).get("user_message")

    if turn_state is not None:
        turn_state["qualifying_tool_calls"] = int(turn_state.get("qualifying_tool_calls") or 0) + 1
        turn_state.setdefault("qualifying_tool_events", []).append(event)
        del turn_state["qualifying_tool_events"][:-20]

    if board is None:
        return {
            "summary": None,
            "prompt_messages": prompt_messages,
            "board": None,
            "completed_boards": completed_task_board_views(session),
            "created": False,
        }

    board["tool_call_count"] = int(board.get("tool_call_count") or 0) + 1
    board["qualifying_tool_calls"] = int(board.get("qualifying_tool_calls") or 0) + 1
    board.setdefault("recent_tool_events", []).append(event)
    del board["recent_tool_events"][:-30]
    board["updated_at"] = _now_iso()

    method_display = str(event.get("method_label") or tool_name)
    if event.get("success"):
        _append_unique(board.setdefault("successful_methods", []), method_display)
    else:
        _append_unique(board.setdefault("failed_methods", []), method_display)
        observed = board.setdefault("observed_failures", {})
        key = str(event.get("method_key") or tool_name)
        observed[key] = int(observed.get(key) or 0) + 1

    return {
        "summary": None,
        "prompt_messages": prompt_messages,
        "board": board,
        "completed_boards": completed_task_board_views(session),
        "created": False,
    }


def _failure_report_summary(blocker_type: str) -> str:
    if blocker_type in _BLOCKER_LABELS:
        return _BLOCKER_LABELS[blocker_type]
    return "A repeated method failure was reported."


def apply_task_board_failure_report(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    ensure_task_board_state(session)
    board = get_active_task_board(session)
    if not board:
        return {
            "ok": True,
            "task_id": None,
            "summary": "Managed task tracking is not active right now.",
            "board": None,
            "completed_boards": completed_task_board_views(session),
            "prompt_messages": [],
        }

    method_key = _collapse_text(str(args.get("method_key") or ""), limit=160) or "method"
    method_label = _collapse_text(str(args.get("method_label") or ""), limit=180) or method_key
    failure_summary = _collapse_text(str(args.get("failure_summary") or ""), limit=220) or "Method exhausted."
    attempt_count = int(args.get("attempt_count") or 0)
    state_changed = bool(args.get("state_changed"))
    blocker_type = _normalize_status(args.get("suspected_blocker_type", "none"), default="none", allowed=_BLOCKER_TYPES)
    family = _family_for_tool(method_key.split("|", 1)[0])

    signature = f"{method_key}|{failure_summary}|{attempt_count}|{blocker_type}|{int(state_changed)}"
    if signature == str(board.get("last_failure_signature") or ""):
        return {
            "ok": True,
            "task_id": board.get("task_id"),
            "summary": "Duplicate failure report ignored. Continue from the current reassessed board.",
            "board": task_board_view(board),
            "completed_boards": completed_task_board_views(session),
            "prompt_messages": [],
        }

    _append_unique(board.setdefault("failed_methods", []), method_label)
    board["last_failure_signature"] = signature
    board["updated_at"] = _now_iso()

    if attempt_count < TASK_BOARD_METHOD_FAILURE_THRESHOLD:
        summary = (
            f"Failure noted for {method_label}. "
            f"The runtime will not reassess until the retry threshold reaches {TASK_BOARD_METHOD_FAILURE_THRESHOLD}."
        )
        _board_log(board, "failure", summary)
        return {
            "ok": True,
            "task_id": board.get("task_id"),
            "summary": summary,
            "board": task_board_view(board),
            "completed_boards": completed_task_board_views(session),
            "prompt_messages": [],
        }

    if blocker_type in {"credentials", "2fa", "account_choice"}:
        blocked_summary = _failure_report_summary(blocker_type)
        archive_active_task_board(
            session,
            status="blocked",
            summary=blocked_summary,
            blocked_reason=blocker_type,
        )
        return {
            "ok": True,
            "task_id": board.get("task_id"),
            "summary": blocked_summary,
            "board": task_board_view(get_active_task_board(session)),
            "completed_boards": completed_task_board_views(session),
            "prompt_messages": [
                {
                    "role": "system",
                    "content": (
                        "The runtime marked this task as blocked waiting on the user.\n"
                        f"Reason: {blocked_summary}\n"
                        "Ask only for that missing user-dependent input, then continue."
                    ),
                }
            ],
        }

    result = _reassess_board_runtime(
        session,
        board,
        reason=(
            f"Method failed {attempt_count} times without success: {method_label}. "
            "Revise the board and continue with a materially different method."
        ),
        failure_report={
            "method_key": method_key,
            "method_label": method_label,
            "failure_summary": failure_summary,
            "attempt_count": attempt_count,
            "state_changed": state_changed,
            "suspected_blocker_type": blocker_type,
            "family": family,
        },
        recent_events=list(board.get("recent_tool_events") or []),
    )
    return {
        "ok": True,
        "task_id": board.get("task_id"),
        "summary": result["summary"],
        "board": task_board_view(board),
        "completed_boards": completed_task_board_views(session),
        "prompt_messages": result["prompt_messages"],
    }


def apply_task_board_update(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    """Legacy compatibility shim.

    The runtime now owns the task board. The main execution model should not call this.
    """
    board = get_active_task_board(session)
    return {
        "ok": True,
        "task_id": board.get("task_id") if board else None,
        "summary": (
            f"The task board is runtime-owned. Use {TASK_BOARD_INTERNAL_TOOL_NAME} only after the same method truly failed three times, "
            "or when credentials / 2FA / account choice from the user are required."
        ),
        "board": task_board_view(board),
        "completed_boards": completed_task_board_views(session),
    }


def _sync_board_progress_from_turn(
    session: Any,
    board: Dict[str, Any],
    *,
    assistant_text: str,
    recent_events: List[Dict[str, Any]],
) -> None:
    plan = _planner_refresh(
        session,
        board=board,
        mode="progress_sync",
        recent_events=recent_events,
        assistant_text=assistant_text,
    )
    _apply_planner_result(board, plan)
    if not board.get("next_method"):
        board["next_method"] = _default_next_method()
    board["updated_at"] = _now_iso()
    _set_progress_summary(board)
    if plan.get("plan_notes"):
        _board_log(board, "progress", str(plan["plan_notes"]))


def _can_runtime_complete_board(board: Dict[str, Any], assistant_text: str, external_tool_calls: int) -> bool:
    if external_tool_calls <= 0:
        return False
    if str(board.get("state") or "") != "active":
        return False
    if not _collapse_text(assistant_text, limit=260):
        return False
    sub_goals = list(board.get("sub_goals") or [])
    if not sub_goals:
        return False
    unfinished = [item for item in sub_goals if str(item.get("status") or "").lower() != "done"]
    if not unfinished:
        return True
    return all(_is_verification_like_sub_goal(item) for item in unfinished)


def finalize_task_board_turn(session: Any, assistant_text: str) -> Optional[Dict[str, Any]]:
    ensure_task_board_state(session)
    turn_state = _current_turn_state(session)
    session._task_board_candidate = None
    if not turn_state:
        return None

    board = get_active_task_board(session)
    summary: Optional[str] = None
    external_tool_calls = int(turn_state.get("qualifying_tool_calls") or 0)

    if board and str(board.get("state") or "") == "active" and external_tool_calls > 0:
        _sync_board_progress_from_turn(
            session,
            board,
            assistant_text=assistant_text,
            recent_events=list(turn_state.get("qualifying_tool_events") or []),
        )

    if board:
        if assistant_text:
            completion_summary = _assistant_completion_summary(assistant_text)
            archive_active_task_board(session, status="completed", summary=completion_summary)
            summary = completion_summary
        else:
            interruption_summary = "The managed task ended before a final assistant reply was produced."
            archive_active_task_board(session, status="interrupted", summary=interruption_summary)
            summary = interruption_summary

    result_board = get_active_task_board(session)
    completed_views = completed_task_board_views(session)
    _set_turn_state(session, None)
    if summary is None and result_board is None and not completed_views:
        return None
    return {
        "summary": summary,
        "board": result_board,
        "completed_boards": completed_views,
    }
