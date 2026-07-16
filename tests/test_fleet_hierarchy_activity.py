from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app_backend import runtime
from app_backend.remote_control_store import RemoteControlPlaneStore
from app_backend.remote_desktop_client import _fleet_capability_view
from shared.fleet_upstream_activity import (
    activity_snapshot,
    mark_upstream_request_sent,
    pending_upstream_requests,
    queue_upstream_request,
    record_incoming_delegation,
    record_upstream_request_decision,
)
from shared.fleet_connection import write_fleet_connection


ROOT = Path(__file__).resolve().parents[1]


def _paired_store(tmp_path: Path):
    store = RemoteControlPlaneStore(root_path=tmp_path / "control")
    manager = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Root manager",
        device_platform="desktop",
        device_key="root-key",
    )
    enrollment = store.create_worker_enrollment(
        user_id=0,
        desktop_id=manager["desktop_id"],
        display_name="Leaf",
        metadata={"transport": "yggdrasil", "source": "standalone_yggdrasil_pairing"},
    )
    paired = store.complete_worker_enrollment(
        enrollment_token=enrollment["enrollment_token"],
        device_name="Leaf",
        device_platform="windows",
        device_key="leaf-key",
    )
    return store, manager, paired["desktop"]["desktop_id"]


def test_capability_directory_only_publishes_allowed_targets():
    snapshot = {
        "manager": {"desktop_id": "local-manager"},
        "desktops": [
            {"desktop_id": "local-manager"},
            {"desktop_id": "child-a"},
        ],
        "identities": [
            {"identity_id": "manager-1", "display_name": "Main", "role": "manager"},
            {"identity_id": "worker-1", "display_name": "Research", "role": "worker"},
        ],
    }

    manager_only = _fleet_capability_view(
        snapshot,
        {"delegate_manager": True, "delegate_workers": False, "create_workers": False},
    )
    all_targets = _fleet_capability_view(
        snapshot,
        {"delegate_manager": True, "delegate_workers": True, "create_workers": True},
    )

    assert manager_only["node_role"] == "intermediary"
    assert manager_only["child_count"] == 1
    assert [target["role"] for target in manager_only["targets"]] == ["manager"]
    assert [target["display_name"] for target in all_targets["targets"]] == ["Main", "Research"]
    assert all_targets["can_create_workers"] is True
    assert "sessions" not in all_targets
    assert "providers" not in all_targets


def test_local_activity_ledger_survives_request_and_delegation_lifecycle(tmp_path: Path):
    request = queue_upstream_request(
        tmp_path,
        request_kind="approval",
        identity_id="worker-1",
        identity_label="Research",
        message="May I use the release workspace?",
    )
    assert pending_upstream_requests(tmp_path)[0]["activity_id"] == request["activity_id"]

    sent = mark_upstream_request_sent(tmp_path, request["activity_id"])
    assert sent["status"] == "sent"
    decided = record_upstream_request_decision(
        tmp_path,
        request_id=request["activity_id"],
        decision="approved",
        response="Use the release workspace, read-only.",
    )
    assert decided["status"] == "approved"
    assert decided["response"] == "Use the release workspace, read-only."

    record_incoming_delegation(
        tmp_path,
        delegation_id="delegation-1",
        message="Inspect the service.",
        identity_id="manager-1",
        identity_label="Main",
        status="running",
    )
    completed = record_incoming_delegation(
        tmp_path,
        delegation_id="delegation-1",
        message="Inspect the service.",
        identity_id="manager-1",
        identity_label="Main",
        status="completed",
        report={"summary": "Healthy"},
    )
    assert completed["status"] == "completed"
    assert completed["report"]["summary"] == "Healthy"
    snapshot = activity_snapshot(tmp_path)
    assert {item["activity_kind"] for item in snapshot["items"]} == {"request", "delegation"}


def test_manager_store_persists_capabilities_and_upstream_decisions(tmp_path: Path):
    store, manager, desktop_id = _paired_store(tmp_path)
    state = store.record_connection_permission_state(
        user_id=0,
        desktop_id=desktop_id,
        policy={
            "permissions": {"delegate_manager": True, "delegate_workers": False, "create_workers": False},
            "capabilities": {
                "node_role": "leaf",
                "child_count": 0,
                "targets": [{"target_kind": "manager", "display_name": "Main", "role": "manager"}],
            },
        },
    )
    request = store.record_upstream_request(
        user_id=0,
        desktop_id=desktop_id,
        request_id="request-1",
        request_kind="blocked",
        message="Provider is unavailable.",
        identity_id="manager-1",
        identity_label="Main",
    )
    decided = store.decide_upstream_request(
        user_id=0,
        desktop_id=desktop_id,
        request_id=request["request_id"],
        decision="replied",
        response="Switch to the configured local provider.",
    )
    snapshot = store.get_fleet_snapshot(user_id=0, desktop_id=manager["desktop_id"])

    assert state["capabilities"]["node_role"] == "leaf"
    assert decided["status"] == "replied"
    assert snapshot["upstream_requests"][0]["response"] == "Switch to the configured local provider."


def test_local_agent_can_queue_a_narrow_request_to_its_manager(tmp_path: Path, monkeypatch):
    write_fleet_connection(
        home=tmp_path,
        payload={
            "apiBaseUrl": "http://[200::1]:8787",
            "managerUrl": "http://[200::1]:8787",
            "sessionToken": "paired-session",
            "desktop": {"desktop_id": "leaf", "display_name": "Leaf"},
            "transport": {"kind": "yggdrasil"},
        },
    )
    monkeypatch.setattr(runtime, "runtime_home", lambda: tmp_path)
    monkeypatch.setattr(
        runtime,
        "_fleet_snapshot_uncached",
        lambda: {"identities": [{"identity_id": "worker-1", "display_name": "Research"}]},
    )
    session = SimpleNamespace(fleet_identity_id="worker-1", fleet_worker_id=None)

    result = runtime._fleet_tool_request_manager(
        session,
        {"request_kind": "question", "message": "Which branch should I use?"},
    )

    assert result["ok"] is True
    queued = pending_upstream_requests(tmp_path)
    assert queued[0]["identity_label"] == "Research"
    assert queued[0]["request_kind"] == "question"


def test_role_aware_renderer_contains_all_four_surfaces_and_no_free_text_remote_selector():
    workspace = (ROOT / "desktop_app/renderer_client/src/desktop/DesktopFleetWorkspace.tsx").read_text(encoding="utf-8")
    hierarchy = (ROOT / "desktop_app/renderer_client/src/desktop/desktopFleetHierarchy.ts").read_text(encoding="utf-8")
    machines = (ROOT / "desktop_app/renderer_client/src/desktop/DesktopFleetMachinesPanel.tsx").read_text(encoding="utf-8")
    activity = (ROOT / "desktop_app/renderer_client/src/desktop/DesktopFleetActivityPanel.tsx").read_text(encoding="utf-8")
    parent = (ROOT / "desktop_app/renderer_client/src/desktop/DesktopFleetParentPanel.tsx").read_text(encoding="utf-8")

    for role in ("standalone", "root_manager", "leaf", "intermediary"):
        assert role in hierarchy or role in workspace
    assert "Side by side" in workspace
    assert "Stacked" in workspace
    assert "Add computer below" in workspace
    assert "targetsForConnection" in machines
    assert "This computer is the point of view" in machines
    assert "Your direct manager" in parent
    assert "DesktopFleetParentPanel" in workspace
    assert "Worker name on the other computer" not in machines
    assert "REQUEST THE MANAGER" in activity
    assert "INCOMING DELEGATIONS" in activity


def test_fleet_ui_keeps_forms_clean_and_help_out_of_the_primary_scan_path():
    machines = (ROOT / "desktop_app/renderer_client/src/desktop/DesktopFleetMachinesPanel.tsx").read_text(encoding="utf-8")
    info = (ROOT / "desktop_app/renderer_client/src/desktop/DesktopFleetInfoButton.tsx").read_text(encoding="utf-8")
    scale = (ROOT / "desktop_app/renderer_client/src/desktop/desktopFleetUi.ts").read_text(encoding="utf-8")
    worker_state = (ROOT / "desktop_app/renderer_client/src/desktop/desktopFleetWorkerState.ts").read_text(encoding="utf-8")

    assert "current[selectedMachine.id] === prompt" in machines
    assert "[selectedMachine.id]: ''" in machines
    assert "accessibilityHint={text}" in info
    assert "tooltipText" in info
    assert "dismissOutside" in info
    assert "event.key === 'Escape'" in info
    assert "zIndex: 20" in machines
    assert "body: 12" in scale
    assert "usage_limit_reached" in worker_state
    assert "Provider error:" not in worker_state
