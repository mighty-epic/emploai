from __future__ import annotations

import asyncio
import os
import secrets
import socket
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from fastapi import WebSocket

SUPPORTED_REMOTE_CONTROL_ROUTING_MODES = {"single_process", "sqlite_broker"}
REMOTE_CONTROL_INSTANCE_ID = (
    os.getenv("EMPLOAI_REMOTE_CONTROL_INSTANCE_ID", "").strip()
    or f"{socket.gethostname()}:{os.getpid()}:{secrets.token_hex(4)}"
)


def remote_control_routing_mode() -> str:
    return str(os.getenv("EMPLOAI_REMOTE_CONTROL_ROUTING_MODE", "single_process") or "single_process").strip().lower()


def remote_control_sqlite_broker_enabled() -> bool:
    return remote_control_routing_mode() == "sqlite_broker"


def _positive_int_env(name: str) -> Optional[int]:
    value = str(os.getenv(name, "") or "").strip()
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def remote_control_routing_status() -> Dict[str, Any]:
    worker_hints = {
        "EMPLOAI_REMOTE_CONTROL_WORKERS": _positive_int_env("EMPLOAI_REMOTE_CONTROL_WORKERS"),
        "WEB_CONCURRENCY": _positive_int_env("WEB_CONCURRENCY"),
        "UVICORN_WORKERS": _positive_int_env("UVICORN_WORKERS"),
    }
    requested_workers = max([value or 1 for value in worker_hints.values()] or [1])
    mode = remote_control_routing_mode()
    mode_valid = mode in SUPPORTED_REMOTE_CONTROL_ROUTING_MODES
    allow_unsafe = str(os.getenv("EMPLOAI_REMOTE_CONTROL_ALLOW_UNSAFE_MULTIPROCESS", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    supported = mode_valid and ((mode == "single_process" and requested_workers <= 1) or mode == "sqlite_broker")
    return {
        "instance_id": REMOTE_CONTROL_INSTANCE_ID,
        "mode": mode,
        "mode_valid": mode_valid,
        "supported_modes": sorted(SUPPORTED_REMOTE_CONTROL_ROUTING_MODES),
        "broker": "sqlite" if mode == "sqlite_broker" else None,
        "supported": bool(supported),
        "allow_unsafe_multiprocess": bool(allow_unsafe),
        "requested_workers": requested_workers,
        "worker_hints": worker_hints,
        "requires_sticky_sessions_or_broker": requested_workers > 1 and mode != "sqlite_broker",
        "cross_process_command_routing": mode == "sqlite_broker",
    }


def assert_remote_control_routing_supported() -> None:
    status = remote_control_routing_status()
    if not status["mode_valid"]:
        raise RuntimeError(
            "Invalid EMPLOAI_REMOTE_CONTROL_ROUTING_MODE. "
            f"Expected one of {status['supported_modes']}, got {status['mode']!r}. "
            f"Routing status: {status}"
        )
    if status["supported"] or status["allow_unsafe_multiprocess"]:
        return
    raise RuntimeError(
        "Remote desktop websocket command routing is in-process. Run the control plane with one worker, "
        "or add sticky routing/external broker support before using multiple workers. "
        f"Routing status: {status}"
    )


@dataclass
class RemoteDesktopConnection:
    user_id: int
    desktop_id: str
    websocket: WebSocket
    loop: asyncio.AbstractEventLoop
    session_token_hash: Optional[str] = None
    connection_id: str = field(default_factory=lambda: f"conn_{secrets.token_hex(8)}")
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    pending_replies: Dict[str, asyncio.Future] = field(default_factory=dict, repr=False)


class RemoteDesktopConnectionManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._connections: Dict[str, RemoteDesktopConnection] = {}
        self.instance_id = REMOTE_CONTROL_INSTANCE_ID

    @staticmethod
    def _fail_pending_replies(connection: RemoteDesktopConnection, message: str) -> None:
        for future in list(connection.pending_replies.values()):
            if future.done():
                continue

            def fail_reply(target: asyncio.Future = future) -> None:
                if not target.done():
                    target.set_exception(RuntimeError(message))

            try:
                connection.loop.call_soon_threadsafe(fail_reply)
            except RuntimeError:
                if not future.done():
                    future.cancel()

    @staticmethod
    def _close_replaced_connection(connection: RemoteDesktopConnection) -> None:
        async def close_websocket() -> None:
            try:
                await connection.websocket.close(code=4000)
            except Exception:
                pass

        try:
            connection.loop.call_soon_threadsafe(lambda: asyncio.create_task(close_websocket()))
        except RuntimeError:
            return

    def register(
        self,
        *,
        user_id: int,
        desktop_id: str,
        websocket: WebSocket,
        loop: asyncio.AbstractEventLoop,
        session_token_hash: Optional[str] = None,
    ) -> RemoteDesktopConnection:
        connection = RemoteDesktopConnection(
            user_id=int(user_id),
            desktop_id=str(desktop_id),
            websocket=websocket,
            loop=loop,
            session_token_hash=str(session_token_hash or "").strip() or None,
        )
        with self._lock:
            previous = self._connections.get(connection.desktop_id)
            if previous is not None and int(previous.user_id) != int(connection.user_id):
                raise RuntimeError("The desktop connection belongs to another account")
            self._connections[connection.desktop_id] = connection
        if previous is not None:
            self._fail_pending_replies(previous, "The paired desktop reconnected")
            self._close_replaced_connection(previous)
        return connection

    def unregister(
        self,
        desktop_id: Optional[str],
        *,
        connection_id: Optional[str] = None,
        reason: str = "The paired desktop disconnected",
    ) -> bool:
        if not desktop_id:
            return False
        removed: Optional[RemoteDesktopConnection] = None
        with self._lock:
            current = self._connections.get(str(desktop_id))
            if current is None:
                return False
            if connection_id and current.connection_id != str(connection_id):
                return False
            removed = self._connections.pop(str(desktop_id), None)
        if removed is not None:
            self._fail_pending_replies(removed, reason)
            return True
        return False

    def get(self, desktop_id: Optional[str]) -> Optional[RemoteDesktopConnection]:
        if not desktop_id:
            return None
        with self._lock:
            return self._connections.get(str(desktop_id))

    def is_connected(self, desktop_id: Optional[str]) -> bool:
        return self.get(desktop_id) is not None

    def is_connected_for_user(self, desktop_id: Optional[str], user_id: int) -> bool:
        connection = self.get(desktop_id)
        return connection is not None and int(connection.user_id) == int(user_id)

    def is_active_connection(self, desktop_id: Optional[str], connection_id: Optional[str]) -> bool:
        if not desktop_id or not connection_id:
            return False
        with self._lock:
            current = self._connections.get(str(desktop_id))
            return current is not None and current.connection_id == str(connection_id)

    def connected_desktop_ids_for_user(self, user_id: int) -> list[str]:
        with self._lock:
            return sorted(
                connection.desktop_id
                for connection in self._connections.values()
                if int(connection.user_id) == int(user_id)
            )

    def _connection_for_command(
        self,
        *,
        desktop_id: str,
        user_id: Optional[int] = None,
    ) -> RemoteDesktopConnection:
        connection = self.get(desktop_id)
        if connection is None:
            raise RuntimeError("The paired desktop is offline")
        if user_id is not None and int(connection.user_id) != int(user_id):
            raise RuntimeError("The paired desktop is unavailable for this account")
        return connection

    async def send_command(
        self,
        *,
        desktop_id: str,
        user_id: Optional[int] = None,
        command_type: str,
        payload: dict,
    ) -> str:
        connection = self._connection_for_command(desktop_id=desktop_id, user_id=user_id)

        command_id = f"cmd_{secrets.token_hex(8)}"
        try:
            async with connection.send_lock:
                await connection.websocket.send_json(
                    {
                        "type": "command",
                        "command_id": command_id,
                        "payload": {
                            "name": command_type,
                            **(payload or {}),
                        },
                    }
                )
        except Exception as exc:
            self.unregister(
                connection.desktop_id,
                connection_id=connection.connection_id,
                reason="The paired desktop connection failed",
            )
            raise RuntimeError("The paired desktop connection failed") from exc
        return command_id

    async def request_command(
        self,
        *,
        desktop_id: str,
        user_id: Optional[int] = None,
        command_type: str,
        payload: dict,
        timeout_seconds: float = 30.0,
    ) -> Dict[str, Any]:
        connection = self._connection_for_command(desktop_id=desktop_id, user_id=user_id)

        command_id = f"cmd_{secrets.token_hex(8)}"
        future = connection.loop.create_future()
        connection.pending_replies[command_id] = future
        try:
            try:
                async with connection.send_lock:
                    await connection.websocket.send_json(
                        {
                            "type": "command",
                            "command_id": command_id,
                            "payload": {
                                "name": command_type,
                                **(payload or {}),
                            },
                        }
                    )
            except Exception as exc:
                connection.pending_replies.pop(command_id, None)
                self.unregister(
                    connection.desktop_id,
                    connection_id=connection.connection_id,
                    reason="The paired desktop connection failed",
                )
                raise RuntimeError("The paired desktop connection failed") from exc
            result = await asyncio.wait_for(future, timeout=max(0.5, timeout_seconds))
            return dict(result or {})
        finally:
            connection.pending_replies.pop(command_id, None)

    def resolve_command_reply(
        self,
        *,
        desktop_id: Optional[str],
        connection_id: Optional[str] = None,
        command_id: Optional[str],
        payload: dict,
    ) -> bool:
        connection = self.get(desktop_id)
        if connection is None or not command_id:
            return False
        if connection_id and connection.connection_id != str(connection_id):
            return False
        future = connection.pending_replies.get(str(command_id))
        if future is None or future.done():
            return False
        future.set_result(dict(payload or {}))
        return True


_manager: Optional[RemoteDesktopConnectionManager] = None


def get_remote_desktop_manager() -> RemoteDesktopConnectionManager:
    global _manager
    if _manager is None:
        _manager = RemoteDesktopConnectionManager()
    return _manager
