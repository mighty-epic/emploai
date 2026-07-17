from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app_backend.fleet_local_runtime import LocalFleetRuntime
from app_backend.fleet_task_dispatch import try_dispatch_fleet_worker_task, try_stop_fleet_worker_task
from app_backend.remote_control_store import RemoteControlPlaneStore


class _DisconnectedDesktopManager:
    def is_connected_for_user(self, _desktop_id, _user_id):
        return False


class _FakeOrchestrator:
    def __init__(self, runtime):
        self.runtime = runtime
        self.completed = []

    async def prepare_turn(self, session_id, *, origin_channel):
        return SimpleNamespace(
            acquired=True,
            busy=False,
            error=None,
            session_id=session_id,
            worker=self.runtime,
        )

    async def complete_turn(self, lease):
        self.completed.append(lease.session_id)


class _FakeBridge:
    def __init__(self, runtime):
        self.runtime = runtime
        self.orchestrator = _FakeOrchestrator(runtime)
        self.sessions = {}

    def get_session(self, session_id):
        if session_id not in self.sessions:
            raise ValueError("Session not found")
        return self.sessions[session_id]

    def create_session(self, name, **kwargs):
        assert kwargs["activate"] is False
        assert kwargs["fleet_identity_role"] == "worker"
        session = SimpleNamespace(
            id=f"session-{len(self.sessions) + 1}",
            name=name,
            fleet_identity_role="worker",
            fleet_worker_id=kwargs["fleet_worker_id"],
        )
        self.sessions[session.id] = session
        return session


def _local_worker_task(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user_id = 0
    desktop = store.ensure_standalone_manager_desktop(
        user_id=user_id,
        display_name="Manager",
        device_platform="desktop",
        device_key="fleet-local-runtime-manager",
    )
    worker = store.create_local_worker(
        user_id=user_id,
        desktop_id=desktop["desktop_id"],
        display_name="Local Worker",
        metadata={"created_by": "desktop_user_request"},
    )
    task = store.assign_worker_task(
        user_id=user_id,
        worker_id=worker["worker_id"],
        prompt="Complete the local worker task",
        source="manager",
    )
    return store, user_id, worker, task


async def _wait_for_report(store, *, user_id, task_id):
    deadline = asyncio.get_running_loop().time() + 3.0
    while asyncio.get_running_loop().time() < deadline:
        task = store.get_worker_task(user_id=user_id, task_id=task_id)
        if task.get("report_id"):
            return task
        await asyncio.sleep(0.01)
    raise AssertionError("local Fleet task did not produce a report")


def test_local_worker_dispatch_runs_shared_turn_and_persists_report(tmp_path):
    store, user_id, worker, task = _local_worker_task(tmp_path)
    runtime_session = SimpleNamespace(chat_history=[], should_interrupt=False, interrupt_message=None)
    bridge = _FakeBridge(runtime_session)
    deltas = []

    async def run_turn(runtime, **kwargs):
        assert kwargs["surface_mode"] == "fleet"
        assert kwargs["source_client_id"] == f"fleet:{task['task_id']}"
        runtime.chat_history.append(
            {
                "role": "assistant",
                "metadata": {"artifact_ids": ["artifact-local-1"]},
            }
        )
        return {
            "session_id": "session-1",
            "assistant_text": (
                "status: completed\n"
                "summary: Local task completed.\n"
                "evidence: Verified the saved result.\n"
                "confidence: high\n"
                "next_suggested_action: Review the result."
            ),
        }

    runtime = LocalFleetRuntime(run_turn=run_turn)

    async def scenario():
        dispatched = await try_dispatch_fleet_worker_task(
            store=store,
            remote_desktop_manager=_DisconnectedDesktopManager(),
            user_id=user_id,
            worker=worker,
            task=task,
            is_remote_session_active=lambda **_: False,
            dispatch_local_task=lambda **kwargs: runtime.dispatch(
                **kwargs,
                bridge_factory=lambda _user_id: bridge,
                publish_fleet_delta=lambda **payload: deltas.append(payload),
            ),
        )
        completed = await _wait_for_report(store, user_id=user_id, task_id=task["task_id"])
        return dispatched, completed

    dispatched, completed = asyncio.run(scenario())

    assert dispatched["status"] == "running"
    assert dispatched["metadata"]["dispatch_transport"] == "local_runtime"
    assert completed["status"] == "completed"
    assert completed["report_id"]
    snapshot = store.get_fleet_snapshot(user_id=user_id)
    report = next(item for item in snapshot["reports"] if item["report_id"] == completed["report_id"])
    assert report["summary"] == "Local task completed."
    assert report["confidence"] == "high"
    assert report["artifacts"] == [{"artifact_id": "artifact-local-1", "session_id": "session-1"}]
    assert bridge.orchestrator.completed == ["session-1"]
    assert any(delta["event_type"] == "fleet_task_report" for delta in deltas)


def test_local_worker_stop_interrupts_runtime_and_completes_stopped_report(tmp_path):
    store, user_id, worker, task = _local_worker_task(tmp_path)
    runtime_session = SimpleNamespace(chat_history=[], should_interrupt=False, interrupt_message="old")
    bridge = _FakeBridge(runtime_session)
    started = asyncio.Event()

    async def run_turn(runtime, **_kwargs):
        started.set()
        deadline = asyncio.get_running_loop().time() + 2.0
        while not runtime.should_interrupt and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
        return {"session_id": "session-1", "assistant_text": "status: stopped\nsummary: Stopped."}

    runtime = LocalFleetRuntime(run_turn=run_turn)

    async def scenario():
        dispatched = await try_dispatch_fleet_worker_task(
            store=store,
            remote_desktop_manager=_DisconnectedDesktopManager(),
            user_id=user_id,
            worker=worker,
            task=task,
            is_remote_session_active=lambda **_: False,
            dispatch_local_task=lambda **kwargs: runtime.dispatch(
                **kwargs,
                bridge_factory=lambda _user_id: bridge,
            ),
        )
        await asyncio.wait_for(started.wait(), timeout=1.0)
        stopped_task = store.update_worker_task_status(
            user_id=user_id,
            task_id=task["task_id"],
            status="stopped",
            metadata={"reason": "test stop"},
        )
        sent = await try_stop_fleet_worker_task(
            store=store,
            remote_desktop_manager=_DisconnectedDesktopManager(),
            user_id=user_id,
            task=stopped_task,
            is_remote_session_active=lambda **_: False,
            stop_local_task=lambda **kwargs: runtime.stop(**kwargs),
        )
        completed = await _wait_for_report(store, user_id=user_id, task_id=task["task_id"])
        return dispatched, sent, completed

    dispatched, sent, completed = asyncio.run(scenario())

    assert dispatched["status"] == "running"
    assert sent is True
    assert runtime_session.should_interrupt is True
    assert runtime_session.interrupt_message is None
    assert completed["status"] == "stopped"
    snapshot = store.get_fleet_snapshot(user_id=user_id)
    report = next(item for item in snapshot["reports"] if item["report_id"] == completed["report_id"])
    assert report["status"] == "stopped"
    assert report["raw"]["transport"] == "local_runtime"
