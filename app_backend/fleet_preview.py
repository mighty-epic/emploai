from __future__ import annotations

import asyncio
import secrets
from typing import Any, Awaitable, Callable, Dict, Optional

from app_backend.fleet_policy import FLEET_PREVIEW_MODE, preview_dispatch_target
from app_backend.remote_command_broker import request_remote_desktop_command_via_broker
from app_backend.remote_control_runtime import remote_control_sqlite_broker_enabled


SessionActiveChecker = Callable[..., bool]
DesktopUnavailableChecker = Callable[[str], bool]
DesktopOfflineMarker = Callable[..., None]
LocalPreviewCapture = Callable[..., Awaitable[Dict[str, Any]]]


async def capture_local_worker_preview(*, worker: Dict[str, Any]) -> Dict[str, Any]:
    from app_backend.capture_runtime import capture_screen_snapshot

    loop = asyncio.get_running_loop()
    capture = await loop.run_in_executor(
        None,
        lambda: capture_screen_snapshot(max_width=1280, jpeg_quality=68),
    )
    return {
        "status": "captured",
        "detail": f"Captured the current desktop used by {worker.get('display_name') or 'the local worker'}.",
        "capture": capture,
    }


async def capture_local_desktop_preview(*, desktop: Dict[str, Any]) -> Dict[str, Any]:
    from app_backend.capture_runtime import capture_screen_snapshot

    loop = asyncio.get_running_loop()
    capture = await loop.run_in_executor(
        None,
        lambda: capture_screen_snapshot(max_width=1280, jpeg_quality=62),
    )
    return {
        "status": "captured",
        "detail": f"Captured the current view on {desktop.get('display_name') or 'this computer'}.",
        "capture": capture,
    }


def _bounded_preview_capture(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    capture = dict(value)
    encoded = str(capture.get("image_base64") or "")
    if not encoded:
        return None
    if len(encoded) > 2_000_000:
        raise RuntimeError("Captured preview exceeded the safe image size limit")
    return capture


async def request_fleet_desktop_preview(
    *,
    store: Any,
    remote_desktop_manager: Any,
    user_id: int,
    desktop: Dict[str, Any],
    manager_desktop_id: str,
    is_remote_session_active: SessionActiveChecker,
    is_desktop_unavailable_error: Optional[DesktopUnavailableChecker] = None,
    mark_desktop_offline: Optional[DesktopOfflineMarker] = None,
    capture_local_preview: Optional[LocalPreviewCapture] = None,
    timeout_seconds: float = 10.0,
) -> Dict[str, Any]:
    """Capture one bounded, view-only frame without persisting its image data."""

    preview_id = f"fdp_{secrets.token_hex(8)}"
    desktop_id = str(desktop.get("desktop_id") or "").strip()
    if not desktop_id:
        raise KeyError("Unknown desktop")
    payload: Dict[str, Any] = {
        "preview_id": preview_id,
        "desktop_id": desktop_id,
        "display_name": desktop.get("display_name"),
        "view_only": True,
        "mode": FLEET_PREVIEW_MODE,
    }
    dispatch_status = "recorded"
    detail = "Preview request recorded."
    command_id: Optional[str] = None

    if desktop_id == str(manager_desktop_id or "").strip():
        try:
            local_capture = capture_local_preview or capture_local_desktop_preview
            result = await local_capture(desktop=desktop)
            dispatch_status = str(result.get("status") or "captured").strip()[:80] or "captured"
            detail = str(result.get("detail") or "Local desktop preview captured.").strip()
            capture = _bounded_preview_capture(result.get("capture"))
            if capture:
                payload["capture"] = capture
        except Exception as exc:
            dispatch_status = "failed"
            detail = f"Local desktop preview failed: {type(exc).__name__}: {exc}"
    elif (
        not remote_desktop_manager.is_connected_for_user(desktop_id, int(user_id))
        and not remote_control_sqlite_broker_enabled()
    ):
        dispatch_status = "offline"
        detail = "This computer is offline; reconnect it before requesting a preview."
    elif not is_remote_session_active(desktop_id=desktop_id, user_id=int(user_id)):
        dispatch_status = "expired"
        detail = "This computer's Fleet session expired; reconnect it before requesting a preview."
    else:
        try:
            if remote_desktop_manager.is_connected_for_user(desktop_id, int(user_id)):
                reply = await remote_desktop_manager.request_command(
                    desktop_id=desktop_id,
                    user_id=int(user_id),
                    command_type="fleet_worker_preview",
                    payload=payload,
                    timeout_seconds=timeout_seconds,
                )
            else:
                result = await request_remote_desktop_command_via_broker(
                    store=store,
                    user_id=int(user_id),
                    desktop_id=desktop_id,
                    command_name="fleet_worker_preview",
                    payload=payload,
                    timeout_seconds=timeout_seconds,
                )
                reply = {"ok": True, "result": result}
            if not bool(reply.get("ok", False)):
                raise RuntimeError(str(reply.get("error") or "This computer rejected the preview request"))
            result = dict(reply.get("result") or {})
            command_id = str(result.get("command_id") or "").strip() or None
            dispatch_status = str(result.get("status") or "captured").strip()[:80] or "captured"
            detail = str(result.get("detail") or "View-only desktop preview captured.").strip()
            capture = _bounded_preview_capture(result.get("capture"))
            if capture:
                payload["capture"] = capture
        except asyncio.TimeoutError:
            dispatch_status = "timeout"
            detail = "This computer did not return a preview within 10 seconds."
        except (KeyError, RuntimeError) as exc:
            dispatch_status = "failed"
            detail = str(exc)
            if (
                is_desktop_unavailable_error
                and is_desktop_unavailable_error(detail)
                and mark_desktop_offline
            ):
                mark_desktop_offline(user_id=int(user_id), desktop_id=desktop_id, reason=detail)

    return {
        "ok": True,
        **payload,
        "dispatch_status": dispatch_status,
        "command_id": command_id,
        "detail": detail,
    }


async def request_fleet_worker_preview(
    *,
    store: Any,
    remote_desktop_manager: Any,
    user_id: int,
    worker: Dict[str, Any],
    requested_by: str,
    is_remote_session_active: SessionActiveChecker,
    is_desktop_unavailable_error: Optional[DesktopUnavailableChecker] = None,
    mark_desktop_offline: Optional[DesktopOfflineMarker] = None,
    capture_local_preview: Optional[LocalPreviewCapture] = None,
    timeout_seconds: float = 10.0,
) -> Dict[str, Any]:
    preview_id = f"fpv_{secrets.token_hex(8)}"
    desktop_id = preview_dispatch_target(worker)
    dispatch_status = "recorded"
    command_id: Optional[str] = None
    detail = "Preview request recorded."
    payload = {
        "preview_id": preview_id,
        "worker_id": worker.get("worker_id"),
        "display_name": worker.get("display_name"),
        "desktop_id": desktop_id,
        "view_only": True,
        "mode": FLEET_PREVIEW_MODE,
    }
    if str(worker.get("kind") or "") != "remote":
        try:
            local_capture = capture_local_preview or capture_local_worker_preview
            result = await local_capture(worker=worker)
            dispatch_status = str(result.get("status") or "captured").strip()[:80] or "captured"
            detail = str(result.get("detail") or "Local worker preview captured.").strip()
            if isinstance(result.get("capture"), dict):
                payload["capture"] = dict(result["capture"])
        except Exception as exc:
            dispatch_status = "failed"
            detail = f"Local worker preview failed: {type(exc).__name__}: {exc}"
    elif not desktop_id:
        dispatch_status = "missing_desktop"
        detail = "Worker does not have an enrolled desktop identity."
    elif (
        not remote_desktop_manager.is_connected_for_user(desktop_id, int(user_id))
        and not remote_control_sqlite_broker_enabled()
    ):
        dispatch_status = "offline"
        detail = "Worker desktop is offline; preview will be available after reconnect."
    elif not is_remote_session_active(desktop_id=desktop_id, user_id=int(user_id)):
        dispatch_status = "expired"
        detail = "Worker desktop session expired; preview requires reconnect."
    else:
        try:
            if remote_desktop_manager.is_connected_for_user(desktop_id, int(user_id)):
                reply = await remote_desktop_manager.request_command(
                    desktop_id=desktop_id,
                    user_id=int(user_id),
                    command_type="fleet_worker_preview",
                    payload=payload,
                    timeout_seconds=timeout_seconds,
                )
            else:
                result = await request_remote_desktop_command_via_broker(
                    store=store,
                    user_id=int(user_id),
                    desktop_id=desktop_id,
                    command_name="fleet_worker_preview",
                    payload=payload,
                    timeout_seconds=timeout_seconds,
                )
                reply = {"ok": True, "result": result}
            if not bool(reply.get("ok", False)):
                raise RuntimeError(str(reply.get("error") or "Worker desktop rejected the preview request"))
            result = dict(reply.get("result") or {})
            command_id = str(result.get("command_id") or "").strip() or None
            dispatch_status = str(result.get("status") or "captured").strip()[:80] or "captured"
            detail = str(result.get("detail") or "Worker desktop preview captured.").strip()
            if isinstance(result.get("capture"), dict):
                payload["capture"] = dict(result["capture"])
        except asyncio.TimeoutError:
            dispatch_status = "timeout"
            detail = "Worker desktop did not acknowledge the preview request in time."
        except KeyError:
            dispatch_status = "failed"
            detail = "Worker desktop is unavailable for this account."
        except RuntimeError as exc:
            dispatch_status = "failed"
            detail = str(exc)
            if (
                desktop_id
                and is_desktop_unavailable_error
                and is_desktop_unavailable_error(detail)
                and mark_desktop_offline
            ):
                mark_desktop_offline(
                    user_id=int(user_id),
                    desktop_id=desktop_id,
                    reason=detail,
                )

    payload.update({"dispatch_status": dispatch_status, "command_id": command_id, "detail": detail})
    preview_state = store.record_worker_preview_request(
        user_id=int(user_id),
        worker_id=str(worker.get("worker_id") or ""),
        preview_id=preview_id,
        status=dispatch_status,
        requested_by=str(requested_by or "app"),
        mode=FLEET_PREVIEW_MODE,
        command_id=command_id,
        detail=detail,
        metadata={
            "capture": {
                key: value
                for key, value in dict(payload.get("capture") or {}).items()
                if key != "image_base64"
            }
        } if payload.get("capture") else None,
    )
    return {"ok": True, **payload, "preview": preview_state.get("preview")}
