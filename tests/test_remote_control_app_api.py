import base64
import asyncio
import json
import threading
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from mobile_app.backend import app_server
from mobile_app.backend.auth_store import AppAuthStore
from mobile_app.backend.remote_control_runtime import RemoteDesktopConnectionManager
from mobile_app.backend.remote_control_store import REMOTE_CONTROL_DB_FILENAME, RemoteControlPlaneStore


def _paired_remote_session(tmp_path):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    store = app_server._remote_control_store

    user = store.register_user(email="remote@example.com", password="CorrectHorse!2026", display_name="Remote User")
    desktop_login = store.login(
        email="remote@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Desk",
        device_platform="desktop-electron",
        device_key="desk-key",
    )
    mobile_login = store.login(
        email="remote@example.com",
        password="CorrectHorse!2026",
        actor_kind="mobile",
        device_name="Phone",
        device_platform="android",
        device_key="phone-key",
    )
    pairing = store.create_pairing(
        user_id=user["user_id"],
        desktop_id=desktop_login["desktop"]["desktop_id"],
    )
    store.complete_pairing(
        user_id=user["user_id"],
        pairing_token=pairing["pairing_token"],
        mobile_id=mobile_login["mobile"]["mobile_id"],
    )
    return store, user, desktop_login, mobile_login


def test_legacy_app_pairing_secret_bootstrap_issues_device_token(tmp_path, monkeypatch):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    monkeypatch.setenv(app_server.PAIRING_SECRET_ENV, "pair-secret")

    client = TestClient(app_server.create_app())
    started = client.post(
        "/api/app/pair/start",
        headers={"X-App-Pair-Secret": "pair-secret"},
        json={"device_name": "Test Phone"},
    )
    completed = client.post(
        "/api/app/pair/complete",
        json={
            "pairing_token": started.json()["pairing_token"],
            "device_name": "Test Phone",
            "device_platform": "ios",
        },
    )
    me = client.get("/api/app/me", headers={"Authorization": f"Bearer {completed.json()['access_token']}"})
    devices = client.get("/api/app/devices", headers={"Authorization": f"Bearer {completed.json()['access_token']}"})
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()

    assert started.status_code == 200
    assert started.json()["pairing_token"]
    assert completed.status_code == 200
    assert completed.json()["device_id"]
    assert me.status_code == 200
    assert me.json()["device_name"] == "Test Phone"
    assert me.json()["device_platform"] == "ios"
    assert devices.status_code == 200
    assert devices.json()[0]["device_id"] == completed.json()["device_id"]
    assert devices.json()[0]["device_name"] == "Test Phone"


def test_legacy_app_devices_reject_direct_remote_session_without_local_store(tmp_path, monkeypatch):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)

    def fail_list_devices(*, user_id):
        raise AssertionError("remote sessions must not inspect local trusted devices on the cloud backend")

    monkeypatch.setattr(app_server._auth_store, "list_devices", fail_list_devices)

    client = TestClient(app_server.create_app())
    response = client.get("/api/app/devices", headers={"Authorization": f"Bearer {desktop_login['session_token']}"})

    assert response.status_code == 409
    assert "local app backend" in response.json()["detail"]


def test_legacy_app_device_revoke_is_rate_limited(tmp_path, monkeypatch):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    monkeypatch.setenv(app_server.PAIRING_SECRET_ENV, "pair-secret")

    client = TestClient(app_server.create_app())
    started = client.post(
        "/api/app/pair/start",
        headers={"X-App-Pair-Secret": "pair-secret"},
        json={"device_name": "Test Phone"},
    )
    completed = client.post(
        "/api/app/pair/complete",
        json={
            "pairing_token": started.json()["pairing_token"],
            "device_name": "Test Phone",
            "device_platform": "ios",
        },
    )
    headers = {"Authorization": f"Bearer {completed.json()['access_token']}"}

    statuses = [
        client.post("/api/app/devices/not-a-device/revoke", headers=headers).status_code
        for _ in range(app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS)
    ]
    limited = client.post("/api/app/devices/not-a-device/revoke", headers=headers)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()

    assert statuses == [404] * app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS
    assert limited.status_code == 429


def test_legacy_app_pair_start_rate_limits_invalid_secret_attempts(tmp_path, monkeypatch):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    monkeypatch.setenv(app_server.PAIRING_SECRET_ENV, "pair-secret")

    client = TestClient(app_server.create_app())
    statuses = [
        client.post(
            "/api/app/pair/start",
            headers={"X-App-Pair-Secret": "wrong-secret"},
            json={"device_name": "Test Phone"},
        ).status_code
        for _ in range(app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS)
    ]
    limited = client.post(
        "/api/app/pair/start",
        headers={"X-App-Pair-Secret": "wrong-secret"},
        json={"device_name": "Test Phone"},
    )
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()

    assert statuses == [401] * app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS
    assert limited.status_code == 429


def test_legacy_app_pair_complete_rate_limits_malformed_tokens(tmp_path):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()

    client = TestClient(app_server.create_app())
    payload = {
        "pairing_token": "not-a-valid-legacy-pairing-token",
        "device_name": "Test Phone",
        "device_platform": "ios",
    }
    statuses = [
        client.post("/api/app/pair/complete", json=payload).status_code
        for _ in range(app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS)
    ]
    limited = client.post("/api/app/pair/complete", json=payload)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()

    assert statuses == [400] * app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS
    assert limited.status_code == 429


def test_fleet_api_snapshot_local_worker_task_report_and_binding(tmp_path):
    store, user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}

    snapshot = client.get("/api/fleet/snapshot", headers=headers)
    assert snapshot.status_code == 200
    assert snapshot.json()["manager"]["role"] == "manager"

    worker_response = client.post("/api/fleet/workers/local", headers=headers, json={})
    assert worker_response.status_code == 200
    worker = worker_response.json()
    assert worker["display_name"] == "Worker-001"

    task_response = client.post(
        f"/api/fleet/workers/{worker['worker_id']}/tasks",
        headers=headers,
        json={"prompt": "Collect notes", "source": "manager"},
    )
    assert task_response.status_code == 200
    task = task_response.json()
    assert task["status"] == "queued"

    running_response = client.put(
        f"/api/fleet/tasks/{task['task_id']}/status",
        headers=headers,
        json={"status": "running"},
    )
    assert running_response.status_code == 200
    assert running_response.json()["status"] == "running"

    report_response = client.post(
        f"/api/fleet/tasks/{task['task_id']}/report",
        headers=headers,
        json={
            "status": "completed",
            "summary": "Collected notes.",
            "evidence": [{"kind": "artifact", "id": "art_1"}],
            "confidence": "high",
        },
    )
    assert report_response.status_code == 200
    assert report_response.json()["summary"] == "Collected notes."
    duplicate_report_response = client.post(
        f"/api/fleet/tasks/{task['task_id']}/report",
        headers=headers,
        json={
            "status": "completed",
            "summary": "Collected notes again.",
            "evidence": [{"kind": "artifact", "id": "art_2"}],
            "confidence": "high",
        },
    )
    assert duplicate_report_response.status_code == 409
    assert "already has a completed report" in duplicate_report_response.json()["detail"]

    binding_response = client.put(
        "/api/fleet/workspace-bindings",
        headers=headers,
        json={
            "workspace_id": "workspace-notes",
            "machine_id": desktop_login["desktop"]["desktop_id"],
            "local_path": "C:/Work/Notes",
            "label": "Notes",
        },
    )
    assert binding_response.status_code == 200

    snapshot = client.get("/api/fleet/snapshot", headers=headers).json()
    assert len(snapshot["workers"]) == 1
    assert snapshot["active_identity"]["role"] == "manager"
    assert snapshot["identities"]
    assert len(snapshot["reports"]) == 1
    assert snapshot["workspace_bindings"][0]["workspace_id"] == "workspace-notes"


def test_fleet_api_mobile_snapshot_uses_paired_desktop_manager_scope(tmp_path):
    store, user, old_desktop_login, mobile_login = _paired_remote_session(tmp_path)
    current_desktop_login = store.login(
        email=user["email"],
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Current Desk",
        device_platform="desktop-electron",
        device_key="current-desk-key",
    )
    pairing = store.create_pairing(
        user_id=user["user_id"],
        desktop_id=current_desktop_login["desktop"]["desktop_id"],
    )
    store.complete_pairing(
        user_id=user["user_id"],
        pairing_token=pairing["pairing_token"],
        mobile_id=mobile_login["mobile"]["mobile_id"],
    )

    client = TestClient(app_server.create_app())
    response = client.get("/api/fleet/snapshot", headers={"Authorization": f"Bearer {mobile_login['session_token']}"})
    identities_response = client.get("/api/fleet/identities", headers={"Authorization": f"Bearer {mobile_login['session_token']}"})

    assert response.status_code == 200
    assert identities_response.status_code == 200
    managers = [item for item in response.json()["identities"] if item["role"] == "manager"]
    identity_managers = [item for item in identities_response.json() if item["role"] == "manager"]
    assert len(managers) == 1
    assert len(identity_managers) == 1
    assert managers[0]["desktop_id"] == current_desktop_login["desktop"]["desktop_id"]
    assert identity_managers[0]["desktop_id"] == current_desktop_login["desktop"]["desktop_id"]
    assert managers[0]["desktop_id"] != old_desktop_login["desktop"]["desktop_id"]
    assert response.json()["manager"]["desktop_id"] == current_desktop_login["desktop"]["desktop_id"]


def test_fleet_api_requires_review_for_completed_report_without_evidence(tmp_path):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}

    worker = client.post("/api/fleet/workers/local", headers=headers, json={}).json()
    first_task = client.post(
        f"/api/fleet/workers/{worker['worker_id']}/tasks",
        headers=headers,
        json={"prompt": "Verify the build", "source": "manager"},
    ).json()
    second_task = client.post(
        f"/api/fleet/workers/{worker['worker_id']}/tasks",
        headers=headers,
        json={"prompt": "Ship after verification", "source": "manager"},
    ).json()
    client.put(
        f"/api/fleet/tasks/{first_task['task_id']}/status",
        headers=headers,
        json={"status": "running"},
    )

    report_response = client.post(
        f"/api/fleet/tasks/{first_task['task_id']}/report",
        headers=headers,
        json={
            "status": "completed",
            "summary": "Build appears verified.",
            "evidence": [],
            "artifacts": [],
            "confidence": "high",
        },
    )
    continue_response = client.post(
        f"/api/fleet/workers/{worker['worker_id']}/queue/continue",
        headers=headers,
        json={"source": "manager"},
    )

    assert report_response.status_code == 200
    assert report_response.json()["status"] == "needs_review"
    assert report_response.json()["confidence"] == "medium"
    assert report_response.json()["blockers"][0]["kind"] == "report_validation"
    assert continue_response.status_code == 409
    assert "active task" in continue_response.json()["detail"].lower()
    snapshot = client.get("/api/fleet/snapshot", headers=headers).json()
    worker_snapshot = next(item for item in snapshot["workers"] if item["worker_id"] == worker["worker_id"])
    assert worker_snapshot["status"] == "needs_review"
    assert worker_snapshot["active_task_id"] == first_task["task_id"]
    queued = next(item for item in snapshot["tasks"] if item["task_id"] == second_task["task_id"])
    assert queued["status"] == "queued"


def test_fleet_task_workspace_write_blocks_without_active_binding(tmp_path):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}

    worker_response = client.post("/api/fleet/workers/local", headers=headers, json={})
    assert worker_response.status_code == 200
    worker = worker_response.json()

    task_response = client.post(
        f"/api/fleet/workers/{worker['worker_id']}/tasks",
        headers=headers,
        json={
            "prompt": "Create a file in the project workspace",
            "source": "manager",
            "workspace_id": "workspace-missing",
            "requires_workspace_write": True,
        },
    )
    assert task_response.status_code == 200
    task = task_response.json()
    assert task["status"] == "blocked"
    blocker = task["metadata"]["workspace_binding_blocker"]
    assert blocker["reason"] == "workspace_binding_missing_or_inactive"
    assert blocker["workspace_id"] == "workspace-missing"


def test_fleet_group_workspace_write_blocks_every_worker_without_active_binding(tmp_path):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}

    first_worker = client.post(
        "/api/fleet/workers/local",
        headers=headers,
        json={"display_name": "Writer A"},
    ).json()
    second_worker = client.post(
        "/api/fleet/workers/local",
        headers=headers,
        json={"display_name": "Writer B"},
    ).json()
    snapshot = client.get("/api/fleet/snapshot", headers=headers)
    assert snapshot.status_code == 200
    identities_by_worker = {
        item.get("worker_id"): item
        for item in snapshot.json()["identities"]
        if item.get("worker_id")
    }
    first_identity = identities_by_worker[first_worker["worker_id"]]
    second_identity = identities_by_worker[second_worker["worker_id"]]
    first_chat = client.put(
        f"/api/fleet/identities/{first_identity['identity_id']}/active-chat",
        headers=headers,
        json={"chat_id": "writer-a-chat", "source": "test"},
    )
    second_chat = client.put(
        f"/api/fleet/identities/{second_identity['identity_id']}/active-chat",
        headers=headers,
        json={"chat_id": "writer-b-chat", "source": "test"},
    )
    group_response = client.post(
        "/api/fleet/groups",
        headers=headers,
        json={
            "display_name": "Writers",
            "worker_ids": [first_worker["worker_id"], second_worker["worker_id"]],
        },
    )
    confirmation = client.post(
        "/api/app/confirmations",
        headers=headers,
        json={
            "action_kind": "fleet_group_dispatch",
            "title": "Dispatch to writers?",
            "message": "Test dispatch confirmation",
            "risk_tier": "access",
            "origin_surface": "test",
            "payload": {"group_id": group_response.json()["group_id"]},
        },
    )
    approved = client.post(
        f"/api/app/confirmations/{confirmation.json()['confirmation_id']}/approve",
        headers=headers,
        json={"decided_by_surface": "test"},
    )

    response = client.post(
        f"/api/fleet/groups/{group_response.json()['group_id']}/tasks",
        headers={**headers, "X-EmploAI-Confirmation-Id": approved.json()["confirmation_id"]},
        json={
            "prompt": "Create a file in the project workspace",
            "source": "manager",
            "workspace_id": "workspace-group",
            "requires_workspace_write": True,
        },
    )

    assert group_response.status_code == 200
    assert first_chat.status_code == 200
    assert second_chat.status_code == 200
    assert confirmation.status_code == 200
    assert approved.status_code == 200
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) == 2
    assert {task["status"] for task in tasks} == {"blocked"}
    assert {
        task["metadata"]["workspace_binding_blocker"]["reason"]
        for task in tasks
    } == {"workspace_binding_missing_or_inactive"}
    assert {
        task["metadata"]["workspace_binding_blocker"]["workspace_id"]
        for task in tasks
    } == {"workspace-group"}
    targets_by_worker = {
        task["worker_id"]: task["metadata"]["target_session_id"]
        for task in tasks
    }
    assert targets_by_worker[first_worker["worker_id"]] == "writer-a-chat"
    assert targets_by_worker[second_worker["worker_id"]] == "writer-b-chat"


def test_fleet_worker_reset_requires_shared_confirmation(tmp_path):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}

    worker_response = client.post("/api/fleet/workers/local", headers=headers, json={})
    assert worker_response.status_code == 200
    worker = worker_response.json()

    rejected = client.post(
        f"/api/fleet/workers/{worker['worker_id']}/reset",
        headers=headers,
        json={"reason": "test reset"},
    )
    confirmation = client.post(
        "/api/app/confirmations",
        headers=headers,
        json={
            "action_kind": "fleet_worker_reset",
            "title": "Reset worker?",
            "message": "Test confirmation",
            "risk_tier": "danger",
            "origin_surface": "test",
            "payload": {"worker_id": worker["worker_id"]},
        },
    )
    assert confirmation.status_code == 200
    approved = client.post(
        f"/api/app/confirmations/{confirmation.json()['confirmation_id']}/approve",
        headers=headers,
        json={"decided_by_surface": "test"},
    )
    assert approved.status_code == 200

    reset = client.post(
        f"/api/fleet/workers/{worker['worker_id']}/reset",
        headers={**headers, "X-EmploAI-Confirmation-Id": approved.json()["confirmation_id"]},
        json={"reason": "test reset"},
    )

    assert rejected.status_code == 409
    assert rejected.json()["detail"]["error_type"] == "confirmation_required"
    assert reset.status_code == 200
    assert reset.json()["deleted"] is True
    archived = client.get("/api/app/recovery", headers=headers)
    assert archived.status_code == 200
    assert any(item["object_kind"] == "worker" and item["object_id"] == worker["worker_id"] for item in archived.json()["items"])


def test_confirmation_create_is_rate_limited(tmp_path):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}
    payload = {
        "action_kind": "fleet_worker_reset",
        "title": "Reset worker?",
        "message": "Test confirmation",
        "risk_tier": "danger",
        "origin_surface": "test",
        "payload": {"worker_id": "worker-test"},
    }

    statuses = [
        client.post("/api/app/confirmations", headers=headers, json=payload).status_code
        for _ in range(app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS)
    ]
    limited = client.post("/api/app/confirmations", headers=headers, json=payload)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()

    assert statuses == [200] * app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS
    assert limited.status_code == 429


def test_confirmation_decision_is_rate_limited_for_unknown_ids(tmp_path):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}

    statuses = [
        client.post(
            "/api/app/confirmations/conf_not_real/approve",
            headers=headers,
            json={"decided_by_surface": "test"},
        ).status_code
        for _ in range(app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS)
    ]
    limited = client.post(
        "/api/app/confirmations/conf_not_real/approve",
        headers=headers,
        json={"decided_by_surface": "test"},
    )
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()

    assert statuses == [404] * app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS
    assert limited.status_code == 429


def test_recovery_permanent_delete_requires_shared_confirmation(tmp_path):
    store, user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}
    archive = store.archive_item(
        user_id=user["user_id"],
        object_kind="chat",
        object_id="chat_1",
        display_name="Old chat",
        payload={"session": {"id": "chat_1", "messages": []}},
    )

    denied = client.delete(f"/api/app/recovery/{archive['archive_id']}", headers=headers)
    assert denied.status_code == 409
    assert denied.json()["detail"]["error_type"] == "confirmation_required"

    created = client.post(
        "/api/app/confirmations",
        headers=headers,
        json={
            "action_kind": "recovery_permanent_delete",
            "title": "Delete forever",
            "message": "Delete the archived chat forever.",
            "risk_tier": "danger",
            "origin_surface": "desktop",
            "payload": {"archive_id": archive["archive_id"]},
        },
    )
    assert created.status_code == 200
    confirmation_id = created.json()["confirmation_id"]

    approved = client.post(
        f"/api/app/confirmations/{confirmation_id}/approve",
        headers=headers,
        json={"decided_by_surface": "desktop"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    deleted = client.delete(
        f"/api/app/recovery/{archive['archive_id']}",
        headers={**headers, "X-EmploAI-Confirmation-Id": confirmation_id},
    )
    assert deleted.status_code == 200
    assert deleted.json()["item"]["status"] == "purged"


def test_recovery_restore_is_rate_limited_for_unknown_archives(tmp_path):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}

    statuses = [
        client.post("/api/app/recovery/arch_not_real/restore", headers=headers).status_code
        for _ in range(app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS)
    ]
    limited = client.post("/api/app/recovery/arch_not_real/restore", headers=headers)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()

    assert statuses == [404] * app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS
    assert limited.status_code == 429


def test_fleet_api_mobile_can_manage_identity_and_worker_queue(tmp_path):
    store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    mobile_headers = {"Authorization": f"Bearer {mobile_login['session_token']}"}

    worker_response = client.post("/api/fleet/workers/local", headers=mobile_headers, json={"display_name": "Mobile Worker"})
    assert worker_response.status_code == 200
    worker = worker_response.json()

    snapshot = client.get("/api/fleet/snapshot", headers=mobile_headers)
    assert snapshot.status_code == 200
    worker_identity = next(item for item in snapshot.json()["identities"] if item.get("worker_id") == worker["worker_id"])

    active_response = client.put(
        "/api/fleet/active-identity",
        headers=mobile_headers,
        json={"identity_id": worker_identity["identity_id"], "selected_chat_id": "worker-chat-mobile", "source": "mobile"},
    )
    assert active_response.status_code == 200
    assert active_response.json()["active_identity_id"] == worker_identity["identity_id"]

    first_task = client.post(
        f"/api/fleet/workers/{worker['worker_id']}/tasks",
        headers=mobile_headers,
        json={"prompt": "First mobile task", "source": "mobile", "target_session_id": "worker-chat-mobile"},
    )
    second_task = client.post(
        f"/api/fleet/workers/{worker['worker_id']}/tasks",
        headers=mobile_headers,
        json={"prompt": "Second mobile task", "source": "mobile"},
    )
    assert first_task.status_code == 200
    assert second_task.status_code == 200
    assert first_task.json()["metadata"]["target_session_id"] == "worker-chat-mobile"
    assert second_task.json()["metadata"]["target_session_id"] == "worker-chat-mobile"

    reorder_response = client.put(
        "/api/fleet/tasks/reorder",
        headers=mobile_headers,
        json={
            "worker_id": worker["worker_id"],
            "task_ids": [second_task.json()["task_id"], first_task.json()["task_id"]],
        },
    )
    assert reorder_response.status_code == 200
    assert [task["task_id"] for task in reorder_response.json()[:2]] == [
        second_task.json()["task_id"],
        first_task.json()["task_id"],
    ]

    report_response = client.post(
        f"/api/fleet/tasks/{second_task.json()['task_id']}/report",
        headers=mobile_headers,
        json={"status": "completed", "summary": "Mobile task done."},
    )
    assert report_response.status_code == 200
    search_response = client.post(
        "/api/fleet/reports/search",
        headers=mobile_headers,
        json={"query": "mobile task", "worker": "Mobile Worker"},
    )
    assert search_response.status_code == 200
    assert search_response.json()["count"] == 1


def test_fleet_stop_worker_uses_active_task_row_when_worker_pointer_is_stale(tmp_path):
    store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}

    worker_response = client.post("/api/fleet/workers/local", headers=headers, json={})
    assert worker_response.status_code == 200
    worker = worker_response.json()

    task_response = client.post(
        f"/api/fleet/workers/{worker['worker_id']}/tasks",
        headers=headers,
        json={"prompt": "Keep this task running", "source": "manager"},
    )
    assert task_response.status_code == 200
    task = task_response.json()

    running_response = client.put(
        f"/api/fleet/tasks/{task['task_id']}/status",
        headers=headers,
        json={"status": "running"},
    )
    assert running_response.status_code == 200

    store._conn.execute(
        "UPDATE fleet_workers SET active_task_id = NULL WHERE worker_id = ?",
        (worker["worker_id"],),
    )
    store._conn.commit()

    stop_response = client.post(
        f"/api/fleet/workers/{worker['worker_id']}/stop",
        headers=headers,
        json={
            "reason": "Stop the visible task",
            "metadata": {"task_id": task["task_id"], "stopped_from": "mobile_fleet"},
        },
    )

    assert stop_response.status_code == 200
    payload = stop_response.json()
    assert payload["stopped"] is True
    assert payload["task"]["task_id"] == task["task_id"]
    assert payload["task"]["status"] == "stopped"
    assert payload["task"]["metadata"]["reason"] == "Stop the visible task"
    assert payload["task"]["metadata"]["stopped_from"] == "mobile_fleet"


def test_fleet_stop_all_uses_active_task_rows_when_worker_pointers_are_stale(tmp_path):
    store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}

    first_worker = client.post("/api/fleet/workers/local", headers=headers, json={"display_name": "First"}).json()
    second_worker = client.post("/api/fleet/workers/local", headers=headers, json={"display_name": "Second"}).json()
    first_task = client.post(
        f"/api/fleet/workers/{first_worker['worker_id']}/tasks",
        headers=headers,
        json={"prompt": "First task", "source": "manager"},
    ).json()
    second_task = client.post(
        f"/api/fleet/workers/{second_worker['worker_id']}/tasks",
        headers=headers,
        json={"prompt": "Second task", "source": "manager"},
    ).json()
    assert client.put(
        f"/api/fleet/tasks/{first_task['task_id']}/status",
        headers=headers,
        json={"status": "running"},
    ).status_code == 200
    assert client.put(
        f"/api/fleet/tasks/{second_task['task_id']}/status",
        headers=headers,
        json={"status": "running"},
    ).status_code == 200

    store._conn.execute("UPDATE fleet_workers SET active_task_id = NULL")
    store._conn.commit()

    confirmation = client.post(
        "/api/app/confirmations",
        headers=headers,
        json={
            "action_kind": "fleet_stop_all",
            "title": "Stop all?",
            "message": "Stop all active work.",
            "risk_tier": "danger",
            "origin_surface": "test",
            "payload": {},
        },
    )
    approved = client.post(
        f"/api/app/confirmations/{confirmation.json()['confirmation_id']}/approve",
        headers=headers,
        json={"decided_by_surface": "test"},
    )
    assert approved.status_code == 200

    stop_all = client.post(
        "/api/fleet/stop-all",
        headers={**headers, "X-EmploAI-Confirmation-Id": approved.json()["confirmation_id"]},
        json={"reason": "Stop every visible task", "metadata": {"stopped_from": "mobile_fleet"}},
    )

    assert stop_all.status_code == 200
    payload = stop_all.json()
    assert payload["stopped_count"] == 2
    stopped_task_ids = {item["task"]["task_id"] for item in payload["results"] if item.get("stopped")}
    assert stopped_task_ids == {first_task["task_id"], second_task["task_id"]}


def test_fleet_api_remote_worker_enrollment_without_worker_login(tmp_path):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}

    enrollment_response = client.post(
        "/api/fleet/enrollments",
        headers=headers,
        json={"display_name": "Remote Worker"},
    )
    assert enrollment_response.status_code == 200
    token = enrollment_response.json()["enrollment_token"]

    complete_response = client.post(
        "/api/fleet/enrollments/complete",
        json={
            "enrollment_token": token,
            "device_name": "Worker VPS",
            "device_platform": "linux",
            "device_key": "worker-vps",
        },
    )
    assert complete_response.status_code == 200
    payload = complete_response.json()
    assert payload["session_token"]
    assert payload["worker"]["kind"] == "remote"
    assert payload["worker"]["display_name"] == "Remote Worker"

    reused = client.post(
        "/api/fleet/enrollments/complete",
        json={
            "enrollment_token": token,
            "device_name": "Worker VPS 2",
            "device_platform": "linux",
            "device_key": "worker-vps-2",
        },
    )
    assert reused.status_code == 400


def test_fleet_api_remote_worker_enrollment_requires_stable_worker_identity(tmp_path):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}

    enrollment_response = client.post(
        "/api/fleet/enrollments",
        headers=headers,
        json={"display_name": "Remote Worker"},
    )
    assert enrollment_response.status_code == 200
    token = enrollment_response.json()["enrollment_token"]

    missing_key = client.post(
        "/api/fleet/enrollments/complete",
        json={
            "enrollment_token": token,
            "device_name": "Worker VPS",
            "device_platform": "linux",
        },
    )
    manager_key = client.post(
        "/api/fleet/enrollments/complete",
        json={
            "enrollment_token": token,
            "device_name": "Worker VPS",
            "device_platform": "linux",
            "device_key": "desk-key",
        },
    )
    valid = client.post(
        "/api/fleet/enrollments/complete",
        json={
            "enrollment_token": token,
            "device_name": "Worker VPS",
            "device_platform": "linux",
            "device_key": "worker-vps-unique",
        },
    )

    assert missing_key.status_code == 400
    assert "device_key" in missing_key.json()["detail"]
    assert manager_key.status_code == 400
    assert "worker-specific" in manager_key.json()["detail"]
    assert valid.status_code == 200
    assert valid.json()["worker"]["kind"] == "remote"


def test_fleet_api_remote_worker_preview_dispatches_to_connected_worker_desktop(tmp_path, monkeypatch):
    store, user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}

    enrollment = client.post("/api/fleet/enrollments", headers=headers, json={"display_name": "Preview Worker"})
    assert enrollment.status_code == 200
    completed = client.post(
        "/api/fleet/enrollments/complete",
        json={
            "enrollment_token": enrollment.json()["enrollment_token"],
            "device_name": "Preview VPS",
            "device_platform": "linux",
            "device_key": "preview-worker-key",
        },
    )
    assert completed.status_code == 200
    worker = completed.json()["worker"]
    worker_desktop_id = worker["machine_desktop_id"]
    manager = _FakeRemoteDesktopManager(
        {"status": "acknowledged", "detail": "Preview command accepted."},
        connected_ids={worker_desktop_id},
    )
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    response = client.post(f"/api/fleet/workers/{worker['worker_id']}/preview", headers=headers)
    snapshot = client.get("/api/fleet/snapshot", headers=headers).json()
    updated_worker = next(item for item in snapshot["workers"] if item["worker_id"] == worker["worker_id"])

    assert response.status_code == 200
    payload = response.json()
    assert payload["dispatch_status"] == "acknowledged"
    assert payload["desktop_id"] == worker_desktop_id
    assert manager.calls[0]["desktop_id"] == worker_desktop_id
    assert manager.calls[0]["command_type"] == "fleet_worker_preview"
    assert manager.calls[0]["payload"]["preview_id"] == payload["preview_id"]
    assert updated_worker["metadata"]["latest_preview_request"]["preview_id"] == payload["preview_id"]
    assert updated_worker["metadata"]["latest_preview_request"]["status"] == "acknowledged"
    assert any(event["event_type"] == "worker_preview_requested" for event in snapshot["audit_events"])


def test_fleet_api_remote_worker_preview_uses_sqlite_broker_when_socket_is_on_another_worker(tmp_path, monkeypatch):
    store, user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}

    enrollment = client.post("/api/fleet/enrollments", headers=headers, json={"display_name": "Broker Preview Worker"})
    assert enrollment.status_code == 200
    completed = client.post(
        "/api/fleet/enrollments/complete",
        json={
            "enrollment_token": enrollment.json()["enrollment_token"],
            "device_name": "Broker Preview VPS",
            "device_platform": "linux",
            "device_key": "broker-preview-worker",
        },
    )
    assert completed.status_code == 200
    worker = completed.json()["worker"]
    worker_desktop_id = worker["machine_desktop_id"]
    manager = _FakeRemoteDesktopManager({}, connected_ids={"different-desktop"})
    monkeypatch.setenv("EMPLOAI_REMOTE_CONTROL_ROUTING_MODE", "sqlite_broker")
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)
    completed_claim = {}

    def complete_brokered_command():
        deadline = time.time() + 3.0
        while time.time() < deadline:
            claimed = store.claim_remote_desktop_commands(
                user_id=user["user_id"],
                desktop_id=worker_desktop_id,
                instance_id="worker-with-websocket",
            )
            if claimed:
                completed_claim.update(claimed[0])
                store.complete_remote_desktop_command(
                    command_id=claimed[0]["command_id"],
                    user_id=user["user_id"],
                    desktop_id=worker_desktop_id,
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
                return
            time.sleep(0.02)
        completed_claim["error"] = "brokered preview command was not queued"

    completer = threading.Thread(target=complete_brokered_command, daemon=True)
    completer.start()
    response = client.post(f"/api/fleet/workers/{worker['worker_id']}/preview", headers=headers)
    completer.join(timeout=3.0)

    assert not completer.is_alive()
    assert completed_claim.get("error") is None
    assert response.status_code == 200
    payload = response.json()
    assert payload["dispatch_status"] == "acknowledged"
    assert payload["desktop_id"] == worker_desktop_id
    assert payload["detail"] == "Broker preview accepted."
    assert completed_claim["command_type"] == "fleet_worker_preview"
    assert completed_claim["payload"]["preview_id"] == payload["preview_id"]
    assert manager.calls == []


def test_fleet_api_remote_worker_task_run_and_stop_use_sqlite_broker_when_socket_is_on_another_worker(tmp_path, monkeypatch):
    store, user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}

    enrollment = client.post("/api/fleet/enrollments", headers=headers, json={"display_name": "Broker Task Worker"})
    assert enrollment.status_code == 200
    completed = client.post(
        "/api/fleet/enrollments/complete",
        json={
            "enrollment_token": enrollment.json()["enrollment_token"],
            "device_name": "Broker Task VPS",
            "device_platform": "linux",
            "device_key": "broker-task-worker",
        },
    )
    assert completed.status_code == 200
    worker = completed.json()["worker"]
    worker_desktop_id = worker["machine_desktop_id"]
    manager = _FakeRemoteDesktopManager({}, connected_ids={"different-desktop"})
    monkeypatch.setenv("EMPLOAI_REMOTE_CONTROL_ROUTING_MODE", "sqlite_broker")
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    task_response = client.post(
        f"/api/fleet/workers/{worker['worker_id']}/tasks",
        headers=headers,
        json={"prompt": "Run through broker", "source": "manager"},
    )
    assert task_response.status_code == 200
    task = task_response.json()
    assert task["status"] == "running"
    run_commands = store.claim_remote_desktop_commands(
        user_id=user["user_id"],
        desktop_id=worker_desktop_id,
        instance_id="worker-with-websocket",
    )
    assert len(run_commands) == 1
    assert run_commands[0]["command_type"] == "fleet_run_task"
    assert run_commands[0]["payload"]["task_id"] == task["task_id"]
    assert run_commands[0]["payload"]["worker_id"] == worker["worker_id"]
    assert run_commands[0]["payload"]["prompt"] == "Run through broker"

    stop_response = client.put(
        f"/api/fleet/tasks/{task['task_id']}/status",
        headers=headers,
        json={"status": "stopped", "metadata": {"stopped_from": "test"}},
    )
    assert stop_response.status_code == 200
    assert stop_response.json()["status"] == "stopped"
    stop_commands = store.claim_remote_desktop_commands(
        user_id=user["user_id"],
        desktop_id=worker_desktop_id,
        instance_id="worker-with-websocket",
    )
    assert len(stop_commands) == 1
    assert stop_commands[0]["command_type"] == "fleet_stop_task"
    assert stop_commands[0]["payload"] == {"task_id": task["task_id"], "worker_id": worker["worker_id"]}
    assert manager.calls == []


def test_fleet_api_local_worker_preview_records_placeholder_without_dispatch(tmp_path, monkeypatch):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}
    worker = client.post("/api/fleet/workers/local", headers=headers, json={}).json()
    manager = _FakeRemoteDesktopManager({}, connected_ids={desktop_login["desktop"]["desktop_id"]})
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    response = client.post(f"/api/fleet/workers/{worker['worker_id']}/preview", headers=headers)

    assert response.status_code == 200
    assert response.json()["dispatch_status"] == "local_placeholder"
    assert manager.calls == []


def test_fleet_enrollment_complete_rate_limits_unknown_tokens(tmp_path):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    client = TestClient(app_server.create_app())
    payload = {
        "enrollment_token": "not-a-real-enrollment-token-000",
        "device_name": "Worker VPS",
        "device_platform": "linux",
        "device_key": "worker-vps",
    }

    statuses = [
        client.post("/api/fleet/enrollments/complete", json=payload).status_code
        for _ in range(app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS)
    ]
    limited = client.post("/api/fleet/enrollments/complete", json=payload)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()

    assert statuses == [404] * app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS
    assert limited.status_code == 429


def test_remote_mobile_token_can_read_app_profile_and_sessions(tmp_path, monkeypatch):
    store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    store.update_shared_snapshot(
        user_id=user["user_id"],
        desktop_id=desktop_login["desktop"]["desktop_id"],
        snapshot={
            "desktop_id": desktop_login["desktop"]["desktop_id"],
            "desktop_name": "Desk",
            "current_session_id": "sess-1",
            "current_model": "gpt-5",
            "current_variant": "standard",
            "sessions": [
                {
                    "id": "sess-1",
                    "name": "Synced chat",
                    "created_at": "2026-05-31T00:00:00Z",
                    "updated_at": "2026-05-31T00:00:00Z",
                    "model": "gpt-5",
                    "message_count": 1,
                    "workspace": "C:/Users/example/Documents/ProjectA",
                    "origin_channels": ["app"],
                    "is_running": False,
                    "run_state": "idle",
                    "enabled_tool_packs": [],
                    "available_tool_packs": [],
                    "lock_status": {},
                    "headless_eligible": False,
                    "artifact_count": 0,
                }
            ],
            "session_details": {
                "sess-1": {
                    "id": "sess-1",
                    "name": "Synced chat",
                    "created_at": "2026-05-31T00:00:00Z",
                    "updated_at": "2026-05-31T00:00:00Z",
                    "model": "gpt-5",
                    "variant": "standard",
                    "agent_mode": "auto",
                    "workspace": "C:/Users/example/Documents/ProjectA",
                    "messages": [],
                    "timeline_events": [],
                    "completed_task_boards": [],
                    "task_board_armed_next_turn": False,
                    "is_running": False,
                    "run_state": "idle",
                    "enabled_tool_packs": [],
                    "available_tool_packs": [],
                    "lock_status": {},
                    "headless_eligible": False,
                    "artifact_count": 0,
                }
            },
            "jobs": [],
        },
    )

    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {mobile_login['session_token']}"}

    me = client.get("/api/app/me", headers=headers)
    sessions = client.get("/api/app/sessions", headers=headers)
    detail = client.get("/api/app/sessions/sess-1", headers=headers)

    assert me.status_code == 200
    assert me.json()["current_session_id"] == "sess-1"
    assert sessions.status_code == 200
    assert sessions.json()[0]["id"] == "sess-1"
    assert detail.status_code == 200
    assert detail.json()["name"] == "Synced chat"


def test_remote_pairing_api_links_mobile_to_desktop(tmp_path):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    store = app_server._remote_control_store

    user = store.register_user(email="pair-api@example.com", password="CorrectHorse!2026", display_name="Pair API")
    desktop_login = store.login(
        email="pair-api@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Desk",
        device_platform="desktop-electron",
        device_key="pair-api-desk",
    )
    mobile_login = store.login(
        email="pair-api@example.com",
        password="CorrectHorse!2026",
        actor_kind="mobile",
        device_name="Phone",
        device_platform="android",
        device_key="pair-api-phone",
    )
    client = TestClient(app_server.create_app())
    desktop_headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}
    mobile_headers = {"Authorization": f"Bearer {mobile_login['session_token']}"}

    listed = client.get("/api/remote/desktops", headers=mobile_headers)
    started = client.post("/api/remote/pair/start", headers=desktop_headers, json={})
    rejected = client.post("/api/remote/pair/start", headers=mobile_headers, json={})
    completed = client.post(
        "/api/remote/pair/complete",
        headers=mobile_headers,
        json={"pairing_token": started.json()["pairing_token"]},
    )

    assert listed.status_code == 200
    assert listed.json()[0]["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert started.status_code == 200
    assert started.json()["pairing_token"]
    assert rejected.status_code == 403
    assert completed.status_code == 200
    assert completed.json()["desktop"]["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert completed.json()["mobile"]["paired_desktop_id"] == desktop_login["desktop"]["desktop_id"]
    refreshed_mobile = store.resolve_session_token(mobile_login["session_token"])
    assert store.paired_desktop_id_for_payload(refreshed_mobile) == desktop_login["desktop"]["desktop_id"]
    assert store.get_shared_state(user_id=user["user_id"])["current_desktop_id"] == desktop_login["desktop"]["desktop_id"]


def test_remote_pairing_api_rate_limits_pair_start(tmp_path):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    store = app_server._remote_control_store

    store.register_user(email="pair-limit@example.com", password="CorrectHorse!2026", display_name="Pair Limit")
    desktop_login = store.login(
        email="pair-limit@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Desk",
        device_platform="desktop-electron",
        device_key="pair-limit-desk",
    )
    client = TestClient(app_server.create_app())
    desktop_headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}

    statuses = [
        client.post("/api/remote/pair/start", headers=desktop_headers, json={}).status_code
        for _ in range(app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS)
    ]
    limited = client.post("/api/remote/pair/start", headers=desktop_headers, json={})
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()

    assert statuses == [200] * app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS
    assert limited.status_code == 429


class _FakeRemoteDesktopManager:
    def __init__(self, result, *, connected_ids=None):
        self.result = result
        self.calls = []
        self.connected_ids = set(connected_ids or [])

    def is_connected(self, desktop_id):
        return not self.connected_ids or str(desktop_id or "") in self.connected_ids

    def is_connected_for_user(self, desktop_id, user_id):
        return self.is_connected(desktop_id)

    def connected_desktop_ids_for_user(self, user_id):
        return sorted(self.connected_ids)

    async def request_command(self, *, desktop_id, command_type, payload, timeout_seconds=30.0, user_id=None):
        if not self.is_connected(desktop_id):
            raise RuntimeError("The paired desktop is offline")
        self.calls.append(
            {
                "desktop_id": desktop_id,
                "user_id": user_id,
                "command_type": command_type,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        return {"ok": True, "result": self.result}


def _json_proxy_result(payload: dict, *, status_code: int = 200) -> dict:
    return {
        "status_code": status_code,
        "headers": {"content-type": "application/json", "x-desktop-internal": "ignored"},
        "body_base64": base64.b64encode(
            json.dumps(payload).encode("utf-8")
        ).decode("ascii"),
    }


def _remote_session_detail_payload(session_id: str = "sess-1") -> dict:
    return {
        "id": session_id,
        "name": "Synced chat",
        "created_at": "2026-05-31T00:00:00Z",
        "updated_at": "2026-05-31T00:00:00Z",
        "model": "gpt-5",
        "variant": "standard",
        "agent_mode": "auto",
        "workspace": "C:/Users/example/Documents/ProjectA",
        "messages": [],
        "timeline_events": [],
        "completed_task_boards": [],
        "task_board_armed_next_turn": False,
        "is_running": False,
        "run_state": "idle",
        "enabled_tool_packs": [],
        "available_tool_packs": [],
        "lock_status": {},
        "headless_eligible": False,
        "artifact_count": 0,
    }


def test_remote_desktop_request_uses_sqlite_broker_when_socket_is_on_another_worker(tmp_path, monkeypatch):
    store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    desktop_id = desktop_login["desktop"]["desktop_id"]
    manager = _FakeRemoteDesktopManager({}, connected_ids={"different-desktop"})
    monkeypatch.setenv("EMPLOAI_REMOTE_CONTROL_ROUTING_MODE", "sqlite_broker")
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    async def complete_brokered_command():
        deadline = asyncio.get_running_loop().time() + 2.0
        while asyncio.get_running_loop().time() < deadline:
            claimed = store.claim_remote_desktop_commands(
                user_id=user["user_id"],
                desktop_id=desktop_id,
                instance_id="worker-with-websocket",
            )
            if claimed:
                store.complete_remote_desktop_command(
                    command_id=claimed[0]["command_id"],
                    user_id=user["user_id"],
                    desktop_id=desktop_id,
                    ok=True,
                    payload={"ok": True, "result": {"pong": True}},
                )
                return claimed[0]
            await asyncio.sleep(0.05)
        raise AssertionError("brokered command was not queued")

    async def scenario():
        auth = store.resolve_session_token(mobile_login["session_token"])
        completer = asyncio.create_task(complete_brokered_command())
        result = await app_server._remote_request_desktop_command(
            auth,
            command_name="http_request",
            payload={"path": "/api/app/health"},
            timeout_seconds=2.0,
        )
        claimed = await completer
        return result, claimed

    result, claimed = asyncio.run(scenario())

    assert result == {"pong": True}
    assert claimed["command_type"] == "http_request"
    assert claimed["payload"] == {"path": "/api/app/health"}
    assert manager.calls == []


def _assert_websocket_closes(client: TestClient, path: str, code: int, *, headers=None) -> None:
    with client.websocket_connect(path, headers=headers or {}) as websocket:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.receive_json()
    assert exc_info.value.code == code


@pytest.mark.parametrize(
    "path",
    [
        "/ws/app/screen?token=not-a-real-token",
        "/ws/remote/desktop?token=not-a-real-token",
        "/ws/remote/mobile?token=not-a-real-token",
        "/ws/app/chat?token=not-a-real-token",
        "/ws/app/voice?token=not-a-real-token",
    ],
)
def test_websockets_reject_untrusted_origin_in_production(tmp_path, monkeypatch, path):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    monkeypatch.setenv(app_server.DEPLOYMENT_ENV_ENV, "production")
    monkeypatch.delenv(app_server.CORS_ORIGINS_ENV, raising=False)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    client = TestClient(app_server.create_app())

    _assert_websocket_closes(client, path, 4403, headers={"origin": "https://evil.example"})
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()


def test_websocket_allows_configured_origin_before_token_validation(tmp_path, monkeypatch):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    monkeypatch.setenv(app_server.DEPLOYMENT_ENV_ENV, "production")
    monkeypatch.delenv(app_server.CORS_ORIGINS_ENV, raising=False)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    client = TestClient(app_server.create_app())

    _assert_websocket_closes(
        client,
        "/ws/remote/mobile?token=not-a-real-token",
        4401,
        headers={"origin": "https://kraitos.app"},
    )
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()


def test_remote_screen_ws_reports_malformed_desktop_body(tmp_path, monkeypatch):
    store, _user, _desktop_login, mobile_login = _paired_remote_session(tmp_path)

    async def fake_remote_desktop_http_request(auth, **kwargs):
        return {
            "status_code": 200,
            "headers": {"content-type": "application/json"},
            "body_base64": "not valid base64 !!!",
        }

    monkeypatch.setattr(app_server, "_remote_desktop_http_request", fake_remote_desktop_http_request)

    class RecordingScreenWebSocket:
        query_params = {"fps": "1", "max_width": "960", "quality": "55"}

        def __init__(self):
            self.client_state = app_server.WebSocketState.CONNECTED
            self.application_state = app_server.WebSocketState.CONNECTED
            self.sent = []
            self.close_code = None

        async def send_json(self, payload):
            self.sent.append(payload)

        async def close(self, code=1000):
            self.close_code = code
            self.application_state = app_server.WebSocketState.DISCONNECTED

    async def scenario():
        websocket = RecordingScreenWebSocket()
        auth = store.resolve_session_token(mobile_login["session_token"])
        await app_server._handle_remote_screen_ws(websocket, auth, asyncio.Lock())
        return websocket

    websocket = asyncio.run(scenario())

    assert websocket.close_code == 1011
    assert [item["type"] for item in websocket.sent] == ["screen_state", "screen_state"]
    assert websocket.sent[-1]["payload"]["state"] == "error"
    assert "body" in websocket.sent[-1]["payload"]["message"].lower()


def test_remote_screen_ws_rejects_oversized_desktop_body(tmp_path, monkeypatch):
    store, _user, _desktop_login, mobile_login = _paired_remote_session(tmp_path)
    monkeypatch.setattr(app_server, "REMOTE_HTTP_PROXY_MAX_RESPONSE_BODY_BYTES", 8)

    async def fake_remote_desktop_http_request(auth, **kwargs):
        return {
            "status_code": 200,
            "headers": {"content-type": "application/json"},
            "body_base64": base64.b64encode(b"x" * 9).decode("ascii"),
        }

    monkeypatch.setattr(app_server, "_remote_desktop_http_request", fake_remote_desktop_http_request)

    class RecordingScreenWebSocket:
        query_params = {"fps": "1", "max_width": "960", "quality": "55"}

        def __init__(self):
            self.client_state = app_server.WebSocketState.CONNECTED
            self.application_state = app_server.WebSocketState.CONNECTED
            self.sent = []
            self.close_code = None

        async def send_json(self, payload):
            self.sent.append(payload)

        async def close(self, code=1000):
            self.close_code = code
            self.application_state = app_server.WebSocketState.DISCONNECTED

    async def scenario():
        websocket = RecordingScreenWebSocket()
        auth = store.resolve_session_token(mobile_login["session_token"])
        await app_server._handle_remote_screen_ws(websocket, auth, asyncio.Lock())
        return websocket

    websocket = asyncio.run(scenario())

    assert websocket.close_code == 1011
    assert [item["type"] for item in websocket.sent] == ["screen_state", "screen_state"]
    assert websocket.sent[-1]["payload"]["state"] == "error"
    assert "too large" in websocket.sent[-1]["payload"]["message"].lower()


def test_remote_mobile_create_session_dispatches_to_paired_desktop(tmp_path, monkeypatch):
    store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    mobile_headers = {"Authorization": f"Bearer {mobile_login['session_token']}"}

    worker_response = client.post(
        "/api/fleet/workers/local",
        headers=mobile_headers,
        json={"display_name": "Mobile Worker"},
    )
    assert worker_response.status_code == 200
    worker = worker_response.json()
    fleet_snapshot = client.get("/api/fleet/snapshot", headers=mobile_headers)
    worker_identity = next(
        item
        for item in fleet_snapshot.json()["identities"]
        if item.get("worker_id") == worker["worker_id"]
    )

    created_detail = _remote_session_detail_payload("sess-mobile-new")
    created_detail.update(
        {
            "name": "Mobile-created Fleet chat",
            "workspace": "C:/Work/Mobile",
            "enabled_tool_packs": ["workspace_read"],
            "security_permission_mode": "trusted",
            "headless_eligible": True,
            "workspace_id": "workspace-mobile",
            "workspace_binding_status": "bound",
            "telegram_bot_config_id": "bot-mobile",
            "fleet_identity_id": worker_identity["identity_id"],
            "fleet_identity_role": "worker",
            "fleet_worker_id": worker["worker_id"],
        }
    )
    manager = _FakeRemoteDesktopManager({"session": created_detail})
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    response = client.post(
        "/api/app/sessions",
        headers=mobile_headers,
        json={
            "name": "Mobile-created Fleet chat",
            "workspace": "C:/Work/Mobile",
            "workspace_id": "workspace-mobile",
            "workspace_binding_status": "bound",
            "telegram_bot_config_id": "bot-mobile",
            "enabled_tool_packs": ["workspace_read"],
            "security_permission_mode": "trusted",
            "headless_eligible": True,
            "fleet_identity_id": worker_identity["identity_id"],
            "fleet_identity_role": "worker",
            "fleet_worker_id": worker["worker_id"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session"]["id"] == "sess-mobile-new"
    assert body["session"]["fleet_identity_id"] == worker_identity["identity_id"]
    assert len(manager.calls) == 1
    assert manager.calls[0]["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert manager.calls[0]["user_id"] == user["user_id"]
    assert manager.calls[0]["command_type"] == "create_session"
    assert manager.calls[0]["payload"] == {
        "name": "Mobile-created Fleet chat",
        "workspace": "C:/Work/Mobile",
        "workspace_id": "workspace-mobile",
        "workspace_binding_status": "bound",
        "telegram_bot_config_id": "bot-mobile",
        "enabled_tool_packs": ["workspace_read"],
        "security_permission_mode": "trusted",
        "headless_eligible": True,
        "fleet_identity_id": worker_identity["identity_id"],
        "fleet_identity_role": "worker",
        "fleet_worker_id": worker["worker_id"],
    }
    assert store.get_fleet_snapshot(user_id=user["user_id"])["selected_chat_by_identity"][
        worker_identity["identity_id"]
    ] == "sess-mobile-new"


def test_remote_session_detail_filters_internal_planner_timeline_events(tmp_path):
    store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    detail = _remote_session_detail_payload("sess-1")
    detail["timeline_events"] = [
        {
            "id": "planner-1",
            "kind": "runtime",
            "title": "Planner verifier",
            "content": "continue: coding_task_premature_final\nCandidate final: done",
            "tone": "warn",
            "timestamp": "2026-05-31T00:00:01Z",
            "channel": "app",
            "source_format": "app_text",
            "metadata": {
                "candidate_final_preview": "done",
                "auto_continue_count": 1,
            },
        },
        {
            "id": "tool-1",
            "kind": "tool",
            "title": "run_command",
            "content": "npm test",
            "tone": "neutral",
            "timestamp": "2026-05-31T00:00:02Z",
            "channel": "app",
            "source_format": "app_system",
            "metadata": {"tool_name": "run_command"},
        },
        {
            "id": "guard-log",
            "kind": "runtime",
            "title": "Runtime",
            "content": "  Final quality guard forced continuation (coding_task; 1/5).",
            "tone": "neutral",
            "timestamp": "2026-05-31T00:00:03Z",
            "channel": "app",
            "source_format": "app_text",
            "metadata": {},
        },
    ]
    store.update_shared_snapshot(
        user_id=user["user_id"],
        desktop_id=desktop_login["desktop"]["desktop_id"],
        snapshot={
            "desktop_id": desktop_login["desktop"]["desktop_id"],
            "desktop_name": "Desk",
            "current_session_id": "sess-1",
            "current_model": "gpt-5",
            "current_variant": "standard",
            "sessions": [],
            "session_details": {"sess-1": detail},
            "jobs": [],
        },
    )

    client = TestClient(app_server.create_app())
    response = client.get(
        "/api/app/sessions/sess-1",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
    )

    assert response.status_code == 200
    assert [event["id"] for event in response.json()["timeline_events"]] == ["tool-1"]


def test_remote_mobile_session_search_uses_cloud_shared_state_without_local_bridge(tmp_path, monkeypatch):
    store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    detail = _remote_session_detail_payload("sess-search")
    detail.update(
        {
            "name": "Deployment notes",
            "workspace": "C:/Work/Launch",
            "messages": [
                {
                    "role": "user",
                    "content": "Prepare the deploy checklist for the cloud release.",
                    "timestamp": "2026-05-31T00:00:04Z",
                }
            ],
        }
    )
    store.update_shared_snapshot(
        user_id=user["user_id"],
        desktop_id=desktop_login["desktop"]["desktop_id"],
        snapshot={
            "desktop_id": desktop_login["desktop"]["desktop_id"],
            "desktop_name": "Desk",
            "current_session_id": "sess-search",
            "sessions": [
                {
                    "id": "sess-search",
                    "name": "Deployment notes",
                    "created_at": "2026-05-31T00:00:00Z",
                    "updated_at": "2026-05-31T00:00:04Z",
                    "model": "gpt-5",
                    "message_count": 1,
                    "workspace": "C:/Work/Launch",
                }
            ],
            "session_details": {"sess-search": detail},
            "jobs": [],
        },
    )

    def fail_bridge_for_user(user_id):
        raise AssertionError("remote session search must not read local cloud-host session files")

    monkeypatch.setattr(app_server, "_bridge_for_user", fail_bridge_for_user)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/sessions/search",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
        json={"query": "deploy checklist", "limit": 5},
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["kind"] == "message"
    assert results[0]["session_id"] == "sess-search"
    assert "deploy checklist" in results[0]["snippet"]


def test_realtime_event_filters_internal_planner_log():
    event = app_server._sync_event_to_realtime_event(
        {
            "type": "log",
            "session_id": "sess-1",
            "payload": {"message": "Final quality guard forced continuation (coding_task; 1/5)."},
        },
        active_session_id="sess-1",
        client_id=None,
        verbose_mode=True,
    )

    assert event is None


def test_remote_mobile_desktop_owned_app_endpoint_proxies_to_paired_desktop(tmp_path, monkeypatch):
    _store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(_json_proxy_result({"items": [{"key": "demo", "value": True}]}))
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.get(
        "/api/app/agent/config?session_id=sess-1",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
    )

    assert response.status_code == 200
    assert response.json() == {"items": [{"key": "demo", "value": True}]}
    assert response.headers["content-type"].startswith("application/json")
    assert "x-desktop-internal" not in response.headers
    assert len(manager.calls) == 1
    call = manager.calls[0]
    assert call["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert call["user_id"] == user["user_id"]
    assert call["command_type"] == "http_request"
    assert call["payload"]["method"] == "GET"
    assert call["payload"]["path"] == "/api/app/agent/config"
    assert call["payload"]["query_string"] == "session_id=sess-1"


def test_remote_mobile_jarvis_control_endpoint_proxies_to_paired_desktop(tmp_path, monkeypatch):
    _store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(_json_proxy_result({"action": "stop", "message": "Stopped active task"}))
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/agent/control/stop?session_id=sess-jarvis",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
    )

    assert response.status_code == 200
    assert response.json() == {"action": "stop", "message": "Stopped active task"}
    assert len(manager.calls) == 1
    call = manager.calls[0]
    assert call["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert call["user_id"] == user["user_id"]
    assert call["command_type"] == "http_request"
    assert call["payload"]["method"] == "POST"
    assert call["payload"]["path"] == "/api/app/agent/control/stop"
    assert call["payload"]["query_string"] == "session_id=sess-jarvis"


def test_remote_mobile_jarvis_task_spawn_proxies_to_paired_desktop(tmp_path, monkeypatch):
    _store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(_json_proxy_result({"action": "spawn", "message": "Sub-agent task-1 started"}))
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/agent/subagents?session_id=sess-jarvis",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
        json={"prompt": "Audit the mobile Jarvis task flow", "headless": True, "max_turns": 50},
    )

    assert response.status_code == 200
    assert response.json() == {"action": "spawn", "message": "Sub-agent task-1 started"}
    assert len(manager.calls) == 1
    call = manager.calls[0]
    assert call["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert call["user_id"] == user["user_id"]
    assert call["command_type"] == "http_request"
    assert call["payload"]["method"] == "POST"
    assert call["payload"]["path"] == "/api/app/agent/subagents"
    assert call["payload"]["query_string"] == "session_id=sess-jarvis"
    assert call["payload"]["headers"]["content-type"].startswith("application/json")
    forwarded_body = json.loads(base64.b64decode(call["payload"]["body_base64"]).decode("utf-8"))
    assert forwarded_body == {
        "prompt": "Audit the mobile Jarvis task flow",
        "headless": True,
        "max_turns": 50,
    }


def test_remote_mobile_session_tool_packs_proxy_to_paired_desktop(tmp_path, monkeypatch):
    _store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    detail = _remote_session_detail_payload("sess-jarvis")
    detail["enabled_tool_packs"] = ["workspace_read"]
    manager = _FakeRemoteDesktopManager(_json_proxy_result(detail))
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/sessions/sess-jarvis/tool-packs",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
        json={"enabled_tool_packs": ["workspace_read"]},
    )

    assert response.status_code == 200
    assert response.json()["enabled_tool_packs"] == ["workspace_read"]
    assert len(manager.calls) == 1
    call = manager.calls[0]
    assert call["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert call["user_id"] == user["user_id"]
    assert call["command_type"] == "http_request"
    assert call["payload"]["method"] == "POST"
    assert call["payload"]["path"] == "/api/app/sessions/sess-jarvis/tool-packs"
    forwarded_body = json.loads(base64.b64decode(call["payload"]["body_base64"]).decode("utf-8"))
    assert forwarded_body == {"enabled_tool_packs": ["workspace_read"]}


def test_remote_mobile_session_timeline_proxies_to_paired_desktop(tmp_path, monkeypatch):
    _store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(_json_proxy_result({"event": {"id": "evt-1"}}))
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/sessions/sess-jarvis/timeline",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
        json={
            "kind": "runtime",
            "title": "Started",
            "content": "Started a task",
            "tone": "neutral",
            "channel": "app",
            "source_format": "app_text",
        },
    )

    assert response.status_code == 200
    assert response.json()["event"]["id"] == "evt-1"
    assert len(manager.calls) == 1
    call = manager.calls[0]
    assert call["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert call["user_id"] == user["user_id"]
    assert call["command_type"] == "http_request"
    assert call["payload"]["method"] == "POST"
    assert call["payload"]["path"] == "/api/app/sessions/sess-jarvis/timeline"
    forwarded_body = json.loads(base64.b64decode(call["payload"]["body_base64"]).decode("utf-8"))
    assert forwarded_body["title"] == "Started"


def test_session_timeline_rejects_direct_remote_session_without_local_bridge(tmp_path, monkeypatch):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)

    def fail_bridge_for_user(user_id):
        raise AssertionError("remote sessions must not append local timeline events on the cloud backend")

    monkeypatch.setattr(app_server, "_bridge_for_user", fail_bridge_for_user)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/sessions/sess-jarvis/timeline",
        headers={"Authorization": f"Bearer {desktop_login['session_token']}"},
        json={
            "kind": "runtime",
            "title": "Started",
            "content": "Started a task",
            "tone": "neutral",
        },
    )

    assert response.status_code == 409
    assert "local desktop backend" in response.json()["detail"]


def test_session_settings_reject_direct_remote_session_without_local_bridge(tmp_path, monkeypatch):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)

    def fail_bridge_for_user(user_id):
        raise AssertionError("remote sessions must not mutate local session settings on the cloud backend")

    monkeypatch.setattr(app_server, "_bridge_for_user", fail_bridge_for_user)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/sessions/sess-jarvis/tool-packs",
        headers={"Authorization": f"Bearer {desktop_login['session_token']}"},
        json={"enabled_tool_packs": ["workspace_read"]},
    )

    assert response.status_code == 409
    assert "local desktop backend" in response.json()["detail"]


def test_session_settings_update_is_rate_limited(tmp_path, monkeypatch):
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    updates = []

    class FakeBridge:
        def update_session_headless_eligible(self, session_id, headless_eligible):
            updates.append({"session_id": session_id, "headless_eligible": headless_eligible})
            return {"id": session_id}

        def detailed_session_view(self, session):
            detail = _remote_session_detail_payload(str(session.get("id") or "sess-rate"))
            detail["headless_eligible"] = True
            return detail

    monkeypatch.setattr(app_server, "_resolve_token", lambda _authorization: {"user_id": 1})
    monkeypatch.setattr(app_server, "_bridge_for_user", lambda _user_id: FakeBridge())

    client = TestClient(app_server.create_app())
    statuses = [
        client.post(
            "/api/app/sessions/sess-rate/headless-eligibility",
            headers={"Authorization": "Bearer local"},
            json={"headless_eligible": True},
        ).status_code
        for _ in range(app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS)
    ]
    limited = client.post(
        "/api/app/sessions/sess-rate/headless-eligibility",
        headers={"Authorization": "Bearer local"},
        json={"headless_eligible": True},
    )
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()

    assert statuses == [200] * app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS
    assert limited.status_code == 429
    assert len(updates) == app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS


def test_remote_mobile_delete_session_proxies_to_paired_desktop(tmp_path, monkeypatch):
    _store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(_json_proxy_result({"deleted_session_id": "sess-jarvis"}))
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.delete(
        "/api/app/sessions/sess-jarvis",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
    )

    assert response.status_code == 200
    assert response.json() == {"deleted_session_id": "sess-jarvis"}
    assert len(manager.calls) == 1
    call = manager.calls[0]
    assert call["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert call["user_id"] == user["user_id"]
    assert call["command_type"] == "http_request"
    assert call["payload"]["method"] == "DELETE"
    assert call["payload"]["path"] == "/api/app/sessions/sess-jarvis"
    assert call["payload"]["query_string"] == ""
    assert call["payload"]["body_base64"] == ""


def test_session_delete_with_remote_desktop_token_proxies_without_local_bridge(tmp_path, monkeypatch):
    _store, user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(_json_proxy_result({"deleted_session_id": "sess-jarvis"}))
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    def fail_bridge_for_user(user_id):
        raise AssertionError("remote sessions must not delete local cloud-host sessions")

    monkeypatch.setattr(app_server, "_bridge_for_user", fail_bridge_for_user)

    client = TestClient(app_server.create_app())
    response = client.delete(
        "/api/app/sessions/sess-jarvis",
        headers={"Authorization": f"Bearer {desktop_login['session_token']}"},
    )

    assert response.status_code == 200
    assert response.json() == {"deleted_session_id": "sess-jarvis", "current_session_id": None}
    assert len(manager.calls) == 1
    call = manager.calls[0]
    assert call["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert call["user_id"] == user["user_id"]
    assert call["command_type"] == "delete_session"
    assert call["payload"] == {"session_id": "sess-jarvis"}


def test_remote_mobile_chat_send_proxies_to_paired_desktop(tmp_path, monkeypatch):
    _store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(_json_proxy_result({"ok": True, "session_id": "sess-jarvis"}))
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/chat/send",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
        json={"session_id": "sess-jarvis", "text": "Hello from mobile", "source_format": "app_text"},
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == "sess-jarvis"
    assert len(manager.calls) == 1
    call = manager.calls[0]
    assert call["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert call["user_id"] == user["user_id"]
    assert call["command_type"] == "http_request"
    assert call["payload"]["method"] == "POST"
    assert call["payload"]["path"] == "/api/app/chat/send"
    forwarded_body = json.loads(base64.b64decode(call["payload"]["body_base64"]).decode("utf-8"))
    assert forwarded_body["text"] == "Hello from mobile"


def test_chat_send_rejects_direct_remote_session_without_local_runtime(tmp_path, monkeypatch):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)

    def fail_bridge_for_user(user_id):
        raise AssertionError("remote sessions must not run chat turns on the cloud backend")

    monkeypatch.setattr(app_server, "_bridge_for_user", fail_bridge_for_user)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/chat/send",
        headers={"Authorization": f"Bearer {desktop_login['session_token']}"},
        json={"session_id": "sess-jarvis", "text": "Hello from desktop remote"},
    )

    assert response.status_code == 409
    assert "local desktop backend" in response.json()["detail"]


def test_remote_http_proxy_rejects_unsupported_methods():
    assert app_server._should_proxy_remote_http_request("TRACE", "/api/app/agent/config") is False
    assert app_server._should_proxy_remote_http_request("CONNECT", "/api/app/runtime/headless") is False
    assert app_server._should_proxy_remote_http_request("GET", "/api/app/agent/config") is True


def test_remote_mobile_proxy_streaming_body_limit_rejects_before_desktop_dispatch(tmp_path, monkeypatch):
    store, _user, _desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(_json_proxy_result({"ok": True}))
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)
    monkeypatch.setattr(app_server, "REMOTE_HTTP_PROXY_MAX_BODY_BYTES", 8)

    chunks = [b"abcd", b"efgh", b"ijkl"]

    async def receive():
        body = chunks.pop(0)
        return {"type": "http.request", "body": body, "more_body": bool(chunks)}

    request = app_server.Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/app/agent/subagents",
            "query_string": b"session_id=sess-1",
            "headers": [(b"content-type", b"application/octet-stream")],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "scheme": "http",
            "root_path": "",
        },
        receive,
    )
    auth = store.resolve_session_token(mobile_login["session_token"])

    with pytest.raises(app_server.HTTPException) as exc_info:
        asyncio.run(app_server._remote_proxy_http_request(request, auth))

    assert exc_info.value.status_code == 413
    assert manager.calls == []


def test_remote_mobile_proxy_invalid_desktop_status_returns_bad_gateway(tmp_path, monkeypatch):
    _store, _user, _desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(
        {
            "status_code": "not-a-status",
            "headers": {"content-type": "application/json"},
            "body_base64": base64.b64encode(b"{}").decode("ascii"),
        }
    )
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.get(
        "/api/app/agent/config?session_id=sess-1",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
    )

    assert response.status_code == 502
    assert "status" in str(response.json()["detail"]).lower()
    assert len(manager.calls) == 1


def test_remote_mobile_proxy_invalid_desktop_body_returns_bad_gateway(tmp_path, monkeypatch):
    _store, _user, _desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(
        {
            "status_code": 200,
            "headers": {"content-type": "application/json"},
            "body_base64": "not valid base64 !!!",
        }
    )
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.get(
        "/api/app/agent/config?session_id=sess-1",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
    )

    assert response.status_code == 502
    assert "body" in str(response.json()["detail"]).lower()
    assert len(manager.calls) == 1


def test_remote_mobile_proxy_drops_unsafe_desktop_response_headers(tmp_path, monkeypatch):
    _store, _user, _desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(
        {
            "status_code": 200,
            "headers": {
                "content-type": "application/json",
                "etag": "ok\r\nx-injected: yes",
                "cache-control": "no-store",
                "x-desktop-internal": "ignored",
            },
            "body_base64": base64.b64encode(b'{"ok": true}').decode("ascii"),
        }
    )
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.get(
        "/api/app/agent/config?session_id=sess-1",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert response.headers["cache-control"] == "no-store"
    assert "etag" not in response.headers
    assert "x-desktop-internal" not in response.headers


def test_remote_mobile_websocket_rejects_desktop_session_token(tmp_path):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())

    _assert_websocket_closes(client, f"/ws/remote/mobile?token={desktop_login['session_token']}", 4403)


def test_remote_desktop_websocket_rejects_mobile_session_token(tmp_path):
    _store, _user, _desktop_login, mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())

    _assert_websocket_closes(client, f"/ws/remote/desktop?token={mobile_login['session_token']}", 4403)


def test_remote_websockets_reject_invalid_session_token(tmp_path):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    client = TestClient(app_server.create_app())

    _assert_websocket_closes(client, "/ws/remote/mobile?token=not-a-real-token", 4401)
    _assert_websocket_closes(client, "/ws/remote/desktop?token=not-a-real-token", 4401)


def test_remote_websocket_invalid_token_attempts_are_rate_limited(tmp_path, monkeypatch):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    monkeypatch.setattr(app_server, "REMOTE_WS_AUTH_RATE_LIMIT_MAX_ATTEMPTS", 2)
    client = TestClient(app_server.create_app())

    _assert_websocket_closes(client, "/ws/remote/mobile?token=bad-token-a", 4401)
    _assert_websocket_closes(client, "/ws/remote/mobile?token=bad-token-b", 4401)
    _assert_websocket_closes(client, "/ws/remote/mobile?token=bad-token-c", 4408)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()


def test_app_chat_remote_compat_websocket_rejects_desktop_session_token(tmp_path):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())

    _assert_websocket_closes(client, f"/ws/app/chat?token={desktop_login['session_token']}", 4403)


def test_app_chat_websocket_rejects_invalid_session_token(tmp_path):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    client = TestClient(app_server.create_app())

    _assert_websocket_closes(client, "/ws/app/chat?token=not-a-real-token", 4401)


def test_remote_mobile_websocket_dispatches_chat_send_to_paired_desktop(tmp_path, monkeypatch):
    _store, user, _desktop_login, mobile_login = _paired_remote_session(tmp_path)
    dispatched = []

    async def fake_dispatch(auth, *, command_name, payload):
        dispatched.append(
            {
                "auth": auth,
                "command_name": command_name,
                "payload": payload,
            }
        )
        return {"ok": True}

    monkeypatch.setattr(app_server, "_remote_dispatch_command", fake_dispatch)

    client = TestClient(app_server.create_app())
    with client.websocket_connect(
        f"/ws/remote/mobile?token={mobile_login['session_token']}&client_id=phone-client&session_id=sess-phone"
    ) as websocket:
        websocket.send_json(
            {
                "text": "Run the mobile-requested task",
                "session_id": "sess-phone",
                "interrupt_policy": "steer_now",
                "source_format": "app_text",
            }
        )
        seen_types = []
        for _ in range(6):
            message = websocket.receive_json()
            seen_types.append(message.get("type"))
            if message.get("type") == "status" and message.get("payload", {}).get("message") == "dispatched to desktop":
                break

    assert "session_snapshot" in seen_types
    assert len(dispatched) == 1
    assert dispatched[0]["auth"]["user_id"] == user["user_id"]
    assert dispatched[0]["auth"]["actor_kind"] == "mobile"
    assert dispatched[0]["auth"]["mobile_id"] == mobile_login["mobile"]["mobile_id"]
    assert dispatched[0]["auth"]["paired_desktop_id"]
    assert dispatched[0]["command_name"] == "chat_send"
    assert dispatched[0]["payload"] == {
        "text": "Run the mobile-requested task",
        "session_id": "sess-phone",
        "source_format": "app_text",
        "interrupt_policy": "steer_now",
        "source_client_id": "phone-client",
    }


def test_remote_mobile_websocket_follows_explicit_message_session_for_sync(tmp_path, monkeypatch):
    _store, user, _desktop_login, mobile_login = _paired_remote_session(tmp_path)
    dispatched = []
    next_detail = _remote_session_detail_payload("sess-next")
    next_detail["name"] = "Next chat"

    async def fake_dispatch(auth, *, command_name, payload):
        dispatched.append({"command_name": command_name, "payload": payload})
        app_server.get_channel_sync_hub().publish(
            user_id=auth["user_id"],
            event={
                "type": "session_sync",
                "session_id": "sess-next",
                "payload": {
                    "session": next_detail,
                    "sessions": [],
                    "shared_state": {},
                },
            },
        )
        return {"ok": True}

    monkeypatch.setattr(app_server, "_remote_dispatch_command", fake_dispatch)

    client = TestClient(app_server.create_app())
    with client.websocket_connect(
        f"/ws/remote/mobile?token={mobile_login['session_token']}&client_id=phone-client&session_id=sess-old"
    ) as websocket:
        websocket.send_json(
            {
                "text": "Send this in the selected chat",
                "session_id": "sess-next",
                "interrupt_policy": "none",
                "source_format": "app_text",
            }
        )
        seen = []
        for _ in range(8):
            message = websocket.receive_json()
            seen.append(message)
            if message.get("type") == "session_sync" and message.get("session_id") == "sess-next":
                break

    assert dispatched == [
        {
            "command_name": "chat_send",
            "payload": {
                "text": "Send this in the selected chat",
                "session_id": "sess-next",
                "source_format": "app_text",
                "interrupt_policy": "none",
                "source_client_id": "phone-client",
            },
        }
    ]
    assert any(message.get("type") == "user_message" and message.get("session_id") == "sess-next" for message in seen)
    assert any(message.get("type") == "session_sync" and message.get("session_id") == "sess-next" for message in seen)


def test_remote_mobile_websocket_initial_sync_uses_active_fleet_identity_chat(tmp_path):
    store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    mobile_headers = {"Authorization": f"Bearer {mobile_login['session_token']}"}

    worker_response = client.post(
        "/api/fleet/workers/local",
        headers=mobile_headers,
        json={"display_name": "Mobile Worker"},
    )
    assert worker_response.status_code == 200
    worker = worker_response.json()
    fleet_snapshot = client.get("/api/fleet/snapshot", headers=mobile_headers)
    worker_identity = next(
        item
        for item in fleet_snapshot.json()["identities"]
        if item.get("worker_id") == worker["worker_id"]
    )
    active_response = client.put(
        "/api/fleet/active-identity",
        headers=mobile_headers,
        json={
            "identity_id": worker_identity["identity_id"],
            "selected_chat_id": "sess-worker",
            "source": "mobile",
        },
    )
    assert active_response.status_code == 200

    manager_detail = _remote_session_detail_payload("sess-manager")
    manager_detail["name"] = "Manager chat"
    worker_detail = _remote_session_detail_payload("sess-worker")
    worker_detail["name"] = "Worker chat"
    worker_detail["fleet_identity_id"] = worker_identity["identity_id"]
    worker_detail["fleet_identity_role"] = "worker"
    worker_detail["fleet_worker_id"] = worker["worker_id"]
    store.update_shared_snapshot(
        user_id=user["user_id"],
        desktop_id=desktop_login["desktop"]["desktop_id"],
        snapshot={
            "desktop_id": desktop_login["desktop"]["desktop_id"],
            "desktop_name": "Desk",
            "current_session_id": "sess-manager",
            "current_model": "gpt-5",
            "current_variant": "standard",
            "sessions": [
                {
                    **manager_detail,
                    "message_count": 0,
                    "origin_channels": ["app"],
                },
                {
                    **worker_detail,
                    "message_count": 0,
                    "origin_channels": ["app"],
                },
            ],
            "session_details": {
                "sess-manager": manager_detail,
                "sess-worker": worker_detail,
            },
            "jobs": [],
        },
    )

    with client.websocket_connect(f"/ws/remote/mobile?token={mobile_login['session_token']}&client_id=phone-client") as websocket:
        first = websocket.receive_json()
        second = websocket.receive_json()
        app_server.get_channel_sync_hub().publish(
            user_id=user["user_id"],
            event={
                "type": "session_sync",
                "session_id": "sess-manager",
                "payload": {"session": manager_detail, "sessions": []},
            },
        )
        app_server.get_channel_sync_hub().publish(
            user_id=user["user_id"],
            event={
                "type": "session_sync",
                "session_id": "sess-worker",
                "payload": {"session": worker_detail, "sessions": []},
            },
        )
        live_sync = websocket.receive_json()

    assert first["type"] == "session_snapshot"
    assert first["session_id"] == "sess-worker"
    assert second["type"] == "session_sync"
    assert second["session_id"] == "sess-worker"
    assert second["payload"]["session"]["id"] == "sess-worker"
    assert live_sync["type"] == "session_sync"
    assert live_sync["session_id"] == "sess-worker"
    assert live_sync["payload"]["session"]["id"] == "sess-worker"


def test_remote_mobile_websocket_stops_dispatch_after_session_revoked(tmp_path, monkeypatch):
    store, _user, _desktop_login, mobile_login = _paired_remote_session(tmp_path)
    dispatched = []

    async def fake_dispatch(auth, *, command_name, payload):
        dispatched.append({"auth": auth, "command_name": command_name, "payload": payload})
        return {"ok": True}

    monkeypatch.setattr(app_server, "_remote_dispatch_command", fake_dispatch)

    class RevokedMobileWebSocket:
        query_params = {"client_id": "phone-client", "session_id": "sess-phone"}

        def __init__(self):
            self.client_state = app_server.WebSocketState.CONNECTED
            self.application_state = app_server.WebSocketState.CONNECTED
            self.close_code = None
            self.sent = []
            self.received = False

        async def send_json(self, payload):
            self.sent.append(payload)

        async def receive_text(self):
            if self.received:
                raise WebSocketDisconnect(code=1000)
            self.received = True
            store.revoke_session_token(mobile_login["session_token"])
            return json.dumps(
                {
                    "text": "This should not dispatch",
                    "session_id": "sess-phone",
                    "interrupt_policy": "steer_now",
                    "source_format": "app_text",
                }
            )

        async def close(self, code=1000):
            self.close_code = code
            self.application_state = app_server.WebSocketState.DISCONNECTED

    async def scenario():
        websocket = RevokedMobileWebSocket()
        auth = store.resolve_session_token(mobile_login["session_token"])
        with pytest.raises(WebSocketDisconnect) as exc_info:
            await app_server._handle_remote_chat_ws(websocket, auth)
        return websocket, exc_info.value

    websocket, disconnect = asyncio.run(scenario())

    assert disconnect.code == 4401
    assert websocket.close_code == 4401
    assert dispatched == []


def test_remote_mobile_websocket_closes_malformed_json_without_dispatch(tmp_path, monkeypatch):
    store, _user, _desktop_login, mobile_login = _paired_remote_session(tmp_path)
    dispatched = []

    async def fake_dispatch(auth, *, command_name, payload):
        dispatched.append({"auth": auth, "command_name": command_name, "payload": payload})
        return {"ok": True}

    monkeypatch.setattr(app_server, "_remote_dispatch_command", fake_dispatch)

    class MalformedMobileWebSocket:
        query_params = {"client_id": "phone-client", "session_id": "sess-phone"}

        def __init__(self):
            self.client_state = app_server.WebSocketState.CONNECTED
            self.application_state = app_server.WebSocketState.CONNECTED
            self.close_code = None
            self.sent = []
            self.received = False

        async def send_json(self, payload):
            self.sent.append(payload)

        async def receive_text(self):
            if self.received:
                raise WebSocketDisconnect(code=1000)
            self.received = True
            return "{not-json"

        async def close(self, code=1000):
            self.close_code = code
            self.application_state = app_server.WebSocketState.DISCONNECTED

    async def scenario():
        websocket = MalformedMobileWebSocket()
        auth = store.resolve_session_token(mobile_login["session_token"])
        with pytest.raises(WebSocketDisconnect) as exc_info:
            await app_server._handle_remote_chat_ws(websocket, auth)
        return websocket, exc_info.value

    websocket, disconnect = asyncio.run(scenario())

    assert disconnect.code == 4400
    assert websocket.close_code == 4400
    assert dispatched == []


def test_remote_mobile_websocket_closes_oversized_message_without_dispatch(tmp_path, monkeypatch):
    store, _user, _desktop_login, mobile_login = _paired_remote_session(tmp_path)
    dispatched = []
    monkeypatch.setattr(app_server, "REMOTE_WS_MAX_MESSAGE_BYTES", 16)

    async def fake_dispatch(auth, *, command_name, payload):
        dispatched.append({"auth": auth, "command_name": command_name, "payload": payload})
        return {"ok": True}

    monkeypatch.setattr(app_server, "_remote_dispatch_command", fake_dispatch)

    class OversizedMobileWebSocket:
        query_params = {"client_id": "phone-client", "session_id": "sess-phone"}

        def __init__(self):
            self.client_state = app_server.WebSocketState.CONNECTED
            self.application_state = app_server.WebSocketState.CONNECTED
            self.close_code = None
            self.sent = []
            self.received = False

        async def send_json(self, payload):
            self.sent.append(payload)

        async def receive_text(self):
            if self.received:
                raise WebSocketDisconnect(code=1000)
            self.received = True
            return json.dumps({"text": "this message is too large"})

        async def close(self, code=1000):
            self.close_code = code
            self.application_state = app_server.WebSocketState.DISCONNECTED

    async def scenario():
        websocket = OversizedMobileWebSocket()
        auth = store.resolve_session_token(mobile_login["session_token"])
        with pytest.raises(WebSocketDisconnect) as exc_info:
            await app_server._handle_remote_chat_ws(websocket, auth)
        return websocket, exc_info.value

    websocket, disconnect = asyncio.run(scenario())

    assert disconnect.code == 4409
    assert websocket.close_code == 4409
    assert dispatched == []


def test_remote_mobile_command_refuses_revoked_desktop_connection(tmp_path, monkeypatch):
    store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = RemoteDesktopConnectionManager()
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)
    desktop_id = desktop_login["desktop"]["desktop_id"]

    class RecordingWebSocket:
        def __init__(self):
            self.sent = []

        async def send_json(self, payload):
            self.sent.append(payload)

    async def scenario():
        websocket = RecordingWebSocket()
        desktop_auth = store.resolve_session_token(desktop_login["session_token"])
        manager.register(
            user_id=user["user_id"],
            desktop_id=desktop_id,
            websocket=websocket,
            loop=asyncio.get_running_loop(),
            session_token_hash=desktop_auth["session_token_hash"],
        )
        store.mark_desktop_connection(
            user_id=user["user_id"],
            desktop_id=desktop_id,
            status="connected",
            detail="desktop websocket connected",
        )
        mobile_auth = store.resolve_session_token(mobile_login["session_token"])
        store.revoke_session_token(desktop_login["session_token"])

        with pytest.raises(app_server.HTTPException) as exc_info:
            await app_server._remote_dispatch_command(
                mobile_auth,
                command_name="chat_send",
                payload={"text": "Should not reach revoked desktop"},
            )
        return websocket, exc_info.value

    websocket, exc = asyncio.run(scenario())

    assert exc.status_code == 409
    assert "session expired" in str(exc.detail).lower()
    assert websocket.sent == []
    assert manager.get(desktop_id) is None
    desktop = next(item for item in store.list_desktops(user_id=user["user_id"]) if item["desktop_id"] == desktop_id)
    shared_state = store.get_shared_state(user_id=user["user_id"])
    assert desktop["status"] == "offline"
    assert desktop["detail"] == "The paired desktop session expired"
    assert shared_state["desktop_connection"]["desktop_id"] == desktop_id
    assert shared_state["desktop_connection"]["status"] == "offline"
    assert shared_state["desktop_connection"]["detail"] == "The paired desktop session expired"


def test_remote_mobile_dispatch_send_failure_marks_desktop_offline(tmp_path, monkeypatch):
    store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = RemoteDesktopConnectionManager()
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)
    desktop_id = desktop_login["desktop"]["desktop_id"]

    class FailingWebSocket:
        async def send_json(self, payload):
            raise OSError("socket closed")

    async def scenario():
        desktop_auth = store.resolve_session_token(desktop_login["session_token"])
        manager.register(
            user_id=user["user_id"],
            desktop_id=desktop_id,
            websocket=FailingWebSocket(),
            loop=asyncio.get_running_loop(),
            session_token_hash=desktop_auth["session_token_hash"],
        )
        store.mark_desktop_connection(
            user_id=user["user_id"],
            desktop_id=desktop_id,
            status="connected",
            detail="desktop websocket connected",
        )
        mobile_auth = store.resolve_session_token(mobile_login["session_token"])

        with pytest.raises(app_server.HTTPException) as exc_info:
            await app_server._remote_dispatch_command(
                mobile_auth,
                command_name="chat_send",
                payload={"text": "Socket failure should mark offline"},
            )
        return exc_info.value

    exc = asyncio.run(scenario())

    assert exc.status_code == 409
    assert "connection failed" in str(exc.detail).lower()
    assert manager.get(desktop_id) is None
    desktop = next(item for item in store.list_desktops(user_id=user["user_id"]) if item["desktop_id"] == desktop_id)
    shared_state = store.get_shared_state(user_id=user["user_id"])
    assert desktop["status"] == "offline"
    assert desktop["detail"] == "The paired desktop connection failed"
    assert shared_state["desktop_connection"]["desktop_id"] == desktop_id
    assert shared_state["desktop_connection"]["status"] == "offline"
    assert shared_state["desktop_connection"]["detail"] == "The paired desktop connection failed"


def test_remote_mobile_request_send_failure_marks_desktop_offline(tmp_path, monkeypatch):
    store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = RemoteDesktopConnectionManager()
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)
    desktop_id = desktop_login["desktop"]["desktop_id"]

    class FailingWebSocket:
        async def send_json(self, payload):
            raise OSError("socket closed")

    async def scenario():
        desktop_auth = store.resolve_session_token(desktop_login["session_token"])
        manager.register(
            user_id=user["user_id"],
            desktop_id=desktop_id,
            websocket=FailingWebSocket(),
            loop=asyncio.get_running_loop(),
            session_token_hash=desktop_auth["session_token_hash"],
        )
        store.mark_desktop_connection(
            user_id=user["user_id"],
            desktop_id=desktop_id,
            status="connected",
            detail="desktop websocket connected",
        )
        mobile_auth = store.resolve_session_token(mobile_login["session_token"])

        with pytest.raises(app_server.HTTPException) as exc_info:
            await app_server._remote_request_desktop_command(
                mobile_auth,
                command_name="http_request",
                payload={"path": "/api/app/agent/config"},
                timeout_seconds=5,
            )
        return exc_info.value

    exc = asyncio.run(scenario())

    assert exc.status_code == 409
    assert "connection failed" in str(exc.detail).lower()
    assert manager.get(desktop_id) is None
    desktop = next(item for item in store.list_desktops(user_id=user["user_id"]) if item["desktop_id"] == desktop_id)
    shared_state = store.get_shared_state(user_id=user["user_id"])
    assert desktop["status"] == "offline"
    assert desktop["detail"] == "The paired desktop connection failed"
    assert shared_state["desktop_connection"]["desktop_id"] == desktop_id
    assert shared_state["desktop_connection"]["status"] == "offline"
    assert shared_state["desktop_connection"]["detail"] == "The paired desktop connection failed"


def test_fleet_worker_task_dispatch_send_failure_marks_desktop_offline(tmp_path, monkeypatch):
    store, user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    manager = RemoteDesktopConnectionManager()
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)
    desktop_id = desktop_login["desktop"]["desktop_id"]

    class FailingWebSocket:
        async def send_json(self, payload):
            raise OSError("socket closed")

    async def register_failing_desktop():
        desktop_auth = store.resolve_session_token(desktop_login["session_token"])
        manager.register(
            user_id=user["user_id"],
            desktop_id=desktop_id,
            websocket=FailingWebSocket(),
            loop=asyncio.get_running_loop(),
            session_token_hash=desktop_auth["session_token_hash"],
        )

    asyncio.run(register_failing_desktop())
    store.mark_desktop_connection(
        user_id=user["user_id"],
        desktop_id=desktop_id,
        status="connected",
        detail="desktop websocket connected",
    )

    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}
    worker_response = client.post("/api/fleet/workers/local", headers=headers, json={"display_name": "Dispatch Worker"})
    assert worker_response.status_code == 200
    task_response = client.post(
        f"/api/fleet/workers/{worker_response.json()['worker_id']}/tasks",
        headers=headers,
        json={"prompt": "Run through a failing websocket", "source": "manager"},
    )

    assert task_response.status_code == 200
    assert task_response.json()["status"] == "queued"
    assert manager.get(desktop_id) is None
    desktop = next(item for item in store.list_desktops(user_id=user["user_id"]) if item["desktop_id"] == desktop_id)
    shared_state = store.get_shared_state(user_id=user["user_id"])
    assert desktop["status"] == "offline"
    assert desktop["detail"] == "The paired desktop connection failed"
    assert shared_state["desktop_connection"]["status"] == "offline"
    assert shared_state["desktop_connection"]["detail"] == "The paired desktop connection failed"


def test_fleet_worker_stop_send_failure_marks_desktop_offline(tmp_path, monkeypatch):
    store, user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    manager = RemoteDesktopConnectionManager()
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)
    desktop_id = desktop_login["desktop"]["desktop_id"]

    class FailingWebSocket:
        async def send_json(self, payload):
            raise OSError("socket closed")

    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}
    worker_response = client.post("/api/fleet/workers/local", headers=headers, json={"display_name": "Stop Worker"})
    assert worker_response.status_code == 200
    worker = worker_response.json()
    task_response = client.post(
        f"/api/fleet/workers/{worker['worker_id']}/tasks",
        headers=headers,
        json={"prompt": "Long running task", "source": "manager"},
    )
    assert task_response.status_code == 200
    running_response = client.put(
        f"/api/fleet/tasks/{task_response.json()['task_id']}/status",
        headers=headers,
        json={"status": "running"},
    )
    assert running_response.status_code == 200

    async def register_failing_desktop():
        desktop_auth = store.resolve_session_token(desktop_login["session_token"])
        manager.register(
            user_id=user["user_id"],
            desktop_id=desktop_id,
            websocket=FailingWebSocket(),
            loop=asyncio.get_running_loop(),
            session_token_hash=desktop_auth["session_token_hash"],
        )

    asyncio.run(register_failing_desktop())
    store.mark_desktop_connection(
        user_id=user["user_id"],
        desktop_id=desktop_id,
        status="connected",
        detail="desktop websocket connected",
    )

    stop_response = client.post(
        f"/api/fleet/workers/{worker['worker_id']}/stop",
        headers=headers,
        json={"reason": "Stop through a failing websocket"},
    )

    assert stop_response.status_code == 200
    assert stop_response.json()["stopped"] is True
    assert stop_response.json()["live_stop_sent"] is False
    assert manager.get(desktop_id) is None
    desktop = next(item for item in store.list_desktops(user_id=user["user_id"]) if item["desktop_id"] == desktop_id)
    shared_state = store.get_shared_state(user_id=user["user_id"])
    assert desktop["status"] == "offline"
    assert desktop["detail"] == "The paired desktop connection failed"
    assert shared_state["desktop_connection"]["status"] == "offline"
    assert shared_state["desktop_connection"]["detail"] == "The paired desktop connection failed"


def test_remote_mobile_dispatch_send_failure_does_not_mark_replacement_offline(tmp_path, monkeypatch):
    store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = RemoteDesktopConnectionManager()
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)
    desktop_id = desktop_login["desktop"]["desktop_id"]
    replacement_holder = {}

    class ReplacementWebSocket:
        async def send_json(self, payload):
            raise AssertionError("replacement should not receive this command")

    class ReplacedThenFailingWebSocket:
        async def send_json(self, payload):
            desktop_auth = store.resolve_session_token(desktop_login["session_token"])
            replacement_holder["connection"] = manager.register(
                user_id=user["user_id"],
                desktop_id=desktop_id,
                websocket=ReplacementWebSocket(),
                loop=asyncio.get_running_loop(),
                session_token_hash=desktop_auth["session_token_hash"],
            )
            raise OSError("old socket closed")

    async def scenario():
        desktop_auth = store.resolve_session_token(desktop_login["session_token"])
        manager.register(
            user_id=user["user_id"],
            desktop_id=desktop_id,
            websocket=ReplacedThenFailingWebSocket(),
            loop=asyncio.get_running_loop(),
            session_token_hash=desktop_auth["session_token_hash"],
        )
        store.mark_desktop_connection(
            user_id=user["user_id"],
            desktop_id=desktop_id,
            status="connected",
            detail="desktop websocket connected",
        )
        mobile_auth = store.resolve_session_token(mobile_login["session_token"])

        with pytest.raises(app_server.HTTPException) as exc_info:
            await app_server._remote_dispatch_command(
                mobile_auth,
                command_name="chat_send",
                payload={"text": "Old socket failure should not mark replacement offline"},
            )
        return exc_info.value

    exc = asyncio.run(scenario())

    assert exc.status_code == 409
    assert "connection failed" in str(exc.detail).lower()
    assert manager.get(desktop_id) is replacement_holder["connection"]
    desktop = next(item for item in store.list_desktops(user_id=user["user_id"]) if item["desktop_id"] == desktop_id)
    shared_state = store.get_shared_state(user_id=user["user_id"])
    assert desktop["status"] == "connected"
    assert desktop["detail"] == "desktop websocket connected"
    assert shared_state["desktop_connection"]["desktop_id"] == desktop_id
    assert shared_state["desktop_connection"]["status"] == "connected"


def test_remote_mobile_command_repairs_stale_pairing_to_live_desktop(tmp_path, monkeypatch):
    store, user, old_desktop_login, mobile_login = _paired_remote_session(tmp_path)
    replacement_login = store.login(
        email="remote@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Desk",
        device_platform="desktop-electron",
        device_key="replacement-desk-key",
    )
    old_desktop_id = old_desktop_login["desktop"]["desktop_id"]
    replacement_desktop_id = replacement_login["desktop"]["desktop_id"]
    assert old_desktop_id != replacement_desktop_id

    store.update_shared_snapshot(
        user_id=user["user_id"],
        desktop_id=replacement_desktop_id,
        snapshot={
            "desktop_id": replacement_desktop_id,
            "desktop_name": "Desk",
            "current_session_id": "sess-live",
            "current_model": "gpt-5",
            "current_variant": "standard",
            "sessions": [],
            "session_details": {"sess-live": _remote_session_detail_payload("sess-live")},
            "jobs": [],
        },
    )
    manager = _FakeRemoteDesktopManager(
        _remote_session_detail_payload("sess-live"),
        connected_ids={replacement_desktop_id},
    )
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/sessions/sess-live/activate",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
    )
    refreshed_auth = store.resolve_session_token(mobile_login["session_token"])

    assert response.status_code == 200
    assert manager.calls[0]["desktop_id"] == replacement_desktop_id
    assert refreshed_auth["paired_desktop_id"] == replacement_desktop_id


def test_remote_mobile_command_does_not_repair_to_unconfirmed_connected_desktop(tmp_path, monkeypatch):
    store, _user, old_desktop_login, mobile_login = _paired_remote_session(tmp_path)
    old_desktop_id = old_desktop_login["desktop"]["desktop_id"]
    unconfirmed_desktop_id = "dsk_unconfirmed_live"
    assert old_desktop_id != unconfirmed_desktop_id

    manager = _FakeRemoteDesktopManager(
        _remote_session_detail_payload("sess-live"),
        connected_ids={unconfirmed_desktop_id},
    )
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/sessions/sess-live/activate",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
    )
    refreshed_auth = store.resolve_session_token(mobile_login["session_token"])

    assert response.status_code == 409
    assert "offline" in str(response.json()["detail"]).lower()
    assert manager.calls == []
    assert refreshed_auth["paired_desktop_id"] == old_desktop_id


def test_remote_mobile_sleep_runtime_config_proxies_to_paired_desktop(tmp_path, monkeypatch):
    _store, _user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(
        _json_proxy_result(
            {
                "max_concurrent_chats": 4,
                "running_sessions": [],
                "locks": {
                    "interactive_owner_session_id": None,
                    "workspace_write_owner_by_workspace": {},
                },
                "headless_mode_enabled": True,
                "default_sleep_session_by_bot": {"bot-1": "sess-sleep"},
            }
        )
    )
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/runtime/headless",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
        json={"enabled": True, "default_sleep_session_by_bot": {"bot-1": "sess-sleep"}},
    )

    assert response.status_code == 200
    assert response.json()["headless_mode_enabled"] is True
    assert response.json()["default_sleep_session_by_bot"] == {"bot-1": "sess-sleep"}
    assert len(manager.calls) == 1
    call = manager.calls[0]
    assert call["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert call["command_type"] == "http_request"
    assert call["payload"]["method"] == "POST"
    assert call["payload"]["path"] == "/api/app/runtime/headless"
    request_body = json.loads(base64.b64decode(call["payload"]["body_base64"]).decode("utf-8"))
    assert request_body["enabled"] is True
    assert request_body["default_sleep_session_by_bot"] == {"bot-1": "sess-sleep"}


def test_remote_mobile_automation_create_proxies_to_paired_desktop(tmp_path, monkeypatch):
    _store, _user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(
        _json_proxy_result(
            {
                "id": "job-mobile",
                "automation_id": "job-mobile",
                "name": "Daily summary",
                "prompt": "Summarize the day",
                "schedule": "every 5 minutes",
                "enabled": True,
            }
        )
    )
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/automations",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
        json={"name": "Daily summary", "prompt": "Summarize the day", "schedule": "every 5 minutes"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "job-mobile"
    assert len(manager.calls) == 1
    call = manager.calls[0]
    assert call["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert call["command_type"] == "http_request"
    assert call["payload"]["method"] == "POST"
    assert call["payload"]["path"] == "/api/app/automations"
    request_body = json.loads(base64.b64decode(call["payload"]["body_base64"]).decode("utf-8"))
    assert request_body == {"name": "Daily summary", "prompt": "Summarize the day", "schedule": "every 5 minutes"}


def test_remote_automation_detail_reads_cloud_durable_without_local_bridge(tmp_path, monkeypatch):
    store, user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    automation = store.upsert_automation(
        user_id=user["user_id"],
        automation_id="auto-cloud",
        name="Cloud durable automation",
        prompt="Summarize durable state",
        schedule="every 5 minutes",
    )

    def fail_bridge_for_user(user_id):
        raise AssertionError("remote automation detail must not inspect cloud-host local scheduler state")

    monkeypatch.setattr(app_server, "_bridge_for_user", fail_bridge_for_user)

    client = TestClient(app_server.create_app())
    response = client.get(
        "/api/app/automations/auto-cloud",
        headers={"Authorization": f"Bearer {desktop_login['session_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == automation["id"]
    assert response.json()["name"] == "Cloud durable automation"


def test_remote_cron_feed_reads_cloud_events_without_local_bridge(tmp_path, monkeypatch):
    store, user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    event = store.append_automation_event(
        user_id=user["user_id"],
        kind="automation_started",
        event_type="automation_started",
        event_source="test",
        content="Automation started.",
        status="running",
        automation_id="auto-cloud",
    )

    def fail_bridge_for_user(user_id):
        raise AssertionError("remote event feed must not inspect cloud-host local cron feed")

    monkeypatch.setattr(app_server, "_bridge_for_user", fail_bridge_for_user)

    client = TestClient(app_server.create_app())
    response = client.get(
        "/api/app/events",
        headers={"Authorization": f"Bearer {desktop_login['session_token']}"},
    )

    assert response.status_code == 200
    assert response.json()[0]["id"] == event["id"]
    assert response.json()[0]["content"] == "Automation started."


def test_automation_scheduler_actions_reject_direct_remote_session_without_local_scheduler(tmp_path, monkeypatch):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)

    def fail_get_scheduler():
        raise AssertionError("remote sessions must not touch the cloud-host scheduler")

    monkeypatch.setattr(app_server, "get_scheduler", fail_get_scheduler)

    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}
    responses = [
        client.post(
            "/api/app/automations",
            headers=headers,
            json={"name": "Daily summary", "prompt": "Summarize the day", "schedule": "every 5 minutes"},
        ),
        client.post("/api/app/automations/job-cloud/run", headers=headers),
        client.post("/api/app/automations/job-cloud/enable", headers=headers),
        client.post("/api/app/automations/job-cloud/disable", headers=headers),
        client.delete("/api/app/automations/job-cloud", headers=headers),
    ]

    assert [response.status_code for response in responses] == [409, 409, 409, 409, 409]
    assert all("local desktop backend" in response.json()["detail"] for response in responses)


def test_runtime_headless_rejects_direct_remote_session_without_local_bridge(tmp_path, monkeypatch):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)

    def fail_bridge_for_user(user_id):
        raise AssertionError("remote sessions must not configure cloud-host runtime orchestration")

    monkeypatch.setattr(app_server, "_bridge_for_user", fail_bridge_for_user)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/runtime/headless",
        headers={"Authorization": f"Bearer {desktop_login['session_token']}"},
        json={"enabled": True},
    )

    assert response.status_code == 409
    assert "local desktop backend" in response.json()["detail"]


def test_process_wait_stop_rejects_direct_remote_session_without_local_process_control(tmp_path, monkeypatch):
    store, user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    wait = store.upsert_process_wait(
        user_id=user["user_id"],
        command_id="cmd-stop",
        session_id="sess-1",
        pid=12345,
        command="python worker.py",
    )

    def fail_subprocess_run(*args, **kwargs):
        raise AssertionError("remote sessions must not kill cloud-host processes")

    monkeypatch.setattr(app_server.subprocess, "run", fail_subprocess_run)

    client = TestClient(app_server.create_app())
    response = client.post(
        f"/api/app/events/process-waits/{wait['process_wait_id']}/stop",
        headers={"Authorization": f"Bearer {desktop_login['session_token']}"},
        json={"reason": "stop from remote"},
    )

    assert response.status_code == 409
    assert "local desktop backend" in response.json()["detail"]


def test_screenshot_rejects_direct_remote_session_without_cloud_capture(tmp_path, monkeypatch):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)

    def fail_capture_screen_snapshot(**kwargs):
        raise AssertionError("remote sessions must not capture the cloud-host screen")

    monkeypatch.setattr(app_server, "_capture_screen_snapshot", fail_capture_screen_snapshot)

    client = TestClient(app_server.create_app())
    response = client.get(
        "/api/app/screenshot/current",
        headers={"Authorization": f"Bearer {desktop_login['session_token']}"},
    )

    assert response.status_code == 409
    assert "local desktop backend" in response.json()["detail"]


def test_remote_mobile_workspace_git_info_proxies_to_paired_desktop(tmp_path, monkeypatch):
    _store, _user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(
        _json_proxy_result(
            {
                "requestedPath": "C:/work/app",
                "resolvedPath": "C:/work/app",
                "repoRoot": "C:/work/app",
                "isGitRepo": True,
                "currentBranch": "main",
                "branches": ["main", "feature/mobile"],
                "error": None,
            }
        )
    )
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.get(
        "/api/app/workspace/git?path=C%3A%2Fwork%2Fapp",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["currentBranch"] == "main"
    assert len(manager.calls) == 1
    call = manager.calls[0]
    assert call["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert call["command_type"] == "http_request"
    assert call["payload"]["method"] == "GET"
    assert call["payload"]["path"] == "/api/app/workspace/git"
    assert call["payload"]["query_string"] == "path=C%3A%2Fwork%2Fapp"


def test_remote_mobile_workspace_git_checkout_proxies_to_paired_desktop(tmp_path, monkeypatch):
    _store, _user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(
        _json_proxy_result(
            {
                "requestedPath": "C:/work/app",
                "resolvedPath": "C:/work/app",
                "repoRoot": "C:/work/app",
                "isGitRepo": True,
                "currentBranch": "feature/mobile",
                "branches": ["main", "feature/mobile"],
                "error": None,
            }
        )
    )
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/workspace/git/checkout",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
        json={"path": "C:/work/app", "branch": "feature/mobile"},
    )

    assert response.status_code == 200
    assert response.json()["currentBranch"] == "feature/mobile"
    assert len(manager.calls) == 1
    call = manager.calls[0]
    assert call["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert call["command_type"] == "http_request"
    assert call["payload"]["method"] == "POST"
    assert call["payload"]["path"] == "/api/app/workspace/git/checkout"
    request_body = json.loads(base64.b64decode(call["payload"]["body_base64"]).decode("utf-8"))
    assert request_body == {"path": "C:/work/app", "branch": "feature/mobile"}


def test_remote_mobile_telegram_bot_create_proxies_to_paired_desktop(tmp_path, monkeypatch):
    _store, _user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(
        _json_proxy_result(
            {
                "id": "bot-mobile",
                "label": "Mobile Bot",
                "bot_token": "123456:mobile-token",
                "is_default": False,
            }
        )
    )
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/telegram-bots",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
        json={"label": "Mobile Bot", "bot_token": "123456:mobile-token"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "bot-mobile"
    assert len(manager.calls) == 1
    call = manager.calls[0]
    assert call["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert call["command_type"] == "http_request"
    assert call["payload"]["method"] == "POST"
    assert call["payload"]["path"] == "/api/app/telegram-bots"
    request_body = json.loads(base64.b64decode(call["payload"]["body_base64"]).decode("utf-8"))
    assert request_body == {"label": "Mobile Bot", "bot_token": "123456:mobile-token"}


def test_telegram_bot_config_rejects_direct_remote_session_without_local_bridge(tmp_path, monkeypatch):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)

    def fail_bridge_for_user(user_id):
        raise AssertionError("remote sessions must not read local Telegram bot config on the cloud backend")

    monkeypatch.setattr(app_server, "_bridge_for_user", fail_bridge_for_user)

    client = TestClient(app_server.create_app())
    response = client.get(
        "/api/app/telegram-bots",
        headers={"Authorization": f"Bearer {desktop_login['session_token']}"},
    )

    assert response.status_code == 409
    assert "local desktop backend" in response.json()["detail"]


def test_telegram_bot_config_create_is_rate_limited(tmp_path, monkeypatch):
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    created = []

    class FakeBridge:
        def create_telegram_bot_config(self, *, label, bot_token):
            created.append({"label": label, "bot_token": bot_token})
            return {
                "id": f"bot-{len(created)}",
                "label": label,
                "bot_token": bot_token,
                "is_default": len(created) == 1,
            }

    monkeypatch.setattr(app_server, "_resolve_token", lambda _authorization: {"user_id": 1})
    monkeypatch.setattr(app_server, "_bridge_for_user", lambda _user_id: FakeBridge())

    client = TestClient(app_server.create_app())
    payload = {"label": "Mobile Bot", "bot_token": "123456:mobile-token"}
    statuses = [
        client.post("/api/app/telegram-bots", headers={"Authorization": "Bearer local"}, json=payload).status_code
        for _ in range(app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS)
    ]
    limited = client.post("/api/app/telegram-bots", headers={"Authorization": "Bearer local"}, json=payload)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()

    assert statuses == [200] * app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS
    assert limited.status_code == 429
    assert len(created) == app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS


def test_remote_mobile_workspace_restore_proxies_to_paired_desktop(tmp_path, monkeypatch):
    _store, _user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(
        _json_proxy_result(
            {
                "ok": True,
                "restored_path": "C:/work/app",
                "restored_files": [{"path": "README.md"}],
                "missing_original_files": [],
                "conflict_count": 0,
            }
        )
    )
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/workspace/restore",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
        json={"workspace_id": "workspace-1", "local_path": "C:/work/app", "machine_id": "desktop-1"},
    )

    assert response.status_code == 200
    assert response.json()["restored_path"] == "C:/work/app"
    assert len(manager.calls) == 1
    call = manager.calls[0]
    assert call["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert call["command_type"] == "http_request"
    assert call["payload"]["method"] == "POST"
    assert call["payload"]["path"] == "/api/app/workspace/restore"
    request_body = json.loads(base64.b64decode(call["payload"]["body_base64"]).decode("utf-8"))
    assert request_body == {"workspace_id": "workspace-1", "local_path": "C:/work/app", "machine_id": "desktop-1"}


def test_workspace_restore_rejects_direct_remote_session_without_restoring_files(tmp_path, monkeypatch):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    restore_calls = []

    def fake_restore_cloud_workspace_files(**kwargs):
        restore_calls.append(kwargs)
        raise AssertionError("direct remote sessions must not restore files on the cloud host")

    monkeypatch.setattr(app_server, "restore_cloud_workspace_files", fake_restore_cloud_workspace_files)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/workspace/restore",
        headers={"Authorization": f"Bearer {desktop_login['session_token']}"},
        json={
            "workspace_id": "workspace-1",
            "local_path": str(tmp_path / "restored"),
            "machine_id": "desktop-1",
        },
    )

    assert response.status_code == 409
    assert "local desktop backend" in response.json()["detail"]
    assert restore_calls == []


def test_remote_mobile_upload_proxies_multipart_body_to_paired_desktop(tmp_path, monkeypatch):
    _store, _user, _desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(
        _json_proxy_result(
            {
                "upload_id": "upl_remote",
                "filename": "note.txt",
                "accepted": True,
                "session_id": "sess-1",
                "attached": True,
            }
        )
    )
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/upload?session_id=sess-1",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
        files={"file": ("note.txt", b"hello desktop", "text/plain")},
    )

    assert response.status_code == 200
    assert response.json()["upload_id"] == "upl_remote"
    call = manager.calls[0]
    assert call["payload"]["method"] == "POST"
    assert call["payload"]["path"] == "/api/app/upload"
    assert call["payload"]["query_string"] == "session_id=sess-1"
    assert call["payload"]["headers"]["content-type"].startswith("multipart/form-data")
    assert b"hello desktop" in base64.b64decode(call["payload"]["body_base64"])


def test_remote_mobile_session_artifacts_proxy_to_paired_desktop(tmp_path, monkeypatch):
    _store, _user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(
        _json_proxy_result(
            [
                {
                    "artifact_id": "art-1",
                    "title": "Note",
                    "artifact_kind": "text",
                    "source_kind": "tool",
                    "created_at": "2026-05-31T00:00:00Z",
                    "mime_type": "text/plain",
                    "size_bytes": 5,
                }
            ]
        )
    )
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.get(
        "/api/app/sessions/sess-1/artifacts",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
    )

    assert response.status_code == 200
    assert response.json()[0]["artifact_id"] == "art-1"
    call = manager.calls[0]
    assert call["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert call["command_type"] == "http_request"
    assert call["payload"]["method"] == "GET"
    assert call["payload"]["path"] == "/api/app/sessions/sess-1/artifacts"


def test_session_artifacts_reject_direct_remote_session_without_local_bridge(tmp_path, monkeypatch):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)

    def fail_bridge_for_user(user_id):
        raise AssertionError("remote sessions must not read desktop artifacts on the cloud backend")

    monkeypatch.setattr(app_server, "_bridge_for_user", fail_bridge_for_user)

    client = TestClient(app_server.create_app())
    response = client.get(
        "/api/app/sessions/sess-1/artifacts",
        headers={"Authorization": f"Bearer {desktop_login['session_token']}"},
    )

    assert response.status_code == 409
    assert "local desktop backend" in response.json()["detail"]


def test_app_upload_rejects_direct_remote_session_without_local_runtime(tmp_path, monkeypatch):
    _store, _user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)

    def fail_bridge_for_user(user_id):
        raise AssertionError("remote sessions must not attach files on the cloud backend")

    monkeypatch.setattr(app_server, "_bridge_for_user", fail_bridge_for_user)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/app/upload?session_id=sess-1",
        headers={"Authorization": f"Bearer {desktop_login['session_token']}"},
        files={"file": ("note.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 409
    assert "local desktop backend" in response.json()["detail"]


def test_app_upload_is_rate_limited(tmp_path, monkeypatch):
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    attached_files = []

    class FakeSessionManager:
        def get_current_session_id(self):
            return "sess-rate"

    class FakeRuntime:
        session_manager = FakeSessionManager()

    class FakeBridge:
        def attach_pending_file(self, *, runtime, filename, content_type, data):
            attached_files.append(
                {
                    "runtime": runtime,
                    "filename": filename,
                    "content_type": content_type,
                    "data": data,
                }
            )

    monkeypatch.setattr(app_server, "_resolve_token", lambda _authorization: {"user_id": 1})
    monkeypatch.setattr(app_server, "_bridge_for_user", lambda _user_id: FakeBridge())
    monkeypatch.setattr(app_server, "_load_runtime_session_or_409", lambda _bridge, _session_id=None: FakeRuntime())

    client = TestClient(app_server.create_app())
    statuses = [
        client.post(
            "/api/app/upload?session_id=sess-rate",
            headers={"Authorization": "Bearer local"},
            files={"file": (f"note-{index}.txt", b"hello", "text/plain")},
        ).status_code
        for index in range(app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS)
    ]
    limited = client.post(
        "/api/app/upload?session_id=sess-rate",
        headers={"Authorization": "Bearer local"},
        files={"file": ("limited.txt", b"hello", "text/plain")},
    )
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()

    assert statuses == [200] * app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS
    assert limited.status_code == 429
    assert len(attached_files) == app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS
    assert attached_files[0]["filename"] == "note-0.txt"


def test_remote_mobile_voice_status_stays_local_disabled_and_not_proxied(tmp_path, monkeypatch):
    _store, _user, _desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = _FakeRemoteDesktopManager(_json_proxy_result({"ok": False}))
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    client = TestClient(app_server.create_app())
    response = client.get(
        "/api/app/voice/status",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["selected_engine_state"] == "disabled"
    assert response.json()["input_ok"] is False
    assert manager.calls == []


def test_remote_auth_logout_revokes_current_session(tmp_path):
    _store, _user, _desktop_login, mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {mobile_login['session_token']}"}

    logout = client.post("/api/remote/auth/logout", headers=headers)
    profile = client.get("/api/remote/account/me", headers=headers)

    assert logout.status_code == 200
    assert logout.json()["revoked"] is True
    assert logout.json()["disconnected_desktop"] is False
    assert profile.status_code == 401


def test_remote_desktop_logout_disconnects_matching_live_socket(tmp_path, monkeypatch):
    store, user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    manager = RemoteDesktopConnectionManager()
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)
    desktop_id = desktop_login["desktop"]["desktop_id"]

    class LogoutWebSocket:
        def __init__(self):
            self.close_code = None

        async def send_json(self, payload):
            raise AssertionError("logout should not send commands")

        async def close(self, code=1000):
            self.close_code = code

    websocket = LogoutWebSocket()

    async def register_connection():
        auth = store.resolve_session_token(desktop_login["session_token"])
        manager.register(
            user_id=user["user_id"],
            desktop_id=desktop_id,
            websocket=websocket,
            loop=asyncio.get_running_loop(),
            session_token_hash=auth["session_token_hash"],
        )

    asyncio.run(register_connection())

    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}
    logout = client.post("/api/remote/auth/logout", headers=headers)
    profile = client.get("/api/remote/account/me", headers=headers)
    desktop = next(item for item in store.list_desktops(user_id=user["user_id"]) if item["desktop_id"] == desktop_id)

    assert logout.status_code == 200
    assert logout.json()["revoked"] is True
    assert logout.json()["disconnected_desktop"] is True
    assert profile.status_code == 401
    assert manager.get(desktop_id) is None
    assert websocket.close_code == 4401
    assert desktop["status"] == "offline"
    assert desktop["detail"] == "desktop session logged out"


def test_remote_desktop_logout_does_not_disconnect_replacement_socket(tmp_path, monkeypatch):
    store, user, desktop_login, _mobile_login = _paired_remote_session(tmp_path)
    replacement_login = store.login(
        email="remote@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Desk",
        device_platform="desktop-electron",
        device_key="desk-key",
    )
    manager = RemoteDesktopConnectionManager()
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)
    desktop_id = desktop_login["desktop"]["desktop_id"]
    assert replacement_login["desktop"]["desktop_id"] == desktop_id

    class ReplacementWebSocket:
        def __init__(self):
            self.close_code = None

        async def send_json(self, payload):
            raise AssertionError("logout should not send commands")

        async def close(self, code=1000):
            self.close_code = code

    websocket = ReplacementWebSocket()

    async def register_connection():
        auth = store.resolve_session_token(replacement_login["session_token"])
        manager.register(
            user_id=user["user_id"],
            desktop_id=desktop_id,
            websocket=websocket,
            loop=asyncio.get_running_loop(),
            session_token_hash=auth["session_token_hash"],
        )

    asyncio.run(register_connection())

    client = TestClient(app_server.create_app())
    old_headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}
    replacement_headers = {"Authorization": f"Bearer {replacement_login['session_token']}"}
    logout = client.post("/api/remote/auth/logout", headers=old_headers)
    old_profile = client.get("/api/remote/account/me", headers=old_headers)
    replacement_profile = client.get("/api/remote/account/me", headers=replacement_headers)

    assert logout.status_code == 200
    assert logout.json()["revoked"] is True
    assert logout.json()["disconnected_desktop"] is False
    assert old_profile.status_code == 401
    assert replacement_profile.status_code == 200
    assert manager.get(desktop_id) is not None
    assert websocket.close_code is None


def test_remote_account_profile_endpoint_persists_sanitized_profile(tmp_path):
    store, user, _desktop_login, mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {mobile_login['session_token']}"}

    initial = client.get("/api/remote/account/profile", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["profile"]["schema_version"] == 1

    updated = client.put(
        "/api/remote/account/profile",
        headers=headers,
        json={
            "profile": {
                "preferences": {
                    "verbose_mode": True,
                    "interrupt_policy_default": "steer_now",
                },
                "integrations": {
                    "telegram": {
                        "allowed_user_ids": "12345, +67890, nope",
                        "bots": [{"id": "default", "label": "Default", "bot_token": "plaintext-token"}],
                    },
                },
            },
        },
    )
    me = client.get("/api/remote/account/me", headers=headers)

    assert updated.status_code == 200
    saved_profile = updated.json()["profile"]
    assert saved_profile["preferences"]["verbose_mode"] is True
    assert saved_profile["preferences"]["interrupt_policy_default"] == "steer_now"
    assert saved_profile["integrations"]["telegram"]["allowed_user_ids"] == ["12345", "67890"]
    assert "bot_token" not in saved_profile["integrations"]["telegram"]["bots"][0]
    assert me.status_code == 200
    assert me.json()["profile"] == saved_profile
    assert store.get_user_profile(user_id=user["user_id"]) == saved_profile


def test_remote_account_data_delete_resets_profile_secrets_and_shared_state(tmp_path, monkeypatch):
    store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    manager = RemoteDesktopConnectionManager()
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)
    desktop_id = desktop_login["desktop"]["desktop_id"]
    loop = asyncio.new_event_loop()

    class DummyDesktopWebSocket:
        def __init__(self):
            self.close_code = None

        async def send_json(self, payload):
            raise AssertionError("reset should disconnect before sending commands")

        async def close(self, code=1000):
            self.close_code = code

    websocket = DummyDesktopWebSocket()
    desktop_auth = store.resolve_session_token(desktop_login["session_token"])
    manager.register(
        user_id=user["user_id"],
        desktop_id=desktop_id,
        websocket=websocket,
        loop=loop,
        session_token_hash=desktop_auth["session_token_hash"],
    )
    client = TestClient(app_server.create_app())
    headers = {"Authorization": f"Bearer {mobile_login['session_token']}"}
    desktop_headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}
    store.create_pairing(user_id=user["user_id"], desktop_id=desktop_id)
    store.update_user_profile(user_id=user["user_id"], profile={"preferences": {"verbose_mode": True}})
    store.upsert_user_secrets(
        user_id=user["user_id"],
        namespace="setup",
        secrets_payload={"OPENAI_API_KEY": "sk-delete-secret"},
    )
    store.update_shared_snapshot(
        user_id=user["user_id"],
        desktop_id=desktop_login["desktop"]["desktop_id"],
        snapshot={"current_session_id": "sess-1", "sessions": [{"id": "sess-1"}]},
    )

    rejected = client.delete("/api/remote/account/data", headers=headers)
    confirmation = client.post(
        "/api/app/confirmations",
        headers=headers,
        json={
            "action_kind": "remote_account_data_delete",
            "title": "Delete account data?",
            "message": "Test confirmation",
            "risk_tier": "danger",
            "origin_surface": "test",
        },
    )
    assert confirmation.status_code == 200
    approved = client.post(
        f"/api/app/confirmations/{confirmation.json()['confirmation_id']}/approve",
        headers=headers,
        json={"decided_by_surface": "test"},
    )
    assert approved.status_code == 200

    deleted = client.delete(
        "/api/remote/account/data",
        headers={**headers, "X-EmploAI-Confirmation-Id": approved.json()["confirmation_id"]},
    )
    profile = client.get("/api/remote/account/profile", headers=headers)
    secrets = client.get("/api/remote/account/secrets", headers=headers)
    mobile_me = client.get("/api/remote/account/me", headers=headers)
    desktop_me = client.get("/api/remote/account/me", headers=desktop_headers)

    assert rejected.status_code == 409
    assert rejected.json()["detail"]["error_type"] == "confirmation_required"
    assert deleted.status_code == 200
    assert deleted.json()["deleted_secrets"] == 1
    assert deleted.json()["revoked_sessions"] == 1
    assert deleted.json()["revoked_pairings"] == 1
    assert deleted.json()["unpaired_mobiles"] == 1
    assert deleted.json()["reset_desktops"] == 1
    assert deleted.json()["disconnected_desktops"] == 1
    assert deleted.json()["profile_reset"] is True
    assert profile.status_code == 200
    assert profile.json()["profile"]["preferences"]["verbose_mode"] is False
    assert secrets.status_code == 200
    assert secrets.json()["items"] == []
    assert mobile_me.status_code == 200
    assert mobile_me.json()["mobile"]["paired_desktop_id"] is None
    assert desktop_me.status_code == 401
    assert manager.get(desktop_id) is None
    assert websocket.close_code == 4401
    assert store.get_shared_state(user_id=user["user_id"])["sessions"] == []
    loop.close()


def test_remote_google_auth_flow_creates_session(tmp_path, monkeypatch):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")

    async def fake_exchange(code):
        assert code == "google-code"
        return {"id_token": "verified-id-token"}

    def fake_verify(id_token):
        assert id_token == "verified-id-token"
        return {
            "iss": "https://accounts.google.com",
            "sub": "google-sub-api",
            "email": "google-api@example.com",
            "email_verified": True,
            "name": "Google API",
            "picture": "https://example.invalid/profile.png",
        }

    monkeypatch.setattr(app_server, "_exchange_google_oauth_code", fake_exchange)
    monkeypatch.setattr(app_server, "_verify_google_id_token", fake_verify)

    client = TestClient(app_server.create_app())
    started = client.post(
        "/api/remote/auth/google/start",
        json={
            "actor_kind": "mobile",
            "device_name": "Phone",
            "device_platform": "android",
            "device_key": "phone-google-api",
        },
    )
    assert started.status_code == 200
    start_payload = started.json()
    state = parse_qs(urlparse(start_payload["auth_url"]).query)["state"][0]

    pending = client.post(
        "/api/remote/auth/google/poll",
        json={"request_id": start_payload["request_id"], "poll_token": start_payload["poll_token"]},
    )
    callback = client.get(f"/api/remote/auth/google/callback?state={state}&code=google-code")
    completed = client.post(
        "/api/remote/auth/google/poll",
        json={"request_id": start_payload["request_id"], "poll_token": start_payload["poll_token"]},
    )
    repeated = client.post(
        "/api/remote/auth/google/poll",
        json={"request_id": start_payload["request_id"], "poll_token": start_payload["poll_token"]},
    )

    assert pending.status_code == 200
    assert pending.json()["status"] == "pending"
    assert callback.status_code == 200
    assert "Google sign-in complete" in callback.text
    assert completed.status_code == 200
    completed_payload = completed.json()
    assert completed_payload["status"] == "complete"
    assert completed_payload["session_token"]
    assert completed_payload["user"]["email"] == "google-api@example.com"
    assert completed_payload["mobile"]["device_name"] == "Phone"
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "expired"

    me = client.get("/api/remote/account/me", headers={"Authorization": f"Bearer {completed_payload['session_token']}"})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "google-api@example.com"


def test_remote_google_callback_rejects_unknown_state_before_exchange(tmp_path, monkeypatch):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")
    exchange_calls = []

    async def fake_exchange(code):
        exchange_calls.append(code)
        raise AssertionError("unknown callback state should not exchange a Google code")

    monkeypatch.setattr(app_server, "_exchange_google_oauth_code", fake_exchange)

    client = TestClient(app_server.create_app())
    response = client.get("/api/remote/auth/google/callback?state=not-a-real-state&code=google-code")

    assert response.status_code == 200
    assert "not recognized" in response.text
    assert exchange_calls == []


def test_remote_google_auth_start_is_rate_limited(tmp_path, monkeypatch):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")

    client = TestClient(app_server.create_app())
    payload = {
        "actor_kind": "mobile",
        "device_name": "Phone",
        "device_platform": "android",
        "device_key": "rate-limit-phone",
    }

    statuses = [
        client.post("/api/remote/auth/google/start", json=payload).status_code
        for _ in range(app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS)
    ]
    limited = client.post("/api/remote/auth/google/start", json=payload)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()

    assert statuses == [200] * app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS
    assert limited.status_code == 429


def test_remote_google_auth_poll_allows_normal_browser_sign_in_wait(tmp_path, monkeypatch):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "client-secret")

    client = TestClient(app_server.create_app())
    started = client.post(
        "/api/remote/auth/google/start",
        json={
            "actor_kind": "mobile",
            "device_name": "Phone",
            "device_platform": "android",
            "device_key": "poll-budget-phone",
        },
    )
    assert started.status_code == 200
    payload = started.json()

    statuses = [
        client.post(
            "/api/remote/auth/google/poll",
            json={"request_id": payload["request_id"], "poll_token": payload["poll_token"]},
        ).status_code
        for _ in range(app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS + 5)
    ]
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()

    assert statuses == [200] * (app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS + 5)


def test_remote_register_rate_limit_has_client_wide_bucket(tmp_path, monkeypatch):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    monkeypatch.setenv(app_server.AUTH_EMAIL_BACKEND_ENV, "console")

    client = TestClient(app_server.create_app())
    statuses = [
        client.post(
            "/api/remote/auth/register",
            json={"email": f"user-{index}@example.com", "password": "CorrectHorse!2026"},
        ).status_code
        for index in range(app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS)
    ]
    limited = client.post(
        "/api/remote/auth/register",
        json={"email": "extra@example.com", "password": "CorrectHorse!2026"},
    )
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()

    assert statuses == [200] * app_server.REMOTE_AUTH_RATE_LIMIT_MAX_ATTEMPTS
    assert limited.status_code == 429


def test_remote_email_password_auth_requires_otp_before_session(tmp_path, monkeypatch):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    store = app_server._remote_control_store
    sent_codes = []

    async def capture_otp_email(email: str, code: str, purpose: str) -> None:
        sent_codes.append({"email": email, "code": code, "purpose": purpose})

    monkeypatch.setattr(app_server, "_send_remote_auth_otp_email", capture_otp_email)

    client = TestClient(app_server.create_app())
    signup = client.post(
        "/api/remote/auth/register",
        json={
            "email": "otp-api@example.com",
            "password": "BetterPass!2026",
            "display_name": "OTP API",
            "actor_kind": "mobile",
            "device_name": "Phone",
            "device_platform": "android",
            "device_key": "otp-api-phone",
            "remember_me": True,
        },
    )
    assert signup.status_code == 200
    signup_payload = signup.json()
    assert signup_payload["status"] == "otp_required"
    assert signup_payload["purpose"] == "signup_verify"
    assert "session_token" not in signup_payload
    assert "otp_code" not in signup_payload
    assert sent_codes[-1]["email"] == "otp-api@example.com"
    assert sent_codes[-1]["purpose"] == "signup_verify"
    assert store._conn.execute(
        "SELECT user_id FROM users WHERE email = ?",
        ("otp-api@example.com",),
    ).fetchone() is None

    unverified_login = client.post(
        "/api/remote/auth/login",
        json={
            "email": "otp-api@example.com",
            "password": "BetterPass!2026",
            "actor_kind": "desktop",
            "device_name": "Desk",
            "device_platform": "desktop",
            "device_key": "otp-api-unverified-desk",
        },
    )
    assert unverified_login.status_code == 400
    assert "Finish account verification" in unverified_login.json()["detail"]

    bad_code = client.post(
        "/api/remote/auth/otp/verify",
        json={"challenge_id": signup_payload["challenge_id"], "code": "000000"},
    )
    assert bad_code.status_code == 400

    verified = client.post(
        "/api/remote/auth/otp/verify",
        json={"challenge_id": signup_payload["challenge_id"], "code": sent_codes[-1]["code"]},
    )
    assert verified.status_code == 200
    verified_payload = verified.json()
    assert verified_payload["session_token"]
    assert verified_payload["remember_me"] is True
    assert verified_payload["user"]["email_verified_at"]
    assert store._conn.execute(
        "SELECT user_id, email_verified_at FROM users WHERE email = ? AND email_verified_at IS NOT NULL",
        ("otp-api@example.com",),
    ).fetchone() is not None

    login = client.post(
        "/api/remote/auth/login",
        json={
            "email": "otp-api@example.com",
            "password": "BetterPass!2026",
            "actor_kind": "desktop",
            "device_name": "Desk",
            "device_platform": "desktop",
            "device_key": "otp-api-desk",
            "remember_me": False,
        },
    )
    assert login.status_code == 200
    login_payload = login.json()
    assert login_payload["purpose"] == "login_verify"
    assert sent_codes[-1]["purpose"] == "login_verify"
    login_code = sent_codes[-1]["code"]

    resend_too_soon = client.post(
        "/api/remote/auth/otp/resend",
        json={"challenge_id": login_payload["challenge_id"]},
    )
    assert resend_too_soon.status_code == 400
    assert "Wait" in resend_too_soon.json()["detail"]

    app_server._remote_control_store._conn.execute(
        "UPDATE auth_otp_challenges SET resend_available_at = ? WHERE challenge_id = ?",
        (time.time() - 1, login_payload["challenge_id"]),
    )
    app_server._remote_control_store._conn.commit()

    resent = client.post(
        "/api/remote/auth/otp/resend",
        json={"challenge_id": login_payload["challenge_id"]},
    )
    assert resent.status_code == 200
    resent_payload = resent.json()
    assert resent_payload["status"] == "otp_required"
    assert resent_payload["challenge_id"] != login_payload["challenge_id"]
    assert resent_payload["resend_available_in_seconds"] > 0
    assert sent_codes[-1]["email"] == "otp-api@example.com"
    assert sent_codes[-1]["purpose"] == "login_verify"

    old_challenge = client.post(
        "/api/remote/auth/otp/verify",
        json={"challenge_id": login_payload["challenge_id"], "code": login_code},
    )
    assert old_challenge.status_code == 400

    logged_in = client.post(
        "/api/remote/auth/otp/verify",
        json={"challenge_id": resent_payload["challenge_id"], "code": sent_codes[-1]["code"]},
    )
    assert logged_in.status_code == 200
    assert logged_in.json()["remember_me"] is False
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()


def test_remote_email_password_auth_allows_reclaiming_unverified_signup(tmp_path, monkeypatch):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    store = app_server._remote_control_store
    sent_codes = []

    async def capture_otp_email(email: str, code: str, purpose: str) -> None:
        sent_codes.append({"email": email, "code": code, "purpose": purpose})

    monkeypatch.setattr(app_server, "_send_remote_auth_otp_email", capture_otp_email)

    client = TestClient(app_server.create_app())
    first = client.post(
        "/api/remote/auth/register",
        json={
            "email": "otp-reclaim-api@example.com",
            "password": "FirstBetterPass!2026",
            "display_name": "First Pending",
            "actor_kind": "mobile",
            "device_name": "First Phone",
            "device_platform": "android",
            "device_key": "otp-reclaim-api-first",
        },
    )
    assert first.status_code == 200
    first_payload = first.json()
    first_code = sent_codes[-1]["code"]
    assert store._conn.execute(
        "SELECT user_id FROM users WHERE email = ?",
        ("otp-reclaim-api@example.com",),
    ).fetchone() is None

    second = client.post(
        "/api/remote/auth/register",
        json={
            "email": "otp-reclaim-api@example.com",
            "password": "SecondBetterPass!2026",
            "display_name": "Second Pending",
            "actor_kind": "desktop",
            "device_name": "Second Desk",
            "device_platform": "desktop",
            "device_key": "otp-reclaim-api-second",
        },
    )
    assert second.status_code == 200
    second_payload = second.json()
    second_code = sent_codes[-1]["code"]
    assert store._conn.execute(
        "SELECT user_id FROM users WHERE email = ?",
        ("otp-reclaim-api@example.com",),
    ).fetchone() is None

    stale_verify = client.post(
        "/api/remote/auth/otp/verify",
        json={"challenge_id": first_payload["challenge_id"], "code": first_code},
    )
    assert stale_verify.status_code == 400
    assert "expired" in stale_verify.json()["detail"].lower()

    verified = client.post(
        "/api/remote/auth/otp/verify",
        json={"challenge_id": second_payload["challenge_id"], "code": second_code},
    )
    assert verified.status_code == 200
    verified_payload = verified.json()
    assert verified_payload["user"]["display_name"] == "Second Pending"
    assert verified_payload["desktop"]["device_key"] == "otp-reclaim-api-second"

    old_password = client.post(
        "/api/remote/auth/login",
        json={
            "email": "otp-reclaim-api@example.com",
            "password": "FirstBetterPass!2026",
            "actor_kind": "mobile",
        },
    )
    assert old_password.status_code == 400

    new_password = client.post(
        "/api/remote/auth/login",
        json={
            "email": "otp-reclaim-api@example.com",
            "password": "SecondBetterPass!2026",
            "actor_kind": "mobile",
        },
    )
    assert new_password.status_code == 200
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()


def test_remote_email_password_auth_invalidates_challenge_when_email_delivery_fails(tmp_path, monkeypatch):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()
    store = app_server._remote_control_store

    async def fail_otp_email(email: str, code: str, purpose: str) -> None:
        raise RuntimeError("email backend unavailable")

    monkeypatch.setattr(app_server, "_send_remote_auth_otp_email", fail_otp_email)

    client = TestClient(app_server.create_app())
    response = client.post(
        "/api/remote/auth/register",
        json={
            "email": "otp-fail@example.com",
            "password": "BetterPass!2026",
            "display_name": "OTP Fail",
            "actor_kind": "mobile",
            "device_name": "Phone",
            "device_platform": "android",
            "device_key": "otp-fail-phone",
            "remember_me": True,
        },
    )
    rows = store._conn.execute(
        "SELECT challenge_id, consumed_at, replaced_at FROM auth_otp_challenges WHERE email = ?",
        ("otp-fail@example.com",),
    ).fetchall()

    assert response.status_code == 503
    assert "email backend unavailable" in response.json()["detail"]
    assert len(rows) == 1
    assert rows[0]["consumed_at"] is None
    assert rows[0]["replaced_at"] is not None
    assert store._conn.execute(
        "SELECT user_id FROM users WHERE email = ?",
        ("otp-fail@example.com",),
    ).fetchone() is None
    with pytest.raises(ValueError, match="expired"):
        store.resend_auth_otp(challenge_id=rows[0]["challenge_id"])
    app_server._REMOTE_AUTH_RATE_LIMIT.clear()


def test_remote_account_secrets_are_encrypted_and_desktop_reveal_only(tmp_path):
    store, user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    mobile_headers = {"Authorization": f"Bearer {mobile_login['session_token']}"}
    desktop_headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}

    saved = client.put(
        "/api/remote/account/secrets",
        headers=mobile_headers,
        json={
            "namespace": "setup",
            "secrets": {
                "OPENAI_API_KEY": "sk-live-secret",
                "TELEGRAM_BOT_TOKEN": "123456:bot-secret",
            },
            "metadata": {"OPENAI_API_KEY": {"label": "OpenAI API key", "token": "strip-me"}},
        },
    )
    listed = client.get("/api/remote/account/secrets?namespace=setup", headers=mobile_headers)
    mobile_reveal = client.post(
        "/api/remote/account/secrets/reveal",
        headers=mobile_headers,
        json={"namespace": "setup", "names": ["OPENAI_API_KEY"]},
    )
    desktop_reveal = client.post(
        "/api/remote/account/secrets/reveal",
        headers=desktop_headers,
        json={"namespace": "setup", "names": ["OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN"]},
    )
    manual_desktop_reveal = client.post(
        "/api/remote/account/secrets/reveal",
        headers={**desktop_headers, "X-EmploAI-Manual-Secret-Reveal": "true"},
        json={"namespace": "setup", "names": ["OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN"]},
    )

    assert saved.status_code == 200
    assert listed.status_code == 200
    listed_items = listed.json()["items"]
    assert {item["name"] for item in listed_items} == {"OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN"}
    assert all("sk-live-secret" not in json.dumps(item) for item in listed_items)
    assert "token" not in next(item for item in listed_items if item["name"] == "OPENAI_API_KEY")["metadata"]
    assert mobile_reveal.status_code == 403
    assert desktop_reveal.status_code == 403
    assert manual_desktop_reveal.status_code == 200
    assert manual_desktop_reveal.json()["secrets"] == {
        "OPENAI_API_KEY": "sk-live-secret",
        "TELEGRAM_BOT_TOKEN": "123456:bot-secret",
    }
    assert store.reveal_user_secrets(user_id=user["user_id"], namespace="setup", names=["OPENAI_API_KEY"]) == {
        "OPENAI_API_KEY": "sk-live-secret"
    }
    database_bytes = (tmp_path / REMOTE_CONTROL_DB_FILENAME).read_bytes()
    assert b"sk-live-secret" not in database_bytes
    assert b"bot-secret" not in database_bytes


def test_remote_account_secrets_accept_telegram_bot_and_login_namespaces(tmp_path):
    _store, _user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    mobile_headers = {"Authorization": f"Bearer {mobile_login['session_token']}"}
    desktop_headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}

    telegram_saved = client.put(
        "/api/remote/account/secrets",
        headers=mobile_headers,
        json={
            "namespace": "telegram_bots",
            "secrets": {"bot_config_1": "999999:secondary-secret"},
            "metadata": {"bot_config_1": {"label": "Secondary Bot", "kind": "telegram_bot_token"}},
        },
    )
    login_saved = client.put(
        "/api/remote/account/secrets",
        headers=mobile_headers,
        json={
            "namespace": "login_credentials",
            "secrets": {"GMAIL_EMAIL": "person@example.com", "GMAIL_PASSWORD": "gmail-secret"},
        },
    )
    listed = client.get("/api/remote/account/secrets?namespace=telegram_bots", headers=mobile_headers)
    revealed = client.post(
        "/api/remote/account/secrets/reveal",
        headers={**desktop_headers, "X-EmploAI-Manual-Secret-Reveal": "true"},
        json={"namespace": "login_credentials", "names": ["GMAIL_EMAIL", "GMAIL_PASSWORD"]},
    )

    assert telegram_saved.status_code == 200
    assert login_saved.status_code == 200
    assert listed.status_code == 200
    assert listed.json()["items"][0]["name"] == "bot_config_1"
    assert "secondary-secret" not in json.dumps(listed.json())
    assert revealed.status_code == 200
    assert revealed.json()["secrets"] == {
        "GMAIL_EMAIL": "person@example.com",
        "GMAIL_PASSWORD": "gmail-secret",
    }


def test_remote_account_secrets_reject_invalid_namespace_on_list_and_reveal(tmp_path):
    _store, _user, desktop_login, mobile_login = _paired_remote_session(tmp_path)
    client = TestClient(app_server.create_app())
    mobile_headers = {"Authorization": f"Bearer {mobile_login['session_token']}"}
    desktop_headers = {"Authorization": f"Bearer {desktop_login['session_token']}"}

    listed = client.get("/api/remote/account/secrets?namespace=setup/../secrets", headers=mobile_headers)
    revealed = client.post(
        "/api/remote/account/secrets/reveal",
        headers={**desktop_headers, "X-EmploAI-Manual-Secret-Reveal": "true"},
        json={"namespace": "setup/../secrets", "names": []},
    )

    assert listed.status_code == 400
    assert "namespace" in listed.json()["detail"].lower()
    assert revealed.status_code == 400
    assert "namespace" in revealed.json()["detail"].lower()


def test_remote_sidebar_state_update_dispatches_to_paired_desktop(tmp_path, monkeypatch):
    store, user, _desktop_login, mobile_login = _paired_remote_session(tmp_path)
    dispatched = []

    async def fake_dispatch(auth, *, command_name, payload, timeout_seconds=30.0):
        dispatched.append(
            {
                "auth": auth,
                "command_name": command_name,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        store.update_sidebar_state(user_id=int(auth["user_id"]), sidebar_state=payload["state"])
        return {"ok": True}

    async def fake_wait_for_sync_version(user_id, previous_sync_version, *, timeout_seconds=5.0):
        return store.get_shared_state(user_id=int(user_id))

    monkeypatch.setattr(app_server, "_remote_dispatch_command", fake_dispatch)
    monkeypatch.setattr(app_server, "_remote_wait_for_sync_version", fake_wait_for_sync_version)

    client = TestClient(app_server.create_app())
    sidebar_state = {
        "version": 1,
        "projectOrder": ["C:/Work/App"],
        "projects": {"C:/Work/App": {"displayName": "App"}},
        "sessionMeta": {"sess-1": {"pinned": True}},
    }
    response = client.put(
        "/api/app/sidebar-state",
        headers={"Authorization": f"Bearer {mobile_login['session_token']}"},
        json={"state": sidebar_state},
    )

    assert response.status_code == 200
    assert response.json()["state"] == sidebar_state
    assert store.get_sidebar_state(user_id=user["user_id"]) == sidebar_state
    assert dispatched[0]["command_name"] == "update_sidebar_state"
    assert dispatched[0]["payload"] == {"state": sidebar_state}


def test_remote_desktop_manager_request_command_waits_for_command_result():
    class DummyWebSocket:
        def __init__(self):
            self.sent = []
            self.close_code = None

        async def send_json(self, payload):
            self.sent.append(payload)

        async def close(self, code=1000):
            self.close_code = code

    async def scenario():
        manager = RemoteDesktopConnectionManager()
        websocket = DummyWebSocket()
        connection = manager.register(
            user_id=1,
            desktop_id="desk-1",
            websocket=websocket,
            loop=asyncio.get_running_loop(),
        )
        task = asyncio.create_task(
            manager.request_command(
                desktop_id="desk-1",
                user_id=1,
                command_type="http_request",
                payload={"path": "/api/app/agent/config"},
            )
        )
        await asyncio.sleep(0)
        assert websocket.sent
        command_id = websocket.sent[0]["command_id"]
        resolved = manager.resolve_command_reply(
            desktop_id="desk-1",
            connection_id=connection.connection_id,
            command_id=command_id,
            payload={"ok": True, "result": {"status_code": 200}},
        )
        assert resolved is True
        assert await task == {"ok": True, "result": {"status_code": 200}}

    asyncio.run(scenario())


def test_remote_desktop_manager_request_send_failure_unregisters_connection():
    class FailingWebSocket:
        async def send_json(self, payload):
            raise OSError("socket closed")

    async def scenario():
        manager = RemoteDesktopConnectionManager()
        connection = manager.register(
            user_id=1,
            desktop_id="desk-1",
            websocket=FailingWebSocket(),
            loop=asyncio.get_running_loop(),
        )

        with pytest.raises(RuntimeError, match="connection failed"):
            await manager.request_command(
                desktop_id="desk-1",
                user_id=1,
                command_type="http_request",
                payload={"path": "/api/app/agent/config"},
                timeout_seconds=10,
            )

        assert manager.get("desk-1") is None
        assert connection.pending_replies == {}

    asyncio.run(scenario())


def test_remote_desktop_manager_send_failure_does_not_remove_replacement():
    class ReplacementWebSocket:
        async def send_json(self, payload):
            raise AssertionError("replacement should not receive this command")

    async def scenario():
        manager = RemoteDesktopConnectionManager()
        replacement_holder = {}

        class ReplacedThenFailingWebSocket:
            async def send_json(self, payload):
                replacement_holder["connection"] = manager.register(
                    user_id=1,
                    desktop_id="desk-1",
                    websocket=ReplacementWebSocket(),
                    loop=asyncio.get_running_loop(),
                )
                raise OSError("socket closed")

        manager.register(
            user_id=1,
            desktop_id="desk-1",
            websocket=ReplacedThenFailingWebSocket(),
            loop=asyncio.get_running_loop(),
        )

        with pytest.raises(RuntimeError, match="connection failed"):
            await manager.send_command(
                desktop_id="desk-1",
                user_id=1,
                command_type="focus_session",
                payload={"session_id": "sess-1"},
            )

        assert manager.get("desk-1") is replacement_holder["connection"]

    asyncio.run(scenario())


def test_remote_desktop_manager_ignores_stale_unregister_after_reconnect():
    class DummyWebSocket:
        async def send_json(self, payload):
            raise AssertionError("send_json should not be called")

    manager = RemoteDesktopConnectionManager()
    loop = asyncio.new_event_loop()
    try:
        first = manager.register(
            user_id=1,
            desktop_id="desk-1",
            websocket=DummyWebSocket(),
            loop=loop,
        )
        second = manager.register(
            user_id=1,
            desktop_id="desk-1",
            websocket=DummyWebSocket(),
            loop=loop,
        )

        assert manager.get("desk-1") is second

        assert manager.unregister("desk-1", connection_id=first.connection_id) is False
        assert manager.get("desk-1") is second

        assert manager.unregister("desk-1", connection_id=second.connection_id) is True
        assert manager.get("desk-1") is None
    finally:
        loop.close()


def test_remote_desktop_manager_closes_replaced_websocket_on_reconnect():
    class RecordingWebSocket:
        def __init__(self):
            self.close_code = None

        async def send_json(self, payload):
            raise AssertionError("send_json should not be called")

        async def close(self, code=1000):
            self.close_code = code

    async def scenario():
        manager = RemoteDesktopConnectionManager()
        first_websocket = RecordingWebSocket()
        second_websocket = RecordingWebSocket()
        first = manager.register(
            user_id=1,
            desktop_id="desk-1",
            websocket=first_websocket,
            loop=asyncio.get_running_loop(),
        )
        second = manager.register(
            user_id=1,
            desktop_id="desk-1",
            websocket=second_websocket,
            loop=asyncio.get_running_loop(),
        )
        await asyncio.sleep(0)
        return manager, first, second, first_websocket, second_websocket

    manager, first, second, first_websocket, second_websocket = asyncio.run(scenario())

    assert first is not second
    assert manager.get("desk-1") is second
    assert first_websocket.close_code == 4000
    assert second_websocket.close_code is None


def test_remote_desktop_manager_rejects_cross_account_desktop_replacement():
    class DummyWebSocket:
        async def send_json(self, payload):
            raise AssertionError("send_json should not be called")

    manager = RemoteDesktopConnectionManager()
    loop = asyncio.new_event_loop()
    try:
        first = manager.register(
            user_id=1,
            desktop_id="desk-1",
            websocket=DummyWebSocket(),
            loop=loop,
        )

        with pytest.raises(RuntimeError, match="belongs to another account"):
            manager.register(
                user_id=2,
                desktop_id="desk-1",
                websocket=DummyWebSocket(),
                loop=loop,
            )

        assert manager.get("desk-1") is first
    finally:
        loop.close()


def test_remote_desktop_websocket_stops_processing_after_session_revoked(tmp_path, monkeypatch):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    store = app_server._remote_control_store
    manager = RemoteDesktopConnectionManager()
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    user = store.register_user(email="revoked-desktop@example.com", password="CorrectHorse!2026", display_name="Revoked Desktop")
    desktop_login = store.login(
        email="revoked-desktop@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Desk",
        device_platform="desktop-electron",
        device_key="desk-revoked-session",
    )
    desktop_id = desktop_login["desktop"]["desktop_id"]
    user_id = user["user_id"]

    class RevokedDesktopWebSocket:
        def __init__(self):
            self.close_code = None
            self.received = False

        async def send_json(self, payload):
            raise AssertionError("send_json should not be called")

        async def close(self, code=1000):
            self.close_code = code

        async def receive_text(self):
            if self.received:
                raise WebSocketDisconnect(code=1000)
            self.received = True
            store.revoke_session_token(desktop_login["session_token"])
            return json.dumps(
                {
                    "type": "state_snapshot",
                    "payload": {
                        "desktop_id": desktop_id,
                        "desktop_name": "Desk",
                        "current_session_id": "revoked-session",
                        "sessions": [],
                        "session_details": {"revoked-session": _remote_session_detail_payload("revoked-session")},
                        "jobs": [],
                    },
                }
            )

    async def scenario():
        websocket = RevokedDesktopWebSocket()
        auth = store.resolve_session_token(desktop_login["session_token"])
        with pytest.raises(WebSocketDisconnect) as exc_info:
            await app_server._handle_remote_desktop_ws(websocket, auth)
        return websocket, exc_info.value

    websocket, disconnect = asyncio.run(scenario())

    assert disconnect.code == 4401
    assert websocket.close_code == 4401
    assert not manager.is_connected_for_user(desktop_id, user_id)
    shared_state = store.get_shared_state(user_id=user_id)
    assert shared_state["current_session_id"] != "revoked-session"
    assert "revoked-session" not in shared_state["session_details"]


def test_remote_desktop_websocket_closes_malformed_message_and_unregisters(tmp_path, monkeypatch):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    store = app_server._remote_control_store
    manager = RemoteDesktopConnectionManager()
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    user = store.register_user(email="malformed-desktop@example.com", password="CorrectHorse!2026", display_name="Bad Desktop")
    desktop_login = store.login(
        email="malformed-desktop@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Desk",
        device_platform="desktop-electron",
        device_key="desk-malformed-message",
    )
    desktop_id = desktop_login["desktop"]["desktop_id"]
    user_id = user["user_id"]

    class MalformedDesktopWebSocket:
        def __init__(self):
            self.close_code = None
            self.received = False

        async def send_json(self, payload):
            raise AssertionError("send_json should not be called")

        async def close(self, code=1000):
            self.close_code = code

        async def receive_text(self):
            if self.received:
                raise WebSocketDisconnect(code=1000)
            self.received = True
            return "{not-json"

    async def scenario():
        websocket = MalformedDesktopWebSocket()
        auth = store.resolve_session_token(desktop_login["session_token"])
        with pytest.raises(WebSocketDisconnect) as exc_info:
            await app_server._handle_remote_desktop_ws(websocket, auth)
        return websocket, exc_info.value

    websocket, disconnect = asyncio.run(scenario())

    assert disconnect.code == 4400
    assert websocket.close_code == 4400
    assert not manager.is_connected_for_user(desktop_id, user_id)
    desktop = next(item for item in store.list_desktops(user_id=user_id) if item["desktop_id"] == desktop_id)
    assert desktop["status"] == "offline"


def test_remote_desktop_stale_disconnect_does_not_mark_replacement_offline(tmp_path, monkeypatch):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    store = app_server._remote_control_store
    manager = RemoteDesktopConnectionManager()
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    user = store.register_user(email="reconnect@example.com", password="CorrectHorse!2026", display_name="Reconnect User")
    desktop_login = store.login(
        email="reconnect@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Desk",
        device_platform="desktop-electron",
        device_key="desk-reconnect",
    )
    desktop_id = desktop_login["desktop"]["desktop_id"]
    user_id = user["user_id"]

    class ReplacementWebSocket:
        async def send_json(self, payload):
            raise AssertionError("send_json should not be called")

    class StaleDisconnectWebSocket:
        def __init__(self):
            self.replaced = False

        async def receive_text(self):
            if not self.replaced:
                self.replaced = True
                manager.register(
                    user_id=user_id,
                    desktop_id=desktop_id,
                    websocket=ReplacementWebSocket(),
                    loop=asyncio.get_running_loop(),
                )
            raise WebSocketDisconnect(code=1000)

    async def scenario():
        auth = store.resolve_session_token(desktop_login["session_token"])
        with pytest.raises(WebSocketDisconnect):
            await app_server._handle_remote_desktop_ws(
                StaleDisconnectWebSocket(),
                auth,
            )

    asyncio.run(scenario())

    assert manager.is_connected_for_user(desktop_id, user_id)
    desktop = next(item for item in store.list_desktops(user_id=user_id) if item["desktop_id"] == desktop_id)
    shared_state = store.get_shared_state(user_id=user_id)
    assert desktop["status"] == "connected"
    assert shared_state["desktop_connection"]["status"] == "connected"


def test_remote_desktop_stale_socket_snapshot_does_not_overwrite_replacement_state(tmp_path, monkeypatch):
    app_server._auth_store = AppAuthStore(root_path=tmp_path)
    app_server._remote_control_store = RemoteControlPlaneStore(root_path=tmp_path)
    store = app_server._remote_control_store
    manager = RemoteDesktopConnectionManager()
    monkeypatch.setattr(app_server, "get_remote_desktop_manager", lambda: manager)

    user = store.register_user(email="stale-snapshot@example.com", password="CorrectHorse!2026", display_name="Snapshot User")
    desktop_login = store.login(
        email="stale-snapshot@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Desk",
        device_platform="desktop-electron",
        device_key="desk-stale-snapshot",
    )
    desktop_id = desktop_login["desktop"]["desktop_id"]
    user_id = user["user_id"]

    class ReplacementWebSocket:
        async def send_json(self, payload):
            raise AssertionError("send_json should not be called")

    class StaleSnapshotWebSocket:
        def __init__(self):
            self.sent = False

        async def receive_text(self):
            if self.sent:
                raise WebSocketDisconnect(code=1000)
            self.sent = True
            manager.register(
                user_id=user_id,
                desktop_id=desktop_id,
                websocket=ReplacementWebSocket(),
                loop=asyncio.get_running_loop(),
            )
            store.update_shared_snapshot(
                user_id=user_id,
                desktop_id=desktop_id,
                snapshot={
                    "desktop_id": desktop_id,
                    "desktop_name": "Desk",
                    "current_session_id": "replacement-session",
                    "sessions": [],
                    "session_details": {"replacement-session": _remote_session_detail_payload("replacement-session")},
                    "jobs": [],
                },
            )
            return json.dumps(
                {
                    "type": "state_snapshot",
                    "payload": {
                        "desktop_id": desktop_id,
                        "desktop_name": "Desk",
                        "current_session_id": "stale-session",
                        "sessions": [],
                        "session_details": {"stale-session": _remote_session_detail_payload("stale-session")},
                        "jobs": [],
                    },
                }
            )

    async def scenario():
        auth = store.resolve_session_token(desktop_login["session_token"])
        await app_server._handle_remote_desktop_ws(
            StaleSnapshotWebSocket(),
            auth,
        )

    asyncio.run(scenario())

    shared_state = store.get_shared_state(user_id=user_id)
    assert manager.is_connected_for_user(desktop_id, user_id)
    assert shared_state["current_session_id"] == "replacement-session"
    assert "replacement-session" in shared_state["session_details"]
    assert "stale-session" not in shared_state["session_details"]


def test_remote_desktop_manager_reconnect_fails_pending_request_immediately():
    class DummyWebSocket:
        def __init__(self):
            self.sent = []
            self.close_code = None

        async def send_json(self, payload):
            self.sent.append(payload)

        async def close(self, code=1000):
            self.close_code = code

    async def scenario():
        manager = RemoteDesktopConnectionManager()
        first_socket = DummyWebSocket()
        manager.register(
            user_id=1,
            desktop_id="desk-1",
            websocket=first_socket,
            loop=asyncio.get_running_loop(),
        )
        task = asyncio.create_task(
            manager.request_command(
                desktop_id="desk-1",
                user_id=1,
                command_type="http_request",
                payload={"path": "/api/app/agent/config"},
                timeout_seconds=10,
            )
        )
        await asyncio.sleep(0)
        assert first_socket.sent

        manager.register(
            user_id=1,
            desktop_id="desk-1",
            websocket=DummyWebSocket(),
            loop=asyncio.get_running_loop(),
        )
        await asyncio.sleep(0)

        with pytest.raises(RuntimeError, match="reconnected"):
            await task
        assert first_socket.close_code == 4000

    asyncio.run(scenario())


def test_remote_desktop_manager_rejects_command_reply_from_stale_connection():
    class DummyWebSocket:
        def __init__(self):
            self.sent = []

        async def send_json(self, payload):
            self.sent.append(payload)

    async def scenario():
        manager = RemoteDesktopConnectionManager()
        first_socket = DummyWebSocket()
        first = manager.register(
            user_id=1,
            desktop_id="desk-1",
            websocket=first_socket,
            loop=asyncio.get_running_loop(),
        )
        manager.register(
            user_id=1,
            desktop_id="desk-1",
            websocket=DummyWebSocket(),
            loop=asyncio.get_running_loop(),
        )
        second = manager.get("desk-1")
        assert second is not None
        task = asyncio.create_task(
            manager.request_command(
                desktop_id="desk-1",
                user_id=1,
                command_type="http_request",
                payload={"path": "/api/app/agent/config"},
                timeout_seconds=10,
            )
        )
        await asyncio.sleep(0)
        command_id = second.websocket.sent[0]["command_id"]

        stale_resolved = manager.resolve_command_reply(
            desktop_id="desk-1",
            connection_id=first.connection_id,
            command_id=command_id,
            payload={"ok": True, "result": {"status_code": 200}},
        )
        assert stale_resolved is False
        assert not task.done()

        current_resolved = manager.resolve_command_reply(
            desktop_id="desk-1",
            connection_id=second.connection_id,
            command_id=command_id,
            payload={"ok": True, "result": {"status_code": 200}},
        )
        assert current_resolved is True
        assert await task == {"ok": True, "result": {"status_code": 200}}

    asyncio.run(scenario())


def test_remote_desktop_manager_rejects_command_for_wrong_user():
    class DummyWebSocket:
        def __init__(self):
            self.sent = []

        async def send_json(self, payload):
            self.sent.append(payload)

    async def scenario():
        manager = RemoteDesktopConnectionManager()
        websocket = DummyWebSocket()
        manager.register(
            user_id=1,
            desktop_id="desk-1",
            websocket=websocket,
            loop=asyncio.get_running_loop(),
        )

        with pytest.raises(RuntimeError, match="unavailable for this account"):
            await manager.request_command(
                desktop_id="desk-1",
                user_id=2,
                command_type="http_request",
                payload={"path": "/api/app/agent/config"},
            )

        assert websocket.sent == []

    asyncio.run(scenario())
