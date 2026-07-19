from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from cli.tui_constants import MODEL_CONFIGS
from shared.channel_sync import get_channel_sync_hub
from shared.cron_feed_store import CronFeedStore
from shared.openai_api import create_openai_completion
from shared.runtime_attention import hidden_runtime_planner, queue_runtime_system_context
from shared.session_timeline import append_timeline_event, create_timeline_event


_EVENT_STORE_CALLBACK: Optional[Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]] = None
_EVENT_RATE_WINDOW: Dict[int, list[float]] = {}
_FAILURE_COOLDOWNS: Dict[str, float] = {}
MAX_EVENTS_PER_USER_HOUR = 240
REPEATED_FAILURE_COOLDOWN_SECONDS = 10 * 60


def set_event_store_callback(callback: Optional[Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]]) -> None:
    global _EVENT_STORE_CALLBACK
    _EVENT_STORE_CALLBACK = callback


def current_session_id(session: Any) -> Optional[str]:
    manager = getattr(session, "session_manager", None)
    if manager is None:
        return None
    try:
        return manager.get_current_session_id()
    except Exception:
        return None


PROCESS_RESUME_PROMPT = """[PROACTIVE PROCESS CONTINUATION]
The original task was waiting on a background process.

Original user task:
{original_task}

Background command:
- command_id: {command_id}
- pid: {pid}
- shell: {shell}
- cwd: {cwd}
- visible_terminal: {visible_terminal}
- status: {status}
- exit_code: {exit_code}

Recent captured output:
{output}

Runtime note:
{runtime_note}

Continue the original task from this event. Do not final-answer just because the process exited; verify the user's success criteria if a safe verification path exists. If the process failed, diagnose the failure and take the next safe corrective action instead of repeating the same failed method unchanged. If the process is still running, decide whether to keep waiting cheaply, inspect with command_status, send input, stop it, or continue other useful work."""


def _queue_active_run_process_context(session: Any, prompt: str) -> bool:
    return queue_runtime_system_context(
        session,
        headline=(
            "A background command event fired while this agent turn was still running. "
            "This is runtime context, not a new user request."
        ),
        prompt=prompt,
        merge_marker="background command event",
        additional_label="ADDITIONAL BACKGROUND COMMAND EVENT",
    )


def _session_user_id(session: Any) -> int:
    raw = getattr(session, "sync_user_id", None)
    if raw is None:
        raw = getattr(session, "user_id", None)
    try:
        return int(raw or 0)
    except Exception:
        return 0


def _session_name(session: Any) -> Optional[str]:
    current = getattr(session, "session", None)
    return getattr(current, "name", None)


def _safe_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        return json.loads(json.dumps(value, default=str))
    except Exception:
        return {"value": str(value)}


def append_event(
    *,
    user_id: int,
    kind: str,
    content: str,
    status: Optional[str] = None,
    session_id: Optional[str] = None,
    session_name: Optional[str] = None,
    automation_id: Optional[str] = None,
    automation_name: Optional[str] = None,
    event_type: Optional[str] = None,
    event_source: Optional[str] = None,
    importance: str = "normal",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Append one item to the shared Automations/Event feed.

    The file is still named cron-feed.json for compatibility with existing builds,
    but the product concept is now Automations/Event Feed.
    """
    now = time.time()
    user_key = int(user_id or 0)
    window = [ts for ts in _EVENT_RATE_WINDOW.get(user_key, []) if now - ts < 3600]
    if len(window) >= MAX_EVENTS_PER_USER_HOUR and kind != "event_rate_limited":
        kind = "event_rate_limited"
        event_type = "event_rate_limited"
        event_source = "loop_guard"
        status = "blocked"
        importance = "important"
        content = "Automation events were paused because too many events fired in the last hour."
        metadata = {
            **dict(metadata or {}),
            "loop_guard": "max_events_per_hour",
            "max_events_per_hour": MAX_EVENTS_PER_USER_HOUR,
        }
    window.append(now)
    _EVENT_RATE_WINDOW[user_key] = window[-MAX_EVENTS_PER_USER_HOUR:]

    metadata_payload = _safe_json(metadata or {})
    normalized_status = str(status or "").lower()
    normalized_type = str(event_type or kind or "").lower()
    if normalized_status in {"failed", "blocked"} or normalized_type.endswith("_failed"):
        cooldown_basis = json.dumps(
            {
                "user_id": user_key,
                "kind": kind,
                "event_type": event_type,
                "event_source": event_source,
                "automation_id": automation_id,
                "content": str(content or "")[:300],
            },
            sort_keys=True,
            default=str,
        )
        cooldown_key = hashlib.sha256(cooldown_basis.encode("utf-8")).hexdigest()
        previous = float(_FAILURE_COOLDOWNS.get(cooldown_key) or 0)
        if now - previous < REPEATED_FAILURE_COOLDOWN_SECONDS:
            kind = "repeated_failure_paused"
            event_type = "repeated_failure_paused"
            event_source = "loop_guard"
            status = "blocked"
            importance = "important"
            content = "A repeated failure was paused by the runtime cooldown instead of looping."
            metadata_payload.update(
                {
                    "loop_guard": "repeated_failure_cooldown",
                    "cooldown_seconds": REPEATED_FAILURE_COOLDOWN_SECONDS,
                    "cooldown_key": cooldown_key,
                }
            )
        else:
            _FAILURE_COOLDOWNS[cooldown_key] = now
    feed_item = CronFeedStore(user_id=int(user_id or 0)).append(
        kind=kind,
        content=content,
        session_id=session_id,
        session_name=session_name,
        job_id=automation_id,
        job_name=automation_name,
        status=status,
        event_type=event_type,
        event_source=event_source,
        importance=importance,
        metadata=metadata_payload,
    )
    callback = _EVENT_STORE_CALLBACK
    if callable(callback):
        try:
            durable_item = callback(
                {
                    "user_id": int(user_id or 0),
                    "kind": kind,
                    "content": content,
                    "status": status,
                    "session_id": session_id,
                    "session_name": session_name,
                    "automation_id": automation_id,
                    "automation_name": automation_name,
                    "event_type": event_type,
                    "event_source": event_source,
                    "importance": importance,
                    "metadata": metadata_payload,
                }
            )
            if isinstance(durable_item, dict):
                feed_item["durable_event_id"] = durable_item.get("event_id") or durable_item.get("id")
                if durable_item.get("auto_resume") is False:
                    feed_item["auto_resume"] = False
                    feed_item["auto_resume_disabled_reason"] = durable_item.get("auto_resume_disabled_reason")
        except Exception:
            pass
    return feed_item


def append_fleet_report_event(*, user_id: int, report: Dict[str, Any]) -> Dict[str, Any]:
    status = str(report.get("status") or "completed")
    task_id = str(report.get("task_id") or report.get("delegation_id") or "").strip()
    worker_id = str(report.get("worker_id") or "").strip()
    summary = str(report.get("summary") or "Worker report completed.").strip()
    importance = "important" if status in {"failed", "blocked", "needs_review", "stopped"} else "normal"
    return append_event(
        user_id=user_id,
        kind="fleet_report",
        event_type="worker_report_completed",
        event_source="fleet",
        content=f"{worker_id or 'Worker'} reported {status}: {summary}",
        status=status,
        automation_id=task_id or None,
        automation_name=f"Fleet task {task_id}" if task_id else "Fleet task",
        importance=importance,
        metadata={
            "report": report,
            "origin": dict(report.get("origin") or (report.get("raw") or {}).get("origin") or {}),
            "dedupe_key": f"fleet_report:{task_id}:{report.get('report_id') or report.get('status') or 'completed'}" if task_id else None,
        },
    )


def append_fleet_status_event(*, user_id: int, task: Dict[str, Any]) -> Dict[str, Any]:
    status = str(task.get("status") or "").strip() or "updated"
    importance = "important" if status in {"blocked", "needs_review", "failed", "stopped", "offline"} else "normal"
    task_id = str(task.get("task_id") or "").strip()
    worker_id = str(task.get("worker_id") or "").strip()
    return append_event(
        user_id=user_id,
        kind="fleet_status",
        event_type="worker_task_status",
        event_source="fleet",
        content=f"{worker_id or 'Worker'} task {task_id or ''} is {status}".strip(),
        status=status,
        automation_id=task_id or None,
        automation_name=f"Fleet task {task_id}" if task_id else "Fleet task",
        importance=importance,
        metadata={"task": task},
    )


def build_process_event_content(event: Dict[str, Any]) -> str:
    command = str(event.get("command") or "").strip()
    command_id = str(event.get("command_id") or "").strip()
    exit_code = event.get("exit_code")
    visible = bool(event.get("visible_terminal"))
    status = str(event.get("status") or "process_completed")
    if status == "waiting_on_process":
        prefix = "Background process started"
    elif status == "process_running":
        prefix = "Background process is still running"
    elif status == "process_output":
        prefix = "Background process output updated"
    elif status == "process_no_progress":
        prefix = "Background process is taking longer than expected"
    elif status == "process_ready":
        prefix = "Background process reported ready"
    elif status == "process_meaningful_output":
        prefix = "Background process produced useful output"
    elif status == "process_failed" or (exit_code not in (None, 0)):
        prefix = "Background process failed"
    else:
        prefix = "Background process completed"
    output_note = "visible terminal output was not captured" if visible else "recent output captured"
    if exit_code is None:
        return f"{prefix}: {command_id}. {output_note}. Command: {command}"
    return f"{prefix}: {command_id} exited with {exit_code}. {output_note}. Command: {command}"


def _process_timeline_tone(status: str, exit_code: Any) -> str:
    if status == "process_failed" or exit_code not in (None, 0):
        return "error"
    if status in {"process_running", "process_output", "process_no_progress", "process_ready", "process_meaningful_output"}:
        return "warn"
    return "accent" if status == "process_completed" else "neutral"


def _append_process_timeline_event(session: Any, event: Dict[str, Any], *, status: str) -> Optional[Dict[str, Any]]:
    command_id = str(event.get("command_id") or "").strip()
    if not command_id:
        return None
    user_id = _session_user_id(session)
    session_id = current_session_id(session)
    command = str(event.get("command") or "").strip()
    exit_code = event.get("exit_code")
    metadata = _safe_json(event)
    metadata.update(
        {
            "live_command": True,
            "command_id": command_id,
            "process_wait_id": metadata.get("process_wait_id") or f"proc_{int(user_id or 0)}_{command_id}",
            "status": status,
            "output": str(event.get("output") or "")[-8000:],
        }
    )
    timeline_event = create_timeline_event(
        kind="command",
        title=f"Command · {command_id}",
        content=command or build_process_event_content(event),
        tone=_process_timeline_tone(status, exit_code),
        channel="app",
        source_format="app_runtime",
        metadata=metadata,
    )
    stored = append_timeline_event(session, event=timeline_event)
    save_session = getattr(session, "save_session", None)
    if callable(save_session):
        try:
            save_session()
        except Exception:
            pass
    get_channel_sync_hub().publish(
        user_id=user_id,
        event={
            "type": "timeline_event",
            "session_id": session_id,
            "origin_channel": "app",
            "payload": {"event": stored},
        },
    )
    return stored


def _build_process_resume_prompt(
    event: Dict[str, Any],
    *,
    status: str,
    exit_code: Any = None,
    runtime_note: str = "",
) -> str:
    return PROCESS_RESUME_PROMPT.format(
        original_task=str(event.get("original_user_task") or event.get("task_prompt") or "Continue the previous task.").strip(),
        command_id=str(event.get("command_id") or ""),
        pid=str(event.get("pid") or ""),
        shell=str(event.get("shell") or ""),
        cwd=str(event.get("cwd") or ""),
        visible_terminal=bool(event.get("visible_terminal")),
        status=status,
        exit_code="" if exit_code is None else str(exit_code),
        output=str(event.get("output") or "(no captured output)")[:6000],
        runtime_note=str(runtime_note or "(none)")[:1200],
    )


async def _resume_background_process_event(
    session: Any,
    event: Dict[str, Any],
    feed_item: Dict[str, Any],
    *,
    status: str,
    exit_code: Any = None,
    runtime_note: str = "",
) -> Dict[str, Any]:
    user_id = _session_user_id(session)
    session_id = current_session_id(session)
    resume_count_attr = "_proactive_process_resume_count"
    resume_count = int(getattr(session, resume_count_attr, 0) or 0)
    if resume_count >= 8:
        append_event(
            user_id=user_id,
            kind="process_continuation_capped",
            event_type="process_continuation_capped",
            event_source="background_process",
            content=f"Process continuation cap reached for this run; not resuming {event.get('command_id') or ''}.",
            status="blocked",
            session_id=session_id,
            session_name=_session_name(session),
            automation_id=str(event.get("command_id") or "") or None,
            automation_name=str(event.get("command") or "")[:120] or "Background process",
            metadata={"command_event_id": feed_item.get("id"), "resume_count": resume_count},
            importance="important",
        )
        return {"feed_item": feed_item, "resumed": False, "reason": "resume_cap_reached"}

    prompt = _build_process_resume_prompt(event, status=status, exit_code=exit_code, runtime_note=runtime_note)

    if bool(getattr(session, "is_processing", False)):
        append_event(
            user_id=user_id,
            kind="process_continuation_queued",
            event_type="process_continuation_queued",
            event_source="background_process",
            content=f"Queued continuation for background process {event.get('command_id') or ''}.",
            status="queued",
            session_id=session_id,
            session_name=_session_name(session),
            automation_id=str(event.get("command_id") or "") or None,
            automation_name=str(event.get("command") or "")[:120] or "Background process",
            metadata={"command_event_id": feed_item.get("id")},
        )
        queued = _queue_active_run_process_context(session, prompt)
        return {"feed_item": feed_item, "resumed": False, "queued": queued, "reason": "queued_for_active_run"}

    # Reuse the same unified loop path as scheduled automations. It is intentionally
    # imported lazily to avoid pulling Telegram/runtime modules into lightweight tests.
    from telegram_bot.cron_runner import run_cron_job_via_unified_flow

    setattr(session, "is_processing", True)
    try:
        setattr(session, resume_count_attr, resume_count + 1)
        result = await run_cron_job_via_unified_flow(
            session,
            prompt,
            scheduled_job_id=f"process:{event.get('command_id') or int(time.time())}",
        )
        append_event(
            user_id=user_id,
            kind="process_continuation_result",
            event_type="process_continuation_result",
            event_source="background_process",
            content=result,
            status="completed",
            session_id=session_id,
            session_name=_session_name(session),
            automation_id=str(event.get("command_id") or "") or None,
            automation_name=str(event.get("command") or "")[:120] or "Background process",
            metadata={"command_event_id": feed_item.get("id")},
        )
        return {"feed_item": feed_item, "resumed": True, "result": result}
    finally:
        setattr(session, "is_processing", False)


async def _handle_process_no_progress_event(session: Any, event: Dict[str, Any], feed_item: Dict[str, Any]) -> Dict[str, Any]:
    if feed_item.get("auto_resume") is False:
        return {
            "feed_item": feed_item,
            "resumed": False,
            "reason": feed_item.get("auto_resume_disabled_reason") or "auto_resume_disabled",
        }
    if not bool(event.get("auto_resume", True)):
        return {"feed_item": feed_item, "resumed": False, "reason": "auto_resume_disabled"}
    if bool(event.get("persistent")):
        return {"feed_item": feed_item, "resumed": False, "reason": "persistent_command"}
    resume_policy = str(event.get("resume_policy") or "on_exit").strip().lower()
    if resume_policy in {"manual", "none", "off"}:
        return {"feed_item": feed_item, "resumed": False, "reason": "manual_resume_policy"}

    decision = await _hidden_process_no_progress_decision(session, event)
    if decision.get("action") != "wake_agent":
        return {
            "feed_item": feed_item,
            "resumed": False,
            "reason": "planner_kept_waiting",
            "planner_decision": decision,
        }
    note = f"Hidden background-command planner reason: {decision.get('reason') or 'command is taking too long'}"
    return await _resume_background_process_event(
        session,
        {**event, "planner_decision": decision},
        feed_item,
        status="process_no_progress",
        exit_code=None,
        runtime_note=note,
    )


async def _hidden_process_no_progress_decision(session: Any, event: Dict[str, Any]) -> Dict[str, Any]:
    owner = f"background_process:{event.get('command_id') or 'unknown'}"
    with hidden_runtime_planner(session, owner=owner) as acquired:
        if not acquired:
            return {"action": "keep_waiting", "reason": "another hidden runtime planner is already active"}
        try:
            raw = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: _hidden_process_planner_completion(session, event),
            )
            parsed = _extract_json_object(raw or "")
            if not parsed:
                return {"action": "wake_agent", "reason": "planner returned no parseable decision"}
            action = str(parsed.get("action") or "").strip()
            if action not in {"keep_waiting", "wake_agent"}:
                action = "wake_agent"
            return {"action": action, "reason": str(parsed.get("reason") or "")[:800]}
        except Exception as exc:
            return {"action": "wake_agent", "reason": f"hidden process planner failed: {exc}"[:800]}


def _hidden_process_planner_completion(session: Any, event: Dict[str, Any]) -> Optional[str]:
    model_name = _planner_model_name(session)
    client, provider = session.get_client_for_specific_model(model_name)
    if client is None:
        return None
    model_id = MODEL_CONFIGS.get(model_name, {}).get("id", model_name)
    payload = {
        "command": {
            "command_id": event.get("command_id"),
            "command": event.get("command"),
            "pid": event.get("pid"),
            "shell": event.get("shell"),
            "cwd": event.get("cwd"),
            "resume_policy": event.get("resume_policy"),
            "visible_terminal": bool(event.get("visible_terminal")),
            "persistent": bool(event.get("persistent")),
            "started_at": event.get("started_at"),
            "elapsed_seconds": event.get("no_progress_seconds"),
            "deadline_seconds": event.get("deadline_seconds"),
            "total_lines": event.get("total_lines"),
            "output_tail": str(event.get("output") or "")[-6000:],
        },
        "original_user_task": event.get("original_user_task") or event.get("task_prompt"),
        "recent_context": _recent_context(session),
        "agent_is_processing": bool(getattr(session, "is_processing", False)),
    }
    system_prompt = (
        "You are a hidden background-command planner for EmploAI. "
        "You do not talk to the user, use tools, stop processes, or change command settings. "
        "Decide whether a long-running background command checkpoint should wake or notify the main agent now. "
        "Return JSON only with action equal to keep_waiting or wake_agent, and a short reason. "
        "Wake the agent if the output suggests a hang, prompt for input, error, blocked install/build/test, "
        "or if active reasoning is needed to decide whether to inspect, send input, kill, retry, or verify. "
        "Keep waiting if the command still appears to be making normal progress or is expected to take this long."
    )
    user_prompt = json.dumps(payload, ensure_ascii=True, indent=2)
    if provider in {"openai", "openai-codex", "xai", "deepseek", "openrouter", "nvidia", "google"}:
        response = create_openai_completion(
            client,
            model_name=model_name,
            model_id=model_id,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=350,
        )
        return str(response.choices[0].message.content or "") if response.choices else None
    if provider == "anthropic":
        response = client.messages.create(
            model=model_id,
            max_tokens=350,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        parts = getattr(response, "content", None) or []
        return "\n".join(str(getattr(part, "text", "") or "") for part in parts).strip() or None
    return None


def _planner_model_name(session: Any) -> str:
    configured = str(getattr(session, "planner_model", "") or "").strip()
    current = str(getattr(session, "current_model", "") or "").strip()
    default = str(getattr(session, "default_planner_model", "") or "").strip()
    model_name = configured or current or default
    if not model_name:
        raise RuntimeError("No planner model is available")
    return model_name


def _recent_context(session: Any) -> list[Dict[str, str]]:
    history = list(getattr(session, "chat_history", []) or [])[-8:]
    context: list[Dict[str, str]] = []
    for message in history:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "")[:40]
        content = str(message.get("content") or "").replace("\r", " ").strip()
        if len(content) > 1200:
            content = content[:1197] + "..."
        if role and content:
            context.append({"role": role, "content": content})
    return context


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
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


async def handle_background_process_event(session: Any, event: Dict[str, Any]) -> Dict[str, Any]:
    """Record and optionally resume a task when a background command emits an event."""
    user_id = _session_user_id(session)
    session_id = current_session_id(session)
    event = dict(event or {})
    exit_code = event.get("exit_code")
    raw_status = str(event.get("status") or "").strip()
    if raw_status in {"waiting_on_process", "waiting_on_ready_signal", "process_running", "process_output", "process_no_progress", "process_ready", "process_meaningful_output", "process_failed", "process_completed", "process_still_running"}:
        status = raw_status
    else:
        status = "process_failed" if exit_code not in (None, 0) else "process_completed"
    event["status"] = status
    if status == "process_output":
        timeline_event = _append_process_timeline_event(session, event, status=status)
        return {"feed_item": timeline_event, "resumed": False, "reason": status}
    feed_item = append_event(
        user_id=user_id,
        kind=status,
        event_type=status,
        event_source="background_process",
        content=build_process_event_content(event),
        status=status,
        session_id=session_id,
        session_name=_session_name(session),
        automation_id=str(event.get("command_id") or "") or None,
        automation_name=str(event.get("command") or "")[:120] or "Background process",
        importance="important" if status == "process_failed" else "normal",
        metadata=event,
    )

    if status in {"process_running", "process_no_progress", "process_ready", "process_meaningful_output", "process_failed", "process_completed"}:
        _append_process_timeline_event(session, event, status=status)
    if status == "process_no_progress":
        return await _handle_process_no_progress_event(session, event, feed_item)
    if status in {"waiting_on_process", "waiting_on_ready_signal", "process_running", "process_still_running"}:
        return {"feed_item": feed_item, "resumed": False, "reason": status}
    if feed_item.get("auto_resume") is False:
        return {
            "feed_item": feed_item,
            "resumed": False,
            "reason": feed_item.get("auto_resume_disabled_reason") or "auto_resume_disabled",
        }
    if not bool(event.get("auto_resume", True)):
        return {"feed_item": feed_item, "resumed": False, "reason": "auto_resume_disabled"}
    resume_policy = str(event.get("resume_policy") or "on_exit").strip().lower()
    if resume_policy in {"manual", "none", "off"}:
        return {"feed_item": feed_item, "resumed": False, "reason": "manual_resume_policy"}
    if status == "process_ready" and resume_policy != "on_ready":
        return {"feed_item": feed_item, "resumed": False, "reason": "ready_not_requested"}
    if status == "process_meaningful_output" and resume_policy not in {"on_meaningful_output", "on_ready"}:
        return {"feed_item": feed_item, "resumed": False, "reason": "meaningful_output_not_requested"}
    if status in {"process_completed", "process_failed"} and resume_policy not in {"on_exit", "on_ready", "on_meaningful_output"}:
        return {"feed_item": feed_item, "resumed": False, "reason": "exit_not_requested"}
    return await _resume_background_process_event(
        session,
        event,
        feed_item,
        status=status,
        exit_code=exit_code,
    )


def install_background_process_hooks(session: Any, *, event_loop: asyncio.AbstractEventLoop) -> None:
    executor = getattr(session, "tool_executor", None)
    if executor is None:
        return

    def context_provider() -> Dict[str, Any]:
        current = getattr(session, "session", None)
        history = list(getattr(current, "chat_history", []) or [])
        latest_user = next(
            (
                str(message.get("content") or "")
                for message in reversed(history)
                if isinstance(message, dict) and message.get("role") == "user"
            ),
            "",
        )
        return {
            "user_id": _session_user_id(session),
            "session_id": current_session_id(session),
            "session_name": getattr(current, "name", None),
            "fleet_identity_id": getattr(current, "fleet_identity_id", None),
            "task_id": getattr(current, "fleet_task_id", None) or getattr(session, "current_task_id", None),
            "original_user_task": latest_user,
            "auto_resume": True,
        }

    def event_callback(event: Dict[str, Any]) -> None:
        async def _run() -> None:
            try:
                await handle_background_process_event(session, event)
            except Exception as exc:
                append_event(
                    user_id=_session_user_id(session),
                    kind="process_event_error",
                    event_type="process_event_error",
                    event_source="background_process",
                    content=f"Background process event handling failed: {exc}",
                    status="failed",
                    session_id=current_session_id(session),
                    session_name=_session_name(session),
                    metadata={"event": event, "error": str(exc)},
                    importance="important",
                )

        try:
            event_loop.call_soon_threadsafe(lambda: asyncio.create_task(_run()))
        except RuntimeError:
            append_event(
                user_id=_session_user_id(session),
                kind="process_completed",
                event_type=str(event.get("status") or "process_completed"),
                event_source="background_process",
                content=build_process_event_content(event),
                status=str(event.get("status") or "completed"),
                session_id=current_session_id(session),
                session_name=_session_name(session),
                metadata=event,
            )

    executor.background_command_context_provider = context_provider
    executor.background_command_event_callback = event_callback
