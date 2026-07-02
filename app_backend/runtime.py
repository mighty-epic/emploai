from __future__ import annotations

import os
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import quote

import httpx
from runtime_support.ui_helpers import ThinkingModeVisualizer
from cli.agent_tools.definitions import CLI_AGENT_TOOLS
from local_agent_runtime.tool_manifest import AGENT_TOOLS
from shared.channel_sync import get_channel_sync_hub
from shared.runtime_paths import runtime_home
from telegram_bot.telegram_unified_agent import (
    build_unified_system_prompt,
    get_auto_mode_extra_tools,
    get_auto_mode_tool_handlers,
)
from shared.task_board import TASK_BOARD_INTERNAL_TOOL_NAME, get_active_task_board

from shared import begin_chat_turn, merge_openai_tools, run_reserved_chat_turn
from shared.live_config import get_live_config
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
    filter_openai_tools_by_enabled_packs,
    filter_tools_by_enabled_packs,
    tools_for_enabled_packs,
)


STEERING_BETA_ENV = "EMPLO_APP_STEERING_BETA_ENABLED"
REMOTE_CONTROL_BASE_URL_ENV = "EMPLOAI_REMOTE_CONTROL_BASE_URL"
REMOTE_CONTROL_SESSION_TOKEN_ENV = "EMPLOAI_REMOTE_CONTROL_SESSION_TOKEN"
REMOTE_CONTROL_DESKTOP_ID_ENV = "EMPLOAI_REMOTE_CONTROL_DESKTOP_ID"
REMOTE_CONTROL_SESSION_FILENAME = "remote-account-session.json"
DEFAULT_REMOTE_BASE_URL = "https://api.kraitos.app"
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
_CONFIRMED_ARG = {"type": "boolean", "description": "Set true only after the same surface has confirmed this action."}

FLEET_MANAGER_TOOLS = [
    _fleet_tool("fleet_list_workers", "List workers, their task state, queue depth, latest report, groups, and pending grants."),
    _fleet_tool("fleet_create_local_worker", "Create the first or next local logical worker on this manager machine.", {"display_name": {"type": "string"}}),
    _fleet_tool("fleet_create_enrollment", "Create a short-lived enrollment token for a remote worker computer or VPS.", {"display_name": {"type": "string"}, "expires_in_seconds": {"type": "integer", "default": 1800}}),
    _fleet_tool("fleet_rename_worker", "Rename a worker.", {"worker": _WORKER_ARG, "display_name": {"type": "string"}}, ["worker", "display_name"]),
    _fleet_tool("fleet_reset_worker", "Reset a worker identity after confirmation. Stops active work first and preserves terminal reports.", {"worker": _WORKER_ARG, "reason": {"type": "string"}, "confirmed": _CONFIRMED_ARG}, ["worker"]),
    _fleet_tool("fleet_delete_worker", "Delete a worker from the live fleet after confirmation. Stops active work first and preserves terminal reports.", {"worker": _WORKER_ARG, "reason": {"type": "string"}, "confirmed": _CONFIRMED_ARG}, ["worker"]),
    _fleet_tool("fleet_list_groups", "List worker groups."),
    _fleet_tool("fleet_create_group", "Create a worker group.", {"display_name": {"type": "string"}, "worker_ids": {"type": "array", "items": {"type": "string"}}, "description": {"type": "string"}}, ["display_name"]),
    _fleet_tool("fleet_update_group", "Update group name, description, or members.", {"group": _GROUP_ARG, "display_name": {"type": "string"}, "worker_ids": {"type": "array", "items": {"type": "string"}}, "description": {"type": "string"}}, ["group"]),
    _fleet_tool("fleet_delete_group", "Delete a group after confirmation.", {"group": _GROUP_ARG, "confirmed": _CONFIRMED_ARG}, ["group"]),
    _fleet_tool("fleet_assign_task", "Assign a task to one worker. If the worker is busy, the task queues by default.", {"worker": _WORKER_ARG, "prompt": {"type": "string"}}, ["worker", "prompt"]),
    _fleet_tool("fleet_assign_group_task", "Assign a task to every worker in a group after confirmation.", {"group": _GROUP_ARG, "prompt": {"type": "string"}, "confirmed": _CONFIRMED_ARG}, ["group", "prompt"]),
    _fleet_tool("fleet_send_worker_message", "Send a manager message to a worker. Busy workers queue the message by default.", {"worker": _WORKER_ARG, "message": {"type": "string"}}, ["worker", "message"]),
    _fleet_tool("fleet_send_group_message", "Send a manager message to a group after confirmation.", {"group": _GROUP_ARG, "message": {"type": "string"}, "confirmed": _CONFIRMED_ARG}, ["group", "message"]),
    _fleet_tool("fleet_redirect_worker_task", "Redirect the worker's active task now; do not use for normal queued follow-up messages.", {"worker": _WORKER_ARG, "task_id": {"type": "string"}, "direction": {"type": "string"}}, ["direction"]),
    _fleet_tool("fleet_delete_queued_message", "Cancel a queued worker message or task.", {"task_id": {"type": "string"}}, ["task_id"]),
    _fleet_tool("fleet_steer_queued_message", "Remove a queued message and apply it as an immediate redirect to the worker's active task.", {"task_id": {"type": "string"}}, ["task_id"]),
    _fleet_tool("fleet_reorder_worker_queue", "Reorder queued tasks for one worker.", {"worker": _WORKER_ARG, "task_ids": {"type": "array", "items": {"type": "string"}}}, ["worker", "task_ids"]),
    _fleet_tool("fleet_continue_worker_queue", "After reviewing a completed worker report, start the worker's next queued item.", {"worker": _WORKER_ARG, "reviewed_report_id": {"type": "string"}}, ["worker"]),
    _fleet_tool("fleet_update_task", "Update a fleet task state. Prefer fleet_stop_worker for active stop and fleet_delete_queued_message for queued cancel.", {"task_id": {"type": "string"}, "worker": _WORKER_ARG, "action": {"type": "string", "enum": ["pause", "resume", "stop", "cancel"]}, "reason": {"type": "string"}}, ["action"]),
    _fleet_tool("fleet_stop_worker", "Stop one worker's active task and task-owned commands.", {"worker": _WORKER_ARG, "reason": {"type": "string"}}, ["worker"]),
    _fleet_tool("fleet_stop_all", "Stop every reachable active fleet run after confirmation.", {"reason": {"type": "string"}, "confirmed": _CONFIRMED_ARG}),
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
            "- Do not use markdown, bullet points, numbered lists, dash lists, tables, headings, or code fences in the final answer.\n"
            "- Do not say 'see above', 'below', or similar visual references unless you created or opened a visible artifact for the user.\n"
            "- If describing the screen, summarize the useful state naturally instead of listing every visible item.\n"
            "- Voice mode does not reduce your capabilities: use the same tools and verification discipline as chat mode.\n"
            "- If you used tools, mention only the meaningful outcome or next step, not raw tool-call details.\n"
            "- If the answer would be long, give a brief spoken summary and offer to continue, create a file, or open the result."
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


def _remote_session_payload() -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    try:
        home = runtime_home()
        if home is not None:
            path = home / REMOTE_CONTROL_SESSION_FILENAME
            if path.exists():
                parsed = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    payload = parsed
    except Exception:
        payload = {}
    return payload


def _remote_api_config() -> Dict[str, str]:
    payload = _remote_session_payload()
    base_url = str(
        os.getenv(REMOTE_CONTROL_BASE_URL_ENV, "")
        or payload.get("apiBaseUrl")
        or payload.get("api_base_url")
        or DEFAULT_REMOTE_BASE_URL
    ).strip().rstrip("/")
    token = str(
        os.getenv(REMOTE_CONTROL_SESSION_TOKEN_ENV, "")
        or payload.get("sessionToken")
        or payload.get("session_token")
        or ""
    ).strip()
    desktop = payload.get("desktop") if isinstance(payload.get("desktop"), dict) else {}
    return {
        "base_url": base_url or DEFAULT_REMOTE_BASE_URL,
        "token": token,
        "desktop_id": str(
            os.getenv(REMOTE_CONTROL_DESKTOP_ID_ENV, "")
            or (desktop or {}).get("desktop_id")
            or payload.get("desktop_id")
            or ""
        ).strip(),
    }


def _fleet_api_request(method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = _remote_api_config()
    if not config["token"]:
        return {"error": "Fleet tools require a signed-in desktop account.", "error_type": "not_signed_in"}
    try:
        timeout = httpx.Timeout(10.0, connect=3.0, read=10.0, write=10.0)
        with httpx.Client(timeout=timeout) as client:
            response = client.request(
                method.upper(),
                f"{config['base_url']}{path}",
                headers={"Authorization": f"Bearer {config['token']}"},
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
    now = time.monotonic()
    cached = getattr(session, "_fleet_manager_tool_context", None)
    if isinstance(cached, dict) and now - float(cached.get("fetched_at") or 0.0) < FLEET_MANAGER_TOOL_CACHE_SECONDS:
        return cached

    config = _remote_api_config()
    snapshot = _fleet_snapshot_uncached()
    workers = list(snapshot.get("workers") or []) if isinstance(snapshot, dict) else []
    manager = snapshot.get("manager") if isinstance(snapshot, dict) and isinstance(snapshot.get("manager"), dict) else None
    is_primary_manager = bool(
        manager
        and config.get("desktop_id")
        and str(manager.get("desktop_id") or "") == str(config.get("desktop_id") or "")
    )
    context = {
        "enabled": bool(is_primary_manager and not snapshot.get("error")),
        "has_workers": bool(workers),
        "snapshot": snapshot if isinstance(snapshot, dict) else {},
        "desktop_id": config.get("desktop_id") or "",
        "fetched_at": now,
    }
    try:
        setattr(session, "_fleet_manager_tool_context", context)
    except Exception:
        pass
    return context


def _invalidate_fleet_manager_tool_context(session: Any) -> None:
    try:
        setattr(session, "_fleet_manager_tool_context", None)
    except Exception:
        pass


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


def _fleet_confirmation_required(action: str, summary: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    seed = json.dumps({"action": action, "summary": summary, "payload": payload or {}}, sort_keys=True)
    confirmation_id = f"fleet_confirm_{abs(hash(seed)) & 0xFFFFFFFF:08x}"
    return {
        "confirmation_required": True,
        "confirmation_id": confirmation_id,
        "action": action,
        "summary": summary,
        "payload": payload or {},
        "next_valid_actions": ["Ask the user to confirm on this surface, then call the same tool with confirmed=true."],
    }


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
    return {
        "role": "system",
        "content": (
            "FLEET MANAGER MODE:\n"
            "- This desktop is the primary manager for an EmploAI worker fleet.\n"
            "- Use Fleet tools to control workers: create workers, group workers, send or queue work, redirect active work, stop workers, inspect reports/evidence, and continue queues.\n"
            "- Setup/list tools are available even when there are zero workers. Create or enroll workers when the user asks for fleet setup.\n"
            "- Do not use fleet tools for ordinary chat, simple questions, or tasks the manager should answer directly.\n"
            "- For broad delegation, inspect status first, assign clear task prompts, monitor milestones, read reports, then synthesize results for the user.\n"
            "- Sending a message to a busy worker queues by default. Redirecting the active task requires fleet_redirect_worker_task or fleet_steer_queued_message.\n"
            "- After a worker report, review the report before calling fleet_continue_worker_queue. Failed, blocked, low-confidence, stopped, canceled, or needs-review reports require manager review instead of continuing.\n"
            "- Destructive, bulk, and access-sensitive actions require same-surface confirmation before executing.\n"
            "- Prefer compact report/evidence/search tools over loading full timelines unless the user asks or the report is ambiguous.\n"
            f"- Known workers this turn: {worker_text}."
        ),
    }


def _fleet_worker_contract(session: Any) -> dict[str, str]:
    worker_label = (
        str(getattr(session, "fleet_worker_id", "") or "").strip()
        or str(getattr(session, "fleet_identity_id", "") or "").strip()
        or "this worker"
    )
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
        {"display_name": str(args.get("display_name") or "").strip() or None, "metadata": {"created_by": "manager_agent"}},
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
    action = "fleet_reset_worker" if reset else "fleet_delete_worker"
    if not bool(args.get("confirmed")):
        return _fleet_confirmation_required(
            action,
            f"{'Reset' if reset else 'Delete'} {worker.get('display_name') or worker.get('worker_id')} from the live fleet.",
            {"worker_id": worker.get("worker_id"), "active_task_id": worker.get("active_task_id")},
        )
    path = (
        f"/api/fleet/workers/{quote(str(worker.get('worker_id') or ''), safe='')}/reset"
        if reset
        else f"/api/fleet/workers/{quote(str(worker.get('worker_id') or ''), safe='')}?wipe_state=true"
    )
    result = _fleet_api_request(
        "POST" if reset else "DELETE",
        path,
        {"reason": str(args.get("reason") or action), "metadata": {"requested_by": "manager_agent"}} if reset else None,
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
            "fleet_delete_group",
            f"Delete group {group.get('display_name') or group.get('group_id')}.",
            {"group_id": group.get("group_id"), "worker_ids": group.get("worker_ids") or []},
        )
    result = _fleet_api_request("DELETE", f"/api/fleet/groups/{quote(str(group.get('group_id') or ''), safe='')}")
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
            "fleet_send_group_message" if message else "fleet_assign_group_task",
            f"Dispatch to group {group.get('display_name') or group.get('group_id')} with {len(worker_ids)} workers.",
            {"group_id": group.get("group_id"), "worker_ids": worker_ids, "prompt": prompt[:500]},
        )
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
            "fleet_stop_all",
            "Stop every reachable active fleet run.",
            {"reason": str(args.get("reason") or "Fleet stop all")},
        )
    result = _fleet_api_request(
        "POST",
        "/api/fleet/stop-all",
        {"reason": str(args.get("reason") or "Fleet stop all"), "metadata": {"stopped_by": "manager_agent"}},
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


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_interrupt_policy(policy: str) -> str:
    normalized = (policy or "none").strip().lower()
    return normalized if normalized in {"none", "steer_now", "after_tool"} else "none"


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


async def run_app_chat_turn(
    session: Any,
    *,
    user_message: str,
    source_format: str = "app_text",
    surface_mode: Optional[str] = None,
    interrupt_policy: str = "none",
    source_client_id: Optional[str] = None,
    log_callback: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> Dict[str, Any]:
    steering_result = await _request_app_steering(
        session,
        user_message=user_message,
        source_format=source_format,
        interrupt_policy=interrupt_policy,
        surface_mode=surface_mode,
        source_client_id=source_client_id,
    )
    if steering_result is not None:
        return steering_result

    display_label = "App Voice" if source_format == "app_voice_transcript" else "App"
    reservation = await begin_chat_turn(
        session,
        user_message=user_message,
        user_message_payload={
            "channel": "app",
            "source_format": source_format,
            "surface_mode": surface_mode,
            "display_label": display_label,
            "source_client_id": source_client_id,
        },
    )
    if reservation.busy:
        return {
            "ok": False,
            "busy": True,
            "session_id": reservation.session_id,
            "assistant_text": "",
        }

    screen_observation_turn = is_screen_observation_message(user_message)
    task_like_turn = screen_observation_turn or is_task_like_message(user_message)
    tool_evidence_turn = request_requires_tool_evidence(user_message)
    active_tool_packs = list(
        getattr(session, "_active_tool_packs_for_current_run", None)
        or getattr(session, "enabled_tool_packs", [])
        or []
    )
    prelude_messages = []
    if tool_evidence_turn and len(session.chat_history) <= 3:
        prelude_messages.extend(_kickstart_prelude(active_tool_packs))

    system_messages = []
    if screen_observation_turn:
        system_messages.append(_screen_observation_contract(active_tool_packs))
    if source_format == "app_voice_transcript" and str(surface_mode or "").strip().lower() == "jarvis":
        system_messages.append(_jarvis_voice_response_contract())
    if _is_fleet_worker_session(session):
        system_messages.append(_fleet_worker_contract(session))
    if tool_evidence_turn:
        system_messages.append(_task_execution_contract(session, active_tool_packs))
    if not tool_evidence_turn or not task_like_turn:
        system_messages.append(_conversational_turn_guard())
    fleet_tool_context = _fleet_manager_tool_context(session)
    if fleet_tool_context.get("enabled"):
        system_messages.append(_fleet_manager_contract(dict(fleet_tool_context.get("snapshot") or {})))
    session.current_turn_allowed_tool_names = tools_for_enabled_packs(active_tool_packs)
    if fleet_tool_context.get("enabled"):
        session.current_turn_allowed_tool_names.update(FLEET_MANAGER_TOOL_NAMES)
    session.current_turn_allowed_tool_definitions = filter_tools_by_enabled_packs(CLI_AGENT_TOOLS, active_tool_packs)

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
                        if _fleet_manager_tool_context(runtime_session).get("enabled")
                        else {}
                    ),
                }
            ),
            extra_tools_builder=(
                lambda runtime_session: merge_openai_tools(
                    filter_openai_tools_by_enabled_packs(
                        merge_openai_tools(get_auto_mode_extra_tools(), AGENT_TOOLS),
                        getattr(runtime_session, "_active_tool_packs_for_current_run", None)
                        or getattr(runtime_session, "enabled_tool_packs", [])
                        or [],
                    ),
                    (
                        FLEET_MANAGER_TOOLS
                        if _fleet_manager_tool_context(runtime_session).get("enabled")
                        else []
                    ),
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
                if source_format == "app_voice_transcript" and str(surface_mode or "").strip().lower() == "jarvis"
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
    thinking_content = None
    if ThinkingModeVisualizer.should_show_thinking(session.current_model, session.current_variant):
        _, thinking_content = ThinkingModeVisualizer.extract_thinking_content(result.raw_response)

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
    }
