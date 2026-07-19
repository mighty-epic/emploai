from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

from app_backend import runtime
from app_backend import app_server
from app_backend.fleet_identity_profiles import DEFAULT_WORKER_TOOL_PACKS
from shared.tool_packs import MANAGER_CORE_FLEET_TOOLS, PACK_MANAGER_CORE, get_tool_pack


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


def test_manager_context_resolution_does_not_block_the_app_event_loop(monkeypatch):
    event_loop_thread_id = threading.get_ident()
    resolved_thread_ids = []
    monkeypatch.setattr(
        runtime,
        "_fleet_manager_tool_context",
        lambda _session: resolved_thread_ids.append(threading.get_ident()) or {"enabled": True},
    )

    context = asyncio.run(runtime._resolve_fleet_manager_tool_context(object()))

    assert context == {"enabled": True}
    assert resolved_thread_ids == [resolved_thread_ids[0]]
    assert resolved_thread_ids[0] != event_loop_thread_id


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


def test_manager_core_formally_owns_fleet_tools_and_workers_cannot_receive_it():
    manager_core = get_tool_pack(PACK_MANAGER_CORE)

    assert manager_core is not None
    assert runtime.FLEET_MANAGER_TOOL_NAMES.issubset(manager_core.tool_names)
    assert MANAGER_CORE_FLEET_TOOLS.issubset(manager_core.tool_names)
    assert PACK_MANAGER_CORE not in DEFAULT_WORKER_TOOL_PACKS


def test_duplicate_worker_report_enqueues_exactly_one_manager_review(monkeypatch):
    from shared.proactive_runtime import append_fleet_report_event, set_event_store_callback

    class Store:
        def __init__(self):
            self.events = {}
            self.runs = {}

        def record_loop_guard_event(self, **_kwargs):
            return {"allowed": True}

        def append_automation_event(self, **kwargs):
            dedupe_key = kwargs.get("dedupe_key")
            if dedupe_key and dedupe_key in self.events:
                return self.events[dedupe_key]
            event = {**kwargs, "event_id": f"event-{len(self.events) + 1}"}
            if dedupe_key:
                self.events[dedupe_key] = event
            return event

        def get_event_run(self, *, event_run_id, **_kwargs):
            return self.runs.get(event_run_id)

        def create_or_update_event_run(self, *, event_run_id, **kwargs):
            run = {**kwargs, "event_run_id": event_run_id}
            self.runs[event_run_id] = run
            return run

    store = Store()
    monkeypatch.setattr(app_server, "_remote_control_store", store)
    app_server._install_proactive_event_store_callback()
    report = {
        "task_id": "task-1",
        "report_id": "report-1",
        "worker_id": "worker-1",
        "status": "completed",
        "summary": "Done",
        "origin": {"origin_manager_session_id": "manager-chat"},
    }
    try:
        append_fleet_report_event(user_id=0, report=report)
        append_fleet_report_event(user_id=0, report=report)
    finally:
        set_event_store_callback(None)

    assert len(store.runs) == 1
    assert next(iter(store.runs.values()))["target_chat_id"] == "manager-chat"


def test_manager_tools_include_private_connected_computer_delegation(monkeypatch):
    snapshot = {
        "manager": {"desktop_id": "desktop-local", "role": "manager"},
        "desktops": [
            {"desktop_id": "desktop-local", "display_name": "Manager PC", "status": "connected"},
            {"desktop_id": "desktop-vps", "display_name": "Windows VPS", "status": "connected"},
        ],
        "connection_permissions": [
            {
                "desktop_id": "desktop-vps",
                "source": "paired_desktop",
                "permissions": {
                    "delegate_manager": True,
                    "delegate_workers": True,
                    "create_workers": True,
                },
                "capabilities": {
                    "targets": [
                        {
                            "target_kind": "manager",
                            "target_selector": "manager",
                            "display_name": "VPS manager",
                            "status": "active",
                        }
                    ]
                },
            }
        ],
        "workers": [],
    }
    monkeypatch.setattr(runtime, "_fleet_snapshot_uncached", lambda: snapshot)
    calls = []
    monkeypatch.setattr(
        runtime,
        "_fleet_api_request",
        lambda method, path, payload=None, **kwargs: calls.append((method, path, payload, kwargs))
        or {"delegation_id": "delegation-1", "status": "running"},
    )
    session = SimpleNamespace(_fleet_manager_tool_context=None)

    listed = runtime._fleet_tool_list_computers(session, {})
    delegated = runtime._fleet_tool_delegate_computer(
        session,
        {
            "computer": "Windows VPS",
            "prompt": "Minimize the Google Drive window.",
            "target_kind": "manager",
            "target_selector": "manager",
        },
    )

    assert {"fleet_list_computers", "fleet_delegate_computer", "fleet_create_worker_on_computer"}.issubset(
        runtime.FLEET_MANAGER_TOOL_NAMES
    )
    assert listed["count"] == 1
    assert listed["computers"][0]["desktop_id"] == "desktop-vps"
    assert listed["computers"][0]["targets"][0] == {
        "target_kind": "manager",
        "target_selector": "manager",
        "display_name": "VPS manager",
        "status": "active",
        "is_default": False,
        "protected": False,
        "tool_profile": None,
        "capability_tags": [],
    }
    assert calls[0][0:2] == ("POST", "/api/fleet/delegations/route")
    assert calls[0][2]["scope"] == "child"
    assert calls[0][2]["computer"] == "desktop-vps"
    assert calls[0][2]["target_role"] == "manager"
    assert calls[0][2]["identity"] == "manager"
    assert delegated["delegation_id"] == "delegation-1"


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
