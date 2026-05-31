from __future__ import annotations

import asyncio
import secrets
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional

from fastapi import WebSocket


@dataclass
class RemoteDesktopConnection:
    user_id: int
    desktop_id: str
    websocket: WebSocket
    loop: asyncio.AbstractEventLoop
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


class RemoteDesktopConnectionManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._connections: Dict[str, RemoteDesktopConnection] = {}

    def register(
        self,
        *,
        user_id: int,
        desktop_id: str,
        websocket: WebSocket,
        loop: asyncio.AbstractEventLoop,
    ) -> RemoteDesktopConnection:
        connection = RemoteDesktopConnection(
            user_id=int(user_id),
            desktop_id=str(desktop_id),
            websocket=websocket,
            loop=loop,
        )
        with self._lock:
            self._connections[connection.desktop_id] = connection
        return connection

    def unregister(self, desktop_id: Optional[str]) -> None:
        if not desktop_id:
            return
        with self._lock:
            self._connections.pop(str(desktop_id), None)

    def get(self, desktop_id: Optional[str]) -> Optional[RemoteDesktopConnection]:
        if not desktop_id:
            return None
        with self._lock:
            return self._connections.get(str(desktop_id))

    def is_connected(self, desktop_id: Optional[str]) -> bool:
        return self.get(desktop_id) is not None

    async def send_command(
        self,
        *,
        desktop_id: str,
        command_type: str,
        payload: dict,
    ) -> str:
        connection = self.get(desktop_id)
        if connection is None:
            raise RuntimeError("The paired desktop is offline")

        command_id = f"cmd_{secrets.token_hex(8)}"
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
        return command_id


_manager: Optional[RemoteDesktopConnectionManager] = None


def get_remote_desktop_manager() -> RemoteDesktopConnectionManager:
    global _manager
    if _manager is None:
        _manager = RemoteDesktopConnectionManager()
    return _manager

