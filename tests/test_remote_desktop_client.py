import asyncio
import json

import httpx
import pytest

from app_backend import remote_desktop_client


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "http://127.0.0.1:8787/api/app/me")
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError("local runtime request failed", request=request, response=response)


def test_paired_host_retries_startup_failures_without_exiting(monkeypatch):
    attempts: list[str] = []
    statuses: list[dict] = []
    sleeps: list[float] = []

    async def run_once():
        attempts.append("run")
        if len(attempts) == 1:
            raise RuntimeError("local runtime is still starting")
        raise asyncio.CancelledError

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(remote_desktop_client, "_run_remote_desktop_client_until_cancelled", run_once)
    monkeypatch.setattr(remote_desktop_client, "_write_remote_status", lambda **payload: statuses.append(payload))
    monkeypatch.setattr(remote_desktop_client.logger, "exception", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(remote_desktop_client.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(remote_desktop_client.run_remote_desktop_client())

    assert attempts == ["run", "run"]
    assert sleeps == [2.0]
    assert statuses == [
        {
            "state": "degraded",
            "detail": "RuntimeError: local runtime is still starting",
        }
    ]


def test_local_runtime_credentials_refresh_once_after_unauthorized(monkeypatch):
    credentials = remote_desktop_client.LocalRuntimeCredentials(
        api_base_url="http://127.0.0.1:8787",
        access_token="stale-token",
    )
    attempts = []
    monkeypatch.setattr(
        remote_desktop_client,
        "start_runtime_context",
        lambda: {"apiBaseUrl": "http://127.0.0.1:8787", "accessToken": "fresh-token"},
    )

    async def operation(api_base_url, access_token):
        attempts.append((api_base_url, access_token))
        if access_token == "stale-token":
            raise _http_status_error(401)
        return "ok"

    result = asyncio.run(remote_desktop_client._with_local_runtime_credentials(credentials, operation))

    assert result == "ok"
    assert attempts == [
        ("http://127.0.0.1:8787", "stale-token"),
        ("http://127.0.0.1:8787", "fresh-token"),
    ]
    assert credentials.access_token == "fresh-token"


def test_local_runtime_credentials_do_not_retry_non_auth_failure(monkeypatch):
    credentials = remote_desktop_client.LocalRuntimeCredentials(
        api_base_url="http://127.0.0.1:8787",
        access_token="current-token",
    )
    refreshed = []
    monkeypatch.setattr(remote_desktop_client, "start_runtime_context", lambda: refreshed.append(True))

    async def operation(_api_base_url, _access_token):
        raise _http_status_error(503)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(remote_desktop_client._with_local_runtime_credentials(credentials, operation))

    assert refreshed == []


def test_local_runtime_credentials_restart_after_background_runtime_disconnect(monkeypatch):
    credentials = remote_desktop_client.LocalRuntimeCredentials(
        api_base_url="http://127.0.0.1:8787",
        access_token="old-token",
    )
    bootstraps = []
    monkeypatch.setattr(
        remote_desktop_client,
        "start_runtime_context",
        lambda: bootstraps.append(True) or {
            "apiBaseUrl": "http://127.0.0.1:8787",
            "accessToken": "new-token",
        },
    )
    attempts = []

    async def operation(_api_base_url, access_token):
        attempts.append(access_token)
        if len(attempts) == 1:
            request = httpx.Request("GET", "http://127.0.0.1:8787/api/fleet/snapshot")
            raise httpx.ConnectError("runtime stopped", request=request)
        return "restarted"

    result = asyncio.run(remote_desktop_client._with_local_runtime_credentials(credentials, operation))

    assert result == "restarted"
    assert bootstraps == [True]
    assert attempts == ["old-token", "new-token"]


def test_command_result_unwraps_http_json_detail():
    sent = []

    class FakeWebSocket:
        async def send(self, payload):
            sent.append(json.loads(payload))

    request = httpx.Request("GET", "http://127.0.0.1:8787/api/app/screenshot/current")
    response = httpx.Response(
        503,
        request=request,
        json={"detail": "Screenshot capture is unavailable while the Windows desktop is locked."},
    )
    error = httpx.HTTPStatusError("capture failed", request=request, response=response)

    asyncio.run(
        remote_desktop_client._send_command_result(
            FakeWebSocket(),
            asyncio.Lock(),
            command_id="cmd-preview",
            ok=False,
            error=error,
        )
    )

    assert sent[0]["payload"] == {
        "ok": False,
        "status_code": 503,
        "error": "Screenshot capture is unavailable while the Windows desktop is locked.",
        "error_type": "HTTPStatusError",
    }


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


def test_relay_local_chat_command_keeps_local_events_private_on_error(monkeypatch):
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
    assert remote_sent == []


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


@pytest.mark.parametrize("command_name", ["fleet_stop_task", "fleet_redirect_task"])
def test_fleet_task_controls_require_delegation_permission(monkeypatch, tmp_path, command_name):
    monkeypatch.setattr(remote_desktop_client, "runtime_home", lambda: tmp_path)
    monkeypatch.setattr(
        remote_desktop_client,
        "load_connection_policy",
        lambda _home: {
            "permissions": {
                "delegate_manager": False,
                "delegate_workers": False,
            }
        },
    )

    with pytest.raises(PermissionError, match="delegated tasks"):
        asyncio.run(
            remote_desktop_client._handle_command(
                command_name=command_name,
                payload={"task_id": "task-1", "direction": "Try another route"},
                local_api_base_url="http://127.0.0.1:8787",
                local_token="local-token",
                remote_ws=None,
                send_lock=asyncio.Lock(),
            )
        )


def test_provider_availability_sync_is_rejected_by_privacy_boundary():
    with pytest.raises(PermissionError, match="provider"):
        asyncio.run(
            remote_desktop_client._handle_command(
                command_name="provider_availability_sync",
                payload={"records": [{"provider_id": "openai-codex"}]},
                local_api_base_url="http://127.0.0.1:8787",
                local_token="local-token",
                remote_ws=None,
                send_lock=asyncio.Lock(),
            )
        )


@pytest.mark.parametrize(
    "command_name",
    [
        "http_request",
        "create_session",
        "activate_session",
        "delete_session",
        "rename_session",
        "chat_send",
        "pause_run",
        "stop_run",
        "restart_runtime",
        "update_sidebar_state",
    ],
)
def test_direct_runtime_and_state_commands_are_rejected_by_privacy_boundary(command_name):
    with pytest.raises(PermissionError, match="direct runtime"):
        asyncio.run(
            remote_desktop_client._handle_command(
                command_name=command_name,
                payload={},
                local_api_base_url="http://127.0.0.1:8787",
                local_token="local-token",
                remote_ws=None,
                send_lock=asyncio.Lock(),
            )
        )


def test_unknown_paired_computer_command_is_rejected_explicitly():
    with pytest.raises(ValueError, match="Unsupported paired-computer command"):
        asyncio.run(
            remote_desktop_client._handle_command(
                command_name="copy_everything",
                payload={},
                local_api_base_url="http://127.0.0.1:8787",
                local_token="local-token",
                remote_ws=None,
                send_lock=asyncio.Lock(),
            )
        )


def test_host_status_does_not_require_the_local_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(remote_desktop_client, "runtime_home", lambda: tmp_path)
    monkeypatch.setattr(
        "app_backend.fleet_host_control.fleet_host_status",
        lambda: {"host": {"state": "running"}, "runtime": {"ready": False}},
    )

    result = asyncio.run(
        remote_desktop_client._handle_command(
            command_name="fleet_host_status",
            payload={},
            local_api_base_url="",
            local_token="",
            remote_ws=None,
            send_lock=asyncio.Lock(),
        )
    )

    assert result["host"]["state"] == "running"
    assert result["runtime"]["ready"] is False


def test_host_runtime_start_requires_child_owned_permission(monkeypatch, tmp_path):
    monkeypatch.setattr(remote_desktop_client, "runtime_home", lambda: tmp_path)
    monkeypatch.setattr(
        remote_desktop_client,
        "load_connection_policy",
        lambda _home: {"permissions": {"manage_runtime": False}},
    )

    with pytest.raises(PermissionError, match="not allowed"):
        asyncio.run(
            remote_desktop_client._handle_command(
                command_name="fleet_start_runtime",
                payload={},
                local_api_base_url="",
                local_token="",
                remote_ws=None,
                send_lock=asyncio.Lock(),
            )
        )


def test_host_runtime_start_works_without_existing_backend_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(remote_desktop_client, "runtime_home", lambda: tmp_path)
    monkeypatch.setattr(
        remote_desktop_client,
        "load_connection_policy",
        lambda _home: {"permissions": {"manage_runtime": True}},
    )
    monkeypatch.setattr(
        "app_backend.fleet_host_control.start_runtime_from_fleet_host",
        lambda: {"host": {"state": "running"}, "runtime": {"ready": True}},
    )

    result = asyncio.run(
        remote_desktop_client._handle_command(
            command_name="fleet_start_runtime",
            payload={},
            local_api_base_url="",
            local_token="",
            remote_ws=None,
            send_lock=asyncio.Lock(),
        )
    )

    assert result["runtime"]["ready"] is True


def test_host_update_requires_child_owned_permission(monkeypatch, tmp_path):
    monkeypatch.setattr(remote_desktop_client, "runtime_home", lambda: tmp_path)
    monkeypatch.setattr(
        remote_desktop_client,
        "load_connection_policy",
        lambda _home: {"permissions": {"manage_updates": False}},
    )

    with pytest.raises(PermissionError, match="not allowed"):
        asyncio.run(
            remote_desktop_client._handle_command(
                command_name="fleet_update_check",
                payload={},
                local_api_base_url="",
                local_token="",
                remote_ws=None,
                send_lock=asyncio.Lock(),
            )
        )


def test_host_update_start_passes_only_the_confirmed_commit(monkeypatch, tmp_path):
    target = "a" * 40
    monkeypatch.setattr(remote_desktop_client, "runtime_home", lambda: tmp_path)
    monkeypatch.setattr(
        remote_desktop_client,
        "load_connection_policy",
        lambda _home: {"permissions": {"manage_updates": True}},
    )
    received = []
    monkeypatch.setattr(
        "app_backend.fleet_host_control.start_update_from_fleet_host",
        lambda *, expected_commit: received.append(expected_commit) or {"state": "queued", "active": True},
    )

    result = asyncio.run(
        remote_desktop_client._handle_command(
            command_name="fleet_update_start",
            payload={"expected_commit": target, "command": "ignored"},
            local_api_base_url="",
            local_token="",
            remote_ws=None,
            send_lock=asyncio.Lock(),
        )
    )

    assert result == {"state": "queued", "active": True}
    assert received == [target]


def test_screen_preview_is_bounded_and_view_only(monkeypatch):
    monkeypatch.setattr(
        "app_backend.capture_runtime.capture_screen_snapshot",
        lambda **kwargs: {
            "mime_type": "image/jpeg",
            "image_base64": "cHJldmlldw==",
            "width": kwargs["max_width"],
            "height": 720,
            "backend": "test",
            "captured_at": 1.0,
        },
    )
    result = asyncio.run(
        remote_desktop_client._handle_command(
            command_name="fleet_worker_preview",
            payload={
                "preview_id": "fpv_test",
                "worker_id": "wrk_preview",
                "view_only": True,
                "mode": "screen_summary_or_low_rate_preview",
            },
            local_api_base_url="http://127.0.0.1:8787",
            local_token="local-token",
            remote_ws=None,
            send_lock=asyncio.Lock(),
        )
    )

    assert result["status"] == "captured"
    assert result["capture"]["width"] == 1280
    assert result["capture"]["image_base64"] == "cHJldmlldw=="


def test_screen_preview_rejects_non_view_only_requests():
    with pytest.raises(PermissionError, match="view-only"):
        asyncio.run(
            remote_desktop_client._handle_command(
                command_name="fleet_worker_preview",
                payload={"preview_id": "fpv_test", "view_only": False},
                local_api_base_url="http://127.0.0.1:8787",
                local_token="local-token",
                remote_ws=None,
                send_lock=asyncio.Lock(),
            )
        )


def test_screen_preview_returns_structured_unavailable_state(monkeypatch):
    from app_backend.windows_capture_session import DesktopCaptureUnavailableError

    def unavailable(**_kwargs):
        raise DesktopCaptureUnavailableError(
            "Windows desktop is disconnected.",
            code="display_disconnected",
            state="disconnected",
            recovery="Reconnect a display.",
        )

    monkeypatch.setattr("app_backend.capture_runtime.capture_screen_snapshot", unavailable)
    result = asyncio.run(
        remote_desktop_client._handle_command(
            command_name="fleet_worker_preview",
            payload={
                "preview_id": "fpv_test",
                "view_only": True,
                "mode": "screen_summary_or_low_rate_preview",
            },
            local_api_base_url="http://127.0.0.1:8787",
            local_token="local-token",
            remote_ws=None,
            send_lock=asyncio.Lock(),
        )
    )

    assert result == {
        "status": "unavailable",
        "detail": "Windows desktop is disconnected.",
        "capture_capability": {
            "available": False,
            "code": "display_disconnected",
            "state": "disconnected",
            "recovery": "Reconnect a display.",
            "retryable": True,
        },
    }


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
