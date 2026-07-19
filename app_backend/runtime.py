from __future__ import annotations

import asyncio
import os
import json
import inspect
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import quote

import httpx
from runtime_support.ui_helpers import ThinkingModeVisualizer
from cli.agent_tools.definitions import CLI_AGENT_TOOLS
from local_agent_runtime.tool_manifest import AGENT_TOOLS
from app_backend.auth_store import AppAuthStore
from app_backend.local_runtime_server import load_desktop_runtime_config
from app_backend.fleet_identity_profiles import role_locked_tool_packs
from shared.channel_sync import get_channel_sync_hub
from shared.chat_modes import (
    REQUEST_USER_INPUT_TOOL,
    UPDATE_GOAL_STATUS_TOOL,
    add_goal_token_usage,
    active_goal,
    active_plan_mode,
    apply_goal_status_update,
    ensure_plan_mode,
    exit_plan_mode,
    filter_plan_tools,
    goal_mode_system_message,
    normalize_plan_action,
    normalize_plan_question,
    normalize_run_mode,
    plan_mode_system_message,
    record_proposed_plan,
    start_goal,
)
from shared.runtime_paths import runtime_home
from shared.fleet_connection import fleet_connection_configured
from shared.fleet_upstream_activity import queue_upstream_request
from telegram_bot.telegram_unified_agent import (
    build_unified_system_prompt,
    get_auto_mode_extra_tools,
    get_auto_mode_tool_handlers,
)
from shared.task_board import TASK_BOARD_INTERNAL_TOOL_NAME, get_active_task_board

from shared import begin_chat_turn, merge_openai_tools, reserve_failed_chat_turn_retry, run_reserved_chat_turn
from shared.live_config import get_live_config
from shared.standalone_policy import standalone_desktop_enabled
from shared.task_intent import (
    is_screen_observation_message,
    is_task_like_message,
    request_requires_tool_evidence,
)
from shared.tool_pack_prompts import (
    build_pack_aware_kickstart_prelude,
    build_pack_aware_screen_observation_contract,
    build_pack_aware_task_execution_contract,
)
from shared.tool_packs import (
    PACK_MANAGER_CORE,
    filter_openai_tools_by_enabled_packs,
    filter_tools_by_enabled_packs,
    tools_for_enabled_packs,
)


STEERING_BETA_ENV = "EMPLO_APP_STEERING_BETA_ENABLED"
FLEET_MANAGER_TOOL_CACHE_SECONDS = 8.0

def _fleet_tool(
    name: str,
    description: str,
    properties: Optional[Dict[str, Any]] = None,
    required: Optional[list[str]] = None,
) -> Dict[str, Any]:
    parameters: Dict[str, Any] = {"type": "object", "properties": dict(properties or {})}
    if required:
        parameters["required"] = list(required)
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


_WORKER_ARG = {"type": "string", "description": "Worker id or display name, for example Worker-001."}
_GROUP_ARG = {"type": "string", "description": "Group id or display name."}
_COMPUTER_ARG = {"type": "string", "description": "Paired computer id or display name, for example Windows VPS."}
_CONFIRMED_ARG = {"type": "boolean", "description": "Set true only after the same surface has confirmed this action."}
_CONFIRMATION_ID_ARG = {"type": "string", "description": "Confirmation id returned by the previous call for this action."}

FLEET_MANAGER_TOOLS = [
    _fleet_tool("fleet_list_workers", "List workers, their task state, queue depth, latest report, groups, and pending grants."),
    _fleet_tool(
        "fleet_create_local_worker",
        "Create a named local logical worker only when the user explicitly asks for one.",
        {"display_name": {"type": "string"}},
        ["display_name"],
    ),
    _fleet_tool("fleet_create_enrollment", "Create a short-lived enrollment token for a remote worker computer or VPS.", {"display_name": {"type": "string"}, "expires_in_seconds": {"type": "integer", "default": 1800}}),
    _fleet_tool(
        "fleet_delegate",
        "Route actionable work to the local default worker, a child computer's default worker, a child manager, or an explicitly named identity. Unqualified work routes to the local default worker and busy workers queue deterministically.",
        {
            "scope": {"type": "string", "enum": ["auto", "local", "child"], "default": "auto"},
            "computer": _COMPUTER_ARG,
            "identity": {"type": "string", "description": "Optional exact local or published child identity ID/name."},
            "target_role": {"type": "string", "enum": ["auto", "manager", "worker"], "default": "auto"},
            "prompt": {"type": "string"},
            "continuation_task_id": {"type": "string"},
        },
        ["prompt"],
    ),
    _fleet_tool(
        "fleet_context_search",
        "Search redacted indexed activity on this computer and descendants when the user-enabled manager context inspection setting is on.",
        {
            "query": {"type": "string"},
            "computer": _COMPUTER_ARG,
            "limit": {"type": "integer", "default": 20},
        },
        ["query"],
    ),
    _fleet_tool(
        "fleet_context_window",
        "Expand a context-search match to a redacted paged message window. Use route_computer_id from search results for descendant matches.",
        {
            "message_id": {"type": "string"},
            "computer": _COMPUTER_ARG,
            "direction": {"type": "string", "enum": ["around", "previous", "next"], "default": "around"},
            "cursor": {"type": "string"},
        },
        ["message_id"],
    ),
    _fleet_tool("fleet_list_computers", "List directly paired computers, their connection state, allowed actions, and explicitly published delegation targets."),
    _fleet_tool(
        "fleet_delegate_computer",
        "Send a task to a manager or explicitly published worker identity on a directly paired computer. The remote chat and files remain private; only status and a compact report return.",
        {
            "computer": _COMPUTER_ARG,
            "prompt": {"type": "string"},
            "target_kind": {"type": "string", "enum": ["manager", "worker"], "default": "worker"},
            "target_selector": {"type": "string", "description": "Published target selector from fleet_list_computers. Omit for the remote manager."},
        },
        ["computer", "prompt"],
    ),
    _fleet_tool(
        "fleet_create_worker_on_computer",
        "Create a named worker locally on a paired computer only when the user explicitly asks and that computer allows remote worker creation.",
        {"computer": _COMPUTER_ARG, "display_name": {"type": "string"}},
        ["computer", "display_name"],
    ),
    _fleet_tool("fleet_computer_host_status", "Check whether a paired computer's persistent host, backend, and desktop app are running.", {"computer": _COMPUTER_ARG}, ["computer"]),
    _fleet_tool("fleet_start_computer_runtime", "Start the EmploAI backend on a paired computer through its persistent Yggdrasil host.", {"computer": _COMPUTER_ARG}, ["computer"]),
    _fleet_tool("fleet_start_computer_desktop", "Open the EmploAI desktop app and backend on a paired computer through its persistent Yggdrasil host.", {"computer": _COMPUTER_ARG}, ["computer"]),
    _fleet_tool("fleet_check_computer_update", "Check a paired computer's configured Git branch for a safe fast-forward EmploAI update.", {"computer": _COMPUTER_ARG}, ["computer"]),
    _fleet_tool("fleet_update_computer", "Install an exact checked EmploAI commit on a paired computer and restart its backend, desktop app, and persistent host after confirmation.", {"computer": _COMPUTER_ARG, "expected_commit": {"type": "string", "description": "Full 40-character target commit returned by fleet_check_computer_update."}, "confirmed": _CONFIRMED_ARG, "confirmation_id": _CONFIRMATION_ID_ARG}, ["computer", "expected_commit"]),
    _fleet_tool("fleet_rename_worker", "Rename a worker.", {"worker": _WORKER_ARG, "display_name": {"type": "string"}}, ["worker", "display_name"]),
    _fleet_tool("fleet_reset_worker", "Reset a worker identity after confirmation. Stops active work first and preserves terminal reports.", {"worker": _WORKER_ARG, "reason": {"type": "string"}, "confirmed": _CONFIRMED_ARG, "confirmation_id": _CONFIRMATION_ID_ARG}, ["worker"]),
    _fleet_tool("fleet_delete_worker", "Delete a worker from the live fleet after confirmation. Stops active work first and preserves terminal reports.", {"worker": _WORKER_ARG, "reason": {"type": "string"}, "confirmed": _CONFIRMED_ARG, "confirmation_id": _CONFIRMATION_ID_ARG}, ["worker"]),
    _fleet_tool("fleet_list_groups", "List worker groups."),
    _fleet_tool("fleet_create_group", "Create a worker group.", {"display_name": {"type": "string"}, "worker_ids": {"type": "array", "items": {"type": "string"}}, "description": {"type": "string"}}, ["display_name"]),
    _fleet_tool("fleet_update_group", "Update group name, description, or members.", {"group": _GROUP_ARG, "display_name": {"type": "string"}, "worker_ids": {"type": "array", "items": {"type": "string"}}, "description": {"type": "string"}}, ["group"]),
    _fleet_tool("fleet_delete_group", "Delete a group after confirmation.", {"group": _GROUP_ARG, "confirmed": _CONFIRMED_ARG, "confirmation_id": _CONFIRMATION_ID_ARG}, ["group"]),
    _fleet_tool("fleet_assign_task", "Assign a task to one worker. If the worker is busy, the task queues by default.", {"worker": _WORKER_ARG, "prompt": {"type": "string"}}, ["worker", "prompt"]),
    _fleet_tool("fleet_assign_group_task", "Assign a task to every worker in a group after confirmation.", {"group": _GROUP_ARG, "prompt": {"type": "string"}, "confirmed": _CONFIRMED_ARG, "confirmation_id": _CONFIRMATION_ID_ARG}, ["group", "prompt"]),
    _fleet_tool("fleet_send_worker_message", "Send a manager message to a worker. Busy workers queue the message by default.", {"worker": _WORKER_ARG, "message": {"type": "string"}}, ["worker", "message"]),
    _fleet_tool("fleet_send_group_message", "Send a manager message to a group after confirmation.", {"group": _GROUP_ARG, "message": {"type": "string"}, "confirmed": _CONFIRMED_ARG, "confirmation_id": _CONFIRMATION_ID_ARG}, ["group", "message"]),
    _fleet_tool("fleet_redirect_worker_task", "Redirect the worker's active task now; do not use for normal queued follow-up messages.", {"worker": _WORKER_ARG, "task_id": {"type": "string"}, "direction": {"type": "string"}}, ["direction"]),
    _fleet_tool("fleet_delete_queued_message", "Cancel a queued worker message or task.", {"task_id": {"type": "string"}}, ["task_id"]),
    _fleet_tool("fleet_steer_queued_message", "Remove a queued message and apply it as an immediate redirect to the worker's active task.", {"task_id": {"type": "string"}}, ["task_id"]),
    _fleet_tool("fleet_reorder_worker_queue", "Reorder queued tasks for one worker.", {"worker": _WORKER_ARG, "task_ids": {"type": "array", "items": {"type": "string"}}}, ["worker", "task_ids"]),
    _fleet_tool("fleet_continue_worker_queue", "After reviewing a completed worker report, start the worker's next queued item.", {"worker": _WORKER_ARG, "reviewed_report_id": {"type": "string"}}, ["worker"]),
    _fleet_tool("fleet_update_task", "Update a fleet task state. Prefer fleet_stop_worker for active stop and fleet_delete_queued_message for queued cancel.", {"task_id": {"type": "string"}, "worker": _WORKER_ARG, "action": {"type": "string", "enum": ["pause", "resume", "stop", "cancel"]}, "reason": {"type": "string"}}, ["action"]),
    _fleet_tool("fleet_stop_worker", "Stop one worker's active task and task-owned commands.", {"worker": _WORKER_ARG, "reason": {"type": "string"}}, ["worker"]),
    _fleet_tool("fleet_stop_all", "Stop every reachable active fleet run after confirmation.", {"reason": {"type": "string"}, "confirmed": _CONFIRMED_ARG, "confirmation_id": _CONFIRMATION_ID_ARG}),
    _fleet_tool("fleet_inspect_worker", "Inspect one worker's status, active task, queued tasks, and recent reports.", {"worker": _WORKER_ARG}, ["worker"]),
    _fleet_tool("fleet_search_reports", "Search recent worker reports by text, worker, or status.", {"query": {"type": "string"}, "worker": _WORKER_ARG, "status": {"type": "string"}, "limit": {"type": "integer", "default": 5}}),
    _fleet_tool("fleet_read_report", "Read one structured worker report by report id or task id.", {"report_id": {"type": "string"}, "task_id": {"type": "string"}}),
    _fleet_tool("fleet_inspect_evidence", "Inspect compact report evidence and artifact metadata.", {"report_id": {"type": "string"}, "task_id": {"type": "string"}, "worker": _WORKER_ARG}),
    _fleet_tool("fleet_open_worker_timeline", "Open a compact worker task/report timeline without loading full transcripts into context.", {"worker": _WORKER_ARG}, ["worker"]),
    _fleet_tool("fleet_request_worker_preview", "Request a view-only worker screen preview or screen summary. Does not grant remote mouse or keyboard control.", {"worker": _WORKER_ARG}, ["worker"]),
    _fleet_tool("fleet_list_tool_grants", "List pending and recent temporary tool-pack grants.", {"worker": _WORKER_ARG, "status": {"type": "string"}}),
    _fleet_tool("fleet_decide_tool_grant", "Approve, deny, or reduce a temporary tool-pack grant.", {"grant_id": {"type": "string"}, "approved": {"type": "boolean"}, "approved_turns": {"type": "integer", "default": 10}}, ["grant_id", "approved"]),
    _fleet_tool("fleet_check_workspace_binding", "Check whether a workspace has a valid machine-local binding before file-writing work.", {"workspace_id": {"type": "string"}, "machine_id": {"type": "string"}}),
    _fleet_tool("fleet_request_workspace_reconnect", "Ask the user to reconnect a missing or suspicious workspace binding.", {"workspace_id": {"type": "string"}, "machine_id": {"type": "string"}, "reason": {"type": "string"}}),
]

FLEET_MANAGER_TOOL_NAMES = {
    str(tool["function"]["name"])
    for tool in FLEET_MANAGER_TOOLS
    if isinstance(tool.get("function"), dict)
}

FLEET_UPSTREAM_TOOLS = [
    _fleet_tool(
        "fleet_request_manager",
        "Send a narrow question, approval request, or blocker from this local identity to the directly connected manager above.",
        {
            "request_kind": {"type": "string", "enum": ["question", "approval", "blocked"]},
            "message": {"type": "string", "description": "What the manager needs to know or decide."},
        },
        ["request_kind", "message"],
    )
]
FLEET_UPSTREAM_TOOL_NAMES = {"fleet_request_manager"}


def _kickstart_prelude(enabled_tool_packs) -> list[dict[str, str]]:
    return build_pack_aware_kickstart_prelude(enabled_tool_packs)


def _task_execution_contract(session: Any, enabled_tool_packs) -> dict[str, str]:
    return build_pack_aware_task_execution_contract(
        enabled_tool_packs,
        task_board_internal_tool_name=TASK_BOARD_INTERNAL_TOOL_NAME,
        task_board_enabled=bool(get_active_task_board(session)),
        workspace_path=str(getattr(session, "workspace", "") or ""),
    )


def _conversational_turn_guard() -> dict[str, str]:
    return {
        "role": "system",
        "content": (
            "CONVERSATIONAL STYLE NOTE:\n"
            "- All enabled tools remain available on this turn.\n"
            "- For greetings, acknowledgements, thanks, or light conversation, answer directly without forcing unnecessary tool use.\n"
            "- If the user asks about the current workspace, files, browser, desktop, or any other state that requires observation, use the relevant enabled tools instead of claiming they are unavailable.\n"
            "- AGENTS.md, SOUL.md, USER.md, TOOLS.md, and MEMORY.md are already injected when available. If asked about them, answer from injected context instead of calling file tools for those filenames.\n"
            "- Do not read MEMORY.md just to begin work. Touch memory only when you are intentionally saving durable reusable information.\n"
            "- For desktop launches and other major desktop actions, treat the action as an attempt until visual verification confirms the resulting state.\n"
            "- Keep simple conversation concise, but do not hide enabled capabilities from the model."
        ),
    }


def _jarvis_voice_response_contract() -> dict[str, str]:
    return {
        "role": "system",
        "content": (
            "JARVIS VOICE SURFACE:\n"
            "- Treat this as a hands-free voice conversation, not a chat transcript.\n"
            "- The user normally cannot see your transcript, tool stream, markdown, tables, or long lists in this surface.\n"
            "- Your final answer will be spoken aloud through TTS, so write it as natural speech.\n"
            "- Keep the final answer short: usually one or two flowing sentences, unless the user clearly asks for more detail.\n"
            "- Default to about 35 spoken words or fewer for routine answers.\n"
            "- Do not use markdown, bullet points, numbered lists, dash lists, tables, headings, or code fences in the final answer.\n"
            "- Do not say 'see above', 'below', or similar visual references unless you created or opened a visible artifact for the user.\n"
            "- If describing the screen, summarize the useful state naturally instead of listing every visible item.\n"
            "- Voice mode does not reduce your capabilities: use the same tools and verification discipline as chat mode.\n"
            "- The app may speak separate start and progress updates, so do not repeat tool-by-tool status in the final answer.\n"
            "- If you used tools, mention only the meaningful outcome or next step, not raw tool-call details.\n"
            "- If the answer would be long, give a brief spoken summary and offer to continue, create a file, or open the result."
        ),
    }


def _visual_monitor_wake_contract(surface_mode: Optional[str]) -> dict[str, str]:
    jarvis_note = ""
    if str(surface_mode or "").strip().lower() == "jarvis":
        jarvis_note = (
            "- This is a Jarvis continuation. Start with a brief natural continuation message before continuing.\n"
        )
    return {
        "role": "system",
        "content": (
            "VISUAL MONITOR WAKE:\n"
            "- A local visual monitor woke this turn because the screen changed or a no-change checkpoint needed agent attention.\n"
            "- The monitor does not provide before/after images, and monitor screenshots were discarded.\n"
            "- Before taking action or claiming what changed, call describe_screen with a precise question about the current visible state.\n"
            "- If the visible change is unrelated to the task, quietly continue the original task.\n"
            "- If more waiting is needed, start a fresh visual monitor; do not assume a prior monitor is still running.\n"
            f"{jarvis_note}"
        ),
    }


def _format_jarvis_spoken_response(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""

    normalized = re.sub(r"```.*?```", " ", normalized, flags=re.DOTALL)
    cleaned_lines: list[str] = []
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"^(?:[-*•]\s+|\d+[.)]\s+)", "", line)
        if line:
            cleaned_lines.append(line.rstrip(" .;:"))
    collapsed = ". ".join(cleaned_lines) if len(cleaned_lines) > 1 else " ".join(cleaned_lines)
    collapsed = re.sub(r"\s+", " ", collapsed).strip()
    if not collapsed:
        return ""

    max_chars = 420
    if len(collapsed) <= max_chars:
        return collapsed
    clipped = collapsed[:max_chars].rsplit(" ", 1)[0].strip()
    sentence_end = max(clipped.rfind("."), clipped.rfind("!"), clipped.rfind("?"))
    if sentence_end >= 180:
        return clipped[: sentence_end + 1].strip()
    return f"{clipped.rstrip('.,;:')}."


def _screen_observation_contract(enabled_tool_packs) -> dict[str, str]:
    return build_pack_aware_screen_observation_contract(enabled_tool_packs)


def _local_fleet_api_config() -> Dict[str, str]:
    config = load_desktop_runtime_config()
    token_payload = AppAuthStore().ensure_device_token(
        user_id=0,
        device_name="EmploAI Desktop",
        device_platform="desktop-electron",
        token_ttl_seconds=60 * 60 * 24 * 180,
        device_key="desktop-local",
    )
    return {
        "base_url": config.api_base_url.rstrip("/"),
        "token": str(token_payload.get("access_token") or "").strip(),
        "desktop_id": "",
    }


def _fleet_api_request(
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    confirmation_id: Optional[str] = None,
    timeout_seconds: float = 10.0,
) -> Dict[str, Any]:
    config = _local_fleet_api_config()
    if not config["token"]:
        return {"error": "The local desktop token is unavailable.", "error_type": "local_auth_unavailable"}
    try:
        bounded_timeout = max(1.0, float(timeout_seconds or 10.0))
        timeout = httpx.Timeout(bounded_timeout, connect=min(10.0, bounded_timeout), read=bounded_timeout, write=bounded_timeout)
        headers = {"Authorization": f"Bearer {config['token']}"}
        clean_confirmation_id = str(confirmation_id or "").strip()
        if clean_confirmation_id:
            headers["X-EmploAI-Confirmation-Id"] = clean_confirmation_id
        with httpx.Client(timeout=timeout) as client:
            response = client.request(
                method.upper(),
                f"{config['base_url']}{path}",
                headers=headers,
                json=payload if payload is not None else None,
            )
        try:
            data = response.json()
        except Exception:
            data = {"detail": response.text}
        if response.status_code >= 400:
            return {
                "error": str(data.get("detail") or data.get("error") or response.text or response.reason_phrase),
                "error_type": "fleet_api_error",
                "status_code": response.status_code,
            }
        return data if isinstance(data, dict) else {"result": data}
    except Exception as exc:
        return {"error": f"Fleet API request failed: {type(exc).__name__}: {exc}", "error_type": "fleet_api_unavailable"}


def _fleet_snapshot_uncached() -> Dict[str, Any]:
    return _fleet_api_request("GET", "/api/fleet/snapshot")


def _fleet_manager_tool_context(session: Any) -> Dict[str, Any]:
    if _is_fleet_worker_session(session):
        return {
            "enabled": False,
            "has_workers": False,
            "snapshot": {},
            "desktop_id": "",
            "fetched_at": time.monotonic(),
            "reason": "worker_identity",
        }
    now = time.monotonic()
    cached = getattr(session, "_fleet_manager_tool_context", None)
    if isinstance(cached, dict) and now - float(cached.get("fetched_at") or 0.0) < FLEET_MANAGER_TOOL_CACHE_SECONDS:
        return cached

    config = _local_fleet_api_config()
    snapshot = _fleet_snapshot_uncached()
    workers = list(snapshot.get("workers") or []) if isinstance(snapshot, dict) else []
    manager = snapshot.get("manager") if isinstance(snapshot, dict) and isinstance(snapshot.get("manager"), dict) else None
    is_primary_manager = bool(manager)
    context = {
        "enabled": bool(is_primary_manager and not snapshot.get("error")),
        "has_workers": bool(workers),
        "snapshot": snapshot if isinstance(snapshot, dict) else {},
        "desktop_id": str((manager or {}).get("desktop_id") or ""),
        "fetched_at": now,
    }
    try:
        setattr(session, "_fleet_manager_tool_context", context)
    except Exception:
        pass
    return context


async def _resolve_fleet_manager_tool_context(session: Any) -> Dict[str, Any]:
    """Resolve the local Fleet API snapshot without blocking the app event loop.

    The Fleet API is hosted by this same backend. Calling it synchronously from
    an app chat coroutine prevents the backend from serving its own request
    until the HTTP timeout expires.
    """
    return await asyncio.to_thread(_fleet_manager_tool_context, session)


def _invalidate_fleet_manager_tool_context(session: Any) -> None:
    try:
        setattr(session, "_fleet_manager_tool_context", None)
    except Exception:
        pass


def _fleet_upstream_tool_enabled() -> bool:
    try:
        home = runtime_home()
        return bool(home and fleet_connection_configured(home))
    except Exception:
        return False


def _fleet_tool_request_manager(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    request_kind = str(args.get("request_kind") or "").strip().lower()
    message = str(args.get("message") or "").strip()
    if request_kind not in {"question", "approval", "blocked"}:
        return {"error": "request_kind must be question, approval, or blocked", "error_type": "invalid_request_kind"}
    if not message:
        return {"error": "message is required", "error_type": "missing_message"}
    persisted = getattr(session, "session", None)
    task_id = str(
        getattr(session, "fleet_task_id", None)
        or getattr(persisted, "fleet_task_id", None)
        or ""
    ).strip() or None
    snapshot = _fleet_snapshot_uncached()
    local_task = next(
        (
            item
            for item in list(snapshot.get("tasks") or [])
            if task_id and str(item.get("task_id") or "").strip() == task_id
        ),
        None,
    )
    if local_task is not None:
        request_id = f"flr_{uuid.uuid4().hex[:16]}"
        metadata = dict(local_task.get("metadata") or {})
        requests = [dict(item) for item in list(metadata.get("manager_requests") or []) if isinstance(item, dict)]
        requests.append(
            {
                "request_id": request_id,
                "task_id": task_id,
                "request_kind": request_kind,
                "message": message[:8000],
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        metadata["manager_requests"] = requests[-50:]
        target_status = "blocked" if request_kind == "blocked" else "needs_review"
        updated = _fleet_api_request(
            "PUT",
            f"/api/fleet/tasks/{quote(task_id, safe='')}/status",
            {"status": target_status, "metadata": metadata},
        )
        if updated.get("error"):
            return updated
        _invalidate_fleet_manager_tool_context(session)
        return {
            "ok": True,
            "request_id": request_id,
            "task_id": task_id,
            "status": "pending",
            "detail": "The request is attached to this task in the local manager chat.",
        }
    if not _fleet_upstream_tool_enabled():
        return {
            "error": "This worker has no reachable owning manager for this task.",
            "error_type": "fleet_manager_not_connected",
        }
    identity_id = (
        str(getattr(session, "fleet_identity_id", "") or "").strip()
        or str(getattr(persisted, "fleet_identity_id", "") or "").strip()
        or str(getattr(session, "fleet_worker_id", "") or "").strip()
        or str(getattr(persisted, "fleet_worker_id", "") or "").strip()
        or None
    )
    identity_label = identity_id
    for identity in list(snapshot.get("identities") or []):
        if identity_id and identity_id in {
            str(identity.get("identity_id") or "").strip(),
            str(identity.get("worker_id") or "").strip(),
        }:
            identity_label = str(identity.get("display_name") or identity_id)
            break
    queued = queue_upstream_request(
        runtime_home(),
        request_kind=request_kind,
        identity_id=identity_id,
        identity_label=identity_label or "Local agent",
        message=message,
        task_id=task_id,
    )
    return {
        "ok": True,
        "request_id": queued.get("activity_id"),
        "status": queued.get("status"),
        "detail": "The request is queued for the directly connected manager above.",
    }


def _fleet_compact_worker_view(snapshot: Dict[str, Any], worker: Dict[str, Any]) -> Dict[str, Any]:
    worker_id = str(worker.get("worker_id") or "")
    tasks = [
        task
        for task in list(snapshot.get("tasks") or [])
        if str(task.get("worker_id") or "") == worker_id
    ]
    active = next((task for task in tasks if str(task.get("task_id") or "") == str(worker.get("active_task_id") or "")), None)
    queued = [task for task in tasks if str(task.get("status") or "") == "queued"]
    latest_report = next(
        (
            report
            for report in list(snapshot.get("reports") or [])
            if str(report.get("worker_id") or "") == worker_id
        ),
        None,
    )
    return {
        "worker_id": worker_id,
        "display_name": worker.get("display_name"),
        "kind": worker.get("kind"),
        "status": worker.get("status"),
        "detail": worker.get("detail"),
        "active_task_id": worker.get("active_task_id"),
        "active_task": active,
        "queue_depth": len(queued),
        "queued_tasks": queued[:5],
        "latest_report": latest_report,
    }


def _fleet_compact_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    workers = list(snapshot.get("workers") or [])
    return {
        "manager": snapshot.get("manager"),
        "computers": [_fleet_compact_computer_view(snapshot, computer) for computer in _fleet_direct_computers(snapshot)],
        "worker_count": len(workers),
        "workers": [_fleet_compact_worker_view(snapshot, worker) for worker in workers],
        "recent_reports": list(snapshot.get("reports") or [])[:5],
        "tool_grants": list(snapshot.get("tool_grants") or [])[:10],
    }


def _fleet_find_worker(snapshot: Dict[str, Any], selector: str) -> Optional[Dict[str, Any]]:
    needle = str(selector or "").strip().lower()
    workers = list(snapshot.get("workers") or [])
    if not needle and len(workers) == 1:
        return workers[0]
    for worker in workers:
        if str(worker.get("worker_id") or "").lower() == needle:
            return worker
        if str(worker.get("display_name") or "").strip().lower() == needle:
            return worker
    return None


def _fleet_find_group(snapshot: Dict[str, Any], selector: str) -> Optional[Dict[str, Any]]:
    needle = str(selector or "").strip().lower()
    groups = list(snapshot.get("groups") or [])
    if not needle and len(groups) == 1:
        return groups[0]
    for group in groups:
        if str(group.get("group_id") or "").lower() == needle:
            return group
        if str(group.get("display_name") or "").strip().lower() == needle:
            return group
    return None


def _fleet_find_task(snapshot: Dict[str, Any], task_id: str) -> Optional[Dict[str, Any]]:
    needle = str(task_id or "").strip()
    if not needle:
        return None
    return next((task for task in list(snapshot.get("tasks") or []) if str(task.get("task_id") or "") == needle), None)


def _fleet_find_report(snapshot: Dict[str, Any], *, report_id: str = "", task_id: str = "") -> Optional[Dict[str, Any]]:
    clean_report_id = str(report_id or "").strip()
    clean_task_id = str(task_id or "").strip()
    for report in list(snapshot.get("reports") or []):
        if clean_report_id and str(report.get("report_id") or "") == clean_report_id:
            return report
        if clean_task_id and str(report.get("task_id") or "") == clean_task_id:
            return report
    return None


def _fleet_confirmation_required(
    session: Any,
    action_kind: str,
    summary: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    session_id = str(getattr(getattr(session, "session", None), "id", "") or "").strip() or None
    created = _fleet_api_request(
        "POST",
        "/api/app/confirmations",
        {
            "action_kind": action_kind,
            "title": summary[:240],
            "message": summary[:2000],
            "risk_tier": "danger",
            "origin_surface": "manager_agent",
            "origin_identity_id": str(getattr(session, "fleet_identity_id", "") or "").strip() or None,
            "origin_chat_id": session_id,
            "payload": dict(payload or {}),
            "ttl_seconds": 300,
        },
    )
    if created.get("error"):
        return created
    confirmation_id = str(created.get("confirmation_id") or "").strip()
    if not confirmation_id:
        return {"error": "Fleet confirmation could not be created.", "error_type": "confirmation_unavailable"}
    pending = dict(getattr(session, "_fleet_pending_confirmations", {}) or {})
    pending[action_kind] = confirmation_id
    try:
        setattr(session, "_fleet_pending_confirmations", pending)
    except Exception:
        pass
    return {
        "confirmation_required": True,
        "confirmation_id": confirmation_id,
        "action": action_kind,
        "summary": summary,
        "payload": payload or {},
        "next_valid_actions": [
            "Ask the user to confirm on this surface, then call the same tool with confirmed=true and this confirmation_id."
        ],
    }


def _fleet_confirmation_id_for_execution(
    session: Any,
    args: Dict[str, Any],
    *,
    action_kind: str,
) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    if not bool(args.get("confirmed")):
        return None, {"error": "User confirmation is required.", "error_type": "confirmation_required"}
    pending = dict(getattr(session, "_fleet_pending_confirmations", {}) or {})
    confirmation_id = str(args.get("confirmation_id") or pending.get(action_kind) or "").strip()
    if not confirmation_id:
        return None, {"error": "The pending Fleet confirmation id is missing.", "error_type": "confirmation_required"}
    if pending.get(action_kind) and str(pending.get(action_kind)) != confirmation_id:
        return None, {"error": "The Fleet confirmation id does not match this action.", "error_type": "confirmation_mismatch"}
    user_text = str(getattr(session, "last_user_message", "") or "").strip().lower()
    affirmative = bool(re.search(r"\b(yes|confirm|confirmed|approve|approved|proceed|continue|do it|okay|ok)\b", user_text))
    negative = bool(re.search(r"\b(no|deny|denied|cancel|stop|abort|decline)\b", user_text))
    if not affirmative or negative:
        return None, {
            "error": "The latest user message did not explicitly confirm this Fleet action.",
            "error_type": "confirmation_required",
        }
    approved = _fleet_api_request(
        "POST",
        f"/api/app/confirmations/{quote(confirmation_id, safe='')}/approve",
        {"decided_by_surface": "manager_agent", "decided_by_actor": session_id_for_confirmation(session)},
    )
    if approved.get("error"):
        return None, approved
    if str(approved.get("status") or "").strip().lower() != "approved":
        return None, {"error": "Fleet confirmation was not approved.", "error_type": "confirmation_required"}
    pending.pop(action_kind, None)
    try:
        setattr(session, "_fleet_pending_confirmations", pending)
    except Exception:
        pass
    return confirmation_id, None


def session_id_for_confirmation(session: Any) -> Optional[str]:
    return str(getattr(getattr(session, "session", None), "id", "") or "").strip() or None


def _fleet_compact_task_result(task: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "task_id": task.get("task_id"),
        "worker_id": task.get("worker_id"),
        "status": task.get("status"),
        "queue_position": task.get("queue_position"),
        "report_id": task.get("report_id"),
        "prompt": str(task.get("prompt") or "")[:500],
        "next_valid_actions": _fleet_next_actions_for_task(task),
    }


def _fleet_next_actions_for_task(task: Dict[str, Any]) -> list[str]:
    status = str(task.get("status") or "").strip().lower()
    if status == "queued":
        return ["fleet_delete_queued_message", "fleet_reorder_worker_queue", "fleet_steer_queued_message"]
    if status in {"running", "paused", "blocked", "needs_review"}:
        return ["fleet_redirect_worker_task", "fleet_stop_worker", "fleet_update_task"]
    if status == "completed":
        return ["fleet_read_report", "fleet_continue_worker_queue"]
    if status in {"failed", "stopped", "canceled"}:
        return ["fleet_read_report", "fleet_search_reports"]
    return []


def _fleet_manager_contract(snapshot: Dict[str, Any]) -> dict[str, str]:
    worker_names = [
        str(worker.get("display_name") or worker.get("worker_id") or "").strip()
        for worker in list(snapshot.get("workers") or [])[:8]
    ]
    worker_text = ", ".join([name for name in worker_names if name]) or "workers available"
    computer_names = [
        str(computer.get("display_name") or computer.get("desktop_id") or "").strip()
        for computer in _fleet_direct_computers(snapshot)[:8]
    ]
    computer_text = ", ".join([name for name in computer_names if name]) or "no directly paired computers"
    return {
        "role": "system",
        "content": (
            "FLEET MANAGER MODE:\n"
            "- You are this computer's local manager in an EmploAI worker fleet.\n"
            "- Answer conversational questions yourself. For an actionable request that needs desktop, browser, web, files, code, or other execution tools, delegate it with fleet_delegate instead of attempting execution as the manager.\n"
            "- Unqualified actionable work routes to this computer's protected default worker. A named child computer routes to that child's default worker; requests to coordinate a child route to its manager; an explicit identity name wins.\n"
            "- Use Fleet tools to control workers: create workers, group workers, send or queue work, redirect active work, stop workers, inspect reports/evidence, and continue queues.\n"
            "- Setup/list tools are available even when there are zero workers. Create or enroll workers when the user asks for fleet setup.\n"
            "- Paired-computer tools can list published targets, delegate work, create an allowed remote-local worker, and check or start a remote backend or desktop even when its normal EmploAI runtime is closed.\n"
            "- Do not use fleet tools for ordinary chat, simple questions, or tasks the manager should answer directly.\n"
            "- For broad delegation, inspect status first, assign clear task prompts, monitor milestones, read reports, then synthesize results for the user.\n"
            "- Sending a message to a busy worker queues by default. Redirecting the active task requires fleet_redirect_worker_task or fleet_steer_queued_message.\n"
            "- After a worker report, review the report before calling fleet_continue_worker_queue. Failed, blocked, low-confidence, stopped, canceled, or needs-review reports require manager review instead of continuing.\n"
            "- Destructive, bulk, and access-sensitive actions require same-surface confirmation before executing.\n"
            "- Prefer compact report/evidence/search tools over loading full timelines unless the user asks or the report is ambiguous.\n"
            f"- Known workers this turn: {worker_text}.\n"
            f"- Directly paired computers this turn: {computer_text}."
        ),
    }


def _fleet_worker_contract(session: Any) -> dict[str, str]:
    worker_label = (
        str(getattr(session, "fleet_worker_id", "") or "").strip()
        or str(getattr(session, "fleet_identity_id", "") or "").strip()
        or "this worker"
    )
    delegated = str(getattr(session, "fleet_task_mode", "") or "").strip().lower() == "delegated"
    if not delegated:
        return {
            "role": "system",
            "content": (
                "DIRECT WORKER CHAT:\n"
                f"- You are {worker_label}, an execution identity owned by this computer's manager.\n"
                "- This is a normal persistent user chat, not a delegated Fleet assignment.\n"
                "- Use only the worker's configured execution profile and answer naturally.\n"
                "- Do not emit the structured Fleet report format unless the user explicitly asks for it."
            ),
        }
    return {
        "role": "system",
        "content": (
            "FLEET WORKER MODE:\n"
            f"- You are {worker_label}, a managed worker reporting upward to the Fleet manager.\n"
            "- Treat the manager's assigned task as the active completion contract for this worker chat.\n"
            "- Emit concise progress milestones at task start, major phase changes, true blockers, and completion. Do not narrate every tool call.\n"
            "- Before declaring completion, verify the actual success criteria using the available tools and evidence.\n"
            "- If a method fails, change state or choose a meaningfully different method before retrying. Do not loop the same failed action.\n"
            "- If you are blocked, state the exact blocker and what manager action would unblock you.\n"
            "- Your final answer must be a strict structured worker report with these labels: status, summary, evidence, artifacts, blockers, confidence, next_suggested_action.\n"
            "- Use status completed, failed, stopped, blocked, needs_review, or canceled. Evidence is required only when tools, files, screens, apps, or external state were used."
        ),
    }


def _is_fleet_worker_session(session: Any) -> bool:
    role = str(getattr(session, "fleet_identity_role", "") or "").strip().lower()
    return role == "worker" or bool(str(getattr(session, "fleet_worker_id", "") or "").strip())


def _fleet_tool_list_workers(session: Any, _args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    if snapshot.get("error"):
        return snapshot
    _invalidate_fleet_manager_tool_context(session)
    return _fleet_compact_snapshot(snapshot)


def _fleet_tool_create_local_worker(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    result = _fleet_api_request(
        "POST",
        "/api/fleet/workers/local",
        {
            "display_name": str(args.get("display_name") or "").strip(),
            "metadata": {"created_by": "manager_chat_user_request"},
        },
    )
    _invalidate_fleet_manager_tool_context(session)
    return result


def _fleet_tool_create_enrollment(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    result = _fleet_api_request(
        "POST",
        "/api/fleet/enrollments",
        {
            "display_name": str(args.get("display_name") or "").strip() or None,
            "expires_in_seconds": args.get("expires_in_seconds") or 1800,
            "metadata": {"created_by": "manager_agent"},
        },
    )
    _invalidate_fleet_manager_tool_context(session)
    return result


def _fleet_find_computer(snapshot: Dict[str, Any], selector: str) -> Optional[Dict[str, Any]]:
    clean = str(selector or "").strip().casefold()
    if not clean:
        return None
    matches = [
        computer
        for computer in _fleet_direct_computers(snapshot)
        if clean
        in {
            str(computer.get("desktop_id") or "").strip().casefold(),
            str(computer.get("display_name") or "").strip().casefold(),
            str(computer.get("name") or "").strip().casefold(),
        }
    ]
    return matches[0] if len(matches) == 1 else None


def _fleet_direct_computers(snapshot: Dict[str, Any]) -> list[Dict[str, Any]]:
    manager_desktop_id = str((snapshot.get("manager") or {}).get("desktop_id") or "").strip()
    desktops = [
        item
        for item in list(snapshot.get("desktops") or [])
        if str(item.get("desktop_id") or "").strip()
        and str(item.get("desktop_id") or "").strip() != manager_desktop_id
    ]
    published_ids = {
        str(item.get("desktop_id") or "").strip()
        for item in list(snapshot.get("connection_permissions") or [])
        if str(item.get("source") or "").strip().lower() == "paired_desktop"
    }
    if published_ids:
        return [item for item in desktops if str(item.get("desktop_id") or "").strip() in published_ids]
    return desktops


def _fleet_compact_computer_view(snapshot: Dict[str, Any], computer: Dict[str, Any]) -> Dict[str, Any]:
    desktop_id = str(computer.get("desktop_id") or "").strip()
    permission_state = next(
        (
            item
            for item in list(snapshot.get("connection_permissions") or [])
            if str(item.get("desktop_id") or "").strip() == desktop_id
        ),
        {},
    )
    permissions = dict(permission_state.get("permissions") or {})
    targets = []
    for target in list((permission_state.get("capabilities") or {}).get("targets") or []):
        target_kind = str(target.get("target_kind") or "").strip().lower()
        if target_kind == "manager" and not permissions.get("delegate_manager"):
            continue
        if target_kind == "worker" and not permissions.get("delegate_workers"):
            continue
        targets.append({
            "target_kind": target_kind,
            "target_selector": target.get("target_selector"),
            "display_name": target.get("display_name"),
            "status": target.get("status"),
            "is_default": bool(target.get("is_default")),
            "protected": bool(target.get("protected")),
            "tool_profile": target.get("tool_profile"),
            "capability_tags": list(target.get("capability_tags") or []),
        })
    return {
        "desktop_id": desktop_id,
        "display_name": computer.get("display_name"),
        "status": computer.get("status"),
        "detail": computer.get("detail"),
        "last_heartbeat_at": computer.get("last_heartbeat_at"),
        "permissions": permissions,
        "targets": targets,
    }


def _fleet_tool_list_computers(session: Any, _args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    if snapshot.get("error"):
        return snapshot
    _invalidate_fleet_manager_tool_context(session)
    computers = [_fleet_compact_computer_view(snapshot, item) for item in _fleet_direct_computers(snapshot)]
    return {"computers": computers, "count": len(computers)}


def _fleet_origin_refs(session: Any) -> Dict[str, Any]:
    persisted = getattr(session, "session", None)
    session_id = str(getattr(persisted, "id", None) or getattr(session, "id", "") or "").strip() or None
    history = list(getattr(persisted, "chat_history", None) or getattr(session, "chat_history", None) or [])
    last_user = next((item for item in reversed(history) if str(item.get("role") or "") == "user"), {})
    if isinstance(last_user, dict) and not str(last_user.get("stable_message_id") or "").strip():
        last_user["stable_message_id"] = str(uuid.uuid4())
    return {
        "origin_manager_session_id": session_id,
        "origin_manager_message_id": str(last_user.get("stable_message_id") or last_user.get("message_id") or last_user.get("client_message_id") or "").strip() or None,
        "origin_run_id": str(getattr(session, "current_run_id", "") or "").strip() or None,
        "workspace": str(getattr(persisted, "workspace", None) or getattr(session, "workspace", "") or "").strip() or None,
        "workspace_id": getattr(persisted, "workspace_id", None) or getattr(session, "workspace_id", None),
        "security_permission_mode": getattr(persisted, "security_permission_mode", None) or getattr(session, "security_permission_mode", None),
    }


def _fleet_tool_delegate(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    prompt = str(args.get("prompt") or "").strip()
    if not prompt:
        return {"error": "prompt is required.", "error_type": "missing_prompt"}
    result = _fleet_api_request(
        "POST",
        "/api/fleet/delegations/route",
        {
            "scope": str(args.get("scope") or "auto").strip().lower(),
            "computer": str(args.get("computer") or "").strip() or None,
            "identity": str(args.get("identity") or "").strip() or None,
            "target_role": str(args.get("target_role") or "auto").strip().lower(),
            "prompt": prompt,
            "continuation_task_id": str(args.get("continuation_task_id") or "").strip() or None,
            **_fleet_origin_refs(session),
            "metadata": {"assigned_from": "manager_agent"},
        },
    )
    _invalidate_fleet_manager_tool_context(session)
    return result


def _fleet_tool_context_search(_session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return {"error": "query is required.", "error_type": "missing_query"}
    return _fleet_api_request(
        "POST",
        "/api/fleet/context/search",
        {
            "query": query,
            "computer": str(args.get("computer") or "").strip() or None,
            "include_descendants": True,
            "limit": max(1, min(int(args.get("limit") or 20), 100)),
        },
    )


def _fleet_tool_context_window(_session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    message_id = str(args.get("message_id") or "").strip()
    if not message_id:
        return {"error": "message_id is required.", "error_type": "missing_message_id"}
    return _fleet_api_request(
        "POST",
        "/api/fleet/context/window",
        {
            "message_id": message_id,
            "computer": str(args.get("computer") or "").strip() or None,
            "direction": str(args.get("direction") or "around").strip().lower(),
            "cursor": str(args.get("cursor") or "").strip() or None,
        },
    )


def _fleet_tool_delegate_computer(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    if snapshot.get("error"):
        return snapshot
    computer = _fleet_find_computer(snapshot, str(args.get("computer") or ""))
    if not computer:
        return {"error": "Paired computer not found or name is ambiguous.", "error_type": "computer_not_found"}
    prompt = str(args.get("prompt") or "").strip()
    if not prompt:
        return {"error": "prompt is required.", "error_type": "missing_prompt"}
    target_kind = str(args.get("target_kind") or "worker").strip().lower()
    if target_kind not in {"manager", "worker"}:
        return {"error": "target_kind must be manager or worker.", "error_type": "invalid_target_kind"}
    result = _fleet_api_request(
        "POST",
        "/api/fleet/delegations/route",
        {
            "scope": "child",
            "computer": str(computer.get("desktop_id") or ""),
            "prompt": prompt,
            "target_role": target_kind,
            "identity": str(args.get("target_selector") or "").strip() or None,
            **_fleet_origin_refs(session),
            "metadata": {"assigned_from": "manager_agent"},
        },
    )
    _invalidate_fleet_manager_tool_context(session)
    return result


def _fleet_tool_create_worker_on_computer(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    if snapshot.get("error"):
        return snapshot
    computer = _fleet_find_computer(snapshot, str(args.get("computer") or ""))
    if not computer:
        return {"error": "Paired computer not found or name is ambiguous.", "error_type": "computer_not_found"}
    display_name = str(args.get("display_name") or "").strip()
    if not display_name:
        return {"error": "display_name is required.", "error_type": "missing_display_name"}
    result = _fleet_api_request(
        "POST",
        f"/api/fleet/desktops/{quote(str(computer.get('desktop_id') or ''), safe='')}/workers",
        {"display_name": display_name},
    )
    _invalidate_fleet_manager_tool_context(session)
    return result


def _fleet_tool_computer_host_action(
    session: Any,
    args: Dict[str, Any],
    *,
    action: str,
) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    computer = _fleet_find_computer(snapshot, str(args.get("computer") or ""))
    if not computer:
        return {"error": "Paired computer not found or name is ambiguous.", "error_type": "computer_not_found"}
    desktop_id = quote(str(computer.get("desktop_id") or ""), safe="")
    method = "GET" if action == "status" else "POST"
    suffix = {
        "status": "host",
        "runtime": "host/runtime/start",
        "desktop": "host/desktop/start",
        "update_status": "update",
        "update_check": "update/check",
    }[action]
    result = _fleet_api_request(
        method,
        f"/api/fleet/desktops/{desktop_id}/{suffix}",
        {} if method == "POST" else None,
        timeout_seconds=4 * 60.0 if action == "update_check" else 10.0,
    )
    _invalidate_fleet_manager_tool_context(session)
    return result


def _fleet_tool_update_computer(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    computer = _fleet_find_computer(snapshot, str(args.get("computer") or ""))
    if not computer:
        return {"error": "Paired computer not found or name is ambiguous.", "error_type": "computer_not_found"}
    expected_commit = str(args.get("expected_commit") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        return {"error": "Use the full target commit returned by fleet_check_computer_update.", "error_type": "invalid_expected_commit"}
    action = "fleet_computer_update"
    if not bool(args.get("confirmed")):
        return _fleet_confirmation_required(
            session,
            action,
            f"Update and restart EmploAI on {computer.get('display_name') or computer.get('desktop_id')} to commit {expected_commit[:8]}.",
            {"desktop_id": computer.get("desktop_id"), "expected_commit": expected_commit},
        )
    confirmation_id, confirmation_error = _fleet_confirmation_id_for_execution(session, args, action_kind=action)
    if confirmation_error:
        return confirmation_error
    desktop_id = quote(str(computer.get("desktop_id") or ""), safe="")
    result = _fleet_api_request(
        "POST",
        f"/api/fleet/desktops/{desktop_id}/update/start",
        {"expected_commit": expected_commit},
        confirmation_id=confirmation_id,
        timeout_seconds=4 * 60.0,
    )
    _invalidate_fleet_manager_tool_context(session)
    return result


def _fleet_tool_rename_worker(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    worker = _fleet_find_worker(snapshot, str(args.get("worker") or ""))
    if not worker:
        return {"error": "Worker not found.", "error_type": "worker_not_found"}
    result = _fleet_api_request(
        "PUT",
        f"/api/fleet/workers/{quote(str(worker.get('worker_id') or ''), safe='')}",
        {"display_name": str(args.get("display_name") or "").strip(), "metadata": {"renamed_by": "manager_agent"}},
    )
    _invalidate_fleet_manager_tool_context(session)
    return result


def _fleet_tool_reset_or_delete_worker(session: Any, args: Dict[str, Any], *, reset: bool) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    worker = _fleet_find_worker(snapshot, str(args.get("worker") or ""))
    if not worker:
        return {"error": "Worker not found.", "error_type": "worker_not_found"}
    action = "fleet_worker_reset" if reset else "fleet_worker_delete"
    if not bool(args.get("confirmed")):
        return _fleet_confirmation_required(
            session,
            action,
            f"{'Reset' if reset else 'Delete'} {worker.get('display_name') or worker.get('worker_id')} from the live fleet.",
            {"worker_id": worker.get("worker_id"), "active_task_id": worker.get("active_task_id")},
        )
    confirmation_id, confirmation_error = _fleet_confirmation_id_for_execution(
        session,
        args,
        action_kind=action,
    )
    if confirmation_error:
        return confirmation_error
    path = (
        f"/api/fleet/workers/{quote(str(worker.get('worker_id') or ''), safe='')}/reset"
        if reset
        else f"/api/fleet/workers/{quote(str(worker.get('worker_id') or ''), safe='')}?wipe_state=true"
    )
    result = _fleet_api_request(
        "POST" if reset else "DELETE",
        path,
        {"reason": str(args.get("reason") or action), "metadata": {"requested_by": "manager_agent"}} if reset else None,
        confirmation_id=confirmation_id,
    )
    _invalidate_fleet_manager_tool_context(session)
    return result


def _fleet_tool_list_groups(_session: Any, _args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    if snapshot.get("error"):
        return snapshot
    return {"groups": list(snapshot.get("groups") or []), "count": len(list(snapshot.get("groups") or []))}


def _fleet_tool_create_group(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    result = _fleet_api_request(
        "POST",
        "/api/fleet/groups",
        {
            "display_name": str(args.get("display_name") or "").strip(),
            "description": str(args.get("description") or "").strip() or None,
            "worker_ids": list(args.get("worker_ids") or []),
            "metadata": {"created_by": "manager_agent"},
        },
    )
    _invalidate_fleet_manager_tool_context(session)
    return result


def _fleet_tool_update_group(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    group = _fleet_find_group(snapshot, str(args.get("group") or ""))
    if not group:
        return {"error": "Group not found.", "error_type": "group_not_found"}
    result = _fleet_api_request(
        "PUT",
        f"/api/fleet/groups/{quote(str(group.get('group_id') or ''), safe='')}",
        {
            "display_name": str(args.get("display_name") or group.get("display_name") or "").strip(),
            "description": args.get("description") if args.get("description") is not None else group.get("description"),
            "worker_ids": list(args.get("worker_ids") if args.get("worker_ids") is not None else group.get("worker_ids") or []),
            "metadata": {**dict(group.get("metadata") or {}), "updated_by": "manager_agent"},
        },
    )
    _invalidate_fleet_manager_tool_context(session)
    return result


def _fleet_tool_delete_group(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    group = _fleet_find_group(snapshot, str(args.get("group") or ""))
    if not group:
        return {"error": "Group not found.", "error_type": "group_not_found"}
    if not bool(args.get("confirmed")):
        return _fleet_confirmation_required(
            session,
            "fleet_group_delete",
            f"Delete group {group.get('display_name') or group.get('group_id')}.",
            {"group_id": group.get("group_id"), "worker_ids": group.get("worker_ids") or []},
        )
    confirmation_id, confirmation_error = _fleet_confirmation_id_for_execution(
        session,
        args,
        action_kind="fleet_group_delete",
    )
    if confirmation_error:
        return confirmation_error
    result = _fleet_api_request(
        "DELETE",
        f"/api/fleet/groups/{quote(str(group.get('group_id') or ''), safe='')}",
        confirmation_id=confirmation_id,
    )
    _invalidate_fleet_manager_tool_context(session)
    return result


def _fleet_tool_assign_task(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    if snapshot.get("error"):
        return snapshot
    worker = _fleet_find_worker(snapshot, str(args.get("worker") or ""))
    if not worker:
        return {"error": "Worker not found. Call fleet_list_workers and choose an exact worker id or display name.", "error_type": "worker_not_found"}
    prompt = str(args.get("prompt") or "").strip()
    if not prompt:
        return {"error": "Task prompt is required.", "error_type": "missing_prompt"}
    task = _fleet_api_request(
        "POST",
        f"/api/fleet/workers/{quote(str(worker.get('worker_id') or ''), safe='')}/tasks",
        {"prompt": prompt, "source": "manager_agent", "metadata": {"assigned_by": "manager_agent", **dict(args.get("metadata") or {})}},
    )
    _invalidate_fleet_manager_tool_context(session)
    if task.get("error"):
        return task
    return {
        "worker": {
            "worker_id": worker.get("worker_id"),
            "display_name": worker.get("display_name"),
            "status_before": worker.get("status"),
        },
        "task": task,
        "delivery": "started" if str(task.get("status") or "") == "running" else "queued",
    }


def _fleet_tool_assign_group_task(session: Any, args: Dict[str, Any], *, message: bool = False) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    if snapshot.get("error"):
        return snapshot
    group = _fleet_find_group(snapshot, str(args.get("group") or ""))
    if not group:
        return {"error": "Group not found.", "error_type": "group_not_found"}
    prompt = str((args.get("message") if message else args.get("prompt")) or "").strip()
    if not prompt:
        return {"error": "Message or task prompt is required.", "error_type": "missing_prompt"}
    worker_ids = list(group.get("worker_ids") or [])
    if not bool(args.get("confirmed")):
        return _fleet_confirmation_required(
            session,
            "fleet_group_dispatch",
            f"Dispatch to group {group.get('display_name') or group.get('group_id')} with {len(worker_ids)} workers.",
            {"group_id": group.get("group_id"), "worker_ids": worker_ids, "prompt": prompt[:500]},
        )
    confirmation_id, confirmation_error = _fleet_confirmation_id_for_execution(
        session,
        args,
        action_kind="fleet_group_dispatch",
    )
    if confirmation_error:
        return confirmation_error
    result = _fleet_api_request(
        "POST",
        f"/api/fleet/groups/{quote(str(group.get('group_id') or ''), safe='')}/tasks",
        {
            "prompt": prompt,
            "source": "manager_agent",
            "metadata": {
                "assigned_by": "manager_agent",
                "message_kind": "manager_message" if message else "task",
                "bulk_dispatch_confirmed": True,
            },
        },
        confirmation_id=confirmation_id,
    )
    _invalidate_fleet_manager_tool_context(session)
    return {"tasks": result.get("result", result) if isinstance(result, dict) else result, "delivery": "bulk_dispatched"}


def _fleet_tool_send_worker_message(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    forwarded = dict(args)
    forwarded["prompt"] = str(args.get("message") or "")
    forwarded["metadata"] = {"message_kind": "manager_message", "queued_by_default": True}
    result = _fleet_tool_assign_task(session, forwarded)
    if isinstance(result.get("task"), dict):
        result["task"] = _fleet_compact_task_result(result["task"])
    result["message_kind"] = "manager_message"
    return result


def _fleet_tool_inspect_worker(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    if snapshot.get("error"):
        return snapshot
    _invalidate_fleet_manager_tool_context(session)
    worker = _fleet_find_worker(snapshot, str(args.get("worker") or ""))
    if not worker:
        return {"error": "Worker not found.", "error_type": "worker_not_found"}
    worker_id = str(worker.get("worker_id") or "")
    return _fleet_compact_worker_view(snapshot, worker) | {
        "tasks": [
            task
            for task in list(snapshot.get("tasks") or [])
            if str(task.get("worker_id") or "") == worker_id
        ][:20],
        "reports": [
            report
            for report in list(snapshot.get("reports") or [])
            if str(report.get("worker_id") or "") == worker_id
        ][:10],
    }


def _fleet_tool_read_report(_session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    if snapshot.get("error"):
        return snapshot
    report = _fleet_find_report(snapshot, report_id=str(args.get("report_id") or ""), task_id=str(args.get("task_id") or ""))
    if not report:
        return {"error": "Report not found.", "error_type": "report_not_found"}
    return {"report": report, "next_valid_actions": ["fleet_continue_worker_queue", "fleet_open_worker_timeline"]}


def _fleet_tool_inspect_evidence(_session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    if snapshot.get("error"):
        return snapshot
    report = _fleet_find_report(snapshot, report_id=str(args.get("report_id") or ""), task_id=str(args.get("task_id") or ""))
    if not report and str(args.get("worker") or "").strip():
        worker = _fleet_find_worker(snapshot, str(args.get("worker") or ""))
        if worker:
            report = next(
                (item for item in list(snapshot.get("reports") or []) if str(item.get("worker_id") or "") == str(worker.get("worker_id") or "")),
                None,
            )
    if not report:
        return {"error": "Report not found.", "error_type": "report_not_found"}
    return {
        "report_id": report.get("report_id"),
        "task_id": report.get("task_id"),
        "worker_id": report.get("worker_id"),
        "status": report.get("status"),
        "summary": report.get("summary"),
        "evidence": report.get("evidence") or [],
        "artifacts": report.get("artifacts") or [],
        "blockers": report.get("blockers") or [],
    }


def _fleet_tool_open_worker_timeline(_session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    if snapshot.get("error"):
        return snapshot
    worker = _fleet_find_worker(snapshot, str(args.get("worker") or ""))
    if not worker:
        return {"error": "Worker not found.", "error_type": "worker_not_found"}
    worker_id = str(worker.get("worker_id") or "")
    tasks = [_fleet_compact_task_result(task) for task in list(snapshot.get("tasks") or []) if str(task.get("worker_id") or "") == worker_id][:25]
    reports = [report for report in list(snapshot.get("reports") or []) if str(report.get("worker_id") or "") == worker_id][:10]
    return {"worker": _fleet_compact_worker_view(snapshot, worker), "tasks": tasks, "reports": reports}


def _fleet_tool_request_worker_preview(_session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    if snapshot.get("error"):
        return snapshot
    worker = _fleet_find_worker(snapshot, str(args.get("worker") or ""))
    if not worker:
        return {"error": "Worker not found.", "error_type": "worker_not_found"}
    return _fleet_api_request("POST", f"/api/fleet/workers/{quote(str(worker.get('worker_id') or ''), safe='')}/preview", {})


def _fleet_tool_search_reports(_session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    if snapshot.get("error"):
        return snapshot
    worker = None
    worker_selector = str(args.get("worker") or "").strip()
    if worker_selector:
        worker = _fleet_find_worker(snapshot, worker_selector)
        if not worker:
            return {"error": "Worker not found.", "error_type": "worker_not_found"}
    query = str(args.get("query") or "").strip().lower()
    status = str(args.get("status") or "").strip().lower()
    try:
        limit = max(1, min(20, int(args.get("limit") or 5)))
    except Exception:
        limit = 5
    reports = []
    for report in list(snapshot.get("reports") or []):
        if worker and str(report.get("worker_id") or "") != str(worker.get("worker_id") or ""):
            continue
        if status and str(report.get("status") or "").lower() != status:
            continue
        searchable = " ".join(
            [
                str(report.get("summary") or ""),
                str(report.get("next_suggested_action") or ""),
                json.dumps(report.get("blockers") or [], ensure_ascii=False),
            ]
        ).lower()
        if query and query not in searchable:
            continue
        reports.append(report)
        if len(reports) >= limit:
            break
    return {"reports": reports, "count": len(reports)}


def _fleet_tool_redirect_worker_task(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    if snapshot.get("error"):
        return snapshot
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        worker = _fleet_find_worker(snapshot, str(args.get("worker") or ""))
        if not worker:
            return {"error": "task_id or a valid worker with an active task is required.", "error_type": "task_not_found"}
        task_id = str(worker.get("active_task_id") or "").strip()
    if not task_id:
        return {"error": "No active task found to redirect.", "error_type": "task_not_found"}
    result = _fleet_api_request(
        "POST",
        f"/api/fleet/tasks/{quote(task_id, safe='')}/redirect",
        {"direction": str(args.get("direction") or "").strip(), "source": "manager_agent", "metadata": {"redirected_by": "manager_agent"}},
    )
    _invalidate_fleet_manager_tool_context(session)
    return result


def _fleet_tool_delete_queued_message(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        return {"error": "task_id is required.", "error_type": "missing_task_id"}
    result = _fleet_api_request(
        "PUT",
        f"/api/fleet/tasks/{quote(task_id, safe='')}/status",
        {"status": "canceled", "metadata": {"canceled_by": "manager_agent", "reason": "queued message deleted"}},
    )
    _invalidate_fleet_manager_tool_context(session)
    return result


def _fleet_tool_steer_queued_message(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    if snapshot.get("error"):
        return snapshot
    queued = _fleet_find_task(snapshot, str(args.get("task_id") or ""))
    if not queued:
        return {"error": "Queued task not found.", "error_type": "task_not_found"}
    if str(queued.get("status") or "") != "queued":
        return {"error": "Only queued tasks can be steered into an active task.", "error_type": "invalid_task_state"}
    worker = _fleet_find_worker(snapshot, str(queued.get("worker_id") or ""))
    active_task_id = str((worker or {}).get("active_task_id") or "").strip()
    if not active_task_id:
        return {"error": "Worker has no active task to steer.", "error_type": "worker_idle"}
    redirect = _fleet_api_request(
        "POST",
        f"/api/fleet/tasks/{quote(active_task_id, safe='')}/redirect",
        {
            "direction": str(queued.get("prompt") or ""),
            "source": "manager_agent",
            "metadata": {"steered_from_queued_task_id": queued.get("task_id")},
        },
    )
    cancel = _fleet_api_request(
        "PUT",
        f"/api/fleet/tasks/{quote(str(queued.get('task_id') or ''), safe='')}/status",
        {"status": "canceled", "metadata": {"canceled_by": "manager_agent", "steered_to_task_id": active_task_id}},
    )
    _invalidate_fleet_manager_tool_context(session)
    return {"redirect": redirect, "queued_task": cancel}


def _fleet_tool_reorder_worker_queue(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    worker = _fleet_find_worker(snapshot, str(args.get("worker") or ""))
    if not worker:
        return {"error": "Worker not found.", "error_type": "worker_not_found"}
    result = _fleet_api_request(
        "PUT",
        "/api/fleet/tasks/reorder",
        {"worker_id": worker.get("worker_id"), "task_ids": list(args.get("task_ids") or [])},
    )
    _invalidate_fleet_manager_tool_context(session)
    return {"tasks": result.get("result", result)}


def _fleet_tool_continue_worker_queue(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    worker = _fleet_find_worker(snapshot, str(args.get("worker") or ""))
    if not worker:
        return {"error": "Worker not found.", "error_type": "worker_not_found"}
    result = _fleet_api_request(
        "POST",
        f"/api/fleet/workers/{quote(str(worker.get('worker_id') or ''), safe='')}/queue/continue",
        {
            "reviewed_report_id": str(args.get("reviewed_report_id") or "").strip() or None,
            "source": "manager_agent",
            "metadata": {"continued_by": "manager_agent"},
        },
    )
    _invalidate_fleet_manager_tool_context(session)
    return result


def _fleet_tool_stop_worker(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    worker = _fleet_find_worker(snapshot, str(args.get("worker") or ""))
    if not worker:
        return {"error": "Worker not found.", "error_type": "worker_not_found"}
    result = _fleet_api_request(
        "POST",
        f"/api/fleet/workers/{quote(str(worker.get('worker_id') or ''), safe='')}/stop",
        {"reason": str(args.get("reason") or "Stopped by manager agent"), "metadata": {"stopped_by": "manager_agent"}},
    )
    _invalidate_fleet_manager_tool_context(session)
    return result


def _fleet_tool_stop_all(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    if not bool(args.get("confirmed")):
        return _fleet_confirmation_required(
            session,
            "fleet_stop_all",
            "Stop every reachable active fleet run.",
            {"reason": str(args.get("reason") or "Fleet stop all")},
        )
    confirmation_id, confirmation_error = _fleet_confirmation_id_for_execution(
        session,
        args,
        action_kind="fleet_stop_all",
    )
    if confirmation_error:
        return confirmation_error
    result = _fleet_api_request(
        "POST",
        "/api/fleet/stop-all",
        {"reason": str(args.get("reason") or "Fleet stop all"), "metadata": {"stopped_by": "manager_agent"}},
        confirmation_id=confirmation_id,
    )
    _invalidate_fleet_manager_tool_context(session)
    return result


def _fleet_tool_update_task(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    action = str(args.get("action") or "").strip().lower()
    status_by_action = {
        "pause": "paused",
        "resume": "running",
        "stop": "stopped",
        "cancel": "canceled",
    }
    if action not in status_by_action:
        return {"error": "Unsupported action. Use pause, resume, stop, or cancel.", "error_type": "invalid_action"}

    snapshot = _fleet_snapshot_uncached()
    if snapshot.get("error"):
        return snapshot
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        worker = _fleet_find_worker(snapshot, str(args.get("worker") or ""))
        if not worker:
            return {"error": "task_id or a valid worker with an active task is required.", "error_type": "task_not_found"}
        task_id = str(worker.get("active_task_id") or "").strip()
    if not task_id:
        return {"error": "No active task was found to update.", "error_type": "task_not_found"}
    result = _fleet_api_request(
        "PUT",
        f"/api/fleet/tasks/{quote(task_id, safe='')}/status",
        {"status": status_by_action[action], "metadata": {"reason": str(args.get("reason") or ""), "updated_by": "manager_agent"}},
    )
    _invalidate_fleet_manager_tool_context(session)
    return result


def _fleet_tool_list_tool_grants(_session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    if snapshot.get("error"):
        return snapshot
    worker = _fleet_find_worker(snapshot, str(args.get("worker") or "")) if str(args.get("worker") or "").strip() else None
    status = str(args.get("status") or "").strip().lower()
    grants = []
    for grant in list(snapshot.get("tool_grants") or []):
        if worker and str(grant.get("target_id") or "") != str(worker.get("worker_id") or ""):
            continue
        if status and str(grant.get("status") or "").lower() != status:
            continue
        grants.append(grant)
    return {"tool_grants": grants[:50], "count": len(grants)}


def _fleet_tool_decide_tool_grant(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    approved_turns = args.get("approved_turns")
    try:
        turns = max(1, min(10, int(approved_turns))) if approved_turns is not None else None
    except Exception:
        turns = None
    result = _fleet_api_request(
        "POST",
        f"/api/fleet/tool-grants/{quote(str(args.get('grant_id') or ''), safe='')}/decision",
        {"approved": bool(args.get("approved")), "approved_turns": turns, "approved_by": "manager_agent"},
    )
    _invalidate_fleet_manager_tool_context(session)
    return result


def _fleet_tool_check_workspace_binding(_session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = _fleet_snapshot_uncached()
    if snapshot.get("error"):
        return snapshot
    workspace_id = str(args.get("workspace_id") or "").strip()
    machine_id = str(args.get("machine_id") or "").strip()
    bindings = []
    for binding in list(snapshot.get("workspace_bindings") or []):
        if workspace_id and str(binding.get("workspace_id") or "") != workspace_id:
            continue
        if machine_id and str(binding.get("machine_id") or "") != machine_id:
            continue
        bindings.append(binding)
    active = [item for item in bindings if str(item.get("status") or "").lower() == "active"]
    return {"bindings": bindings, "can_write": bool(active), "status": "active" if active else "needs_reconnect"}


def _fleet_tool_request_workspace_reconnect(_session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": True,
        "status": "needs_user_action",
        "workspace_id": str(args.get("workspace_id") or "").strip() or None,
        "machine_id": str(args.get("machine_id") or "").strip() or None,
        "reason": str(args.get("reason") or "Workspace binding must be reconnected before file-writing work."),
        "next_valid_actions": ["Ask the user to reconnect the folder on the relevant machine."],
    }


def _fleet_manager_tool_handlers(session: Any) -> Dict[str, Callable[[Dict[str, Any]], Any]]:
    return {
        "fleet_list_workers": lambda args: _fleet_tool_list_workers(session, args),
        "fleet_create_local_worker": lambda args: _fleet_tool_create_local_worker(session, args),
        "fleet_create_enrollment": lambda args: _fleet_tool_create_enrollment(session, args),
        "fleet_delegate": lambda args: _fleet_tool_delegate(session, args),
        "fleet_context_search": lambda args: _fleet_tool_context_search(session, args),
        "fleet_context_window": lambda args: _fleet_tool_context_window(session, args),
        "fleet_list_computers": lambda args: _fleet_tool_list_computers(session, args),
        "fleet_delegate_computer": lambda args: _fleet_tool_delegate_computer(session, args),
        "fleet_create_worker_on_computer": lambda args: _fleet_tool_create_worker_on_computer(session, args),
        "fleet_computer_host_status": lambda args: _fleet_tool_computer_host_action(session, args, action="status"),
        "fleet_start_computer_runtime": lambda args: _fleet_tool_computer_host_action(session, args, action="runtime"),
        "fleet_start_computer_desktop": lambda args: _fleet_tool_computer_host_action(session, args, action="desktop"),
        "fleet_check_computer_update": lambda args: _fleet_tool_computer_host_action(session, args, action="update_check"),
        "fleet_update_computer": lambda args: _fleet_tool_update_computer(session, args),
        "fleet_rename_worker": lambda args: _fleet_tool_rename_worker(session, args),
        "fleet_reset_worker": lambda args: _fleet_tool_reset_or_delete_worker(session, args, reset=True),
        "fleet_delete_worker": lambda args: _fleet_tool_reset_or_delete_worker(session, args, reset=False),
        "fleet_list_groups": lambda args: _fleet_tool_list_groups(session, args),
        "fleet_create_group": lambda args: _fleet_tool_create_group(session, args),
        "fleet_update_group": lambda args: _fleet_tool_update_group(session, args),
        "fleet_delete_group": lambda args: _fleet_tool_delete_group(session, args),
        "fleet_assign_task": lambda args: _fleet_tool_assign_task(session, args),
        "fleet_assign_group_task": lambda args: _fleet_tool_assign_group_task(session, args),
        "fleet_send_worker_message": lambda args: _fleet_tool_send_worker_message(session, args),
        "fleet_send_group_message": lambda args: _fleet_tool_assign_group_task(session, args, message=True),
        "fleet_redirect_worker_task": lambda args: _fleet_tool_redirect_worker_task(session, args),
        "fleet_delete_queued_message": lambda args: _fleet_tool_delete_queued_message(session, args),
        "fleet_steer_queued_message": lambda args: _fleet_tool_steer_queued_message(session, args),
        "fleet_reorder_worker_queue": lambda args: _fleet_tool_reorder_worker_queue(session, args),
        "fleet_continue_worker_queue": lambda args: _fleet_tool_continue_worker_queue(session, args),
        "fleet_inspect_worker": lambda args: _fleet_tool_inspect_worker(session, args),
        "fleet_search_reports": lambda args: _fleet_tool_search_reports(session, args),
        "fleet_read_report": lambda args: _fleet_tool_read_report(session, args),
        "fleet_inspect_evidence": lambda args: _fleet_tool_inspect_evidence(session, args),
        "fleet_open_worker_timeline": lambda args: _fleet_tool_open_worker_timeline(session, args),
        "fleet_request_worker_preview": lambda args: _fleet_tool_request_worker_preview(session, args),
        "fleet_update_task": lambda args: _fleet_tool_update_task(session, args),
        "fleet_stop_worker": lambda args: _fleet_tool_stop_worker(session, args),
        "fleet_stop_all": lambda args: _fleet_tool_stop_all(session, args),
        "fleet_list_tool_grants": lambda args: _fleet_tool_list_tool_grants(session, args),
        "fleet_decide_tool_grant": lambda args: _fleet_tool_decide_tool_grant(session, args),
        "fleet_check_workspace_binding": lambda args: _fleet_tool_check_workspace_binding(session, args),
        "fleet_request_workspace_reconnect": lambda args: _fleet_tool_request_workspace_reconnect(session, args),
    }


def _fleet_upstream_tool_handlers(session: Any) -> Dict[str, Callable[[Dict[str, Any]], Any]]:
    return {"fleet_request_manager": lambda args: _fleet_tool_request_manager(session, args)}


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_interrupt_policy(policy: str) -> str:
    normalized = (policy or "none").strip().lower()
    return normalized if normalized in {"none", "steer_now", "after_tool"} else "none"


def _openai_function_tool(tool: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(tool.get("function"), dict):
        return tool
    return {
        "type": "function",
        "function": {
            "name": tool.get("name"),
            "description": tool.get("description", ""),
            "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
        },
    }


def _request_user_input_handler(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    question = normalize_plan_question(args or {})
    state = ensure_plan_mode(session)
    timestamp = datetime.now().isoformat()
    state["status"] = "awaiting_user_input"
    state["updated_at"] = timestamp
    state["pending_question"] = question
    session.plan_mode = state
    message = {
        "role": "assistant",
        "content": question["question"],
        "timestamp": timestamp,
        "channel": "app",
        "source_format": "app_plan_question",
        "display_label": "Plan",
        "metadata": {"plan_question": question},
    }
    session.chat_history.append(message)
    session.save_session()
    session_id = session.session_manager.get_current_session_id() if getattr(session, "session_manager", None) else None
    user_id = getattr(session, "sync_user_id", None) or getattr(session, "user_id", None)
    if user_id is not None and session_id:
        get_channel_sync_hub().publish(
            user_id=user_id,
            event={
                "type": "assistant_final",
                "session_id": session_id,
                "origin_channel": "app",
                "payload": {
                    "message": message,
                    "text": question["question"],
                },
            },
        )
    return {
        "ok": True,
        "status": "waiting_for_user",
        "question_id": question["question_id"],
        "message": "Question sent to the user. Stop and wait for the answer before finalizing the plan.",
    }


def _update_goal_status_handler(session: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    result = apply_goal_status_update(session, args or {})
    session.save_session()
    return result


def _apply_incoming_mode_state(
    session: Any,
    *,
    user_message: str,
    run_mode: Optional[str],
    plan_action: Optional[str],
    plan_answer: Optional[Dict[str, Any]],
) -> str:
    effective_mode = normalize_run_mode(run_mode)
    action = normalize_plan_action(plan_action)

    if action in {"approve", "dismiss", "exit"}:
        exit_plan_mode(session, reason=action)
        if action in {"dismiss", "exit"}:
            effective_mode = "normal"

    if effective_mode == "plan" or active_plan_mode(session):
        if action == "answer_question":
            state = ensure_plan_mode(session)
            state["pending_question"] = None
            state["status"] = "active"
            state["updated_at"] = datetime.now().isoformat()
            if plan_answer:
                state["last_answer"] = dict(plan_answer)
            session.plan_mode = state
        elif effective_mode == "plan":
            ensure_plan_mode(session)
        if active_plan_mode(session):
            effective_mode = "plan"

    if normalize_run_mode(run_mode) == "goal":
        start_goal(session, user_message)
        effective_mode = "goal"

    return effective_mode


def _steering_beta_enabled(session: Any) -> bool:
    env_value = os.getenv(STEERING_BETA_ENV)
    if env_value is not None and env_value.strip():
        return _truthy(env_value)

    workspace = Path(getattr(session, "workspace", Path.cwd()))
    config = get_live_config(workspace / "config.json")
    return bool(config.get("channels.app.steering_beta", False))


def _publish_app_message_sync(
    session: Any,
    *,
    session_id: Optional[str],
    message: Dict[str, Any],
) -> None:
    user_id = getattr(session, "sync_user_id", None)
    if user_id is None:
        user_id = getattr(session, "user_id", None)
    if user_id is None or not session_id:
        return

    get_channel_sync_hub().publish(
        user_id=user_id,
        event={
            "type": "user_message",
            "session_id": session_id,
            "origin_channel": message.get("channel"),
            "source_client_id": message.get("source_client_id"),
            "payload": {
                "message": message,
                "text": message.get("content", ""),
            },
        },
    )


async def _request_app_steering(
    session: Any,
    *,
    user_message: str,
    source_format: str,
    interrupt_policy: str,
    surface_mode: Optional[str] = None,
    source_client_id: Optional[str] = None,
    client_message_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    policy = _normalize_interrupt_policy(interrupt_policy)
    if policy == "none" or not _steering_beta_enabled(session):
        return None

    async with session.lock:
        if not session.is_processing:
            return None

        timestamp = datetime.now().isoformat()
        display_label = "App Voice Steering" if source_format == "app_voice_transcript" else "App Steering"
        session.last_user_message = user_message
        steering_message = {
            "role": "user",
            "content": user_message,
            "timestamp": timestamp,
            "channel": "app",
            "source_format": source_format,
            "surface_mode": surface_mode,
            "display_label": display_label,
            "interrupt_policy": policy,
            "steering_beta": True,
            "source_client_id": source_client_id,
            "client_message_id": client_message_id,
        }
        session.chat_history.append(steering_message)

        if hasattr(session, "queue_interrupt"):
            session.queue_interrupt(user_message, deferred=(policy == "after_tool"))
        else:
            session.should_interrupt = True
            session.interrupt_message = user_message

        session.save_session()
        current_session_id = session.session_manager.get_current_session_id() if getattr(session, "session_manager", None) else None
        _publish_app_message_sync(
            session,
            session_id=current_session_id,
            message=steering_message,
        )

    return {
        "ok": True,
        "busy": False,
        "steering": True,
        "session_id": current_session_id,
        "assistant_text": "",
        "steering_policy": policy,
        "steering_status": "queued" if policy == "after_tool" else "armed",
        "context_compressed": False,
        "context_compaction": None,
    }


async def _notify_message_delivery(
    callback: Optional[Callable[[Dict[str, Any]], Any]],
    payload: Dict[str, Any],
) -> None:
    if callback is None:
        return
    try:
        result = callback(payload)
        if inspect.isawaitable(result):
            await result
    except Exception:
        # A disconnected origin must not abort a turn after its message was
        # accepted and persisted.
        pass


async def run_app_chat_turn(
    session: Any,
    *,
    user_message: str,
    source_format: str = "app_text",
    surface_mode: Optional[str] = None,
    interrupt_policy: str = "none",
    source_client_id: Optional[str] = None,
    client_message_id: Optional[str] = None,
    message_accepted_callback: Optional[Callable[[Dict[str, Any]], Any]] = None,
    run_mode: Optional[str] = None,
    plan_action: Optional[str] = None,
    plan_answer: Optional[Dict[str, Any]] = None,
    log_callback: Optional[Callable[[Dict[str, Any]], Any]] = None,
    retry_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    previous_surface_mode = getattr(session, "current_surface_mode", None)
    session.current_surface_mode = str(surface_mode or "chat").strip().lower() or "chat"
    steering_result = None
    if not retry_run_id:
        steering_result = await _request_app_steering(
            session,
            user_message=user_message,
            source_format=source_format,
            interrupt_policy=interrupt_policy,
            surface_mode=surface_mode,
            source_client_id=source_client_id,
            client_message_id=client_message_id,
        )
    if steering_result is not None:
        await _notify_message_delivery(
            message_accepted_callback,
            {
                "status": "steering",
                "session_id": steering_result.get("session_id"),
                "client_message_id": client_message_id,
            },
        )
        if previous_surface_mode is None:
            try:
                delattr(session, "current_surface_mode")
            except Exception:
                session.current_surface_mode = None
        else:
            session.current_surface_mode = previous_surface_mode
        return steering_result

    if source_format == "app_voice_transcript":
        display_label = "App Voice"
    elif source_format == "app_visual_monitor":
        display_label = "Visual Monitor"
    else:
        display_label = "App"
    effective_run_mode = _apply_incoming_mode_state(
        session,
        user_message=user_message,
        run_mode=run_mode,
        plan_action=plan_action,
        plan_answer=plan_answer,
    )
    session.current_turn_run_mode = effective_run_mode
    if retry_run_id:
        reservation = await reserve_failed_chat_turn_retry(session, run_id=retry_run_id)
    else:
        reservation = await begin_chat_turn(
            session,
            user_message=user_message,
            user_message_payload={
                "channel": "app",
                "source_format": source_format,
                "surface_mode": surface_mode,
                "display_label": display_label,
                "source_client_id": source_client_id,
                "client_message_id": client_message_id,
                "run_mode": effective_run_mode,
                "plan_action": normalize_plan_action(plan_action),
                **({"plan_answer": dict(plan_answer)} if isinstance(plan_answer, dict) else {}),
            },
        )
    if reservation.busy:
        await _notify_message_delivery(
            message_accepted_callback,
            {
                "status": "rejected",
                "retryable": True,
                "session_id": reservation.session_id,
                "client_message_id": client_message_id,
            },
        )
        if previous_surface_mode is None:
            try:
                delattr(session, "current_surface_mode")
            except Exception:
                session.current_surface_mode = None
        else:
            session.current_surface_mode = previous_surface_mode
        return {
            "ok": False,
            "busy": True,
            "session_id": reservation.session_id,
            "assistant_text": "",
        }

    reservation_event_meta = dict(getattr(reservation, "event_meta", {}) or {})
    await _notify_message_delivery(
        message_accepted_callback,
        {
            "status": "accepted",
            "session_id": reservation.session_id,
            "client_message_id": client_message_id,
            "run_id": reservation_event_meta.get("run_id"),
            "run_sequence": reservation_event_meta.get("run_sequence"),
        },
    )

    screen_observation_turn = is_screen_observation_message(user_message)
    task_like_turn = screen_observation_turn or is_task_like_message(user_message)
    tool_evidence_turn = request_requires_tool_evidence(user_message)
    fleet_tool_context = await _resolve_fleet_manager_tool_context(session)
    active_tool_packs = list(
        getattr(session, "_active_tool_packs_for_current_run", None)
        or getattr(session, "enabled_tool_packs", [])
        or []
    )
    fleet_role = str(getattr(session, "fleet_identity_role", "") or "").strip().lower()
    if fleet_tool_context.get("enabled"):
        fleet_role = "manager"
    if fleet_role in {"manager", "worker"}:
        active_tool_packs = role_locked_tool_packs(role=fleet_role, requested=active_tool_packs)
        session.enabled_tool_packs = list(active_tool_packs)
        persisted_session = getattr(session, "session", None)
        if persisted_session is not None:
            persisted_session.enabled_tool_packs = list(active_tool_packs)
    prelude_messages = []
    if tool_evidence_turn and len(session.chat_history) <= 3:
        prelude_messages.extend(_kickstart_prelude(active_tool_packs))

    system_messages = []
    if active_plan_mode(session):
        system_messages.append({"role": "system", "content": plan_mode_system_message(session)})
    if active_goal(session):
        goal_message = goal_mode_system_message(session)
        if goal_message:
            system_messages.append({"role": "system", "content": goal_message})
    if screen_observation_turn:
        system_messages.append(_screen_observation_contract(active_tool_packs))
    if source_format == "app_voice_transcript" and str(surface_mode or "").strip().lower() == "jarvis":
        system_messages.append(_jarvis_voice_response_contract())
    if source_format == "app_visual_monitor":
        system_messages.append(_visual_monitor_wake_contract(surface_mode))
    if _is_fleet_worker_session(session):
        system_messages.append(_fleet_worker_contract(session))
    upstream_tool_enabled = _fleet_upstream_tool_enabled()
    if upstream_tool_enabled:
        system_messages.append({
            "role": "system",
            "content": (
                "FLEET UPSTREAM CONNECTION:\n"
                "- This computer has one directly connected manager above it.\n"
                "- Use fleet_request_manager only when work needs a question answered, explicit approval, or a true blocker escalated.\n"
                "- The request sends only its type, message, and this local identity label; it does not expose chats, files, providers, or settings."
            ),
        })
    if tool_evidence_turn:
        system_messages.append(_task_execution_contract(session, active_tool_packs))
    if not tool_evidence_turn or not task_like_turn:
        system_messages.append(_conversational_turn_guard())
    if fleet_tool_context.get("enabled"):
        system_messages.append(_fleet_manager_contract(dict(fleet_tool_context.get("snapshot") or {})))
    manager_core_enabled = PACK_MANAGER_CORE in active_tool_packs
    session.current_turn_allowed_tool_names = tools_for_enabled_packs(active_tool_packs)
    plan_mode_active = bool(active_plan_mode(session))
    goal_mode_active = bool(active_goal(session))
    if manager_core_enabled and not plan_mode_active:
        session.current_turn_allowed_tool_names.update(FLEET_MANAGER_TOOL_NAMES)
    if upstream_tool_enabled and not plan_mode_active:
        session.current_turn_allowed_tool_names.update(FLEET_UPSTREAM_TOOL_NAMES)
    session.current_turn_allowed_tool_definitions = filter_tools_by_enabled_packs(CLI_AGENT_TOOLS, active_tool_packs)
    if plan_mode_active:
        session.current_turn_allowed_tool_definitions = filter_plan_tools(session.current_turn_allowed_tool_definitions)
        session.current_turn_allowed_tool_names = {
            str(tool.get("name") or tool.get("function", {}).get("name") or "")
            for tool in session.current_turn_allowed_tool_definitions
        }
        session.current_turn_allowed_tool_names.add("request_user_input")
    if goal_mode_active:
        session.current_turn_allowed_tool_names.add("update_goal_status")

    try:
        result = await run_reserved_chat_turn(
            session,
            reservation,
            prompt_builder=build_unified_system_prompt,
            tool_handlers_builder=(
                lambda runtime_session: {
                    **get_auto_mode_tool_handlers(runtime_session),
                    **(
                        _fleet_manager_tool_handlers(runtime_session)
                        if manager_core_enabled and not active_plan_mode(runtime_session)
                        else {}
                    ),
                    **(
                        _fleet_upstream_tool_handlers(runtime_session)
                        if _fleet_upstream_tool_enabled() and not active_plan_mode(runtime_session)
                        else {}
                    ),
                    **(
                        {"request_user_input": lambda args: _request_user_input_handler(runtime_session, args)}
                        if active_plan_mode(runtime_session)
                        else {}
                    ),
                    **(
                        {"update_goal_status": lambda args: _update_goal_status_handler(runtime_session, args)}
                        if active_goal(runtime_session)
                        else {}
                    ),
                }
            ),
            extra_tools_builder=(
                lambda runtime_session: (
                    merge_openai_tools(
                        filter_plan_tools(
                            filter_openai_tools_by_enabled_packs(
                                merge_openai_tools(get_auto_mode_extra_tools(), AGENT_TOOLS),
                                getattr(runtime_session, "_active_tool_packs_for_current_run", None)
                                or getattr(runtime_session, "enabled_tool_packs", [])
                                or [],
                            )
                        ),
                        [_openai_function_tool(REQUEST_USER_INPUT_TOOL)],
                    )
                    if active_plan_mode(runtime_session)
                    else merge_openai_tools(
                        filter_openai_tools_by_enabled_packs(
                            merge_openai_tools(get_auto_mode_extra_tools(), AGENT_TOOLS),
                            getattr(runtime_session, "_active_tool_packs_for_current_run", None)
                            or getattr(runtime_session, "enabled_tool_packs", [])
                            or [],
                        ),
                        (
                            FLEET_MANAGER_TOOLS
                            if manager_core_enabled
                            else []
                        ),
                        FLEET_UPSTREAM_TOOLS if _fleet_upstream_tool_enabled() else [],
                        (
                            [_openai_function_tool(UPDATE_GOAL_STATUS_TOOL)]
                            if active_goal(runtime_session)
                            else []
                        ),
                    )
                )
            ),
            system_messages=system_messages,
            prelude_messages=prelude_messages,
            assistant_message_payload={
                "channel": "app",
                "source_format": "app_response",
                "surface_mode": surface_mode,
                "display_label": "App",
                "source_client_id": source_client_id,
            },
            event_sink=log_callback,
            initialize_single_agent=lambda loop: session.init_single_agent(None, loop),
            assistant_content_transform=lambda response: (
                _format_jarvis_spoken_response(
                    ThinkingModeVisualizer.extract_thinking_content(response)[0]
                    if ThinkingModeVisualizer.should_show_thinking(session.current_model, session.current_variant)
                    else response
                )
                if source_format in {"app_voice_transcript", "app_visual_monitor"} and str(surface_mode or "").strip().lower() == "jarvis"
                else (
                    ThinkingModeVisualizer.extract_thinking_content(response)[0]
                    if ThinkingModeVisualizer.should_show_thinking(session.current_model, session.current_variant)
                    else response
                )
            ),
        )
    finally:
        session.current_turn_allowed_tool_names = None
        session.current_turn_allowed_tool_definitions = []
        session.current_turn_run_mode = None
        if getattr(session, "tool_executor", None):
            try:
                session.tool_executor.security_context_provider = None
            except Exception:
                pass
        if previous_surface_mode is None:
            try:
                delattr(session, "current_surface_mode")
            except Exception:
                session.current_surface_mode = None
        else:
            session.current_surface_mode = previous_surface_mode
    thinking_content = None
    if ThinkingModeVisualizer.should_show_thinking(session.current_model, session.current_variant):
        _, thinking_content = ThinkingModeVisualizer.extract_thinking_content(result.raw_response)
    if active_plan_mode(session):
        record_proposed_plan(session, result.assistant_text or result.raw_response or "")
    if active_goal(session):
        add_goal_token_usage(session, result.input_tokens, result.output_tokens)
    if active_plan_mode(session) or active_goal(session):
        try:
            session.save_session()
        except Exception:
            pass

    return {
        "ok": result.ok,
        "busy": result.busy,
        "steering": False,
        "session_id": result.session_id,
        "assistant_text": result.assistant_text,
        "raw_response": result.raw_response,
        "thinking_content": thinking_content,
        "duration_seconds": result.duration_seconds,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "total_tokens": result.total_tokens,
        "context_compressed": bool(reservation.context_compressed or result.context_compressed),
        "context_compaction": result.context_compaction or reservation.context_compaction,
        "failure": getattr(result, "failure", None),
    }
