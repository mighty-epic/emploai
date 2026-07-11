from __future__ import annotations

import asyncio

import pytest

from app_backend.remote_command_broker import (
    BrokeredRemoteCommandError,
    dispatch_remote_desktop_command_via_broker,
    pump_remote_desktop_command_broker,
    request_remote_desktop_command_via_broker,
)
from app_backend.remote_control_store import RemoteControlPlaneStore


def _store_with_desktop(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user_id = 0
    desktop = store.ensure_standalone_manager_desktop(
        user_id=user_id,
        display_name="Broker Desktop",
        device_platform="desktop",
        device_key="broker-desktop",
    )
    return store, user_id, str(desktop["desktop_id"])


async def _complete_next_brokered_command(
    *,
    store: RemoteControlPlaneStore,
    user_id: int,
    desktop_id: str,
    ok: bool,
    payload: dict,
) -> dict:
    deadline = asyncio.get_running_loop().time() + 2.0
    while asyncio.get_running_loop().time() < deadline:
        claimed = store.claim_remote_desktop_commands(
            user_id=user_id,
            desktop_id=desktop_id,
            instance_id="worker-with-socket",
        )
        if claimed:
            store.complete_remote_desktop_command(
                command_id=str(claimed[0]["command_id"]),
                user_id=user_id,
                desktop_id=desktop_id,
                ok=ok,
                payload=payload,
            )
            return claimed[0]
        await asyncio.sleep(0.01)
    raise AssertionError("brokered command was not queued")


def test_dispatch_remote_desktop_command_via_broker_enqueues_one_way_command(tmp_path):
    store, user_id, desktop_id = _store_with_desktop(tmp_path)

    command_id = dispatch_remote_desktop_command_via_broker(
        store=store,
        user_id=user_id,
        desktop_id=desktop_id,
        command_name="state_snapshot",
        payload={"scope": "active"},
    )

    claimed = store.claim_remote_desktop_commands(
        user_id=user_id,
        desktop_id=desktop_id,
        instance_id="worker-with-socket",
    )
    assert len(claimed) == 1
    assert claimed[0]["command_id"] == command_id
    assert claimed[0]["command_type"] == "state_snapshot"
    assert claimed[0]["payload"] == {"scope": "active"}
    assert claimed[0]["wants_reply"] is False


def test_request_remote_desktop_command_via_broker_returns_result(tmp_path):
    store, user_id, desktop_id = _store_with_desktop(tmp_path)

    async def scenario():
        request_task = asyncio.create_task(
            request_remote_desktop_command_via_broker(
                store=store,
                user_id=user_id,
                desktop_id=desktop_id,
                command_name="http_request",
                payload={"path": "/api/app/health"},
                timeout_seconds=2.0,
            )
        )
        claimed = await _complete_next_brokered_command(
            store=store,
            user_id=user_id,
            desktop_id=desktop_id,
            ok=True,
            payload={"ok": True, "result": {"status": "ok"}},
        )
        result = await request_task
        return result, claimed

    result, claimed = asyncio.run(scenario())

    assert result == {"status": "ok"}
    assert claimed["wants_reply"] is True
    assert claimed["payload"] == {"path": "/api/app/health"}


def test_request_remote_desktop_command_via_broker_raises_desktop_error(tmp_path):
    store, user_id, desktop_id = _store_with_desktop(tmp_path)

    async def scenario():
        request_task = asyncio.create_task(
            request_remote_desktop_command_via_broker(
                store=store,
                user_id=user_id,
                desktop_id=desktop_id,
                command_name="http_request",
                payload={"path": "/api/app/sessions/missing"},
                timeout_seconds=2.0,
            )
        )
        await _complete_next_brokered_command(
            store=store,
            user_id=user_id,
            desktop_id=desktop_id,
            ok=False,
            payload={"ok": False, "error": "Desktop route failed", "status_code": 418},
        )
        return await request_task

    with pytest.raises(BrokeredRemoteCommandError) as exc_info:
        asyncio.run(scenario())

    assert exc_info.value.detail == "Desktop route failed"
    assert exc_info.value.status_code == 418


def test_pump_remote_desktop_command_broker_sends_claimed_commands(tmp_path, monkeypatch):
    store, user_id, desktop_id = _store_with_desktop(tmp_path)
    monkeypatch.setenv("EMPLOAI_REMOTE_CONTROL_ROUTING_MODE", "sqlite_broker")
    command_id = dispatch_remote_desktop_command_via_broker(
        store=store,
        user_id=user_id,
        desktop_id=desktop_id,
        command_name="sync",
        payload={"after": "event-1"},
    )

    class FakeManager:
        instance_id = "api-worker"

        def __init__(self):
            self.active = True

        def is_active_connection(self, requested_desktop_id, connection_id):
            return self.active and requested_desktop_id == desktop_id and connection_id == "conn-1"

    class FakeWebsocket:
        def __init__(self, manager):
            self.manager = manager
            self.sent = []

        async def send_json(self, payload):
            self.sent.append(payload)
            self.manager.active = False

    class FakeConnection:
        def __init__(self, manager):
            self.connection_id = "conn-1"
            self.send_lock = asyncio.Lock()
            self.websocket = FakeWebsocket(manager)

    async def scenario():
        manager = FakeManager()
        connection = FakeConnection(manager)
        await asyncio.wait_for(
            pump_remote_desktop_command_broker(
                store=store,
                user_id=user_id,
                desktop_id=desktop_id,
                connection=connection,
                manager=manager,
                poll_interval_seconds=0.01,
            ),
            timeout=1.0,
        )
        return connection.websocket.sent

    sent = asyncio.run(scenario())

    assert sent == [
        {
            "type": "command",
            "command_id": command_id,
            "payload": {"name": "sync", "after": "event-1"},
        }
    ]
