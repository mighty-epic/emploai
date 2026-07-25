from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app_backend import remote_desktop_client
from app_backend.remote_control_store import RemoteControlPlaneStore
from shared.fleet_connection import write_fleet_connection
from shared.fleet_connection_policy import (
    decide_permission_request,
    load_connection_policy,
    record_permission_request,
    set_connection_permissions,
)


ROOT = Path(__file__).resolve().parents[1]


def _write_connection(home: Path) -> None:
    write_fleet_connection(
        home=home,
        payload={
            "apiBaseUrl": "http://[200::1]:8787",
            "managerUrl": "http://[200::1]:8787",
            "sessionToken": "paired-session",
            "desktop": {"desktop_id": "desktop-remote", "display_name": "Remote PC"},
            "transport": {"kind": "yggdrasil"},
        },
    )


def test_paired_computer_owns_permissions_and_manager_request_needs_decision(tmp_path: Path):
    _write_connection(tmp_path)

    initial = load_connection_policy(tmp_path)
    assert initial["permissions"] == {
        "delegate_manager": True,
        "delegate_workers": True,
        "create_workers": False,
        "configure_manager_tools": False,
        "manage_runtime": True,
        "manage_updates": True,
    }

    local = set_connection_permissions(
        tmp_path,
        {"delegate_manager": True, "delegate_workers": False, "create_workers": False, "manage_runtime": True, "manage_updates": True},
    )
    assert local["permissions"]["delegate_workers"] is False

    pending = record_permission_request(
        tmp_path,
        request_id="request-1",
        requested={"delegate_manager": True, "delegate_workers": True, "create_workers": True, "manage_runtime": True, "manage_updates": True},
        reason="Need a build worker",
    )
    assert pending["pendingRequest"]["status"] == "pending"
    assert pending["permissions"]["create_workers"] is False

    denied = decide_permission_request(tmp_path, request_id="request-1", approve=False)
    assert denied["pendingRequest"] is None
    assert denied["permissions"]["create_workers"] is False
    assert denied["lastDecision"]["status"] == "denied"


def test_manager_store_tracks_computers_delegations_and_permission_state_without_remote_identity(tmp_path: Path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    manager = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager",
        device_platform="desktop",
        device_key="manager-key",
    )
    enrollment = store.create_worker_enrollment(
        user_id=0,
        desktop_id=manager["desktop_id"],
        display_name="Remote PC",
        metadata={"transport": "yggdrasil", "source": "standalone_yggdrasil_pairing"},
    )
    paired = store.complete_worker_enrollment(
        enrollment_token=enrollment["enrollment_token"],
        device_name="Remote PC",
        device_platform="windows",
        device_key="remote-key",
    )
    desktop_id = paired["desktop"]["desktop_id"]
    awaiting_handshake = store.connection_permission_state(user_id=0, desktop_id=desktop_id)

    state = store.record_connection_permission_state(
        user_id=0,
        desktop_id=desktop_id,
        policy={
            "permissions": {"delegate_manager": True, "delegate_workers": False, "create_workers": False},
            "pendingRequest": None,
        },
    )
    delegation = store.create_computer_delegation(
        user_id=0,
        desktop_id=desktop_id,
        prompt="Inspect the service and report only the outcome.",
        target_kind="manager",
    )
    completed = store.update_computer_delegation(
        user_id=0,
        delegation_id=delegation["delegation_id"],
        status="completed",
        report={"summary": "Service is healthy."},
    )
    snapshot = store.get_fleet_snapshot(user_id=0, desktop_id=manager["desktop_id"])

    assert paired["worker"] is None
    assert all(item.get("desktop_id") != desktop_id for item in snapshot["identities"])
    assert awaiting_handshake["source"] == "pairing_default"
    assert state["source"] == "paired_desktop"
    assert state["permissions"]["delegate_workers"] is False
    assert completed["report"]["summary"] == "Service is healthy."
    assert snapshot["delegations"][0]["delegation_id"] == delegation["delegation_id"]


def test_connected_computer_cannot_update_another_computers_delegation(tmp_path: Path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    manager = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager",
        device_platform="desktop",
        device_key="manager-key",
    )

    def pair(device_key: str):
        enrollment = store.create_worker_enrollment(
            user_id=0,
            desktop_id=manager["desktop_id"],
            display_name=device_key,
            metadata={"transport": "yggdrasil", "source": "standalone_yggdrasil_pairing"},
        )
        return store.complete_worker_enrollment(
            enrollment_token=enrollment["enrollment_token"],
            device_name=device_key,
            device_platform="windows",
            device_key=device_key,
        )["desktop"]["desktop_id"]

    first_desktop_id = pair("First PC")
    second_desktop_id = pair("Second PC")
    delegation = store.create_computer_delegation(
        user_id=0,
        desktop_id=first_desktop_id,
        prompt="Inspect the first computer.",
    )

    with pytest.raises(KeyError, match="Unknown computer delegation"):
        store.update_computer_delegation(
            user_id=0,
            desktop_id=second_desktop_id,
            delegation_id=delegation["delegation_id"],
            status="completed",
            report={"summary": "forged"},
        )

    unchanged = store.get_computer_delegation(user_id=0, delegation_id=delegation["delegation_id"])
    assert unchanged["status"] == "queued"
    assert unchanged["report"] == {}


def test_legacy_yggdrasil_auto_worker_is_hidden_but_paired_computer_remains_visible(tmp_path: Path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    manager = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager",
        device_platform="desktop",
        device_key="manager-key",
    )
    enrollment = store.create_worker_enrollment(
        user_id=0,
        desktop_id=manager["desktop_id"],
        display_name="Legacy PC",
        metadata={"source": "legacy-test"},
    )
    paired = store.complete_worker_enrollment(
        enrollment_token=enrollment["enrollment_token"],
        device_name="Legacy PC",
        device_platform="windows",
        device_key="legacy-key",
    )
    worker_id = paired["worker"]["worker_id"]
    desktop_id = paired["desktop"]["desktop_id"]
    legacy_metadata = {
        "transport": "yggdrasil",
        "source": "standalone_yggdrasil_pairing",
        "machine_name": "Legacy PC",
    }
    with store._lock:
        store._conn.execute(
            "UPDATE fleet_workers SET metadata = ? WHERE worker_id = ?",
            (json.dumps(legacy_metadata), worker_id),
        )
        store._conn.commit()

    snapshot = store.get_fleet_snapshot(user_id=0, desktop_id=manager["desktop_id"])

    assert any(item["desktop_id"] == desktop_id for item in snapshot["desktops"])
    assert all(item["worker_id"] != worker_id for item in snapshot["workers"])
    assert all(item.get("worker_id") != worker_id for item in snapshot["identities"])
    with pytest.raises(KeyError, match="Unknown worker"):
        store.get_worker(user_id=0, worker_id=worker_id)


def test_connection_state_loop_sends_only_permission_state_and_heartbeat(monkeypatch):
    sent: list[dict] = []

    class FakeWebSocket:
        async def send(self, payload):
            sent.append(json.loads(payload))

    monkeypatch.setattr(remote_desktop_client, "runtime_home", lambda: None)

    async def stop_after_first_cycle(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(remote_desktop_client.asyncio, "sleep", stop_after_first_cycle)

    async def scenario():
        with pytest.raises(asyncio.CancelledError):
            await remote_desktop_client._connection_state_loop(
                FakeWebSocket(),
                send_lock=asyncio.Lock(),
                desktop_id="desktop-remote",
                desktop_name="Remote PC",
            )

    asyncio.run(scenario())

    assert [item["type"] for item in sent] == ["fleet_permission_state", "heartbeat"]
    serialized = json.dumps(sent)
    for forbidden in ("sessions", "session_details", "jobs", "sidebar_state", "provider_availability", "state_snapshot"):
        assert forbidden not in serialized


def test_delegate_command_resolves_agent_locally_and_returns_report_only(monkeypatch):
    sent: list[dict] = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"session": {"id": "private-local-session"}}

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    class FakeRemoteWebSocket:
        async def send(self, payload):
            sent.append(json.loads(payload))

    async def fake_request_json(_client, **_kwargs):
        return {
            "identities": [
                {
                    "identity_id": "local-manager",
                    "role": "manager",
                    "display_name": "Manager",
                    "worker_id": None,
                }
            ]
        }

    async def fake_chat(**_kwargs):
        return {"assistant_text": "Remote service is healthy.", "failure": None}

    monkeypatch.setattr(remote_desktop_client.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(remote_desktop_client, "_request_json", fake_request_json)
    monkeypatch.setattr(remote_desktop_client, "_relay_local_chat_command", fake_chat)
    monkeypatch.setattr(remote_desktop_client, "runtime_home", lambda: None)

    report = asyncio.run(
        remote_desktop_client._handle_command(
            command_name="fleet_delegate",
            payload={
                "delegation_id": "delegation-1",
                "prompt": "Check the remote service.",
                "target_kind": "manager",
            },
            local_api_base_url="http://127.0.0.1:8787",
            local_token="local-token",
            remote_ws=FakeRemoteWebSocket(),
            send_lock=asyncio.Lock(),
        )
    )

    assert report["summary"] == "Remote service is healthy."
    assert [item["type"] for item in sent] == ["fleet_delegation_status", "fleet_delegation_report"]
    assert "private-local-session" not in json.dumps(sent)


def test_remote_worker_creation_is_local_only_and_never_returns_an_identity(monkeypatch, tmp_path: Path):
    _write_connection(tmp_path)
    set_connection_permissions(
        tmp_path,
        {"delegate_manager": True, "delegate_workers": True, "create_workers": True},
    )

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"worker_id": "private-worker-id", "display_name": "Build worker"}

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(remote_desktop_client.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(remote_desktop_client, "runtime_home", lambda: tmp_path)

    result = asyncio.run(
        remote_desktop_client._handle_command(
            command_name="fleet_create_local_worker",
            payload={"display_name": "Build worker"},
            local_api_base_url="http://127.0.0.1:8787",
            local_token="local-token",
            remote_ws=None,
            send_lock=asyncio.Lock(),
        )
    )

    assert result == {
        "created": True,
        "display_name": "Build worker",
        "detail": "The worker was created locally on the paired computer.",
    }
    assert "private-worker-id" not in json.dumps(result)


def test_remote_worker_delete_removes_a_default_worker(
    monkeypatch,
    tmp_path: Path,
):
    _write_connection(tmp_path)
    set_connection_permissions(
        tmp_path,
        {"delegate_manager": True, "delegate_workers": True, "create_workers": True},
    )
    requests = []
    deleted = []

    async def fake_request_json(
        _client,
        *,
        method,
        url,
        token,
        json_body=None,
        company_id=None,
    ):
        requests.append((method, url, token, json_body, company_id))
        if url.endswith("/api/fleet/snapshot"):
            return {
                "identities": [
                    {
                        "identity_id": "worker-default",
                        "worker_id": "wrk-default",
                        "display_name": "Default Worker",
                        "role": "worker",
                        "protected": False,
                        "is_default": True,
                    }
                ]
            }
        if url.endswith("/api/app/confirmations"):
            return {"confirmation_id": "confirmation-child"}
        return {"confirmation_id": "confirmation-child"}

    class FakeResponse:
        def raise_for_status(self):
            return None

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def delete(self, url, **kwargs):
            deleted.append((url, kwargs))
            return FakeResponse()

    monkeypatch.setattr(remote_desktop_client, "_request_json", fake_request_json)
    monkeypatch.setattr(remote_desktop_client.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(remote_desktop_client, "runtime_home", lambda: tmp_path)

    result = asyncio.run(
        remote_desktop_client._handle_command(
            command_name="fleet_delete_local_worker",
            payload={
                "identity_id": "worker-default",
                "company_id": "company-one",
                "parent_confirmation_id": "confirmation-parent",
            },
            local_api_base_url="http://127.0.0.1:8787",
            local_token="local-token",
            remote_ws=None,
            send_lock=asyncio.Lock(),
        )
    )

    assert result["deleted"] is True
    assert result["display_name"] == "Default Worker"
    assert requests[0][-1] == "company-one"
    assert deleted[0][0].endswith("/api/fleet/workers/wrk-default")
    assert (
        deleted[0][1]["headers"]["X-EmploAI-Confirmation-Id"]
        == "confirmation-child"
    )


def test_fleet_ui_explains_multi_computer_private_connection_contract():
    connection_panel = (ROOT / "desktop_app/renderer_client/src/desktop/DesktopFleetConnectionPanel.tsx").read_text(encoding="utf-8")
    machines_panel = (ROOT / "desktop_app/renderer_client/src/desktop/DesktopFleetMachinesPanel.tsx").read_text(encoding="utf-8")
    relay = (ROOT / "app_backend/remote_desktop_client.py").read_text(encoding="utf-8")
    routes = (ROOT / "app_backend/app_server_routes_fleet.py").read_text(encoding="utf-8")

    assert "CONNECT TWO OR MORE COMPUTERS" in connection_panel
    assert "Repeat from the same manager" in connection_panel
    assert "chats, agents, settings, files, and provider state stay local" in connection_panel
    assert "No remote identities are copied" in machines_panel
    assert "The worker is created and stored there only" in machines_panel
    assert "fleet_remote_worker_delete" in machines_panel
    assert "PROTECTED" in machines_panel
    assert "permissionState?.source === 'paired_desktop'" in machines_panel
    assert "UPDATE REQUIRED" in machines_panel
    assert "connected with an older Fleet protocol" in routes
    assert '"type": "state_snapshot"' not in relay
    assert '"type": "sync_event"' not in relay
