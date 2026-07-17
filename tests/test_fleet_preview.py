from __future__ import annotations

import asyncio

from app_backend.fleet_preview import request_fleet_desktop_preview, request_fleet_worker_preview
from app_backend.remote_control_store import RemoteControlPlaneStore


class _FakePreviewManager:
    def __init__(self, result=None, *, connected=True, error=None):
        self.result = result or {}
        self.connected = connected
        self.error = error
        self.calls = []

    def is_connected_for_user(self, desktop_id, user_id):
        return bool(self.connected)

    async def request_command(self, *, desktop_id, user_id, command_type, payload, timeout_seconds):
        self.calls.append(
            {
                "desktop_id": desktop_id,
                "user_id": user_id,
                "command_type": command_type,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.error:
            raise RuntimeError(self.error)
        return {"ok": True, "result": self.result}


def _store_with_manager(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user_id = 0
    desktop = store.ensure_standalone_manager_desktop(
        user_id=user_id,
        display_name="Manager",
        device_platform="desktop",
        device_key="preview-manager",
    )
    return store, user_id, str(desktop["desktop_id"])


def _remote_worker(store, *, user_id, manager_desktop_id):
    enrollment = store.create_worker_enrollment(
        user_id=user_id,
        desktop_id=manager_desktop_id,
        display_name="Remote Preview Worker",
    )
    completed = store.complete_worker_enrollment(
        enrollment_token=enrollment["enrollment_token"],
        device_name="Remote Worker",
        device_platform="linux",
        device_key="remote-preview-worker",
    )
    return completed["worker"]


def test_request_fleet_worker_preview_dispatches_connected_remote_worker(tmp_path):
    store, user_id, manager_desktop_id = _store_with_manager(tmp_path)
    worker = _remote_worker(store, user_id=user_id, manager_desktop_id=manager_desktop_id)
    manager = _FakePreviewManager(
        {
            "status": "captured",
            "detail": "Preview captured.",
            "command_id": "cmd_preview",
            "capture": {
                "mime_type": "image/jpeg",
                "image_base64": "cmVtb3RlLXByZXZpZXc=",
                "width": 640,
                "height": 360,
                "backend": "test",
                "captured_at": 1.0,
            },
        }
    )

    result = asyncio.run(
        request_fleet_worker_preview(
            store=store,
            remote_desktop_manager=manager,
            user_id=user_id,
            worker=worker,
            requested_by="desktop",
            is_remote_session_active=lambda **_: True,
        )
    )

    assert result["dispatch_status"] == "captured"
    assert result["command_id"] == "cmd_preview"
    assert result["detail"] == "Preview captured."
    assert result["capture"]["image_base64"] == "cmVtb3RlLXByZXZpZXc="
    assert manager.calls[0]["desktop_id"] == worker["machine_desktop_id"]
    assert manager.calls[0]["command_type"] == "fleet_worker_preview"
    assert manager.calls[0]["payload"]["preview_id"] == result["preview_id"]
    updated = store.get_worker(user_id=user_id, worker_id=worker["worker_id"])
    assert updated["metadata"]["latest_preview_request"]["status"] == "captured"
    assert "image_base64" not in updated["metadata"]["latest_preview_request"]["metadata"]["capture"]


def test_request_fleet_worker_preview_captures_local_worker_without_remote_dispatch(tmp_path):
    store, user_id, manager_desktop_id = _store_with_manager(tmp_path)
    worker = store.create_local_worker(user_id=user_id, desktop_id=manager_desktop_id)
    manager = _FakePreviewManager()

    result = asyncio.run(
        request_fleet_worker_preview(
            store=store,
            remote_desktop_manager=manager,
            user_id=user_id,
            worker=worker,
            requested_by="desktop",
            is_remote_session_active=lambda **_: True,
            capture_local_preview=lambda **_: asyncio.sleep(
                0,
                result={
                    "status": "captured",
                    "detail": "Local preview captured.",
                    "capture": {
                        "mime_type": "image/jpeg",
                        "image_base64": "bG9jYWwtcHJldmlldw==",
                        "width": 800,
                        "height": 450,
                        "backend": "test",
                        "captured_at": 1.0,
                    },
                },
            ),
        )
    )

    assert result["dispatch_status"] == "captured"
    assert result["detail"] == "Local preview captured."
    assert result["capture"]["image_base64"] == "bG9jYWwtcHJldmlldw=="
    assert manager.calls == []


def test_request_fleet_worker_preview_uses_sqlite_broker_for_remote_socket(tmp_path, monkeypatch):
    store, user_id, manager_desktop_id = _store_with_manager(tmp_path)
    worker = _remote_worker(store, user_id=user_id, manager_desktop_id=manager_desktop_id)
    manager = _FakePreviewManager(connected=False)
    monkeypatch.setenv("EMPLOAI_REMOTE_CONTROL_ROUTING_MODE", "sqlite_broker")

    async def complete_brokered_command():
        deadline = asyncio.get_running_loop().time() + 2.0
        while asyncio.get_running_loop().time() < deadline:
            claimed = store.claim_remote_desktop_commands(
                user_id=user_id,
                desktop_id=worker["machine_desktop_id"],
                instance_id="worker-with-websocket",
            )
            if claimed:
                store.complete_remote_desktop_command(
                    command_id=claimed[0]["command_id"],
                    user_id=user_id,
                    desktop_id=worker["machine_desktop_id"],
                    ok=True,
                    payload={
                        "ok": True,
                        "result": {
                            "status": "acknowledged",
                            "detail": "Broker preview accepted.",
                            "command_id": "cmd_broker_preview",
                        },
                    },
                )
                return claimed[0]
            await asyncio.sleep(0.01)
        raise AssertionError("brokered preview command was not queued")

    async def scenario():
        preview_task = asyncio.create_task(
            request_fleet_worker_preview(
                store=store,
                remote_desktop_manager=manager,
                user_id=user_id,
                worker=worker,
                requested_by="desktop",
                is_remote_session_active=lambda **_: True,
                timeout_seconds=2.0,
            )
        )
        claimed = await complete_brokered_command()
        result = await preview_task
        return result, claimed

    result, claimed = asyncio.run(scenario())

    assert result["dispatch_status"] == "acknowledged"
    assert result["detail"] == "Broker preview accepted."
    assert result["command_id"] == "cmd_broker_preview"
    assert claimed["command_type"] == "fleet_worker_preview"
    assert claimed["payload"]["preview_id"] == result["preview_id"]
    assert manager.calls == []


def test_request_fleet_worker_preview_marks_unavailable_remote_desktop(tmp_path):
    store, user_id, manager_desktop_id = _store_with_manager(tmp_path)
    worker = _remote_worker(store, user_id=user_id, manager_desktop_id=manager_desktop_id)
    marked_offline = []
    manager = _FakePreviewManager(error="The paired desktop is offline")

    result = asyncio.run(
        request_fleet_worker_preview(
            store=store,
            remote_desktop_manager=manager,
            user_id=user_id,
            worker=worker,
            requested_by="desktop",
            is_remote_session_active=lambda **_: True,
            is_desktop_unavailable_error=lambda detail: "offline" in detail,
            mark_desktop_offline=lambda **kwargs: marked_offline.append(kwargs),
        )
    )

    assert result["dispatch_status"] == "failed"
    assert result["detail"] == "The paired desktop is offline"
    assert marked_offline == [
        {
            "user_id": user_id,
            "desktop_id": worker["machine_desktop_id"],
            "reason": "The paired desktop is offline",
        }
    ]


def test_request_fleet_desktop_preview_captures_remote_computer_without_persisting_image(tmp_path):
    store, user_id, manager_desktop_id = _store_with_manager(tmp_path)
    worker = _remote_worker(store, user_id=user_id, manager_desktop_id=manager_desktop_id)
    desktop_id = worker["machine_desktop_id"]
    desktop = next(item for item in store.list_desktops(user_id=user_id) if item["desktop_id"] == desktop_id)
    manager = _FakePreviewManager(
        {
            "status": "captured",
            "detail": "Computer preview captured.",
            "capture": {
                "mime_type": "image/jpeg",
                "image_base64": "Y29tcHV0ZXItcHJldmlldw==",
                "width": 960,
                "height": 540,
                "backend": "test",
                "captured_at": 2.0,
            },
        }
    )

    result = asyncio.run(
        request_fleet_desktop_preview(
            store=store,
            remote_desktop_manager=manager,
            user_id=user_id,
            desktop=desktop,
            manager_desktop_id=manager_desktop_id,
            is_remote_session_active=lambda **_: True,
        )
    )

    assert result["dispatch_status"] == "captured"
    assert result["desktop_id"] == desktop_id
    assert result["capture"]["image_base64"] == "Y29tcHV0ZXItcHJldmlldw=="
    assert manager.calls[0]["payload"]["view_only"] is True
    assert "latest_preview_request" not in store.get_worker(
        user_id=user_id,
        worker_id=worker["worker_id"],
    )["metadata"]


def test_request_fleet_desktop_preview_keeps_connection_online_when_only_display_is_unavailable(tmp_path):
    store, user_id, manager_desktop_id = _store_with_manager(tmp_path)
    worker = _remote_worker(store, user_id=user_id, manager_desktop_id=manager_desktop_id)
    desktop_id = worker["machine_desktop_id"]
    desktop = next(item for item in store.list_desktops(user_id=user_id) if item["desktop_id"] == desktop_id)
    manager = _FakePreviewManager(
        {
            "status": "unavailable",
            "detail": "The Windows display is disconnected.",
            "capture_capability": {
                "available": False,
                "code": "display_disconnected",
                "state": "disconnected",
                "recovery": "Reconnect a display.",
                "retryable": True,
                "ignored": "must not cross the API boundary",
            },
        }
    )
    marked_offline = []

    result = asyncio.run(
        request_fleet_desktop_preview(
            store=store,
            remote_desktop_manager=manager,
            user_id=user_id,
            desktop=desktop,
            manager_desktop_id=manager_desktop_id,
            is_remote_session_active=lambda **_: True,
            is_desktop_unavailable_error=lambda detail: "offline" in detail,
            mark_desktop_offline=lambda **kwargs: marked_offline.append(kwargs),
        )
    )

    assert result["dispatch_status"] == "unavailable"
    assert result["capture_capability"] == {
        "available": False,
        "code": "display_disconnected",
        "state": "disconnected",
        "recovery": "Reconnect a display.",
        "retryable": True,
    }
    assert "capture" not in result
    assert marked_offline == []


def test_request_fleet_desktop_preview_captures_manager_computer_locally(tmp_path):
    store, user_id, manager_desktop_id = _store_with_manager(tmp_path)
    desktop = next(item for item in store.list_desktops(user_id=user_id) if item["desktop_id"] == manager_desktop_id)
    manager = _FakePreviewManager()

    result = asyncio.run(
        request_fleet_desktop_preview(
            store=store,
            remote_desktop_manager=manager,
            user_id=user_id,
            desktop=desktop,
            manager_desktop_id=manager_desktop_id,
            is_remote_session_active=lambda **_: True,
            capture_local_preview=lambda **_: asyncio.sleep(
                0,
                result={
                    "status": "captured",
                    "detail": "Local computer captured.",
                    "capture": {
                        "mime_type": "image/jpeg",
                        "image_base64": "bG9jYWwtY29tcHV0ZXI=",
                        "width": 800,
                        "height": 450,
                        "backend": "test",
                        "captured_at": 3.0,
                    },
                },
            ),
        )
    )

    assert result["dispatch_status"] == "captured"
    assert result["capture"]["image_base64"] == "bG9jYWwtY29tcHV0ZXI="
    assert manager.calls == []
