from __future__ import annotations

from app_backend import company_runtime_context
from app_backend.company_runtime_context import resolve_local_company_runtime
from app_backend.company_store import CompanyStore
from app_backend.remote_control_store import RemoteControlPlaneStore


def _desktop(store: RemoteControlPlaneStore):
    return store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Owner PC",
        device_platform="desktop-electron",
        device_key="local-app:test-device",
    )


def _company_store(path):
    return CompanyStore(
        root_path=path,
        protect_payload=lambda payload, *, purpose: {
            "purpose": purpose,
            "payload": dict(payload),
        },
        unprotect_payload=lambda envelope, *, purpose: dict(
            envelope["payload"]
        ),
    )


def test_each_company_membership_gets_a_protected_manager_and_default_worker(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    desktop = _desktop(store)
    desktop_id = desktop["desktop_id"]

    company_a = store.ensure_company_membership_identities(
        user_id=0,
        desktop_id=desktop_id,
        company_id="company-a",
        company_name="Owner PC",
        membership_role="root_controller",
        adopt_unscoped=True,
    )
    company_b = store.ensure_company_membership_identities(
        user_id=0,
        desktop_id=desktop_id,
        company_id="company-b",
        company_name="Owner PC",
        membership_role="worker_node",
        adopt_unscoped=False,
    )
    repeated_company_a = store.ensure_company_membership_identities(
        user_id=0,
        desktop_id=desktop_id,
        company_id="company-a",
        company_name="Owner PC",
        membership_role="root_controller",
        adopt_unscoped=True,
    )

    assert company_a["manager_identity"]["identity_id"] != company_b["manager_identity"]["identity_id"]
    assert company_a["default_worker_identity"]["identity_id"] != company_b["default_worker_identity"]["identity_id"]
    assert company_a["manager_identity"]["metadata"]["company_id"] == "company-a"
    assert company_b["manager_identity"]["metadata"]["company_id"] == "company-b"
    assert company_a["default_worker_identity"]["is_default"] is True
    assert company_b["default_worker_identity"]["is_default"] is True
    assert company_a["manager_identity"]["protected"] is True
    assert company_b["manager_identity"]["protected"] is True
    assert company_a["default_worker_identity"]["protected"] is False
    assert company_b["default_worker_identity"]["protected"] is False
    assert repeated_company_a["manager_identity"]["identity_id"] == company_a["manager_identity"]["identity_id"]
    assert (
        repeated_company_a["default_worker_identity"]["identity_id"]
        == company_a["default_worker_identity"]["identity_id"]
    )

    # Reopening the device shell must not recreate a global pair or demote a
    # different company's default worker.
    _desktop(store)
    raw = store.get_fleet_snapshot(user_id=0, desktop_id=desktop_id)
    assert len([item for item in raw["identities"] if item["role"] == "manager"]) == 2
    assert len([item for item in raw["identities"] if item["role"] == "worker" and item["is_default"]]) == 2


def test_deleted_company_default_worker_stays_deleted(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    desktop = _desktop(store)
    pair = store.ensure_company_membership_identities(
        user_id=0,
        desktop_id=desktop["desktop_id"],
        company_id="company-a",
        company_name="Owner PC",
        membership_role="root_controller",
        adopt_unscoped=True,
    )

    deleted = store.delete_worker(
        user_id=0,
        worker_id=pair["default_worker_identity"]["worker_id"],
    )
    store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Owner PC",
        device_platform="desktop-electron",
        device_key="local-app:test-device",
    )
    repeated = store.ensure_company_membership_identities(
        user_id=0,
        desktop_id=desktop["desktop_id"],
        company_id="company-a",
        company_name="Owner PC",
        membership_role="root_controller",
        adopt_unscoped=True,
    )

    assert deleted["deleted"] is True
    assert repeated["manager_identity"]["protected"] is True
    assert repeated["default_worker_identity"] is None
    scoped = store.get_fleet_snapshot(
        user_id=0,
        desktop_id=desktop["desktop_id"],
        company_id="company-a",
        company_computer_ids=[desktop["desktop_id"]],
    )
    assert [item for item in scoped["identities"] if item["role"] == "worker"] == []


def test_company_snapshot_never_exposes_another_company_identity_or_task(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    desktop = _desktop(store)
    desktop_id = desktop["desktop_id"]
    company_a = store.ensure_company_membership_identities(
        user_id=0,
        desktop_id=desktop_id,
        company_id="company-a",
        company_name="Owner PC",
        membership_role="root_controller",
        adopt_unscoped=True,
    )
    company_b = store.ensure_company_membership_identities(
        user_id=0,
        desktop_id=desktop_id,
        company_id="company-b",
        company_name="Owner PC",
        membership_role="worker_node",
        adopt_unscoped=False,
    )
    worker_a = company_a["default_worker_identity"]["worker_id"]
    worker_b = company_b["default_worker_identity"]["worker_id"]
    store.assign_worker_task(
        user_id=0,
        worker_id=worker_a,
        prompt="Company A work",
        metadata={"company_id": "company-a"},
    )
    store.assign_worker_task(
        user_id=0,
        worker_id=worker_b,
        prompt="Company B work",
        metadata={"company_id": "company-b"},
    )

    snapshot_a = store.get_fleet_snapshot(
        user_id=0,
        desktop_id=desktop_id,
        company_id="company-a",
        company_computer_ids=[desktop_id],
    )
    snapshot_b = store.get_fleet_snapshot(
        user_id=0,
        desktop_id=desktop_id,
        company_id="company-b",
        company_computer_ids=[desktop_id],
    )

    assert {item["metadata"]["company_id"] for item in snapshot_a["identities"]} == {"company-a"}
    assert {item["metadata"]["company_id"] for item in snapshot_b["identities"]} == {"company-b"}
    assert [item["prompt"] for item in snapshot_a["tasks"]] == ["Company A work"]
    assert [item["prompt"] for item in snapshot_b["tasks"]] == ["Company B work"]
    assert snapshot_a["active_identity"]["role"] == "manager"
    assert snapshot_b["active_identity"]["role"] == "manager"


def test_company_snapshot_does_not_leak_delegations_through_shared_computer(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    root = _desktop(store)
    child = store.ensure_standalone_manager_desktop(
        user_id=0,
        display_name="Shared child",
        device_platform="desktop-electron",
        device_key="local-app:shared-child",
    )
    company_a = store.create_computer_delegation(
        user_id=0,
        desktop_id=child["desktop_id"],
        prompt="Company A delegation",
        metadata={"company_id": "company-a"},
    )
    company_b = store.create_computer_delegation(
        user_id=0,
        desktop_id=child["desktop_id"],
        prompt="Company B delegation",
        metadata={"company_id": "company-b"},
    )

    snapshot_a = store.get_fleet_snapshot(
        user_id=0,
        desktop_id=root["desktop_id"],
        company_id="company-a",
        company_computer_ids=[root["desktop_id"], child["desktop_id"]],
    )
    snapshot_b = store.get_fleet_snapshot(
        user_id=0,
        desktop_id=root["desktop_id"],
        company_id="company-b",
        company_computer_ids=[root["desktop_id"], child["desktop_id"]],
    )

    assert [item["delegation_id"] for item in snapshot_a["delegations"]] == [
        company_a["delegation_id"]
    ]
    assert [item["delegation_id"] for item in snapshot_b["delegations"]] == [
        company_b["delegation_id"]
    ]


def test_company_identity_chat_selection_does_not_replace_global_session(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    desktop = _desktop(store)
    company = store.ensure_company_membership_identities(
        user_id=0,
        desktop_id=desktop["desktop_id"],
        company_id="company-a",
        company_name="Owner PC",
        membership_role="root_controller",
        adopt_unscoped=True,
    )
    manager_id = company["manager_identity"]["identity_id"]
    store.update_shared_snapshot(
        user_id=0,
        desktop_id=desktop["desktop_id"],
        snapshot={"current_session_id": "legacy-global-chat"},
    )

    store.set_active_chat_for_fleet_identity(
        user_id=0,
        identity_id=manager_id,
        chat_id="company-a-chat",
        desktop_id=desktop["desktop_id"],
        company_id="company-a",
    )

    assert store.get_shared_state(user_id=0)["current_session_id"] == "legacy-global-chat"
    snapshot = store.get_fleet_snapshot(
        user_id=0,
        desktop_id=desktop["desktop_id"],
        company_id="company-a",
        company_computer_ids=[desktop["desktop_id"]],
    )
    assert snapshot["selected_chat_by_identity"][manager_id] == "company-a-chat"


def test_explicit_company_migration_scopes_only_unscoped_fleet_records(
    tmp_path,
):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    desktop = _desktop(store)
    legacy_snapshot = store.get_fleet_snapshot(
        user_id=0,
        desktop_id=desktop["desktop_id"],
    )
    legacy_identity_ids = {
        item["identity_id"] for item in legacy_snapshot["identities"]
    }
    other = store.ensure_company_membership_identities(
        user_id=0,
        desktop_id=desktop["desktop_id"],
        company_id="company-other",
        company_name="Other Company",
        membership_role="worker_node",
        adopt_unscoped=False,
    )
    other_identity_ids = {
        other["manager_identity"]["identity_id"],
        other["default_worker_identity"]["identity_id"],
    }

    preview = store.preview_unscoped_company_records(user_id=0)
    assert preview["unscoped_total"] >= 4

    report = store.migrate_unscoped_company_records(
        user_id=0,
        company_id="company-root",
    )
    snapshot = store.get_fleet_snapshot(
        user_id=0,
        desktop_id=desktop["desktop_id"],
    )
    identities = {
        item["identity_id"]: item for item in snapshot["identities"]
    }

    assert report["migrated_total"] >= 4
    assert {
        identities[identity_id]["metadata"]["company_id"]
        for identity_id in legacy_identity_ids
    } == {"company-root"}
    assert {
        identities[identity_id]["metadata"]["company_id"]
        for identity_id in other_identity_ids
    } == {"company-other"}
    assert (
        store.migrate_unscoped_company_records(
            user_id=0,
            company_id="company-root",
        )["migrated_total"]
        == 0
    )


def test_company_fleet_cleanup_preserves_other_company_and_computer(
    tmp_path,
):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    desktop = _desktop(store)
    company_a = store.ensure_company_membership_identities(
        user_id=0,
        desktop_id=desktop["desktop_id"],
        company_id="company-a",
        company_name="Company A",
        membership_role="root_controller",
        adopt_unscoped=True,
    )
    company_b = store.ensure_company_membership_identities(
        user_id=0,
        desktop_id=desktop["desktop_id"],
        company_id="company-b",
        company_name="Company B",
        membership_role="worker_node",
        adopt_unscoped=False,
    )
    task_a = store.assign_worker_task(
        user_id=0,
        worker_id=company_a["default_worker_identity"]["worker_id"],
        prompt="Company A task",
        metadata={"company_id": "company-a"},
    )
    task_b = store.assign_worker_task(
        user_id=0,
        worker_id=company_b["default_worker_identity"]["worker_id"],
        prompt="Company B task",
        metadata={"company_id": "company-b"},
    )

    report = store.delete_company_records(
        user_id=0,
        company_id="company-a",
    )
    raw = store.get_fleet_snapshot(
        user_id=0,
        desktop_id=desktop["desktop_id"],
    )

    assert report["deleted_total"] > 0
    assert desktop["desktop_id"] in {
        item["desktop_id"] for item in raw["desktops"]
    }
    assert task_a["task_id"] not in {
        item["task_id"] for item in raw["tasks"]
    }
    assert task_b["task_id"] in {
        item["task_id"] for item in raw["tasks"]
    }
    assert {
        item["metadata"].get("company_id") for item in raw["identities"]
    } == {"company-b"}


def test_paired_membership_reconciles_its_own_local_identity_pair(
    tmp_path,
    monkeypatch,
):
    root_company_store = _company_store(tmp_path / "root-company")
    root_company = root_company_store.ensure_default_company(
        computer_id="root-computer",
        computer_name="Root",
        manager_identity={
            "identity_id": "root-manager",
            "display_name": "Root Manager",
            "role": "manager",
            "status": "active",
            "metadata": {},
        },
        default_worker_identity={
            "identity_id": "root-worker",
            "display_name": "Root Worker",
            "role": "worker",
            "status": "active",
            "metadata": {"is_default": True},
        },
    )
    bundle = root_company_store.register_child_membership(
        company_id=root_company["company_id"],
        parent_computer_id="root-computer",
        child_computer_id="root-view-of-child",
        child_computer_name="Child",
    )
    monkeypatch.setattr(
        company_runtime_context,
        "load_fleet_connection",
        lambda _home: {"companyMembership": bundle},
    )
    monkeypatch.setattr(
        company_runtime_context,
        "runtime_home",
        lambda: tmp_path / "child-home",
    )

    child_fleet_store = RemoteControlPlaneStore(
        root_path=tmp_path / "child-fleet"
    )
    child_company_store = _company_store(tmp_path / "child-company")
    runtime = resolve_local_company_runtime(
        auth={
            "user_id": 0,
            "device_id": "child-device",
            "device_name": "Child",
            "device_platform": "desktop-electron",
        },
        company_store=child_company_store,
        fleet_store=child_fleet_store,
    )

    assert runtime is not None
    companies = child_company_store.list_companies(
        computer_id=runtime["computer_id"]
    )
    assert len(companies) == 2
    assert runtime["company_id"] != root_company["company_id"]
    member_company = child_company_store.get_company(
        root_company["company_id"]
    )
    member_identity_ids = {
        item["identity_id"] for item in member_company["employees"]
    }
    member_snapshot = child_fleet_store.get_fleet_snapshot(
        user_id=0,
        desktop_id=runtime["computer_id"],
        company_id=root_company["company_id"],
        company_computer_ids=[runtime["computer_id"]],
    )
    assert len(member_identity_ids) == 2
    assert {
        item["identity_id"] for item in member_snapshot["identities"]
    } == member_identity_ids
