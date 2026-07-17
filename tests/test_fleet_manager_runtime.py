from __future__ import annotations

from types import SimpleNamespace

from app_backend import runtime


def test_fleet_api_config_uses_local_control_plane(monkeypatch):
    monkeypatch.setattr(
        runtime,
        "_local_fleet_api_config",
        lambda: {
            "base_url": "http://127.0.0.1:8787",
            "token": "local-token",
            "desktop_id": "",
        },
    )

    assert runtime._local_fleet_api_config()["token"] == "local-token"


def test_local_fleet_manager_context_is_enabled_without_remote_account(monkeypatch):
    session = object()
    monkeypatch.setattr(
        runtime,
        "_local_fleet_api_config",
        lambda: {
            "base_url": "http://127.0.0.1:8787",
            "token": "local-token",
            "desktop_id": "",
        },
    )
    monkeypatch.setattr(
        runtime,
        "_fleet_snapshot_uncached",
        lambda: {
            "manager": {"desktop_id": "local-manager", "role": "manager"},
            "workers": [],
        },
    )

    context = runtime._fleet_manager_tool_context(session)

    assert context["enabled"] is True
    assert context["has_workers"] is False


def test_local_worker_identity_never_receives_manager_fleet_tools(monkeypatch):
    session = SimpleNamespace(fleet_identity_role="worker", fleet_worker_id="worker-1")
    monkeypatch.setattr(
        runtime,
        "_local_fleet_api_config",
        lambda: (_ for _ in ()).throw(AssertionError("worker must not resolve manager control credentials")),
    )

    context = runtime._fleet_manager_tool_context(session)

    assert context["enabled"] is False
    assert context["reason"] == "worker_identity"


def test_agent_fleet_confirmation_creates_approves_and_forwards_audited_confirmation(monkeypatch):
    session = SimpleNamespace(
        session=SimpleNamespace(id="manager-chat"),
        fleet_identity_id="manager-identity",
        last_user_message="Yes, I confirm. Delete the group.",
    )
    monkeypatch.setattr(
        runtime,
        "_fleet_snapshot_uncached",
        lambda: {
            "groups": [{"group_id": "group-1", "display_name": "Research", "worker_ids": ["worker-1"]}],
            "workers": [],
        },
    )
    calls = []

    def fake_request(method, path, payload=None, *, confirmation_id=None):
        calls.append((method, path, payload, confirmation_id))
        if path == "/api/app/confirmations":
            return {"confirmation_id": "confirmation-1", "status": "pending"}
        if path.endswith("/approve"):
            return {"confirmation_id": "confirmation-1", "status": "approved"}
        return {"ok": True, "deleted": True}

    monkeypatch.setattr(runtime, "_fleet_api_request", fake_request)

    pending = runtime._fleet_tool_delete_group(session, {"group": "Research"})
    completed = runtime._fleet_tool_delete_group(
        session,
        {"group": "Research", "confirmed": True, "confirmation_id": pending["confirmation_id"]},
    )

    assert pending["confirmation_required"] is True
    assert calls[0][2]["action_kind"] == "fleet_group_delete"
    assert calls[1][1] == "/api/app/confirmations/confirmation-1/approve"
    assert calls[2][1] == "/api/fleet/groups/group-1"
    assert calls[2][3] == "confirmation-1"
    assert completed["deleted"] is True


def test_agent_fleet_confirmation_rejects_model_confirmation_without_affirmative_user_message(monkeypatch):
    session = SimpleNamespace(
        session=SimpleNamespace(id="manager-chat"),
        last_user_message="Tell me what deleting the group would do.",
        _fleet_pending_confirmations={"fleet_group_delete": "confirmation-1"},
    )
    monkeypatch.setattr(
        runtime,
        "_fleet_snapshot_uncached",
        lambda: {"groups": [{"group_id": "group-1", "display_name": "Research", "worker_ids": []}]},
    )
    calls = []
    monkeypatch.setattr(
        runtime,
        "_fleet_api_request",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"ok": True},
    )

    result = runtime._fleet_tool_delete_group(
        session,
        {"group": "Research", "confirmed": True, "confirmation_id": "confirmation-1"},
    )

    assert result["error_type"] == "confirmation_required"
    assert calls == []


def test_agent_remote_update_requires_confirmation_and_forwards_exact_commit(monkeypatch):
    target = "b" * 40
    session = SimpleNamespace(
        session=SimpleNamespace(id="manager-chat"),
        fleet_identity_id="manager-identity",
        last_user_message="Yes, update and restart the Windows VPS.",
    )
    monkeypatch.setattr(
        runtime,
        "_fleet_snapshot_uncached",
        lambda: {"desktops": [{"desktop_id": "desktop-vps", "display_name": "Windows VPS"}]},
    )
    calls = []

    def fake_request(method, path, payload=None, **kwargs):
        calls.append((method, path, payload, kwargs))
        if path == "/api/app/confirmations":
            return {"confirmation_id": "confirmation-update", "status": "pending"}
        if path.endswith("/approve"):
            return {"confirmation_id": "confirmation-update", "status": "approved"}
        return {"state": "queued", "active": True}

    monkeypatch.setattr(runtime, "_fleet_api_request", fake_request)

    pending = runtime._fleet_tool_update_computer(
        session,
        {"computer": "Windows VPS", "expected_commit": target},
    )
    started = runtime._fleet_tool_update_computer(
        session,
        {
            "computer": "Windows VPS",
            "expected_commit": target,
            "confirmed": True,
            "confirmation_id": pending["confirmation_id"],
        },
    )

    assert pending["confirmation_required"] is True
    assert calls[0][2]["action_kind"] == "fleet_computer_update"
    assert calls[2][1] == "/api/fleet/desktops/desktop-vps/update/start"
    assert calls[2][2] == {"expected_commit": target}
    assert calls[2][3]["confirmation_id"] == "confirmation-update"
    assert started["active"] is True
