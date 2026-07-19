from __future__ import annotations

import time

import pytest

from app_backend.fleet_identity_creation import validate_local_worker_creation
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
    assert snapshot["workers"][0]["protected"] is True


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
    assert defaults[0]["protected"] is True
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


def test_protected_default_worker_can_be_renamed_but_not_deleted(tmp_path):
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
    with pytest.raises(PermissionError, match="protected default worker"):
        store.delete_worker(user_id=0, worker_id=default_worker["worker_id"])


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
