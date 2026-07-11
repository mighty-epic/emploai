import asyncio
import json

import pytest

from app_backend import remote_desktop_client


def test_terminal_local_chat_event_error_marks_errors_and_known_warnings_terminal():
    assert remote_desktop_client._terminal_local_chat_event_error(
        {"type": "error", "payload": {"message": "Provider auth failed"}}
    ) == "Provider auth failed"
    assert remote_desktop_client._terminal_local_chat_event_error(
        {"type": "warning", "payload": {"message": "Session is already processing another message"}}
    ) == "Session is already processing another message"
    assert remote_desktop_client._terminal_local_chat_event_error(
        {"type": "warning", "payload": {"message": "Transient note"}}
    ) is None


def test_relay_local_chat_command_fails_fast_after_forwarding_local_error(monkeypatch):
    local_sent: list[dict] = []
    remote_sent: list[dict] = []

    class FakeLocalWebSocket:
        async def send(self, payload):
            local_sent.append(json.loads(payload))

        async def recv(self):
            return json.dumps(
                {
                    "type": "error",
                    "session_id": "sess-provider",
                    "payload": {
                        "message": "Provider authentication, quota, or permission error.",
                        "code": "provider_auth_or_quota_error",
                    },
                }
            )

    class FakeConnect:
        async def __aenter__(self):
            return FakeLocalWebSocket()

        async def __aexit__(self, *_args):
            return False

    class FakeRemoteWebSocket:
        async def send(self, payload):
            remote_sent.append(json.loads(payload))

    monkeypatch.setattr(remote_desktop_client, "websocket_connect", lambda *_args, **_kwargs: FakeConnect())

    async def scenario():
        with pytest.raises(RuntimeError, match="Provider authentication"):
            await remote_desktop_client._relay_local_chat_command(
                local_api_base_url="http://127.0.0.1:8787",
                local_token="local-token",
                session_id="sess-provider",
                text="hello",
                source_format="app_text",
                interrupt_policy="none",
                source_client_id="mobile-client",
                remote_ws=FakeRemoteWebSocket(),
                send_lock=asyncio.Lock(),
            )

    asyncio.run(scenario())

    assert local_sent == [
        {
            "text": "hello",
            "session_id": "sess-provider",
            "source_format": "app_text",
            "interrupt_policy": "none",
            "source_client_id": "mobile-client",
        }
    ]
    assert remote_sent == [
        {
            "type": "sync_event",
            "payload": {
                "type": "error",
                "session_id": "sess-provider",
                "payload": {
                    "message": "Provider authentication, quota, or permission error.",
                    "code": "provider_auth_or_quota_error",
                },
            },
        }
    ]


def test_fleet_stop_task_records_pending_stop_without_active_session():
    remote_desktop_client.FLEET_ACTIVE_TASK_SESSIONS.clear()
    remote_desktop_client.FLEET_STOP_REQUESTED_TASKS.clear()

    async def scenario():
        return await remote_desktop_client._handle_command(
            command_name="fleet_stop_task",
            payload={"task_id": "task-early-stop"},
            local_api_base_url="http://127.0.0.1:8787",
            local_token="local-token",
            remote_ws=None,
            send_lock=asyncio.Lock(),
        )

    try:
        result = asyncio.run(scenario())
        assert result == {
            "stopped": False,
            "pending": True,
            "task_id": "task-early-stop",
            "detail": "Stop recorded; Fleet task is not active on this desktop yet.",
        }
        assert "task-early-stop" in remote_desktop_client.FLEET_STOP_REQUESTED_TASKS
    finally:
        remote_desktop_client.FLEET_ACTIVE_TASK_SESSIONS.clear()
        remote_desktop_client.FLEET_STOP_REQUESTED_TASKS.clear()


def test_fleet_worker_preview_command_returns_screen_capture(monkeypatch):
    sent: list[dict] = []

    capture = {
        "mime_type": "image/jpeg",
        "image_base64": "d29ya2VyLXByZXZpZXc=",
        "width": 1280,
        "height": 720,
        "backend": "test",
        "captured_at": 1.0,
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return capture

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(remote_desktop_client.httpx, "AsyncClient", FakeAsyncClient)

    class FakeRemoteWebSocket:
        async def send(self, payload):
            sent.append(json.loads(payload))

    async def scenario():
        return await remote_desktop_client._handle_command(
            command_name="fleet_worker_preview",
            payload={
                "preview_id": "fpv_test",
                "worker_id": "wrk_preview",
                "display_name": "Preview Worker",
            },
            local_api_base_url="http://127.0.0.1:8787",
            local_token="local-token",
            remote_ws=FakeRemoteWebSocket(),
            send_lock=asyncio.Lock(),
        )

    result = asyncio.run(scenario())

    assert result["preview_id"] == "fpv_test"
    assert result["worker_id"] == "wrk_preview"
    assert result["status"] == "captured"
    assert result["capture"] == capture
    assert sent == [
        {
            "type": "status",
            "payload": {
                "message": "Preview requested for Preview Worker.",
                "fleet_preview": {
                    "preview_id": "fpv_test",
                    "worker_id": "wrk_preview",
                    "status": "captured",
                    "detail": result["detail"],
                    "view_only": True,
                },
            },
        }
    ]


def test_fleet_run_task_honors_pending_stop_before_local_chat(monkeypatch):
    remote_desktop_client.FLEET_ACTIVE_TASK_SESSIONS.clear()
    remote_desktop_client.FLEET_STOP_REQUESTED_TASKS.clear()
    remote_desktop_client.FLEET_STOP_REQUESTED_TASKS.add("task-early-stop")
    remote_sent: list[dict] = []

    class FakeRemoteWebSocket:
        async def send(self, payload):
            remote_sent.append(json.loads(payload))

    async def fail_if_chat_relay_runs(**_kwargs):
        raise AssertionError("pending Fleet stop should prevent local chat relay")

    monkeypatch.setattr(remote_desktop_client, "_relay_local_chat_command", fail_if_chat_relay_runs)

    async def scenario():
        return await remote_desktop_client._handle_command(
            command_name="fleet_run_task",
            payload={
                "task_id": "task-early-stop",
                "worker_id": "worker-1",
                "worker_name": "Worker One",
                "prompt": "Do the task",
                "target_session_id": "sess-worker-1",
            },
            local_api_base_url="http://127.0.0.1:8787",
            local_token="local-token",
            remote_ws=FakeRemoteWebSocket(),
            send_lock=asyncio.Lock(),
        )

    try:
        result = asyncio.run(scenario())
        assert result == {
            "task_id": "task-early-stop",
            "worker_id": "worker-1",
            "session_id": "sess-worker-1",
            "stopped": True,
            "summary": "Task stopped by manager before the worker turn started.",
        }
        assert [event["type"] for event in remote_sent] == ["fleet_task_status", "fleet_task_report"]
        report = remote_sent[1]["payload"]
        assert report["status"] == "stopped"
        assert report["summary"] == "Task stopped by manager before the worker turn started."
        assert report["blockers"] == ["Stopped by manager"]
        assert report["raw"] == {
            "session_id": "sess-worker-1",
            "stopped": True,
            "stopped_before_start": True,
        }
        assert "task-early-stop" not in remote_desktop_client.FLEET_ACTIVE_TASK_SESSIONS
        assert "task-early-stop" not in remote_desktop_client.FLEET_STOP_REQUESTED_TASKS
    finally:
        remote_desktop_client.FLEET_ACTIVE_TASK_SESSIONS.clear()
        remote_desktop_client.FLEET_STOP_REQUESTED_TASKS.clear()
