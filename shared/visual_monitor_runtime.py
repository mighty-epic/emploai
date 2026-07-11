from __future__ import annotations

import asyncio
import base64
import io
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from cli.tui_constants import MODEL_CONFIGS
from shared.openai_api import create_openai_completion
from shared.runtime_attention import hidden_runtime_planner, queue_runtime_system_context


VISUAL_MONITOR_THRESHOLDS: Dict[str, float] = {
    "10%": 0.10,
    "30%": 0.30,
    "50%": 0.50,
    "70%": 0.70,
}
VISUAL_MONITOR_BASELINE_SECONDS = 5.0
VISUAL_MONITOR_POLL_SECONDS = 2.0
VISUAL_MONITOR_CAPTURE_WIDTH = 320
VISUAL_MONITOR_DESCRIPTION_WIDTH = 960
VISUAL_MONITOR_NO_CHANGE_SECONDS = [60.0, 300.0]
VISUAL_MONITOR_NO_CHANGE_REPEAT_SECONDS = 600.0


def normalize_visual_monitor_threshold(value: Any) -> tuple[str, float]:
    text = str(value or "").strip()
    if not text:
        raise ValueError("threshold_preset is required")
    if text in VISUAL_MONITOR_THRESHOLDS:
        return text, VISUAL_MONITOR_THRESHOLDS[text]
    if text.endswith("%") and text[:-1].strip().isdigit():
        normalized = f"{int(text[:-1].strip())}%"
        if normalized in VISUAL_MONITOR_THRESHOLDS:
            return normalized, VISUAL_MONITOR_THRESHOLDS[normalized]
    raise ValueError("threshold_preset must be one of: 10%, 30%, 50%, 70%")


def visual_monitor_changed_fraction(previous: Any, current: Any, *, pixel_threshold: int = 25) -> float:
    if previous is None or current is None:
        return 0.0
    if getattr(previous, "size", None) != getattr(current, "size", None):
        return 1.0
    from PIL import ImageChops

    diff = ImageChops.difference(previous, current).convert("L")
    mask = diff.point(lambda value: 255 if int(value) > int(pixel_threshold) else 0)
    histogram = mask.histogram()
    changed = histogram[255] if len(histogram) > 255 else 0
    total = max(1, mask.width * mask.height)
    return changed / float(total)


@dataclass
class VisualMonitor:
    monitor_id: str
    threshold_preset: str
    threshold_fraction: float
    reason: str
    context: Dict[str, Any]
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    started_at: float = field(default_factory=time.time)
    canceled: threading.Event = field(default_factory=threading.Event)
    thread: Optional[threading.Thread] = None
    _next_no_change_index: int = 0
    _next_no_change_deadline: float = VISUAL_MONITOR_NO_CHANGE_SECONDS[0]

    def start(self, manager: "VisualMonitorManager") -> None:
        self.thread = threading.Thread(target=self._run, args=(manager,), daemon=True)
        self.thread.start()

    def cancel(self) -> None:
        self.canceled.set()

    def _emit(self, payload: Dict[str, Any]) -> None:
        callback = self.event_callback
        if not callable(callback):
            return
        event = {
            **payload,
            "event_source": "visual_monitor",
            "monitor_id": self.monitor_id,
            "threshold_preset": self.threshold_preset,
            "threshold_fraction": self.threshold_fraction,
            "reason": self.reason,
            "started_at": self.started_at,
            "elapsed_seconds": max(0.0, time.time() - self.started_at),
            **dict(self.context or {}),
        }
        try:
            callback(event)
        except Exception:
            pass

    def _run(self, manager: "VisualMonitorManager") -> None:
        from app_backend.capture_runtime import capture_screen_image

        baseline = None
        last_baseline_at = 0.0
        try:
            while not self.canceled.is_set():
                try:
                    image, backend = capture_screen_image(max_width=VISUAL_MONITOR_CAPTURE_WIDTH)
                except Exception as exc:
                    self._emit({"status": "monitor_failed", "error": str(exc)[:500]})
                    return
                try:
                    now = time.time()
                    if baseline is None:
                        baseline = image.copy()
                        last_baseline_at = now
                        self._emit({"status": "monitor_started", "backend": backend})
                    else:
                        changed_fraction = visual_monitor_changed_fraction(baseline, image)
                        if changed_fraction >= self.threshold_fraction:
                            self._emit(
                                {
                                    "status": "visual_change",
                                    "backend": backend,
                                    "changed_fraction": changed_fraction,
                                }
                            )
                            return
                        if now - last_baseline_at >= VISUAL_MONITOR_BASELINE_SECONDS:
                            try:
                                baseline.close()
                            except Exception:
                                pass
                            baseline = image.copy()
                            last_baseline_at = now

                    elapsed = now - self.started_at
                    if elapsed >= self._next_no_change_deadline:
                        self._emit(
                            {
                                "status": "no_change",
                                "backend": backend,
                                "no_change_seconds": elapsed,
                                "deadline_seconds": self._next_no_change_deadline,
                            }
                        )
                        self._advance_no_change_deadline()
                finally:
                    try:
                        image.close()
                    except Exception:
                        pass
                self.canceled.wait(VISUAL_MONITOR_POLL_SECONDS)
        finally:
            try:
                if baseline is not None:
                    baseline.close()
            except Exception:
                pass
            manager._remove(self.monitor_id)

    def _advance_no_change_deadline(self) -> None:
        self._next_no_change_index += 1
        if self._next_no_change_index < len(VISUAL_MONITOR_NO_CHANGE_SECONDS):
            self._next_no_change_deadline = VISUAL_MONITOR_NO_CHANGE_SECONDS[self._next_no_change_index]
            return
        self._next_no_change_deadline += VISUAL_MONITOR_NO_CHANGE_REPEAT_SECONDS


class VisualMonitorManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._monitors: Dict[str, VisualMonitor] = {}

    def start_monitor(
        self,
        *,
        threshold_preset: Any,
        reason: Any,
        context: Optional[Dict[str, Any]] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        preset, fraction = normalize_visual_monitor_threshold(threshold_preset)
        context_dict = dict(context or {})
        replaced: List[str] = []
        with self._lock:
            existing = list(self._monitors.values())
        for existing_monitor in existing:
            existing_monitor.cancel()
            replaced.append(existing_monitor.monitor_id)
            existing_monitor._emit({"status": "monitor_stopped", "stop_reason": "Replaced by a new visual monitor"})

        monitor_id = f"vmon_{uuid.uuid4().hex[:12]}"
        monitor = VisualMonitor(
            monitor_id=monitor_id,
            threshold_preset=preset,
            threshold_fraction=fraction,
            reason=str(reason or "").strip()[:1000],
            context=context_dict,
            event_callback=event_callback,
        )
        with self._lock:
            self._monitors[monitor_id] = monitor
        monitor.start(self)
        return {
            "ok": True,
            "monitor_id": monitor_id,
            "threshold_preset": preset,
            "threshold_fraction": fraction,
            "scope": "full_screen",
            "baseline_refresh_seconds": VISUAL_MONITOR_BASELINE_SECONDS,
            "no_change_schedule_seconds": [60, 300, 600],
            "replaced": replaced,
            "replaced_count": len(replaced),
            "message": "Visual monitor started.",
        }

    def stop_monitor(
        self,
        *,
        monitor_id: Optional[str] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        identity_id: Optional[str] = None,
        reason: str = "Stopped",
    ) -> Dict[str, Any]:
        stopped: List[str] = []
        with self._lock:
            monitors = list(self._monitors.values())
        for monitor in monitors:
            context = monitor.context or {}
            matches = False
            if monitor_id and monitor.monitor_id == monitor_id:
                matches = True
            if session_id and str(context.get("session_id") or "") == str(session_id):
                matches = True
            if task_id and str(context.get("task_id") or "") == str(task_id):
                matches = True
            if identity_id and str(context.get("fleet_identity_id") or "") == str(identity_id):
                matches = True
            if not any([monitor_id, session_id, task_id, identity_id]):
                matches = True
            if matches:
                monitor.cancel()
                stopped.append(monitor.monitor_id)
                monitor._emit({"status": "monitor_stopped", "stop_reason": reason})
        return {"ok": True, "stopped": stopped, "stopped_count": len(stopped)}

    def active_count(self, *, session_id: Optional[str] = None, identity_id: Optional[str] = None) -> int:
        with self._lock:
            monitors = list(self._monitors.values())
        if not session_id and not identity_id:
            return len(monitors)
        count = 0
        for monitor in monitors:
            context = monitor.context or {}
            if session_id and str(context.get("session_id") or "") == str(session_id):
                count += 1
                continue
            if identity_id and str(context.get("fleet_identity_id") or "") == str(identity_id):
                count += 1
        return count

    def _remove(self, monitor_id: str) -> None:
        with self._lock:
            self._monitors.pop(monitor_id, None)


_VISUAL_MONITOR_MANAGER = VisualMonitorManager()


def get_visual_monitor_manager() -> VisualMonitorManager:
    return _VISUAL_MONITOR_MANAGER


def _session_id(session: Any) -> Optional[str]:
    current = getattr(session, "session", None)
    value = str(getattr(current, "id", "") or "").strip()
    if value:
        return value
    manager = getattr(session, "session_manager", None)
    if manager and callable(getattr(manager, "get_current_session_id", None)):
        return str(manager.get_current_session_id() or "").strip() or None
    return None


def _session_user_id(session: Any) -> int:
    try:
        return int(getattr(session, "user_id", 0) or 0)
    except Exception:
        return 0


def visual_monitor_context(session: Any) -> Dict[str, Any]:
    current = getattr(session, "session", None)
    history = list(getattr(current, "chat_history", None) or getattr(session, "chat_history", []) or [])
    latest_user = ""
    for message in reversed(history):
        if isinstance(message, dict) and message.get("role") == "user":
            latest_user = str(message.get("content") or "")
            break
    return {
        "user_id": _session_user_id(session),
        "session_id": _session_id(session),
        "session_name": getattr(current, "name", None),
        "fleet_identity_id": getattr(current, "fleet_identity_id", None) or getattr(session, "fleet_identity_id", None),
        "fleet_worker_id": getattr(current, "fleet_worker_id", None) or getattr(session, "fleet_worker_id", None),
        "task_id": getattr(current, "fleet_task_id", None) or getattr(session, "current_task_id", None),
        "surface_mode": getattr(session, "current_surface_mode", None),
        "original_user_task": latest_user,
    }


def install_visual_monitor_hooks(session: Any, *, event_loop: asyncio.AbstractEventLoop) -> None:
    executor = getattr(session, "tool_executor", None)
    if executor is None:
        return

    executor.visual_monitor_context_provider = lambda: visual_monitor_context(session)

    def event_callback(event: Dict[str, Any]) -> None:
        async def _run() -> None:
            await handle_visual_monitor_event(session, event)

        try:
            event_loop.call_soon_threadsafe(lambda: asyncio.create_task(_run()))
        except RuntimeError:
            pass

    executor.visual_monitor_event_callback = event_callback


async def handle_visual_monitor_event(session: Any, event: Dict[str, Any]) -> Dict[str, Any]:
    status = str((event or {}).get("status") or "").strip()
    if status in {"monitor_started", "monitor_stopped"}:
        return {"resumed": False, "reason": status}
    if status == "monitor_failed":
        return await _wake_main_agent(session, event, trigger="monitor_failed")
    if status == "visual_change":
        return await _wake_main_agent(session, event, trigger="visual_change")
    if status == "no_change":
        if bool(getattr(session, "is_processing", False)):
            return {"resumed": False, "reason": "agent_busy_monitor_kept_running"}
        decision = await _hidden_planner_no_change_decision(session, event)
        if decision.get("action") == "wake_agent":
            get_visual_monitor_manager().stop_monitor(
                monitor_id=str(event.get("monitor_id") or ""),
                reason="Hidden planner woke the main agent",
            )
            return await _wake_main_agent(session, {**event, "planner_decision": decision}, trigger="no_change")
        return {"resumed": False, "reason": "planner_kept_monitoring", "planner_decision": decision}
    return {"resumed": False, "reason": status or "unknown_visual_monitor_event"}


async def _wake_main_agent(session: Any, event: Dict[str, Any], *, trigger: str) -> Dict[str, Any]:
    if bool(getattr(session, "is_processing", False)):
        prompt = _visual_monitor_wake_prompt(event, trigger=trigger)
        queued = _queue_active_run_visual_monitor_context(session, prompt)
        return {"resumed": False, "queued": queued, "reason": "queued_for_active_run"}

    prompt = _visual_monitor_wake_prompt(event, trigger=trigger)
    from app_backend.runtime import run_app_chat_turn

    result = await run_app_chat_turn(
        session,
        user_message=prompt,
        source_format="app_visual_monitor",
        surface_mode=str(event.get("surface_mode") or "") or None,
        interrupt_policy="none",
        source_client_id=f"visual_monitor:{event.get('monitor_id') or ''}",
    )
    return {"resumed": bool(result.get("ok")), "result": result}


def _queue_active_run_visual_monitor_context(session: Any, prompt: str) -> bool:
    return queue_runtime_system_context(
        session,
        headline=(
            "A background visual monitor fired while this agent turn was still running. "
            "This is runtime context, not a new user request."
        ),
        prompt=prompt,
        merge_marker="background visual monitor",
        additional_label="ADDITIONAL VISUAL MONITOR EVENT",
    )


def _visual_monitor_wake_prompt(event: Dict[str, Any], *, trigger: str) -> str:
    changed = event.get("changed_fraction")
    changed_text = ""
    if isinstance(changed, (int, float)):
        changed_text = f"\nChanged screen area: {float(changed) * 100:.1f}%."
    no_change = event.get("no_change_seconds")
    no_change_text = ""
    if isinstance(no_change, (int, float)):
        no_change_text = f"\nNo meaningful visual change for about {int(float(no_change))} seconds."
    jarvis_note = ""
    if str(event.get("surface_mode") or "").strip().lower() == "jarvis":
        jarvis_note = (
            "\nThis wake belongs to Jarvis. Start with a brief continuation message, "
            "then continue the task normally."
        )
    return (
        "[VISUAL MONITOR WAKE]\n"
        f"Trigger: {trigger}.\n"
        f"Original wait reason: {event.get('reason') or 'Visual monitor wait'}."
        f"{changed_text}{no_change_text}{jarvis_note}\n\n"
        "A visual monitor woke this run. This is runtime context, not a new user request. "
        "Do not assume what changed from monitor pixels alone. "
        "First inspect the live screen with describe_screen using a precise question, then decide how to continue "
        "the original task. If the change is unrelated to the task, quietly continue with the task."
    )


async def _hidden_planner_no_change_decision(session: Any, event: Dict[str, Any]) -> Dict[str, Any]:
    if bool(getattr(session, "is_processing", False)):
        return {"action": "keep_monitoring", "reason": "main session is busy"}
    owner = f"visual_monitor:{event.get('monitor_id') or 'unknown'}"
    with hidden_runtime_planner(session, owner=owner) as acquired:
        if not acquired:
            return {"action": "keep_monitoring", "reason": "another hidden runtime planner is already active"}
        try:
            description = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: _describe_screen_for_hidden_planner(session, event),
            )
            raw = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: _hidden_planner_completion(session, event, description),
            )
            parsed = _extract_json_object(raw or "")
            if not parsed:
                return {"action": "wake_agent", "reason": "planner returned no parseable decision"}
            action = str(parsed.get("action") or "").strip()
            if action not in {"keep_monitoring", "wake_agent"}:
                action = "wake_agent"
            return {
                "action": action,
                "reason": str(parsed.get("reason") or "")[:800],
                "screen_description": description,
            }
        except Exception as exc:
            return {"action": "wake_agent", "reason": f"hidden planner failed: {exc}"[:800]}


def _describe_screen_for_hidden_planner(session: Any, event: Dict[str, Any]) -> str:
    from app_backend.capture_runtime import capture_screen_image
    from cli.agent_tools.loop import _analyze_image_sidecar

    image, _backend = capture_screen_image(max_width=VISUAL_MONITOR_DESCRIPTION_WIDTH)
    try:
        output = io.BytesIO()
        image.save(output, format="PNG")
        image_data = base64.b64encode(output.getvalue()).decode("utf-8")
    finally:
        try:
            image.close()
        except Exception:
            pass

    model_name = _planner_model_name(session)
    client, provider = session.get_client_for_specific_model(model_name)
    model_config = MODEL_CONFIGS.get(model_name, {})
    model_id = model_config.get("id", model_name)
    api_type = model_config.get("api", "chat")
    question = (
        "Describe the current visible desktop state for a hidden planner. "
        "Focus on whether the screen appears stuck, still loading, waiting for user input, showing an error, "
        "or otherwise relevant to this wait: "
        f"{event.get('reason') or ''}"
    )
    return _analyze_image_sidecar(
        provider=provider,
        model_id=model_id,
        client=client,
        api_type=api_type,
        tool_name="describe_screen",
        image_data=image_data,
        question=question,
        log=lambda *_args, **_kwargs: None,
    )


def _planner_model_name(session: Any) -> str:
    configured = str(getattr(session, "planner_model", "") or "").strip()
    current = str(getattr(session, "current_model", "") or "").strip()
    default = str(getattr(session, "default_planner_model", "") or "").strip()
    model_name = configured or current or default
    if not model_name:
        raise RuntimeError("No planner model is available")
    return model_name


def _hidden_planner_completion(session: Any, event: Dict[str, Any], screen_description: str) -> Optional[str]:
    model_name = _planner_model_name(session)
    client, provider = session.get_client_for_specific_model(model_name)
    if client is None:
        return None
    model_id = MODEL_CONFIGS.get(model_name, {}).get("id", model_name)
    payload = {
        "monitor": {
            "monitor_id": event.get("monitor_id"),
            "reason": event.get("reason"),
            "threshold_preset": event.get("threshold_preset"),
            "no_change_seconds": event.get("no_change_seconds"),
            "deadline_seconds": event.get("deadline_seconds"),
        },
        "original_user_task": event.get("original_user_task"),
        "recent_context": _recent_context(session),
        "screen_description": screen_description,
    }
    system_prompt = (
        "You are a hidden visual-monitor planner for EmploAI. "
        "You do not talk to the user and you cannot use tools or change monitor settings. "
        "Decide whether a no-change visual monitor checkpoint means the main agent should wake now. "
        "Return JSON only with action equal to keep_monitoring or wake_agent, and a short reason. "
        "Wake the agent if the screen appears stuck, blocked, errored, waiting for input, or if the task likely needs active reasoning. "
        "Keep monitoring if the screen appears to still be normally waiting/loading and no user-facing action is needed yet."
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


def _recent_context(session: Any) -> List[Dict[str, str]]:
    history = list(getattr(session, "chat_history", []) or [])[-8:]
    context: List[Dict[str, str]] = []
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
