from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from mobile_app.backend.remote_control_runtime import remote_control_sqlite_broker_enabled


logger = logging.getLogger(__name__)


class BrokeredRemoteCommandError(RuntimeError):
    def __init__(self, detail: str, *, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = _safe_error_status(status_code)


def _safe_error_status(status_code: object) -> int:
    try:
        value = int(status_code or 502)
    except (TypeError, ValueError):
        return 502
    if value < 400 or value > 599:
        return 502
    return value


async def wait_for_brokered_remote_command(
    *,
    store: Any,
    user_id: int,
    command_id: str,
    timeout_seconds: float,
    poll_interval_seconds: float = 0.1,
) -> Dict[str, Any]:
    deadline = time.monotonic() + max(0.5, float(timeout_seconds or 30.0))
    while True:
        result = store.get_remote_desktop_command_result(command_id=command_id, user_id=int(user_id))
        if result and str(result.get("status") or "") in {"completed", "failed", "expired"}:
            payload = dict(result.get("payload") or {})
            if str(result.get("status") or "") == "expired":
                payload.setdefault("ok", False)
                payload.setdefault("error", "Remote desktop command expired")
            return payload
        if time.monotonic() >= deadline:
            raise asyncio.TimeoutError()
        await asyncio.sleep(max(0.01, float(poll_interval_seconds or 0.1)))


def dispatch_remote_desktop_command_via_broker(
    *,
    store: Any,
    user_id: int,
    desktop_id: str,
    command_name: str,
    payload: Optional[Dict[str, Any]] = None,
    ttl_seconds: int = 30,
) -> str:
    queued = store.enqueue_remote_desktop_command(
        user_id=int(user_id),
        desktop_id=str(desktop_id),
        command_type=str(command_name),
        payload=dict(payload or {}),
        wants_reply=False,
        ttl_seconds=ttl_seconds,
    )
    return str(queued["command_id"])


async def request_remote_desktop_command_via_broker(
    *,
    store: Any,
    user_id: int,
    desktop_id: str,
    command_name: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout_seconds: float = 30.0,
) -> Dict[str, Any]:
    queued = store.enqueue_remote_desktop_command(
        user_id=int(user_id),
        desktop_id=str(desktop_id),
        command_type=str(command_name),
        payload=dict(payload or {}),
        wants_reply=True,
        ttl_seconds=max(1, int(timeout_seconds or 30.0) + 5),
    )
    reply = await wait_for_brokered_remote_command(
        store=store,
        user_id=int(user_id),
        command_id=str(queued["command_id"]),
        timeout_seconds=timeout_seconds,
    )
    if not bool(reply.get("ok", False)):
        detail = str(reply.get("error") or "The paired desktop could not complete the request")
        raise BrokeredRemoteCommandError(detail, status_code=_safe_error_status(reply.get("status_code")))
    return dict(reply.get("result") or {})


async def pump_remote_desktop_command_broker(
    *,
    store: Any,
    user_id: int,
    desktop_id: str,
    connection: Any,
    manager: Any,
    poll_interval_seconds: float = 0.25,
) -> None:
    if not remote_control_sqlite_broker_enabled():
        return

    connection_id = str(getattr(connection, "connection_id", "connection"))
    instance_id = f"{getattr(manager, 'instance_id', 'remote')}:{connection_id}"
    while manager.is_active_connection(desktop_id, connection_id):
        try:
            commands = store.claim_remote_desktop_commands(
                user_id=int(user_id),
                desktop_id=str(desktop_id),
                instance_id=instance_id,
                limit=10,
            )
            for command in commands:
                command_id = str(command.get("command_id") or "").strip()
                try:
                    async with connection.send_lock:
                        await connection.websocket.send_json(
                            {
                                "type": "command",
                                "command_id": command_id,
                                "payload": {
                                    "name": str(command.get("command_type") or ""),
                                    **dict(command.get("payload") or {}),
                                },
                            }
                        )
                except Exception as exc:
                    store.fail_remote_desktop_command(
                        command_id=command_id,
                        user_id=int(user_id),
                        desktop_id=str(desktop_id),
                        error=f"The paired desktop connection failed: {exc}",
                    )
                    raise
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[remote] broker command pump failed for %s", desktop_id)
        await asyncio.sleep(max(0.01, float(poll_interval_seconds or 0.25)))
