from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from anthropic import Anthropic

from bot_core.hooks import HookEvent, HookType
from cli.agent_tools.loop import LoopResult, run_tool_loop
from cli.tui_constants import MODEL_CONFIGS
from shared.artifact_store import ChatArtifactStore
from shared.channel_sync import get_channel_sync_hub
from shared.openai_api import create_openai_completion
from shared.session_timeline import (
    append_timeline_event,
    build_log_timeline_event,
    build_tool_timeline_event,
    create_timeline_event,
)
from shared.task_board import (
    TASK_BOARD_FAILURE_REPORT_TOOL,
    TASK_BOARD_INTERNAL_TOOL_NAME,
    apply_task_board_failure_report,
    archive_active_task_board,
    before_model_turn_messages,
    completed_task_board_views,
    finalize_task_board_turn,
    get_active_task_board,
    get_display_task_board,
    handle_tool_result,
    note_user_turn,
    task_board_view,
)
from shared.task_intent import is_screen_observation_message, is_task_like_message


EventSink = Callable[[Dict[str, Any]], Any]
PromptBuilder = Callable[[Any, str, str, str], str]
ToolHandlersBuilder = Callable[[Any], Dict[str, Callable[[Dict[str, Any]], Any]]]
ExtraToolsBuilder = Callable[[Any], List[Dict[str, Any]]]
SingleAgentInitializer = Callable[[asyncio.AbstractEventLoop], None]
AssistantContentTransform = Callable[[str], str]
FILE_SNAPSHOT_TOOL_NAMES = {"write_file", "edit_file", "append_file"}
COMMAND_OUTPUT_TOOL_NAMES = {"run_command", "execute_command", "run_background_command", "command_status"}
BROWSER_OBSERVATION_TOOL_NAMES = {"browser_snapshot", "observe_browser", "browser_read_text"}
VISUAL_SCREEN_TOOL_NAMES = {"describe_screen", "browser_screenshot"}
_NON_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
TEXT_PREVIEW_HEAD_CHARS = 900
TEXT_PREVIEW_TAIL_CHARS = 900


@dataclass
class TurnReservation:
    busy: bool = False
    task_id: int = 0
    session_id: Optional[str] = None
    is_session_start: bool = False
    context_compressed: bool = False
    context_compaction: Optional[Dict[str, Any]] = None
    event_meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SharedTurnResult:
    ok: bool = False
    busy: bool = False
    abandoned: bool = False
    session_id: Optional[str] = None
    assistant_text: str = ""
    raw_response: str = ""
    duration_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    context_compressed: bool = False
    context_compaction: Optional[Dict[str, Any]] = None


def _collapse_for_verifier(value: Any, *, limit: int = 1800) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
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


def _desktop_window_context_message(session: Any) -> Optional[Dict[str, str]]:
    allowed_tools = set(getattr(session, "current_turn_allowed_tool_names", None) or [])
    enabled_packs = set(getattr(session, "enabled_tool_packs", None) or [])
    if "observe_desktop" not in allowed_tools and "interactive_desktop" not in enabled_packs:
        return None
    try:
        from bot_core.system_info import format_active_windows_snapshot

        snapshot = format_active_windows_snapshot(limit=30)
    except Exception:
        snapshot = "Unavailable"
    if not str(snapshot or "").strip() or str(snapshot).strip() == "Unavailable":
        return None
    return {
        "role": "system",
        "content": (
            "LIVE DESKTOP WINDOW SNAPSHOT (fresh before this model turn):\n"
            f"{snapshot}\n"
            "- Use exact visible window titles from this snapshot with focus_window when a target is already open.\n"
            "- Before typing, clicking, or sending a hotkey, make sure the intended target window is active or explicitly focus it.\n"
            "- If the active window is a system power/shutdown, lock, sign-out, or unrelated user window, do not continue the task through that window; first dismiss or avoid it safely and re-observe.\n"
            "- Do not use broad close shortcuts such as Alt+F4 for ambiguous cleanup. Prefer close_window with an exact target title, Escape/Cancel for a visible modal, or another targeted route."
        ),
    }


def _task_contract_context_message(session: Any) -> Optional[Dict[str, str]]:
    user_request = _collapse_for_verifier(getattr(session, "last_user_message", ""), limit=900)
    if not user_request:
        return None
    if not (is_screen_observation_message(user_request) or is_task_like_message(user_request)):
        return None

    allowed_tools = set(getattr(session, "current_turn_allowed_tool_names", None) or [])
    enabled_packs = set(getattr(session, "enabled_tool_packs", None) or [])
    if not allowed_tools and not enabled_packs:
        return None

    return {
        "role": "system",
        "content": (
            "CURRENT TASK CONTRACT (fresh before this model turn):\n"
            f"User request: {user_request}\n"
            "- Treat the request above as the active completion contract for this turn.\n"
            "- Finish only when the requested observable end state is true and verified in the relevant surface. "
            "Artifacts, intentions, typed paths, file reads, or host-app launches are not enough for visible UI/open/send tasks.\n"
            "- For local file open/show tasks, prefer open_file or a direct OS/app file-open command with the exact resolved path; "
            "use GUI Open dialogs only as a fallback and abandon them if they do not change visible state.\n"
            "- If the last route failed or produced no useful state change, re-observe or inspect state, classify what failed, "
            "then switch method family/tool surface unless new evidence makes retrying materially different.\n"
            "- User-directed work in communication/account apps is allowed, including WhatsApp, Gmail, Microsoft apps, email, messaging, "
            "calendar, and collaboration platforms. Proceed after verifying recipient/account/target identity and intended content/action; "
            "personal-account or communication context by itself is not a blocker."
        ),
    }


def _planner_verifier_system_prompt() -> str:
    return (
        "You are a final-answer verifier for an autonomous desktop agent. "
        "Your job is to decide whether the assistant's candidate final answer can be shown to the user. "
        "Infer the task-specific success obligations from the original user request. "
        "Use tool evidence as proof; do not treat the assistant final answer as proof by itself. "
        "If an obligation required visible UI state, message sending, file opening, browser navigation, or a running app, "
        "require concrete tool evidence for that state. "
        "If safe useful tool actions remain, choose retry. "
        "Choose true_blocker only when the evidence shows the task cannot safely proceed without user action, login, identity choice, "
        "missing app/account state, or external state not available to the agent. "
        "Do not classify a user-directed task inside the user's personal apps/accounts as blocked solely because the app/account is personal. "
        "This includes WhatsApp, Gmail, Microsoft apps, email, messaging, calendar, and collaboration platforms. "
        "The safety obligation is verified recipient/account/target identity and intended content/action. "
        "Return only strict JSON with keys: action, reason, failed_obligation, evidence_gap, retry_instruction, must_use_tool. "
        "action must be one of allow, retry, true_blocker. must_use_tool must be boolean."
    )


def _planner_verifier_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    trace = []
    for item in list(payload.get("tool_trace") or [])[-28:]:
        if not isinstance(item, dict):
            continue
        trace.append(
            {
                "tool": _collapse_for_verifier(item.get("tool"), limit=80),
                "args": _collapse_for_verifier(item.get("args"), limit=450),
                "result": _collapse_for_verifier(item.get("result"), limit=1200),
            }
        )
    return {
        "original_user_request": _collapse_for_verifier(payload.get("user_request"), limit=1600),
        "candidate_final_answer": _collapse_for_verifier(payload.get("assistant_final"), limit=1800),
        "tool_trace": trace,
        "decision_instructions": {
            "allow": "All material obligations are supported by evidence, or a true blocker is explicitly classified separately.",
            "retry": "A material obligation lacks evidence and at least one safe useful tool action remains.",
            "true_blocker": "The evidence shows the agent cannot proceed safely without user/external action.",
        },
    }


def _planner_model_for_final_verifier(session: Any) -> str:
    configured = str(getattr(session, "planner_model", "") or "").strip()
    default = str(getattr(session, "default_planner_model", "") or "").strip()
    current = str(getattr(session, "current_model", "") or "").strip()
    return configured or default or current


def _planner_final_completion(session: Any, *, prompt_payload: Dict[str, Any]) -> Optional[str]:
    model_name = _planner_model_for_final_verifier(session)
    if not model_name:
        return None
    try:
        client, provider = session.get_client_for_specific_model(model_name)
    except Exception:
        return None
    if client is None:
        return None

    model_id = MODEL_CONFIGS.get(model_name, {}).get("id", model_name)
    system_prompt = _planner_verifier_system_prompt()
    user_prompt = json.dumps(prompt_payload, ensure_ascii=True, indent=2)

    try:
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
            return str(response.choices[0].message.content or "") if response.choices else None

        if provider == "anthropic":
            response = client.messages.create(
                model=model_id,
                max_tokens=700,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            parts = getattr(response, "content", None) or []
            text_parts = [getattr(part, "text", "") for part in parts if getattr(part, "text", "")]
            return "\n".join(text_parts).strip() or None
    except Exception:
        return None
    return None


def _planner_final_verdict(session: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    prompt_payload = _planner_verifier_payload(payload)
    raw = _planner_final_completion(session, prompt_payload=prompt_payload)
    parsed = _extract_json_object(raw or "") or {}
    action = str(parsed.get("action") or "allow").strip().lower()
    if action not in {"allow", "retry", "true_blocker"}:
        action = "allow"

    failed_obligation = _collapse_for_verifier(parsed.get("failed_obligation"), limit=240)
    evidence_gap = _collapse_for_verifier(parsed.get("evidence_gap"), limit=400)
    reason = _collapse_for_verifier(parsed.get("reason") or failed_obligation or "planner_final_verifier", limit=400)
    retry_instruction = _collapse_for_verifier(parsed.get("retry_instruction"), limit=900)
    must_use_tool = bool(parsed.get("must_use_tool", action == "retry"))

    if action == "retry":
        original_request = _collapse_for_verifier(prompt_payload.get("original_user_request"), limit=900)
        instruction_parts = [
            "[Hidden runtime continuation: your previous answer was not shown to the user.]",
            "A planner verifier found the user's task is not sufficiently evidenced yet.",
        ]
        if original_request:
            instruction_parts.append(f"Original user request still active: {original_request}")
        if failed_obligation:
            instruction_parts.append(f"Failed obligation: {failed_obligation}.")
        if evidence_gap:
            instruction_parts.append(f"Evidence gap: {evidence_gap}.")
        if retry_instruction:
            instruction_parts.append(f"Next action: {retry_instruction}")
        instruction_parts.append(
            "Continue the original task from the current state. Do not ask whether to continue. "
            "Use a safe, materially useful tool action before final-answering, then verify the result. "
            "Treat the user's requested observable end state as the success criterion. "
            "Do not repeat the same failed method loop; switch method family/tool surface unless new evidence makes the retry materially different."
        )
        continuation_instruction = " ".join(instruction_parts)
    else:
        continuation_instruction = ""

    return {
        "action": "continue" if action == "retry" else "allow",
        "reason": f"planner_{action}:{reason}",
        "failed_obligation": failed_obligation,
        "evidence_gap": evidence_gap,
        "retry_instruction": continuation_instruction,
        "continuation_instruction": continuation_instruction,
        "must_use_tool": must_use_tool,
    }


def merge_openai_tools(*tool_groups: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for group in tool_groups:
        for tool in group or []:
            func = tool.get("function", {})
            name = func.get("name")
            if not name or name in seen:
                continue
            merged.append(tool)
            seen.add(name)
    return merged


def current_session_id(session: Any) -> Optional[str]:
    if not getattr(session, "session_manager", None):
        return None
    return session.session_manager.get_current_session_id()


def compact_session_history(
    session: Any,
    *,
    reason: str = "manual",
    announce: bool = False,
    event_meta: Optional[Dict[str, Any]] = None,
):
    context_manager = getattr(session, "context_manager", None)
    if not context_manager:
        return None

    model_id = session.current_model or "claude-sonnet-4-5"
    result = context_manager.compact(
        session.chat_history,
        model_id,
        reason=reason,
    )
    if result.applied:
        session.chat_history = result.messages
        if hasattr(session, "message_id_map"):
            rebuilt_map: Dict[int, int] = {}
            for index, message in enumerate(session.chat_history):
                message_id = message.get("message_id")
                if message_id is not None:
                    rebuilt_map[message_id] = index
            session.message_id_map = rebuilt_map
        session.last_context_compaction = _compaction_metadata(result)
        if announce:
            _publish_compaction_status(session, result, event_meta=event_meta)
    return result


def _publish_compaction_status(session: Any, result: Any, *, event_meta: Optional[Dict[str, Any]] = None) -> None:
    if not result:
        return

    _append_and_publish_timeline_event(
        session,
        event=create_timeline_event(
            kind="compaction",
            title="Context Compaction",
            content=result.message,
            tone="accent",
            channel=(event_meta or {}).get("channel"),
            source_format=(event_meta or {}).get("source_format"),
            metadata=_compaction_metadata(result),
        ),
        event_meta=event_meta,
    )
    _publish_sync_event(
        session,
        _turn_sync_event(
            event_type="status",
            session_id=current_session_id(session),
            payload={"message": result.message},
            event_meta=event_meta or {},
        ),
    )


def _compaction_metadata(result: Any) -> Dict[str, Any]:
    payload = dict(result.to_dict())
    payload.pop("messages", None)
    return payload


async def _emit_event(event_sink: Optional[EventSink], event: Dict[str, Any]) -> None:
    if not event_sink:
        return
    maybe = event_sink(event)
    if asyncio.iscoroutine(maybe):
        await maybe


def _publish_sync_event(session: Any, event: Dict[str, Any]) -> None:
    user_id = getattr(session, "user_id", None)
    if user_id is None:
        return
    get_channel_sync_hub().publish(user_id=user_id, event=event)


def _message_sync_event(
    *,
    event_type: str,
    session_id: Optional[str],
    message: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "type": event_type,
        "session_id": session_id,
        "origin_channel": message.get("channel"),
        "source_client_id": message.get("source_client_id"),
        "payload": {
            "message": message,
            "text": message.get("content", ""),
        },
    }


def _turn_sync_event(
    *,
    event_type: str,
    session_id: Optional[str],
    payload: Optional[Dict[str, Any]] = None,
    event_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    meta = dict(event_meta or {})
    return {
        "type": event_type,
        "session_id": session_id,
        "origin_channel": meta.get("channel"),
        "source_client_id": meta.get("source_client_id"),
        "payload": payload or {},
    }


def _task_board_sync_event(
    *,
    session_id: Optional[str],
    board: Optional[Dict[str, Any]],
    completed_boards: Optional[List[Dict[str, Any]]] = None,
    summary: Optional[str],
    event_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return _turn_sync_event(
        event_type="task_board",
        session_id=session_id,
        payload={
            "board": task_board_view(board),
            "completed_task_boards": list(completed_boards or []),
            "summary": summary or (board or {}).get("latest_summary"),
        },
        event_meta=event_meta,
    )


def _timeline_sync_event(
    *,
    session_id: Optional[str],
    event: Dict[str, Any],
    event_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return _turn_sync_event(
        event_type="timeline_event",
        session_id=session_id,
        payload={"event": event},
        event_meta=event_meta,
    )


def _append_and_publish_timeline_event(
    session: Any,
    *,
    event: Dict[str, Any],
    event_meta: Optional[Dict[str, Any]] = None,
    save_session: bool = False,
) -> Dict[str, Any]:
    stored = append_timeline_event(session, event=event)
    if save_session:
        session.save_session()
    _publish_sync_event(
        session,
        _timeline_sync_event(
            session_id=current_session_id(session),
            event=stored,
            event_meta=event_meta,
        ),
    )
    return stored


def _memory_context(session: Any) -> str:
    if not getattr(session, "session_context", None):
        return ""
    if not getattr(session.session_context, "can_access_memory", False):
        return ""
    memory_manager = getattr(session, "memory_manager", None)
    if not memory_manager:
        return ""

    session_id = current_session_id(session)
    build_prompt_context = getattr(memory_manager, "build_prompt_context", None)
    if callable(build_prompt_context):
        return build_prompt_context(
            session_id=session_id,
            recent_days=7,
            recent_chars=3000,
            long_term_chars=4000,
        )

    get_long_term_context = getattr(memory_manager, "get_long_term_context", None)
    if callable(get_long_term_context):
        return get_long_term_context()
    return ""


def _build_file_context(pending_files: List[Dict[str, Any]]) -> str:
    if not pending_files:
        return ""

    safe_files: List[Dict[str, Any]] = []
    for item in pending_files:
        safe_item = dict(item)
        if "image_base64" in safe_item:
            safe_item["image_base64"] = "[omitted - stored]"
        safe_files.append(safe_item)

    file_context = json.dumps(safe_files, indent=2)
    if len(file_context) > 8000:
        file_context = file_context[:7800] + "\n... [truncated]"
    return file_context


def _artifact_store_for_session(session: Any, *, session_id: Optional[str] = None) -> Optional[ChatArtifactStore]:
    user_id = getattr(session, "user_id", None)
    resolved_session_id = str(session_id or current_session_id(session) or "").strip()
    if user_id is None or not resolved_session_id:
        return None
    return ChatArtifactStore(user_id=int(user_id), session_id=resolved_session_id)


def _sanitize_artifact_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, item in value.items():
            if key in {"image_base64", "base64", "image_data", "data"} and isinstance(item, str):
                cleaned[key] = f"[omitted image data: {len(item)} chars]"
            else:
                cleaned[str(key)] = _sanitize_artifact_metadata(item)
        return cleaned
    if isinstance(value, list):
        return [_sanitize_artifact_metadata(item) for item in value[:80]]
    return value


def _artifact_summary_payload(store: ChatArtifactStore, artifact_id: str) -> Optional[Dict[str, Any]]:
    record = store.get_record(artifact_id)
    if not record:
        return None
    return store.build_summary_view(record)


def _publish_artifact_created(
    session: Any,
    *,
    reservation: TurnReservation,
    store: Optional[ChatArtifactStore],
    artifact_ids: List[str],
    schedule_emit: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> None:
    if not store or not artifact_ids:
        return
    artifacts = [
        summary
        for artifact_id in artifact_ids
        for summary in [_artifact_summary_payload(store, artifact_id)]
        if summary is not None
    ]
    if not artifacts:
        return
    _publish_sync_event(
        session,
        _turn_sync_event(
            event_type="artifact_created",
            session_id=reservation.session_id,
            payload={"artifacts": artifacts},
            event_meta=reservation.event_meta,
        ),
    )
    if schedule_emit:
        schedule_emit({"type": "artifact_created", "artifacts": artifacts})


def _workspace_relative_text(session: Any, path: Path) -> str:
    workspace = str(getattr(session, "workspace", "") or "").strip()
    if not workspace:
        return path.name
    try:
        return str(path.resolve().relative_to(Path(workspace).expanduser().resolve())).replace("\\", "/")
    except Exception:
        return str(path)


def _resolve_workspace_path(session: Any, path_value: Optional[str]) -> Optional[Path]:
    text = str(path_value or "").strip()
    if not text:
        return None
    workspace = str(getattr(session, "workspace", "") or "").strip()
    try:
        candidate = Path(text).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()
        if workspace:
            return (Path(workspace).expanduser().resolve() / candidate).resolve()
        return candidate.resolve()
    except Exception:
        return None


def _track_mutated_file_path(
    touched_file_paths: set[Path],
    session: Any,
    *,
    tool_name: str,
    tool_args: Dict[str, Any],
    tool_result: Any,
) -> None:
    if tool_name not in FILE_SNAPSHOT_TOOL_NAMES:
        return
    candidate = None
    if isinstance(tool_result, dict):
        candidate = tool_result.get("path")
    if not candidate:
        candidate = tool_args.get("path")
    resolved = _resolve_workspace_path(session, str(candidate or ""))
    if resolved is not None:
        touched_file_paths.add(resolved)


def _command_output_text(command: str, tool_result: Any, *, cwd: Optional[str] = None) -> str:
    if isinstance(tool_result, dict):
        stdout = str(tool_result.get("stdout") or "")
        stderr = str(tool_result.get("stderr") or "")
        exit_code = tool_result.get("exit_code")
        error = str(tool_result.get("error") or "")
        lines = [f"$ {command or '[command omitted]'}"]
        if cwd:
            lines.append(f"[cwd] {cwd}")
        if exit_code is not None:
            lines.append(f"[exit_code] {exit_code}")
        if error:
            lines.append(f"[error]\n{error}")
        if stdout:
            lines.append(f"[stdout]\n{stdout}")
        if stderr:
            lines.append(f"[stderr]\n{stderr}")
        return "\n\n".join(lines)
    return f"$ {command or '[command omitted]'}\n\n{str(tool_result or '')}"


def _artifact_preview_for_command(command: str, tool_result: Any) -> str:
    if isinstance(tool_result, dict):
        stdout = str(tool_result.get("stdout") or "")
        stderr = str(tool_result.get("stderr") or "")
        tail = "\n".join(part for part in [stdout[-700:], stderr[-500:]] if part)
        return f"$ {command or '[command omitted]'}\n\n{tail}".strip()
    return f"$ {command or '[command omitted]'}\n\n{str(tool_result or '')}".strip()


def _safe_slug(value: str, *, fallback: str = "artifact") -> str:
    slug = _NON_FILENAME_RE.sub("-", str(value or "").strip()).strip("-.")
    return slug[:80] or fallback


def _preview_text(
    value: str,
    *,
    head_chars: int = TEXT_PREVIEW_HEAD_CHARS,
    tail_chars: int = TEXT_PREVIEW_TAIL_CHARS,
) -> str:
    text = str(value or "")
    if len(text) <= head_chars + tail_chars + 64:
        return text
    omitted = len(text) - head_chars - tail_chars
    return f"{text[:head_chars]}\n\n...[middle truncated: {omitted} chars]...\n\n{text[-tail_chars:]}"


def _serialize_search_text(*parts: Any) -> str:
    text_parts: List[str] = []
    for part in parts:
        if not part:
            continue
        if isinstance(part, dict):
            text_parts.append(json.dumps(part, ensure_ascii=False, default=str))
        elif isinstance(part, (list, tuple)):
            text_parts.append(json.dumps(list(part), ensure_ascii=False, default=str))
        else:
            text_parts.append(str(part))
    return "\n".join(item for item in text_parts if item)


def _artifact_text_for_browser_observation(tool_name: str, tool_result: Any) -> str:
    if isinstance(tool_result, dict):
        if tool_name == "browser_read_text":
            page_text = str(tool_result.get("text") or "").strip()
            title = str(tool_result.get("title") or "").strip()
            url = str(tool_result.get("url") or "").strip()
            selector = str(tool_result.get("selector") or "").strip()
            mode = str(tool_result.get("mode") or tool_result.get("backend") or "").strip()
            prefix_lines = [
                item
                for item in [
                    f"Title: {title}" if title else "",
                    f"URL: {url}" if url else "",
                    f"Selector: {selector or '<page body>'}",
                    f"Mode: {mode}" if mode else "",
                ]
                if item
            ]
            if page_text:
                prefix_lines.append("")
                prefix_lines.append(page_text)
                return "\n".join(prefix_lines).strip()
        formatted = str(tool_result.get("formatted") or "").strip()
        if formatted:
            return formatted
        return json.dumps(_sanitize_artifact_metadata(tool_result), ensure_ascii=False, indent=2, default=str)
    return str(tool_result or "")


def _artifact_text_for_ocr(tool_result: Any) -> str:
    if isinstance(tool_result, dict):
        plain = str(tool_result.get("plain_text") or tool_result.get("unfiltered_text") or "").strip()
        if plain:
            return plain
        elements = list(tool_result.get("elements", []) or [])
        sample = []
        for item in elements[:120]:
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                if text:
                    sample.append(text)
        return "\n".join(sample)
    return str(tool_result or "")


def _capture_tool_artifact_ids(
    session: Any,
    *,
    store: Optional[ChatArtifactStore],
    tool_name: str,
    tool_args: Dict[str, Any],
    tool_result: Any,
    task_id: Optional[int],
) -> List[str]:
    if not store:
        return []

    metadata = {
        "tool_args": _sanitize_artifact_metadata(tool_args),
        "tool_result": _sanitize_artifact_metadata(tool_result),
    }
    artifact_ids: List[str] = []
    workspace = str(getattr(session, "workspace", "") or "").strip() or None
    task_id_text = str(task_id) if task_id is not None else None

    if tool_name in COMMAND_OUTPUT_TOOL_NAMES:
        command = str(tool_args.get("command") or tool_args.get("cmd") or "").strip()
        cwd = str(tool_args.get("cwd") or "").strip() or None
        text = _command_output_text(command, tool_result, cwd=cwd)
        created = store.create_text_artifact(
            artifact_kind="command_output",
            title=f"Command output: {command or tool_name}",
            text=text,
            source_kind="agent",
            payload_file_name=f"{tool_name}-{_safe_command_filename(command)}.txt",
            summary_text=text,
            preview_text=_artifact_preview_for_command(command, tool_result),
            search_text=json.dumps({"command": command, "cwd": cwd, "result": _sanitize_artifact_metadata(tool_result)}, ensure_ascii=False, default=str),
            source_tool=tool_name,
            source_command=command or None,
            workspace=workspace,
            task_id=task_id_text,
            metadata=metadata,
        )
        artifact_ids.append(created.artifact_id)
        return artifact_ids

    if tool_name == "describe_screen" and isinstance(tool_result, dict):
        description = str(tool_result.get("description") or "").strip()
        question = str(tool_result.get("question") or "").strip()
        summary_text = "\n".join(item for item in [description, f"Question: {question}" if question else ""] if item).strip()
        image_base64 = str(tool_result.get("image_base64") or "").strip()
        if image_base64:
            created = store.create_base64_image_artifact(
                artifact_kind="screenshot",
                title="Screen capture",
                image_base64=image_base64,
                source_kind="agent",
                payload_file_name="screen-capture.png",
                summary_text=summary_text or "Screen capture artifact",
                preview_text=summary_text or "Screen capture artifact",
                search_text=_serialize_search_text(summary_text, metadata),
                source_tool=tool_name,
                workspace=workspace,
                task_id=task_id_text,
                metadata=metadata,
            )
        else:
            created = store.create_text_artifact(
                artifact_kind="screen_description",
                title="Screen description",
                text=summary_text or json.dumps(metadata, ensure_ascii=False, indent=2, default=str),
                source_kind="agent",
                source_tool=tool_name,
                workspace=workspace,
                task_id=task_id_text,
                metadata=metadata,
            )
        artifact_ids.append(created.artifact_id)
        return artifact_ids

    if tool_name == "ocr_screen":
        text = _artifact_text_for_ocr(tool_result)
        if text.strip():
            created = store.create_text_artifact(
                artifact_kind="ocr_text",
                title="OCR screen text",
                text=text,
                source_kind="agent",
                summary_text=text,
                preview_text=_preview_text(text, head_chars=700, tail_chars=450),
                search_text=_serialize_search_text(text, metadata),
                source_tool=tool_name,
                workspace=workspace,
                task_id=task_id_text,
                metadata=metadata,
            )
            artifact_ids.append(created.artifact_id)
        return artifact_ids

    if tool_name == "observe_desktop":
        text = str(tool_result or "").strip()
        if text:
            created = store.create_text_artifact(
                artifact_kind="screen_description",
                title="Desktop observation",
                text=text,
                source_kind="agent",
                source_tool=tool_name,
                workspace=workspace,
                task_id=task_id_text,
                metadata=metadata,
            )
            artifact_ids.append(created.artifact_id)
        return artifact_ids

    if tool_name in BROWSER_OBSERVATION_TOOL_NAMES:
        text = _artifact_text_for_browser_observation(tool_name, tool_result)
        if text.strip():
            title = "Browser observation"
            if isinstance(tool_result, dict):
                page_title = str(tool_result.get("title") or "").strip()
                if tool_name == "browser_read_text":
                    title = f"Browser text: {page_title}" if page_title else "Browser text extract"
                elif page_title:
                    title = f"Browser observation: {page_title}"
            created = store.create_text_artifact(
                artifact_kind="browser_observation",
                title=title,
                text=text,
                source_kind="agent",
                source_tool=tool_name,
                workspace=workspace,
                task_id=task_id_text,
                metadata=metadata,
            )
            artifact_ids.append(created.artifact_id)
        return artifact_ids

    if tool_name == "browser_screenshot" and isinstance(tool_result, dict):
        image_base64 = str(tool_result.get("image_base64") or "").strip()
        title = str(tool_result.get("title") or "").strip() or "Browser screenshot"
        url = str(tool_result.get("url") or "").strip()
        summary_text = "\n".join(item for item in [title, url] if item).strip() or "Browser screenshot"
        if image_base64:
            created = store.create_base64_image_artifact(
                artifact_kind="browser_screenshot",
                title=title if title.startswith("Browser") else f"Browser screenshot: {title}",
                image_base64=image_base64,
                source_kind="agent",
                payload_file_name="browser-screenshot.png",
                summary_text=summary_text,
                preview_text=summary_text,
                search_text=_serialize_search_text(summary_text, metadata),
                source_tool=tool_name,
                workspace=workspace,
                task_id=task_id_text,
                metadata=metadata,
            )
            artifact_ids.append(created.artifact_id)
        return artifact_ids

    return artifact_ids


def _safe_command_filename(command: str) -> str:
    return _safe_slug(command[:80] if command else "command-output", fallback="command-output")


def _snapshot_touched_file_artifact_ids(
    session: Any,
    *,
    store: Optional[ChatArtifactStore],
    touched_file_paths: set[Path],
    task_id: Optional[int],
) -> List[str]:
    if not store or not touched_file_paths:
        return []
    artifact_ids: List[str] = []
    workspace = str(getattr(session, "workspace", "") or "").strip() or None
    task_id_text = str(task_id) if task_id is not None else None
    for path in sorted(touched_file_paths, key=lambda item: str(item)):
        try:
            resolved = path.resolve()
        except Exception:
            continue
        if not resolved.exists() or not resolved.is_file():
            continue
        file_path = _workspace_relative_text(session, resolved)
        mime_type, _ = mimetypes.guess_type(str(resolved))
        try:
            raw = resolved.read_bytes()
        except Exception:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = None
        if text is not None:
            created = store.create_text_artifact(
                artifact_kind="file_snapshot",
                title=f"File snapshot: {file_path}",
                text=text,
                mime_type=(mime_type or "text/plain; charset=utf-8"),
                source_kind="agent",
                payload_file_name=resolved.name,
                summary_text=text,
                preview_text=_preview_text(text),
                search_text=text,
                file_path=file_path,
                workspace=workspace,
                task_id=task_id_text,
                metadata={"final_per_turn": True, "path": file_path},
            )
        else:
            created = store.create_bytes_artifact(
                artifact_kind="file_snapshot",
                title=f"File snapshot: {file_path}",
                data=raw,
                mime_type=(mime_type or "application/octet-stream"),
                source_kind="agent",
                payload_file_name=resolved.name,
                summary_text=file_path,
                preview_text=file_path,
                search_text=file_path,
                file_path=file_path,
                workspace=workspace,
                task_id=task_id_text,
                metadata={"final_per_turn": True, "path": file_path},
            )
        artifact_ids.append(created.artifact_id)
    return artifact_ids


async def begin_chat_turn(
    session: Any,
    *,
    user_message: str,
    user_message_payload: Optional[Dict[str, Any]] = None,
) -> TurnReservation:
    payload = dict(user_message_payload or {})

    async with session.lock:
        if session.is_processing:
            return TurnReservation(busy=True, session_id=current_session_id(session))

        session.current_task_id += 1
        task_id = session.current_task_id
        session.start_browser_task(task_id, user_message)
        session.should_interrupt = False
        session.is_processing = True

        timestamp = datetime.now().isoformat()
        message = {
            "role": "user",
            "content": user_message,
            "timestamp": timestamp,
        }
        message.update(payload)

        session.last_user_message = user_message
        session.chat_history.append(message)
        task_board_summary = note_user_turn(session, user_message)

        message_id = payload.get("message_id")
        if message_id is not None and hasattr(session, "message_id_map"):
            session.message_id_map[message_id] = len(session.chat_history) - 1

        is_session_start = len(session.chat_history) == 1
        if is_session_start:
            session.refresh_system_info()

        context_compressed = False
        context_compaction: Optional[Dict[str, Any]] = None
        if getattr(session, "context_manager", None):
            model_id = session.current_model or "claude-sonnet-4-5"
            if session.context_manager.needs_compression(session.chat_history, model_id):
                compaction_result = compact_session_history(session, reason="auto_pre_turn")
                if compaction_result and compaction_result.applied:
                    context_compressed = True
                    context_compaction = _compaction_metadata(compaction_result)
                    _publish_compaction_status(session, compaction_result)

        session.save_session()
        _publish_sync_event(
            session,
            _message_sync_event(
                event_type="user_message",
                session_id=current_session_id(session),
                message=message,
            ),
        )
        if task_board_summary:
            _publish_sync_event(
                session,
                _task_board_sync_event(
                    session_id=current_session_id(session),
                    board=get_active_task_board(session),
                    completed_boards=completed_task_board_views(session),
                    summary=task_board_summary,
                    event_meta={
                        "channel": payload.get("channel"),
                        "source_format": payload.get("source_format"),
                        "display_label": payload.get("display_label"),
                        "source_client_id": payload.get("source_client_id"),
                    },
                ),
            )
        return TurnReservation(
            busy=False,
            task_id=task_id,
            session_id=current_session_id(session),
            is_session_start=is_session_start,
            context_compressed=context_compressed,
            context_compaction=context_compaction,
            event_meta={
                "channel": payload.get("channel"),
                "source_format": payload.get("source_format"),
                "display_label": payload.get("display_label"),
                "source_client_id": payload.get("source_client_id"),
            },
        )


async def run_reserved_chat_turn(
    session: Any,
    reservation: TurnReservation,
    *,
    prompt_builder: PromptBuilder,
    tool_handlers_builder: Optional[ToolHandlersBuilder] = None,
    extra_tools_builder: Optional[ExtraToolsBuilder] = None,
    system_messages: Optional[List[Dict[str, Any]]] = None,
    prelude_messages: Optional[List[Dict[str, Any]]] = None,
    assistant_message_payload: Optional[Dict[str, Any]] = None,
    event_sink: Optional[EventSink] = None,
    initialize_single_agent: Optional[SingleAgentInitializer] = None,
    assistant_content_transform: Optional[AssistantContentTransform] = None,
) -> SharedTurnResult:
    task_id = reservation.task_id
    raw_response = ""
    response_buffer: List[str] = []

    try:
        client, provider = session.get_client_for_model()
        if not client:
            raise RuntimeError(f"No API key configured for provider: {provider}")

        async with session.lock:
            pending_files = list(getattr(session, "pending_files", []))
            session.pending_files = []

        file_context = _build_file_context(pending_files)
        skills_index = ""
        active_skills_context = ""
        if getattr(session, "skill_registry", None):
            skills_index = f"\n\n{session.skill_registry.get_skills_index()}"
            if getattr(session, "active_skills", None):
                active_skills_context = (
                    "\n\n# LOADED SPECIALIZED SKILLS\n"
                    f"{session.skill_registry.get_active_skills_context(session.active_skills)}"
                )

        memory_context = _memory_context(session)
        custom_system_prompt = prompt_builder(
            session,
            memory_context=memory_context,
            skills_index=skills_index,
            active_skills_context=active_skills_context,
        )

        messages: List[Dict[str, Any]] = [{"role": "system", "content": custom_system_prompt}]
        injected_messages = list(system_messages or [])
        if file_context:
            injected_messages.insert(
                0,
                {
                    "role": "system",
                    "content": f"USER ATTACHMENTS (structured data):\n{file_context}",
                },
            )
        messages.extend(injected_messages)
        messages.extend(prelude_messages or [])
        messages.extend(
            {"role": item.get("role", "user"), "content": item.get("content", "")}
            for item in session.chat_history
        )

        running_loop = asyncio.get_running_loop()
        artifact_store = _artifact_store_for_session(session, session_id=reservation.session_id)
        touched_file_paths: set[Path] = set()
        turn_artifact_ids: List[str] = []
        file_snapshots_flushed = False

        def _schedule_emit(event: Dict[str, Any]) -> None:
            if not event_sink:
                return
            try:
                asyncio.run_coroutine_threadsafe(_emit_event(event_sink, event), running_loop)
            except RuntimeError:
                pass

        def log_func(text: str) -> None:
            if text.strip() and getattr(session, "verbose_mode", False):
                _append_and_publish_timeline_event(
                    session,
                    event=build_log_timeline_event(
                        message=text,
                        channel=reservation.event_meta.get("channel"),
                        source_format=reservation.event_meta.get("source_format"),
                    ),
                    event_meta=reservation.event_meta,
                )
            _publish_sync_event(
                session,
                _turn_sync_event(
                    event_type="log",
                    session_id=reservation.session_id,
                    payload={"message": text},
                    event_meta=reservation.event_meta,
                ),
            )
            _schedule_emit({"type": "log", "message": text})

        def log_inline_func(text: str) -> None:
            if text.strip():
                response_buffer.append(text)

        def begin_stream_func() -> None:
            response_buffer.clear()

        def append_stream_func(text: str) -> None:
            response_buffer.append(text)
            _schedule_emit({"type": "assistant_delta", "delta": text})

        def append_reasoning_func(text: str) -> None:
            if not str(text or "").strip():
                return
            _schedule_emit({"type": "reasoning_delta", "delta": text})

        def finish_stream_func() -> None:
            return None

        def update_status_func() -> None:
            return None

        def _emit_task_board(summary: Optional[str], board: Optional[Dict[str, Any]]) -> None:
            if not board and not summary:
                return
            _publish_sync_event(
                session,
                _task_board_sync_event(
                    session_id=reservation.session_id,
                    board=board,
                    completed_boards=completed_task_board_views(session),
                    summary=summary,
                    event_meta=reservation.event_meta,
                ),
            )
            _schedule_emit(
                {
                    "type": "task_board",
                    "board": task_board_view(board),
                    "completed_task_boards": completed_task_board_views(session),
                    "summary": summary or (board or {}).get("latest_summary"),
                }
            )

        def before_model_turn_func(_turn_number: int, _messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
            task_messages = list(before_model_turn_messages(session))
            task_contract_context = _task_contract_context_message(session)
            desktop_context = _desktop_window_context_message(session)
            if task_contract_context:
                _schedule_emit(
                    {
                        "type": "model_context",
                        "kind": "current_task_contract",
                        "content": task_contract_context.get("content", ""),
                    }
                )
            if desktop_context:
                _schedule_emit(
                    {
                        "type": "model_context",
                        "kind": "desktop_window_snapshot",
                        "content": desktop_context.get("content", ""),
                    }
                )
            task_focus = None
            board = get_display_task_board(session)
            if isinstance(board, dict):
                task_focus = str(board.get("current_focus") or board.get("main_goal") or "").strip() or None
            artifact_messages = artifact_store.build_prompt_messages(
                user_message=str(getattr(session, "last_user_message", "") or ""),
                task_focus=task_focus,
            ) if artifact_store else []
            messages = [*task_messages]
            if task_contract_context:
                messages.append(task_contract_context)
            if desktop_context:
                messages.append(desktop_context)
            messages.extend(artifact_messages)
            return messages

        def _flush_file_snapshot_artifacts() -> None:
            nonlocal file_snapshots_flushed
            if file_snapshots_flushed:
                return
            file_snapshots_flushed = True
            artifact_ids = _snapshot_touched_file_artifact_ids(
                session,
                store=artifact_store,
                touched_file_paths=touched_file_paths,
                task_id=reservation.task_id,
            )
            turn_artifact_ids.extend(
                artifact_id for artifact_id in artifact_ids if artifact_id not in turn_artifact_ids
            )
            _publish_artifact_created(
                session,
                reservation=reservation,
                store=artifact_store,
                artifact_ids=artifact_ids,
                schedule_emit=_schedule_emit,
            )

        def on_tool_use_func(tool_name: str, tool_args: Dict[str, Any], tool_result: Any, dur_ms: float):
            _track_mutated_file_path(
                touched_file_paths,
                session,
                tool_name=tool_name,
                tool_args=tool_args,
                tool_result=tool_result,
            )
            if getattr(session, "verbose_mode", False):
                _append_and_publish_timeline_event(
                    session,
                    event=build_tool_timeline_event(
                        tool_name=tool_name,
                        tool_args=tool_args,
                        tool_result=tool_result,
                        duration_ms=dur_ms,
                        channel=reservation.event_meta.get("channel"),
                        source_format=reservation.event_meta.get("source_format"),
                    ),
                    event_meta=reservation.event_meta,
                )
            artifact_ids = _capture_tool_artifact_ids(
                session,
                store=artifact_store,
                tool_name=tool_name,
                tool_args=tool_args,
                tool_result=tool_result,
                task_id=reservation.task_id,
            )
            turn_artifact_ids.extend(
                artifact_id for artifact_id in artifact_ids if artifact_id not in turn_artifact_ids
            )
            _publish_sync_event(
                session,
                _turn_sync_event(
                    event_type="tool_use",
                    session_id=reservation.session_id,
                    payload={
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "tool_result": tool_result,
                        "duration_ms": dur_ms,
                        "artifact_ids": artifact_ids,
                    },
                    event_meta=reservation.event_meta,
                ),
            )
            _schedule_emit(
                {
                    "type": "tool_use",
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "tool_result": tool_result,
                    "duration_ms": dur_ms,
                    "artifact_ids": artifact_ids,
                }
            )
            _publish_artifact_created(
                session,
                reservation=reservation,
                store=artifact_store,
                artifact_ids=artifact_ids,
                schedule_emit=_schedule_emit,
            )
            prompt_messages: List[Dict[str, Any]] = []
            if tool_name == TASK_BOARD_INTERNAL_TOOL_NAME and isinstance(tool_result, dict):
                _emit_task_board(tool_result.get("summary"), get_display_task_board(session))
                prompt_messages = list(tool_result.get("prompt_messages") or [])
            else:
                task_effect = handle_tool_result(
                    session,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    tool_result=tool_result,
                    channel=reservation.event_meta.get("channel"),
                )
                if task_effect.get("summary") or task_effect.get("created"):
                    _emit_task_board(task_effect.get("summary"), task_effect.get("board"))
                prompt_messages = list(task_effect.get("prompt_messages") or [])
            return prompt_messages

        def on_auto_continue_func(payload: Dict[str, Any]) -> None:
            safe_payload = dict(payload or {})
            _publish_sync_event(
                session,
                _turn_sync_event(
                    event_type="auto_continue",
                    session_id=reservation.session_id,
                    payload=safe_payload,
                    event_meta=reservation.event_meta,
                ),
            )
            _schedule_emit({"type": "auto_continue", **safe_payload})

        def judge_final_candidate_func(payload: Dict[str, Any]) -> Dict[str, Any]:
            return _planner_final_verdict(session, payload)

        callbacks = {
            "log": log_func,
            "log_inline": log_inline_func,
            "begin_stream": begin_stream_func,
            "append_stream": append_stream_func,
            "append_reasoning": append_reasoning_func,
            "finish_stream": finish_stream_func,
            "update_status": update_status_func,
            "before_model_turn": before_model_turn_func,
            "on_tool_use": on_tool_use_func,
            "on_auto_continue": on_auto_continue_func,
            "judge_final_candidate": judge_final_candidate_func,
        }

        model_config = MODEL_CONFIGS.get(session.current_model, {})
        auto_provider = model_config.get("provider", "openai")
        auto_model_id = model_config.get("id", session.current_model)
        api_type = model_config.get("api", "chat")

        auto_client = client
        if auto_provider == "anthropic" and not getattr(session, "anthropic_client", None):
            api_key = session.config_manager.get_api_key("anthropic") or os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError("Claude requires API key")
            session.anthropic_client = Anthropic(api_key=api_key)
            auto_client = session.anthropic_client

        if not getattr(session, "single_agent", None):
            init = initialize_single_agent or (lambda loop: session.init_single_agent(None, loop))
            init(running_loop)

        active_task_board = get_active_task_board(session)
        if getattr(session, "tool_executor", None) and tool_handlers_builder:
            handlers = dict(tool_handlers_builder(session))
            if active_task_board:
                handlers[TASK_BOARD_INTERNAL_TOOL_NAME] = lambda args: apply_task_board_failure_report(session, args)
            session.tool_executor.custom_tool_handlers = handlers
        elif getattr(session, "tool_executor", None):
            session.tool_executor.custom_tool_handlers = (
                {TASK_BOARD_INTERNAL_TOOL_NAME: lambda args: apply_task_board_failure_report(session, args)}
                if active_task_board
                else {}
            )

        extra_tools = extra_tools_builder(session) if extra_tools_builder else None
        if active_task_board:
            extra_tools = merge_openai_tools(extra_tools, [TASK_BOARD_FAILURE_REPORT_TOOL])
        base_tools = list(getattr(session, "current_turn_allowed_tool_definitions", []) or [])

        _publish_sync_event(
            session,
            _turn_sync_event(
                event_type="status",
                session_id=reservation.session_id,
                payload={"message": "running", "run_state": "running"},
                event_meta=reservation.event_meta,
            ),
        )
        await _emit_event(event_sink, {"type": "status", "message": "running"})
        start_time = time.time()
        loop = asyncio.get_running_loop()
        result: LoopResult = await loop.run_in_executor(
            None,
            lambda: run_tool_loop(
                provider=auto_provider,
                model_id=auto_model_id,
                client=auto_client,
                messages=messages,
                tool_executor=session.tool_executor,
                callbacks=callbacks,
                variant=session.current_variant,
                api_type=api_type,
                extra_tools=extra_tools,
                base_tools=base_tools,
                custom_system_prompt=custom_system_prompt,
            ),
        )

        if session.current_task_id != task_id:
            return SharedTurnResult(
                ok=False,
                abandoned=True,
                session_id=current_session_id(session),
            )

        raw_response = result.content or "".join(response_buffer)
        assistant_text = assistant_content_transform(raw_response) if assistant_content_transform else raw_response
        finalized_task_board = finalize_task_board_turn(session, assistant_text or "")
        post_compaction_result = None
        _flush_file_snapshot_artifacts()
        if assistant_text:
            assistant_message = {
                "role": "assistant",
                "content": assistant_text,
                "timestamp": datetime.now().isoformat(),
                "metadata": {
                    "artifact_ids": list(turn_artifact_ids),
                },
            }
            assistant_message.update(assistant_message_payload or {})
            if isinstance(assistant_message.get("metadata"), dict):
                merged_ids = list(assistant_message["metadata"].get("artifact_ids") or [])
                for artifact_id in turn_artifact_ids:
                    if artifact_id not in merged_ids:
                        merged_ids.append(artifact_id)
                assistant_message["metadata"]["artifact_ids"] = merged_ids
            async with session.lock:
                session.chat_history.append(assistant_message)
                if getattr(session, "context_manager", None):
                    model_id = session.current_model or "claude-sonnet-4-5"
                    if session.context_manager.needs_compression(session.chat_history, model_id):
                        post_compaction_result = compact_session_history(session, reason="auto_post_turn")
                        if post_compaction_result and post_compaction_result.applied:
                            _publish_compaction_status(session, post_compaction_result)
                session.save_session()
            _publish_sync_event(
                session,
                {
                    **_message_sync_event(
                        event_type="assistant_final",
                        session_id=current_session_id(session),
                        message=assistant_message,
                    ),
                    "payload": {
                        "message": assistant_message,
                        "text": assistant_text,
                        "duration_seconds": time.time() - start_time,
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "total_tokens": result.total_tokens,
                        "artifact_ids": list(turn_artifact_ids),
                    },
                },
            )
        if finalized_task_board:
            _publish_sync_event(
                session,
                _task_board_sync_event(
                    session_id=current_session_id(session),
                    board=finalized_task_board.get("board"),
                    completed_boards=finalized_task_board.get("completed_boards") or completed_task_board_views(session),
                    summary=finalized_task_board.get("summary"),
                    event_meta=reservation.event_meta,
                ),
            )
            await _emit_event(
                event_sink,
                {
                    "type": "task_board",
                    "board": task_board_view(finalized_task_board.get("board")),
                    "completed_task_boards": finalized_task_board.get("completed_boards") or completed_task_board_views(session),
                    "summary": finalized_task_board.get("summary"),
                },
            )

        duration = time.time() - start_time
        if assistant_text and getattr(session, "memory_manager", None):
            session.memory_manager.append_to_daily_log(
                f"User: {session.last_user_message[:200]}...\n\nAssistant: {assistant_text[:200]}...",
                "chat",
                session_id=current_session_id(session),
            )

        if assistant_text and getattr(session, "hook_manager", None):
            session.hook_manager.trigger(
                HookType.MESSAGE_PROCESSED,
                HookEvent.create(HookType.MESSAGE_PROCESSED, session.user_id, response=assistant_text),
            )

        if getattr(session, "analytics_tracker", None):
            session.analytics_tracker.track_llm_request(
                session.user_id,
                session.current_model,
                result.input_tokens,
                result.output_tokens,
                duration,
            )

        asyncio.get_running_loop().run_in_executor(None, session.auto_rename_session)

        return SharedTurnResult(
            ok=True,
            session_id=current_session_id(session),
            assistant_text=assistant_text,
            raw_response=raw_response,
            duration_seconds=duration,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            total_tokens=result.total_tokens,
            context_compressed=bool(post_compaction_result and post_compaction_result.applied),
            context_compaction=_compaction_metadata(post_compaction_result) if post_compaction_result and post_compaction_result.applied else None,
        )
    except Exception:
        _flush_file_snapshot_artifacts()
        interrupted_board = archive_active_task_board(
            session,
            status="interrupted",
            summary="The managed task stopped unexpectedly before it could finish.",
        )
        if interrupted_board:
            _publish_sync_event(
                session,
                _task_board_sync_event(
                    session_id=current_session_id(session),
                    board=None,
                    completed_boards=completed_task_board_views(session),
                    summary=interrupted_board.get("completion_summary"),
                    event_meta=reservation.event_meta,
                ),
            )
        raise
    finally:
        _flush_file_snapshot_artifacts()
        async with session.lock:
            if session.current_task_id == task_id:
                session.is_processing = False
                session.save_session()
        _publish_sync_event(
            session,
            _turn_sync_event(
                event_type="status",
                session_id=current_session_id(session),
                payload={"message": "ready", "run_state": "idle"},
                event_meta=reservation.event_meta,
            ),
        )
