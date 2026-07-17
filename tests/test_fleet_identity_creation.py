from __future__ import annotations

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
    assert snapshot["workers"] == []


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
