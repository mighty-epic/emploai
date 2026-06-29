from __future__ import annotations

import asyncio

from mobile_app.backend.fleet_task_dispatch import try_dispatch_fleet_worker_task, try_stop_fleet_worker_task
from mobile_app.backend.remote_control_store import RemoteControlPlaneStore


class _FakeFleetDesktopManager:
    def __init__(self, *, connected: bool):
        self.connected = connected
        self.calls = []

    def is_connected_for_user(self, desktop_id, user_id):
        return bool(self.connected)

    async def send_command(self, *, desktop_id, user_id, command_type, payload):
        if not self.connected:
            raise RuntimeError("The paired desktop is offline")
        self.calls.append(
            {
                "desktop_id": desktop_id,
                "user_id": user_id,
                "command_type": command_type,
                "payload": payload,
            }
        )
        return "cmd_live"


def _store_with_remote_worker_task(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="fleet-dispatch@example.com", password="CorrectHorse!2026", display_name="Fleet Dispatch")
    manager_login = store.login(
        email="fleet-dispatch@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Manager",
        device_platform="desktop",
        device_key="fleet-dispatch-manager",
    )
    enrollment = store.create_worker_enrollment(
        user_id=user["user_id"],
        desktop_id=manager_login["desktop"]["desktop_id"],
        display_name="Remote Dispatch Worker",
    )
    completed = store.complete_worker_enrollment(
        enrollment_token=enrollment["enrollment_token"],
        device_name="Remote Dispatch Worker",
        device_platform="linux",
        device_key="remote-dispatch-worker",
    )
    worker = completed["worker"]
    task = store.assign_worker_task(
        user_id=user["user_id"],
        worker_id=worker["worker_id"],
        prompt="Run through dispatch helper",
        source="manager",
        metadata={"target_session_id": "sess-dispatch"},
    )
    return store, int(user["user_id"]), worker, task


def test_try_dispatch_fleet_worker_task_sends_live_command_when_connected(tmp_path):
    store, user_id, worker, task = _store_with_remote_worker_task(tmp_path)
    manager = _FakeFleetDesktopManager(connected=True)

    result = asyncio.run(
        try_dispatch_fleet_worker_task(
            store=store,
            remote_desktop_manager=manager,
            user_id=user_id,
            worker=worker,
            task=task,
            is_remote_session_active=lambda **_: True,
        )
    )

    assert result["status"] == "running"
    assert manager.calls[0]["command_type"] == "fleet_run_task"
    assert manager.calls[0]["payload"]["task_id"] == task["task_id"]
    assert manager.calls[0]["payload"]["target_session_id"] == "sess-dispatch"
    assert store.claim_remote_desktop_commands(
        user_id=user_id,
        desktop_id=worker["machine_desktop_id"],
        instance_id="other-worker",
    ) == []


def test_fleet_task_run_and_stop_use_sqlite_broker_when_not_connected_here(tmp_path, monkeypatch):
    store, user_id, worker, task = _store_with_remote_worker_task(tmp_path)
    manager = _FakeFleetDesktopManager(connected=False)
    monkeypatch.setenv("EMPLOAI_REMOTE_CONTROL_ROUTING_MODE", "sqlite_broker")

    dispatched = asyncio.run(
        try_dispatch_fleet_worker_task(
            store=store,
            remote_desktop_manager=manager,
            user_id=user_id,
            worker=worker,
            task=task,
            is_remote_session_active=lambda **_: True,
        )
    )
    run_commands = store.claim_remote_desktop_commands(
        user_id=user_id,
        desktop_id=worker["machine_desktop_id"],
        instance_id="worker-with-websocket",
    )

    assert dispatched["status"] == "running"
    assert run_commands[0]["command_type"] == "fleet_run_task"
    assert run_commands[0]["payload"]["task_id"] == task["task_id"]
    assert run_commands[0]["payload"]["prompt"] == "Run through dispatch helper"

    stopped = store.update_worker_task_status(
        user_id=user_id,
        task_id=task["task_id"],
        status="stopped",
        metadata={"reason": "test"},
    )
    stop_sent = asyncio.run(
        try_stop_fleet_worker_task(
            store=store,
            remote_desktop_manager=manager,
            user_id=user_id,
            task=stopped,
            is_remote_session_active=lambda **_: True,
        )
    )
    stop_commands = store.claim_remote_desktop_commands(
        user_id=user_id,
        desktop_id=worker["machine_desktop_id"],
        instance_id="worker-with-websocket",
    )

    assert stop_sent is True
    assert stop_commands[0]["command_type"] == "fleet_stop_task"
    assert stop_commands[0]["payload"] == {"task_id": task["task_id"], "worker_id": worker["worker_id"]}
    assert manager.calls == []
