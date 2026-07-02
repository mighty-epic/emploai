from __future__ import annotations

import asyncio
import secrets
from typing import Any, Callable, Dict, Optional

from app_backend.fleet_policy import FLEET_PREVIEW_MODE, preview_dispatch_target
from app_backend.remote_command_broker import request_remote_desktop_command_via_broker
from app_backend.remote_control_runtime import remote_control_sqlite_broker_enabled


SessionActiveChecker = Callable[..., bool]
DesktopUnavailableChecker = Callable[[str], bool]
DesktopOfflineMarker = Callable[..., None]


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
        dispatch_status = "local_placeholder"
        detail = "Local logical workers do not expose a remote screen preview yet."
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
            dispatch_status = str(result.get("status") or "acknowledged").strip()[:80] or "acknowledged"
            detail = str(result.get("detail") or "Worker desktop acknowledged the preview request.").strip()
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
    )
    return {"ok": True, **payload, "preview": preview_state.get("preview")}
