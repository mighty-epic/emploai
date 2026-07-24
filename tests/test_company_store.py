from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app_backend.company_store import (
    CompanyPartitionError,
    CompanyRootExistsError,
    CompanySelectionError,
    CompanyStore,
)


def _protect(payload, *, purpose):
    return {"storage": "test-vault", "purpose": purpose, "payload": dict(payload)}


def _unprotect(envelope, *, purpose):
    assert envelope["purpose"] == purpose
    return dict(envelope["payload"])


def _store(tmp_path):
    return CompanyStore(
        root_path=tmp_path,
        protect_payload=_protect,
        unprotect_payload=_unprotect,
    )


def _manager():
    return {
        "identity_id": "mgr_local",
        "display_name": "EmploAI Desktop",
        "role": "manager",
        "status": "active",
        "protected": True,
        "metadata": {"protected": True},
    }


def _worker():
    return {
        "identity_id": "wrk_default",
        "display_name": "Default Worker",
        "role": "worker",
        "status": "active",
        "is_default": True,
        "protected": True,
        "metadata": {"is_default": True, "protected": True},
    }


def test_default_company_is_idempotent_and_reconciles_protected_identities(tmp_path):
    store = _store(tmp_path)

    first = store.ensure_default_company(
        computer_id="computer-a",
        computer_name="Owner PC",
        manager_identity=_manager(),
        default_worker_identity=_worker(),
    )
    second = store.ensure_default_company(
        computer_id="computer-a",
        computer_name="Owner PC",
        manager_identity=_manager(),
        default_worker_identity=_worker(),
    )

    assert second["company_id"] == first["company_id"]
    assert second["manifest"]["root_computer_id"] == "computer-a"
    assert len(second["memberships"]) == 1
    assert second["memberships"][0]["manager_identity_id"] == "mgr_local"
    assert second["memberships"][0]["default_worker_identity_id"] == "wrk_default"
    assert {item["company_role"] for item in second["employees"]} == {"CEO", "General worker"}
    assert all(item["protected"] for item in second["employees"])
    assert len(store.list_companies(computer_id="computer-a")) == 1


def test_company_partition_does_not_store_manifest_as_plaintext(tmp_path):
    store = _store(tmp_path)
    company = store.create_root_company(
        computer_id="computer-a",
        computer_name="Owner PC",
        display_name="Private Acme",
    )

    data_path = tmp_path / "companies" / company["company_id"] / "company.data.json"
    raw = data_path.read_text(encoding="utf-8")

    assert json.loads(raw)["algorithm"] == "AES-256-GCM"
    assert "Private Acme" not in raw
    assert "reserved_decisions" not in raw


def test_version_one_rejects_second_locally_owned_root_company(tmp_path):
    store = _store(tmp_path)
    store.create_root_company(
        computer_id="computer-a",
        computer_name="Owner PC",
        display_name="First",
    )

    with pytest.raises(CompanyRootExistsError):
        store.create_root_company(
            computer_id="computer-a",
            computer_name="Owner PC",
            display_name="Second",
        )


def test_active_company_restores_last_explicit_selection(tmp_path):
    store = _store(tmp_path)
    company = store.create_root_company(
        computer_id="computer-a",
        computer_name="Owner PC",
        display_name="Selected Company",
    )

    selected = store.select_company(
        computer_id="computer-a",
        company_id=company["company_id"],
    )
    reopened = _store(tmp_path)

    assert selected["company_id"] == company["company_id"]
    assert reopened.active_company_id(computer_id="computer-a") == company["company_id"]


def test_legacy_migration_requires_and_records_verified_backup(tmp_path):
    store = _store(tmp_path)
    company = store.ensure_default_company(
        computer_id="computer-a",
        computer_name="Owner PC",
        manager_identity=_manager(),
        default_worker_identity=_worker(),
    )

    with pytest.raises(CompanySelectionError, match="backup"):
        store.complete_migration(
            company_id=company["company_id"],
            verified_backup_id="missing",
        )

    store.record_verified_backup(
        company_id=company["company_id"],
        backup_id="cbk_verified",
        created_at="2026-07-23T00:00:00+00:00",
    )
    completed = store.complete_migration(
        company_id=company["company_id"],
        verified_backup_id="cbk_verified",
    )
    saved = store.get_company(company["company_id"])

    assert completed["migration"]["state"] == "completed"
    assert saved["migration"]["verified"] is True
    assert saved["migration"]["verified_backup_id"] == "cbk_verified"
    assert saved["migration"]["mapping_report"]["counts"]["employees"] == 2


def test_root_company_deletion_keeps_signed_tombstone_and_starts_fresh(tmp_path):
    store = _store(tmp_path)
    company = store.ensure_default_company(
        computer_id="computer-a",
        computer_name="Owner PC",
        manager_identity=_manager(),
        default_worker_identity=_worker(),
    )
    company_id = company["company_id"]
    store.record_verified_backup(
        company_id=company_id,
        backup_id="cbk_final",
        created_at="2026-07-23T00:00:00+00:00",
    )

    preview = store.deletion_preview(
        company_id=company_id,
        computer_id="computer-a",
    )
    assert preview["membership_count"] == 1
    with pytest.raises(CompanySelectionError, match="exact company name"):
        store.delete_root_company(
            company_id=company_id,
            computer_id="computer-a",
            company_name_confirmation="Wrong",
            active_work_action="cancel",
        )

    deleted = store.delete_root_company(
        company_id=company_id,
        computer_id="computer-a",
        company_name_confirmation="My Company",
        active_work_action="cancel",
        final_backup_id="cbk_final",
    )
    tombstone = deleted["tombstone"]
    Ed25519PublicKey.from_public_bytes(
        base64.b64decode(tombstone["public_key"])
    ).verify(
        base64.b64decode(tombstone["signature"]),
        json.dumps(
            tombstone["payload"],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8"),
    )

    assert not (tmp_path / "companies" / company_id).exists()
    assert store.active_company_id(computer_id="computer-a") is None
    assert store.list_companies(computer_id="computer-a")[0]["status"] == "revoked"
    replacement = store.ensure_default_company(
        computer_id="computer-a",
        computer_name="Owner PC",
        manager_identity=_manager(),
        default_worker_identity=_worker(),
    )
    assert replacement["company_id"] != company_id


def test_root_identity_role_is_not_shared_with_another_computer(tmp_path):
    store = _store(tmp_path)
    first = store.ensure_default_company(
        computer_id="computer-a",
        computer_name="Owner PC",
        manager_identity=_manager(),
        default_worker_identity=_worker(),
    )
    second = store.ensure_default_company(
        computer_id="computer-b",
        computer_name="Other PC",
        manager_identity={**_manager(), "identity_id": "mgr_other"},
        default_worker_identity={**_worker(), "identity_id": "wrk_other"},
    )

    assert first["company_id"] != second["company_id"]
    assert store.active_company_id(computer_id="computer-a") == first["company_id"]
    assert store.active_company_id(computer_id="computer-b") == second["company_id"]


def test_child_keeps_own_company_and_imports_signed_parent_membership(tmp_path):
    root_store = _store(tmp_path / "root")
    root_company = root_store.ensure_default_company(
        computer_id="root-computer",
        computer_name="Root PC",
        manager_identity=_manager(),
        default_worker_identity=_worker(),
    )
    bundle = root_store.register_child_membership(
        company_id=root_company["company_id"],
        parent_computer_id="root-computer",
        child_computer_id="root-view-of-child",
        child_computer_name="Child PC",
    )

    child_store = _store(tmp_path / "child")
    child_company = child_store.ensure_default_company(
        computer_id="child-local",
        computer_name="Child PC",
        manager_identity={**_manager(), "identity_id": "child-own-manager"},
        default_worker_identity={**_worker(), "identity_id": "child-own-worker"},
    )
    imported = child_store.import_member_company(
        bundle=bundle,
        local_computer_id="child-local",
        local_computer_name="Child PC",
    )

    assert imported["company_id"] == root_company["company_id"]
    assert imported["memberships"][0]["computer_id"] == "child-local"
    assert (
        imported["memberships"][0]["upstream_computer_id"]
        == "root-view-of-child"
    )
    assert imported["upstream_cache"]["algorithm"] == "Ed25519"
    assert child_store.active_company_id(computer_id="child-local") == child_company["company_id"]
    assert len(child_store.list_companies(computer_id="child-local")) == 2


def test_tampered_membership_bundle_is_rejected(tmp_path):
    root_store = _store(tmp_path / "root")
    root_company = root_store.create_root_company(
        computer_id="root-computer",
        computer_name="Root PC",
        display_name="Signed Company",
    )
    bundle = root_store.register_child_membership(
        company_id=root_company["company_id"],
        parent_computer_id="root-computer",
        child_computer_id="root-view-of-child",
        child_computer_name="Child PC",
    )
    bundle["payload"]["manifest"]["display_name"] = "Tampered Company"

    with pytest.raises(CompanyPartitionError, match="signature"):
        _store(tmp_path / "child").import_member_company(
            bundle=bundle,
            local_computer_id="child-local",
            local_computer_name="Child PC",
        )


def test_root_directory_syncs_only_published_child_identities(tmp_path):
    store = _store(tmp_path)
    company = store.ensure_default_company(
        computer_id="root-computer",
        computer_name="Root PC",
        manager_identity=_manager(),
        default_worker_identity=_worker(),
    )
    bundle = store.register_child_membership(
        company_id=company["company_id"],
        parent_computer_id="root-computer",
        child_computer_id="child-computer",
        child_computer_name="Child PC",
    )
    membership_id = bundle["payload"]["membership"]["membership_id"]

    synced = store.sync_published_membership_identities(
        company_id=company["company_id"],
        child_computer_id="child-computer",
        membership_id=membership_id,
        identities=[
            {
                "identity_id": "child-manager",
                "display_name": "Child Manager",
                "role": "manager",
                "status": "active",
                "protected": True,
            },
            {
                "identity_id": "child-worker",
                "display_name": "Child Worker",
                "role": "worker",
                "status": "active",
                "protected": True,
                "is_default": True,
            },
        ],
    )

    saved = store.get_company(company["company_id"])
    child_employees = [
        item
        for item in saved["employees"]
        if item["home_membership_id"] == membership_id
    ]
    assert synced["manager_identity_id"] == "child-manager"
    assert synced["default_worker_identity_id"] == "child-worker"
    assert {item["identity_id"] for item in child_employees} == {
        "child-manager",
        "child-worker",
    }


def test_published_identity_sync_is_idempotent_and_retires_hidden_targets(
    tmp_path,
):
    store = _store(tmp_path)
    company = store.create_root_company(
        computer_id="root-computer",
        computer_name="Root PC",
        display_name="Root Company",
    )
    bundle = store.register_child_membership(
        company_id=company["company_id"],
        parent_computer_id="root-computer",
        child_computer_id="child-computer",
        child_computer_name="Child PC",
    )
    membership_id = bundle["payload"]["membership"]["membership_id"]
    targets = [
        {
            "identity_id": "child-manager",
            "display_name": "Child Manager",
            "role": "manager",
            "status": "active",
            "protected": True,
        },
        {
            "identity_id": "child-worker",
            "display_name": "Child Worker",
            "role": "worker",
            "status": "active",
            "protected": True,
            "is_default": True,
        },
    ]

    store.sync_published_membership_identities(
        company_id=company["company_id"],
        child_computer_id="child-computer",
        membership_id=membership_id,
        identities=targets,
    )
    first_revision = store.get_company(company["company_id"])["revision"]
    store.sync_published_membership_identities(
        company_id=company["company_id"],
        child_computer_id="child-computer",
        membership_id=membership_id,
        identities=targets,
    )
    assert (
        store.get_company(company["company_id"])["revision"]
        == first_revision
    )

    store.sync_published_membership_identities(
        company_id=company["company_id"],
        child_computer_id="child-computer",
        membership_id=membership_id,
        identities=targets[:1],
    )
    saved = store.get_company(company["company_id"])
    hidden_worker = next(
        item
        for item in saved["employees"]
        if item["identity_id"] == "child-worker"
    )
    assert saved["revision"] == first_revision + 1
    assert hidden_worker["status"] == "unavailable"
    assert hidden_worker["published_upstream"] is False


def test_member_cache_rejects_a_signed_revision_rollback(tmp_path):
    root_store = _store(tmp_path / "root")
    root_company = root_store.create_root_company(
        computer_id="root-computer",
        computer_name="Root PC",
        display_name="Root Company",
    )
    first_bundle = root_store.register_child_membership(
        company_id=root_company["company_id"],
        parent_computer_id="root-computer",
        child_computer_id="child-computer",
        child_computer_name="Child PC",
    )
    child_store = _store(tmp_path / "child")
    child_store.import_member_company(
        bundle=first_bundle,
        local_computer_id="child-local",
        local_computer_name="Child PC",
    )
    root_store.update_company(
        company_id=root_company["company_id"],
        manifest_updates={"purpose": "Updated purpose"},
    )
    latest_bundle = root_store.issue_child_membership_bundle(
        company_id=root_company["company_id"],
        child_computer_id="child-computer",
    )
    latest = child_store.import_member_company(
        bundle=latest_bundle,
        local_computer_id="child-local",
        local_computer_name="Child PC",
    )
    assert latest["manifest"]["purpose"] == "Updated purpose"

    with pytest.raises(CompanyPartitionError, match="older"):
        child_store.import_member_company(
            bundle=first_bundle,
            local_computer_id="child-local",
            local_computer_name="Child PC",
        )
