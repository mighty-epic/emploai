from __future__ import annotations

import json
import time

import pytest

from app_backend.fleet_identity_creation import validate_local_worker_creation
from app_backend.fleet_identity_profiles import default_worker_metadata
from app_backend.remote_control_store import RemoteControlPlaneStore


@pytest.mark.parametrize(
    "source",
    [
        "desktop_user_request",
        "mobile_user_request",
        "manager_chat_user_request",
        "paired_manager_request",
    ],
)
def test_local_worker_creation_requires_named_explicit_source(source: str):
    name, metadata = validate_local_worker_creation(
        display_name="  Build agent  ",
        metadata={"created_by": source},
    )

    assert name == "Build agent"
    assert metadata["created_by"] == source


@pytest.mark.parametrize(
    ("display_name", "metadata", "error_type"),
    [
        ("", {"created_by": "desktop_user_request"}, ValueError),
        ("Agent", {}, PermissionError),
        ("Agent", {"created_by": "bootstrap"}, PermissionError),
    ],
)
def test_local_worker_creation_rejects_ambiguous_or_automatic_sources(
    display_name,
    metadata,
    error_type,
):
    with pytest.raises(error_type):
        validate_local_worker_creation(display_name=display_name, metadata=metadata)


def test_store_cannot_bypass_explicit_worker_creation_policy(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    manager = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager PC",
        device_platform="desktop",
        device_key="manager-key",
    )

    with pytest.raises(PermissionError):
        store.create_local_worker(
            user_id=0,
            desktop_id=manager["desktop_id"],
            display_name="Automatic agent",
            metadata={"created_by": "bootstrap"},
        )


def test_deleting_local_worker_does_not_revoke_manager_desktop(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    manager = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager PC",
        device_platform="desktop",
        device_key="manager-key",
    )
    worker = store.create_local_worker(
        user_id=0,
        desktop_id=manager["desktop_id"],
        display_name="Temporary agent",
        metadata={"created_by": "desktop_user_request"},
    )

    result = store.delete_worker(user_id=0, worker_id=worker["worker_id"])
    snapshot = store.get_fleet_snapshot(user_id=0, desktop_id=manager["desktop_id"])

    assert result["connection_revoked"] is False
    assert snapshot["manager"]["desktop_id"] == manager["desktop_id"]
    assert snapshot["manager"]["status"] != "offline"
    assert len(snapshot["workers"]) == 1
    assert snapshot["workers"][0]["is_default"] is True
    assert snapshot["workers"][0]["protected"] is False


def test_startup_reconciles_exactly_one_manager_and_default_worker(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    first = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager PC",
        device_platform="desktop",
        device_key="manager-key",
    )
    second = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager PC",
        device_platform="desktop",
        device_key="manager-key",
    )
    snapshot = store.get_fleet_snapshot(user_id=0, desktop_id=first["desktop_id"])

    assert second["desktop_id"] == first["desktop_id"]
    assert len([identity for identity in snapshot["identities"] if identity["role"] == "manager"]) == 1
    defaults = [worker for worker in snapshot["workers"] if worker["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["protected"] is False
    assert defaults[0]["tool_profile"] == "default_execution"
    assert defaults[0]["enabled_tool_packs"] == [
        "interactive_desktop",
        "browser_isolated",
        "workspace_read",
        "workspace_write",
        "web_research",
    ]

    store._conn.execute(
        "UPDATE fleet_workers SET last_seen_at = ? WHERE worker_id = ?",
        (time.time() - 120, defaults[0]["worker_id"]),
    )
    store._conn.commit()
    refreshed = store.get_fleet_snapshot(user_id=0, desktop_id=first["desktop_id"])
    refreshed_default = next(worker for worker in refreshed["workers"] if worker["is_default"])
    assert refreshed_default["status"] == "idle"


def test_startup_removes_idle_system_default_worker_duplicates(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    desktop = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager PC",
        device_platform="desktop",
        device_key="manager-key",
    )
    duplicate = store.create_local_worker(
        user_id=0,
        desktop_id=desktop["desktop_id"],
        display_name="Default Worker",
        metadata={"created_by": "desktop_user_request"},
    )
    duplicate_metadata = default_worker_metadata(duplicate["metadata"])
    store._conn.execute(
        "UPDATE fleet_workers SET metadata = ? WHERE worker_id = ?",
        (json.dumps(duplicate_metadata), duplicate["worker_id"]),
    )
    store._conn.execute(
        "UPDATE fleet_instances SET metadata = ? WHERE worker_id = ?",
        (json.dumps(duplicate_metadata), duplicate["worker_id"]),
    )
    store._conn.commit()

    store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager PC",
        device_platform="desktop",
        device_key="manager-key",
    )
    workers = store.get_fleet_snapshot(
        user_id=0,
        desktop_id=desktop["desktop_id"],
    )["workers"]

    assert len(workers) == 1
    assert workers[0]["is_default"] is True
    assert workers[0]["protected"] is False


def test_startup_preserves_duplicate_history_as_hidden_removable_worker(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    desktop = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager PC",
        device_platform="desktop",
        device_key="manager-key",
    )
    duplicate = store.create_local_worker(
        user_id=0,
        desktop_id=desktop["desktop_id"],
        display_name="Default Worker",
        metadata={"created_by": "desktop_user_request"},
    )
    duplicate_metadata = default_worker_metadata(duplicate["metadata"])
    store._conn.execute(
        "UPDATE fleet_workers SET metadata = ? WHERE worker_id = ?",
        (json.dumps(duplicate_metadata), duplicate["worker_id"]),
    )
    store._conn.execute(
        "UPDATE fleet_instances SET metadata = ? WHERE worker_id = ?",
        (json.dumps(duplicate_metadata), duplicate["worker_id"]),
    )
    store._conn.commit()
    store.assign_worker_task(
        user_id=0,
        worker_id=duplicate["worker_id"],
        prompt="Preserve this history.",
    )

    store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager PC",
        device_platform="desktop",
        device_key="manager-key",
    )
    workers = store.get_fleet_snapshot(
        user_id=0,
        desktop_id=desktop["desktop_id"],
    )["workers"]
    recovered = next(
        worker for worker in workers if worker["worker_id"] == duplicate["worker_id"]
    )

    assert recovered["is_default"] is False
    assert recovered["protected"] is False
    assert recovered["published_upstream"] is False
    assert recovered["metadata"]["created_by"] == "recovered_default_worker"


def test_manager_optional_tool_packs_persist_across_startup_reconciliation(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    desktop = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager PC",
        device_platform="desktop",
        device_key="manager-key",
    )
    snapshot = store.get_fleet_snapshot(user_id=0, desktop_id=desktop["desktop_id"])
    manager = next(identity for identity in snapshot["identities"] if identity["role"] == "manager")

    updated = store.set_manager_identity_tool_packs(
        user_id=0,
        identity_id=manager["identity_id"],
        enabled_tool_packs=["web_research", "workspace_read"],
    )
    store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager PC",
        device_platform="desktop",
        device_key="manager-key",
    )
    refreshed = store.get_fleet_snapshot(user_id=0, desktop_id=desktop["desktop_id"])
    refreshed_manager = next(identity for identity in refreshed["identities"] if identity["role"] == "manager")

    assert updated["enabled_tool_packs"] == ["manager_core", "web_research", "workspace_read"]
    assert refreshed_manager["enabled_tool_packs"] == updated["enabled_tool_packs"]
    assert {"orchestration", "web", "workspace"}.issubset(refreshed_manager["capability_tags"])


def test_manager_core_cannot_be_removed_from_manager_profile(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    desktop = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager PC",
        device_platform="desktop",
        device_key="manager-key",
    )
    manager = next(
        identity
        for identity in store.get_fleet_snapshot(user_id=0, desktop_id=desktop["desktop_id"])["identities"]
        if identity["role"] == "manager"
    )

    updated = store.set_manager_identity_tool_packs(
        user_id=0,
        identity_id=manager["identity_id"],
        enabled_tool_packs=[],
    )

    assert updated["enabled_tool_packs"] == ["manager_core"]


def test_default_worker_can_be_renamed_and_deleted_without_recreation(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    manager = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager PC",
        device_platform="desktop",
        device_key="manager-key",
    )
    default_worker = next(
        worker
        for worker in store.get_fleet_snapshot(user_id=0, desktop_id=manager["desktop_id"])["workers"]
        if worker["is_default"]
    )

    renamed = store.rename_worker(user_id=0, worker_id=default_worker["worker_id"], display_name="My Worker")
    assert renamed["display_name"] == "My Worker"
    deleted = store.delete_worker(
        user_id=0,
        worker_id=default_worker["worker_id"],
    )
    assert deleted["deleted"] is True

    store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager PC",
        device_platform="desktop",
        device_key="manager-key",
    )
    snapshot = store.get_fleet_snapshot(
        user_id=0,
        desktop_id=manager["desktop_id"],
    )

    assert snapshot["workers"] == []
    managers = [
        item for item in snapshot["identities"] if item["role"] == "manager"
    ]
    assert len(managers) == 1
    assert managers[0]["protected"] is True


def test_additional_worker_identity_carries_its_execution_profile(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    manager = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager PC",
        device_platform="desktop",
        device_key="manager-key",
    )
    worker = store.create_local_worker(
        user_id=0,
        desktop_id=manager["desktop_id"],
        display_name="Build worker",
        metadata={"created_by": "desktop_user_request"},
    )
    snapshot = store.get_fleet_snapshot(user_id=0, desktop_id=manager["desktop_id"])
    identity = next(item for item in snapshot["identities"] if item.get("worker_id") == worker["worker_id"])

    assert identity["tool_profile"] == worker["tool_profile"] == "custom_execution"
    assert identity["enabled_tool_packs"] == worker["enabled_tool_packs"]
    assert "manager_core" not in identity["enabled_tool_packs"]


def test_deleting_selected_worker_cannot_route_its_chat_to_manager(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    manager_desktop = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager PC",
        device_platform="desktop",
        device_key="manager-key",
    )
    worker = store.create_local_worker(
        user_id=0,
        desktop_id=manager_desktop["desktop_id"],
        display_name="Temporary agent",
        metadata={"created_by": "desktop_user_request"},
    )
    before = store.get_fleet_snapshot(user_id=0, desktop_id=manager_desktop["desktop_id"])
    worker_identity = next(
        identity for identity in before["identities"] if identity.get("worker_id") == worker["worker_id"]
    )
    store.set_active_fleet_identity(
        user_id=0,
        identity_id=worker_identity["identity_id"],
        selected_chat_id="worker-chat",
        desktop_id=manager_desktop["desktop_id"],
    )

    store.delete_worker(user_id=0, worker_id=worker["worker_id"])
    snapshot = store.get_fleet_snapshot(user_id=0, desktop_id=manager_desktop["desktop_id"])
    shared_state = store.get_shared_state(user_id=0)

    assert snapshot["active_identity"]["role"] == "manager"
    assert "worker-chat" not in snapshot["selected_chat_by_identity"].values()
    assert shared_state["current_session_id"] is None


def test_snapshot_reads_never_create_or_rotate_manager_identities(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    manager = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager PC",
        device_platform="desktop",
        device_key="manager-key",
    )
    enrollment = store.create_worker_enrollment(
        user_id=0,
        desktop_id=manager["desktop_id"],
        display_name="Child PC",
        metadata={"transport": "yggdrasil"},
    )
    paired = store.complete_worker_enrollment(
        enrollment_token=enrollment["enrollment_token"],
        device_name="Child PC",
        device_platform="windows",
        device_key="child-key",
    )
    child_id = paired["desktop"]["desktop_id"]

    before = store._conn.execute(
        "SELECT instance_id, desktop_id, reset_at FROM fleet_instances WHERE user_id = 0 AND role = 'manager'"
    ).fetchall()
    store.get_fleet_snapshot(user_id=0, desktop_id=child_id)
    store.get_fleet_snapshot(user_id=0, desktop_id=manager["desktop_id"])
    after = store._conn.execute(
        "SELECT instance_id, desktop_id, reset_at FROM fleet_instances WHERE user_id = 0 AND role = 'manager'"
    ).fetchall()

    assert [tuple(row) for row in after] == [tuple(row) for row in before]
    assert len(after) == 1
    assert after[0]["desktop_id"] == manager["desktop_id"]
    assert after[0]["reset_at"] is None


def test_computers_keep_independent_active_identity_selections(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    first = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="First PC",
        device_platform="desktop",
        device_key="first-key",
    )
    second = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Second PC",
        device_platform="desktop",
        device_key="second-key",
    )
    first_snapshot = store.get_fleet_snapshot(user_id=0, desktop_id=first["desktop_id"])
    second_snapshot = store.get_fleet_snapshot(user_id=0, desktop_id=second["desktop_id"])
    first_worker = next(identity for identity in first_snapshot["identities"] if identity["role"] == "worker")
    second_manager = next(identity for identity in second_snapshot["identities"] if identity["role"] == "manager")

    store.set_active_fleet_identity(
        user_id=0,
        identity_id=first_worker["identity_id"],
        desktop_id=first["desktop_id"],
    )
    store.set_active_fleet_identity(
        user_id=0,
        identity_id=second_manager["identity_id"],
        desktop_id=second["desktop_id"],
    )

    for _ in range(3):
        assert store.get_fleet_snapshot(
            user_id=0,
            desktop_id=second["desktop_id"],
        )["active_identity_id"] == second_manager["identity_id"]
        assert store.get_fleet_snapshot(
            user_id=0,
            desktop_id=first["desktop_id"],
        )["active_identity_id"] == first_worker["identity_id"]


def test_remembering_an_inactive_identity_chat_does_not_switch_roles(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    desktop = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Manager PC",
        device_platform="desktop",
        device_key="manager-key",
    )
    snapshot = store.get_fleet_snapshot(user_id=0, desktop_id=desktop["desktop_id"])
    manager = next(identity for identity in snapshot["identities"] if identity["role"] == "manager")
    worker = next(identity for identity in snapshot["identities"] if identity["role"] == "worker")
    store.set_active_fleet_identity(
        user_id=0,
        identity_id=worker["identity_id"],
        selected_chat_id="worker-chat",
        desktop_id=desktop["desktop_id"],
    )

    store.set_active_chat_for_fleet_identity(
        user_id=0,
        identity_id=manager["identity_id"],
        chat_id="manager-chat",
        desktop_id=desktop["desktop_id"],
    )
    refreshed = store.get_fleet_snapshot(user_id=0, desktop_id=desktop["desktop_id"])

    assert refreshed["active_identity_id"] == worker["identity_id"]
    assert refreshed["selected_chat_by_identity"][manager["identity_id"]] == "manager-chat"
    assert refreshed["selected_chat_by_identity"][worker["identity_id"]] == "worker-chat"
