import sqlite3
import base64
import time

import pytest

from app_backend.fleet_policy import (
    MAX_FLEET_ENROLLMENT_TTL_SECONDS,
    MIN_FLEET_ENROLLMENT_TTL_SECONDS,
)
from app_backend.fleet_report_validation import (
    MAX_FLEET_REPORT_LIST_ITEMS,
    MAX_FLEET_REPORT_NEXT_ACTION_CHARS,
    MAX_FLEET_REPORT_SUMMARY_CHARS,
)
from app_backend.remote_control_store import AUTH_OTP_MAX_ATTEMPTS, REMOTE_CONTROL_DB_FILENAME, RemoteControlPlaneStore


def test_remote_control_store_registers_login_and_pairs_mobile_to_desktop(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)

    user = store.register_user(email="user@example.com", password="CorrectHorse!2026", display_name="User")
    assert user["email"] == "user@example.com"

    desktop_login = store.login(
        email="user@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Workstation",
        device_platform="desktop-electron",
        device_key="desktop-key",
    )
    mobile_login = store.login(
        email="user@example.com",
        password="CorrectHorse!2026",
        actor_kind="mobile",
        device_name="Pixel",
        device_platform="android",
        device_key="phone-key",
    )

    desktop_payload = store.resolve_session_token(desktop_login["session_token"])
    mobile_payload = store.resolve_session_token(mobile_login["session_token"])

    assert desktop_payload is not None
    assert mobile_payload is not None
    assert desktop_payload["actor_kind"] == "desktop"
    assert mobile_payload["actor_kind"] == "mobile"

    pairing = store.create_pairing(
        user_id=user["user_id"],
        desktop_id=desktop_login["desktop"]["desktop_id"],
    )
    paired = store.complete_pairing(
        user_id=user["user_id"],
        pairing_token=pairing["pairing_token"],
        mobile_id=mobile_login["mobile"]["mobile_id"],
    )

    assert paired["desktop"]["desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert paired["mobile"]["paired_desktop_id"] == desktop_login["desktop"]["desktop_id"]
    assert store.paired_desktop_id_for_payload(mobile_payload) == desktop_login["desktop"]["desktop_id"]


def test_remote_control_store_paired_desktop_lookup_is_user_scoped(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)

    first_user = store.register_user(email="first@example.com", password="CorrectHorse!2026", display_name="First")
    first_desktop = store.login(
        email="first@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="First Desk",
        device_platform="desktop-electron",
        device_key="first-desktop",
    )
    first_mobile = store.login(
        email="first@example.com",
        password="CorrectHorse!2026",
        actor_kind="mobile",
        device_name="First Phone",
        device_platform="android",
        device_key="first-mobile",
    )
    pairing = store.create_pairing(
        user_id=first_user["user_id"],
        desktop_id=first_desktop["desktop"]["desktop_id"],
    )
    store.complete_pairing(
        user_id=first_user["user_id"],
        pairing_token=pairing["pairing_token"],
        mobile_id=first_mobile["mobile"]["mobile_id"],
    )

    second_user = store.register_user(email="second@example.com", password="CorrectHorse!2026", display_name="Second")
    second_desktop = store.login(
        email="second@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Second Desk",
        device_platform="desktop-electron",
        device_key="second-desktop",
    )

    assert store.paired_desktop_id_for_payload(
        {
            "actor_kind": "mobile",
            "user_id": first_user["user_id"],
            "mobile_id": first_mobile["mobile"]["mobile_id"],
        }
    ) == first_desktop["desktop"]["desktop_id"]
    assert store.paired_desktop_id_for_payload(
        {
            "actor_kind": "mobile",
            "user_id": second_user["user_id"],
            "mobile_id": first_mobile["mobile"]["mobile_id"],
        }
    ) is None
    assert store.paired_desktop_id_for_payload(
        {
            "actor_kind": "desktop",
            "user_id": second_user["user_id"],
            "desktop_id": first_desktop["desktop"]["desktop_id"],
        }
    ) is None
    assert store.paired_desktop_id_for_payload(
        {
            "actor_kind": "desktop",
            "user_id": second_user["user_id"],
            "desktop_id": second_desktop["desktop"]["desktop_id"],
        }
    ) == second_desktop["desktop"]["desktop_id"]


def test_remote_control_store_fleet_snapshot_scopes_manager_identity_to_desktop(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="scope@example.com", password="CorrectHorse!2026", display_name="Scope")
    old_desktop = store.login(
        email="scope@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Old Manager",
        device_platform="desktop-electron",
        device_key="old-manager-key",
    )
    current_desktop = store.login(
        email="scope@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Current Manager",
        device_platform="desktop-electron",
        device_key="current-manager-key",
    )
    old_desktop_id = old_desktop["desktop"]["desktop_id"]
    current_desktop_id = current_desktop["desktop"]["desktop_id"]
    old_snapshot = store.get_fleet_snapshot(user_id=user["user_id"], desktop_id=old_desktop_id)
    old_manager = next(item for item in old_snapshot["identities"] if item["role"] == "manager")
    worker = store.create_local_worker(user_id=user["user_id"], desktop_id=current_desktop_id, display_name="Scoped Worker")

    store.set_active_fleet_identity(
        user_id=user["user_id"],
        identity_id=old_manager["identity_id"],
        selected_chat_id="old-manager-chat",
        source="test",
    )
    scoped_snapshot = store.get_fleet_snapshot(user_id=user["user_id"], desktop_id=current_desktop_id)

    managers = [item for item in scoped_snapshot["identities"] if item["role"] == "manager"]
    assert len(managers) == 1
    assert managers[0]["desktop_id"] == current_desktop_id
    assert scoped_snapshot["manager"]["desktop_id"] == current_desktop_id
    assert scoped_snapshot["active_identity_id"] == managers[0]["identity_id"]
    assert old_manager["identity_id"] not in scoped_snapshot["selected_chat_by_identity"]
    assert any(item["worker_id"] == worker["worker_id"] for item in scoped_snapshot["identities"])


def test_remote_control_store_fleet_snapshot_prunes_inactive_old_manager_identity(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="prune-manager@example.com", password="CorrectHorse!2026", display_name="Prune Manager")
    old_desktop = store.login(
        email="prune-manager@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Old Manager",
        device_platform="desktop-electron",
        device_key="old-prune-manager-key",
    )
    old_desktop_id = old_desktop["desktop"]["desktop_id"]
    old_snapshot = store.get_fleet_snapshot(user_id=user["user_id"], desktop_id=old_desktop_id)
    old_manager = next(item for item in old_snapshot["identities"] if item["role"] == "manager")
    assert store.revoke_session_token(old_desktop["session_token"]) is True

    current_desktop = store.login(
        email="prune-manager@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Current Manager",
        device_platform="desktop-electron",
        device_key="current-prune-manager-key",
    )
    current_desktop_id = current_desktop["desktop"]["desktop_id"]
    store.set_active_fleet_identity(
        user_id=user["user_id"],
        identity_id=old_manager["identity_id"],
        selected_chat_id="old-manager-chat",
        source="test",
    )

    snapshot = store.get_fleet_snapshot(user_id=user["user_id"], desktop_id=current_desktop_id)

    managers = [item for item in snapshot["identities"] if item["role"] == "manager"]
    assert len(managers) == 1
    assert managers[0]["desktop_id"] == current_desktop_id
    assert old_manager["identity_id"] not in {item["identity_id"] for item in snapshot["identities"]}
    assert snapshot["active_identity_id"] == managers[0]["identity_id"]
    assert old_manager["identity_id"] not in snapshot["selected_chat_by_identity"]
    old_row = store._conn.execute(
        "SELECT status, reset_at FROM fleet_instances WHERE instance_id = ?",
        (old_manager["identity_id"],),
    ).fetchone()
    assert old_row["status"] == "stale"
    assert old_row["reset_at"] is not None


def test_remote_control_store_rejects_off_desktop_manager_selection_when_scoped(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="scoped-select@example.com", password="CorrectHorse!2026", display_name="Scoped Select")
    old_desktop = store.login(
        email="scoped-select@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Old Manager",
        device_platform="desktop-electron",
        device_key="old-scoped-select-key",
    )
    current_desktop = store.login(
        email="scoped-select@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Current Manager",
        device_platform="desktop-electron",
        device_key="current-scoped-select-key",
    )
    old_snapshot = store.get_fleet_snapshot(user_id=user["user_id"], desktop_id=old_desktop["desktop"]["desktop_id"])
    old_manager = next(item for item in old_snapshot["identities"] if item["role"] == "manager")

    with pytest.raises(KeyError, match="Unknown fleet identity"):
        store.set_active_fleet_identity(
            user_id=user["user_id"],
            identity_id=old_manager["identity_id"],
            desktop_id=current_desktop["desktop"]["desktop_id"],
            source="test",
        )


def test_remote_control_store_fleet_manager_local_worker_and_task_report(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="fleet@example.com", password="CorrectHorse!2026", display_name="Fleet")
    desktop_login = store.login(
        email="fleet@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Manager PC",
        device_platform="desktop-electron",
        device_key="manager-key",
    )
    desktop_id = desktop_login["desktop"]["desktop_id"]

    snapshot = store.get_fleet_snapshot(user_id=user["user_id"], desktop_id=desktop_id)
    assert snapshot["manager"]["role"] == "manager"
    assert snapshot["manager"]["desktop_id"] == desktop_id

    worker = store.create_local_worker(user_id=user["user_id"], desktop_id=desktop_id)
    assert worker["kind"] == "local"
    assert worker["display_name"] == "Worker-001"

    first_task = store.assign_worker_task(user_id=user["user_id"], worker_id=worker["worker_id"], prompt="Prepare a report")
    second_task = store.assign_worker_task(user_id=user["user_id"], worker_id=worker["worker_id"], prompt="Then summarize it")
    assert first_task["queue_position"] == 1
    assert second_task["queue_position"] == 2

    running = store.update_worker_task_status(user_id=user["user_id"], task_id=first_task["task_id"], status="running")
    assert running["status"] == "running"
    assert store.get_next_queued_worker_task(user_id=user["user_id"], worker_id=worker["worker_id"]) is None

    report = store.complete_worker_task_report(
        user_id=user["user_id"],
        task_id=first_task["task_id"],
        status="completed",
        summary="Report prepared.",
        evidence=[{"kind": "file", "path": "report.md"}],
        artifacts=[{"artifact_id": "art_1"}],
        blockers=[],
        confidence="high",
        next_suggested_action="Review the report.",
    )
    assert report["summary"] == "Report prepared."
    assert report["evidence"][0]["path"] == "report.md"
    assert store.get_next_queued_worker_task(user_id=user["user_id"], worker_id=worker["worker_id"]) is None
    reviewed_worker = store.mark_worker_queue_reviewed(
        user_id=user["user_id"],
        worker_id=worker["worker_id"],
        reviewed_report_id=report["report_id"],
    )
    assert reviewed_worker["metadata"]["last_queue_review"]["reviewed_report_id"] == report["report_id"]
    next_task = store.get_next_queued_worker_task(user_id=user["user_id"], worker_id=worker["worker_id"])
    assert next_task is not None
    assert next_task["task_id"] == second_task["task_id"]

    snapshot = store.get_fleet_snapshot(user_id=user["user_id"], desktop_id=desktop_id)
    assert len(snapshot["workers"]) == 1
    assert snapshot["active_identity"]["role"] == "manager"
    assert snapshot["identities"][0]["role"] == "manager"
    assert len(snapshot["reports"]) == 1
    assert any(event["event_type"] == "worker_report_completed" for event in snapshot["audit_events"])


def test_remote_control_store_repairs_completed_report_without_evidence(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="fleet-review@example.com", password="CorrectHorse!2026", display_name="Fleet Review")
    desktop_login = store.login(
        email="fleet-review@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Manager PC",
        device_platform="desktop-electron",
        device_key="manager-key",
    )
    worker = store.create_local_worker(user_id=user["user_id"], desktop_id=desktop_login["desktop"]["desktop_id"])
    task = store.assign_worker_task(user_id=user["user_id"], worker_id=worker["worker_id"], prompt="Verify a claim")
    store.update_worker_task_status(user_id=user["user_id"], task_id=task["task_id"], status="running")

    report = store.complete_worker_task_report(
        user_id=user["user_id"],
        task_id=task["task_id"],
        status="completed",
        summary="Looks done.",
        evidence=[],
        artifacts=[],
        confidence="high",
    )

    assert report["status"] == "needs_review"
    assert report["confidence"] == "medium"
    assert report["blockers"][0]["kind"] == "report_validation"
    assert report["raw"]["runtime_repaired_fields"]["completion_missing_evidence"] is True
    snapshot = store.get_fleet_snapshot(user_id=user["user_id"], desktop_id=desktop_login["desktop"]["desktop_id"])
    worker_snapshot = next(item for item in snapshot["workers"] if item["worker_id"] == worker["worker_id"])
    assert worker_snapshot["status"] == "needs_review"
    assert worker_snapshot["active_task_id"] == task["task_id"]


def test_remote_control_store_rejects_duplicate_worker_task_reports(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="fleet-duplicate@example.com", password="CorrectHorse!2026", display_name="Fleet Duplicate")
    desktop_login = store.login(
        email="fleet-duplicate@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Manager PC",
        device_platform="desktop-electron",
        device_key="manager-key",
    )
    worker = store.create_local_worker(user_id=user["user_id"], desktop_id=desktop_login["desktop"]["desktop_id"])
    task = store.assign_worker_task(user_id=user["user_id"], worker_id=worker["worker_id"], prompt="Write a report")

    first_report = store.complete_worker_task_report(
        user_id=user["user_id"],
        task_id=task["task_id"],
        status="completed",
        summary="Report complete.",
        evidence=[{"kind": "file", "path": "report.md"}],
    )

    with pytest.raises(ValueError, match="already has a completed report"):
        store.complete_worker_task_report(
            user_id=user["user_id"],
            task_id=task["task_id"],
            status="completed",
            summary="Duplicate report.",
            evidence=[{"kind": "file", "path": "report-v2.md"}],
        )

    snapshot = store.get_fleet_snapshot(user_id=user["user_id"], desktop_id=desktop_login["desktop"]["desktop_id"])
    assert [report["report_id"] for report in snapshot["reports"]] == [first_report["report_id"]]


def test_remote_control_store_bounds_worker_task_report_payloads(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="fleet-report-bounds@example.com", password="CorrectHorse!2026", display_name="Fleet Bounds")
    desktop_login = store.login(
        email="fleet-report-bounds@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Manager PC",
        device_platform="desktop-electron",
        device_key="manager-key",
    )
    worker = store.create_local_worker(user_id=user["user_id"], desktop_id=desktop_login["desktop"]["desktop_id"])
    task = store.assign_worker_task(user_id=user["user_id"], worker_id=worker["worker_id"], prompt="Bound this report")
    evidence = [{"kind": "file", "path": f"report-{index}.md"} for index in range(MAX_FLEET_REPORT_LIST_ITEMS + 3)]
    artifacts = [{"artifact_id": f"art_{index}"} for index in range(MAX_FLEET_REPORT_LIST_ITEMS + 2)]
    blockers = [{"kind": "note", "message": f"blocker {index}"} for index in range(MAX_FLEET_REPORT_LIST_ITEMS + 1)]

    report = store.complete_worker_task_report(
        user_id=user["user_id"],
        task_id=task["task_id"],
        status="completed",
        summary="S" * (MAX_FLEET_REPORT_SUMMARY_CHARS + 25),
        evidence=evidence,
        artifacts=artifacts,
        blockers=blockers,
        next_suggested_action="N" * (MAX_FLEET_REPORT_NEXT_ACTION_CHARS + 25),
    )

    repaired = report["raw"]["runtime_repaired_fields"]
    assert len(report["summary"]) == MAX_FLEET_REPORT_SUMMARY_CHARS
    assert len(report["next_suggested_action"]) == MAX_FLEET_REPORT_NEXT_ACTION_CHARS
    assert len(report["evidence"]) == MAX_FLEET_REPORT_LIST_ITEMS
    assert len(report["artifacts"]) == MAX_FLEET_REPORT_LIST_ITEMS
    assert len(report["blockers"]) == MAX_FLEET_REPORT_LIST_ITEMS
    assert repaired["summary_truncated"] is True
    assert repaired["next_suggested_action_truncated"] is True
    assert repaired["evidence_truncated"] is True
    assert repaired["artifacts_truncated"] is True
    assert repaired["blockers_truncated"] is True
    assert repaired["original_evidence_count"] == len(evidence)
    assert repaired["original_artifact_count"] == len(artifacts)
    assert repaired["original_blocker_count"] == len(blockers)


def test_remote_control_store_fleet_active_identity_group_queue_and_search(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="fleet-state@example.com", password="CorrectHorse!2026", display_name="Fleet State")
    desktop_login = store.login(
        email="fleet-state@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Manager PC",
        device_platform="desktop-electron",
        device_key="manager-state-key",
    )
    desktop_id = desktop_login["desktop"]["desktop_id"]
    first_worker = store.create_local_worker(user_id=user["user_id"], desktop_id=desktop_id, display_name="Worker Alpha")
    second_worker = store.create_local_worker(user_id=user["user_id"], desktop_id=desktop_id, display_name="Worker Beta")

    group = store.create_or_update_group(
        user_id=user["user_id"],
        display_name="Research Team",
        worker_ids=[first_worker["worker_id"], second_worker["worker_id"]],
    )
    assert sorted(group["worker_ids"]) == sorted([first_worker["worker_id"], second_worker["worker_id"]])

    active = store.set_active_fleet_identity(
        user_id=user["user_id"],
        identity_id=first_worker["instance_id"],
        selected_chat_id="worker-chat-1",
        source="test",
    )
    assert active["active_identity_id"] == first_worker["instance_id"]
    assert active["selected_chat_by_identity"][first_worker["instance_id"]] == "worker-chat-1"

    first_task = store.assign_worker_task(
        user_id=user["user_id"],
        worker_id=first_worker["worker_id"],
        prompt="Task one",
        target_session_id="worker-chat-1",
    )
    second_task = store.assign_worker_task(user_id=user["user_id"], worker_id=first_worker["worker_id"], prompt="Task two")
    reordered = store.reorder_worker_tasks(
        user_id=user["user_id"],
        worker_id=first_worker["worker_id"],
        task_ids=[second_task["task_id"], first_task["task_id"]],
    )
    assert [task["task_id"] for task in reordered[:2]] == [second_task["task_id"], first_task["task_id"]]

    running = store.update_worker_task_status(user_id=user["user_id"], task_id=second_task["task_id"], status="running")
    redirected = store.redirect_worker_task(
        user_id=user["user_id"],
        task_id=running["task_id"],
        direction="Use the newer source instead.",
    )
    assert redirected["metadata"]["latest_redirect"] == "Use the newer source instead."

    blocked_report = store.complete_worker_task_report(
        user_id=user["user_id"],
        task_id=running["task_id"],
        status="blocked",
        summary="Need manager input.",
        blockers=["Missing account access"],
    )
    assert blocked_report["status"] == "blocked"
    blocked_worker = store.get_worker(user_id=user["user_id"], worker_id=first_worker["worker_id"])
    assert blocked_worker["status"] == "blocked"
    assert blocked_worker["active_task_id"] == running["task_id"]

    matches = store.search_fleet_reports(user_id=user["user_id"], query="manager input", worker="Worker Alpha")
    assert matches["count"] == 1
    assert matches["reports"][0]["task_id"] == running["task_id"]


def test_remote_control_store_fleet_remote_worker_enrollment_is_single_use(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="enroll@example.com", password="CorrectHorse!2026", display_name="Enroll")
    manager_login = store.login(
        email="enroll@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Manager",
        device_platform="desktop",
        device_key="manager",
    )

    enrollment = store.create_worker_enrollment(
        user_id=user["user_id"],
        desktop_id=manager_login["desktop"]["desktop_id"],
        display_name="Remote Worker",
    )
    result = store.complete_worker_enrollment(
        enrollment_token=enrollment["enrollment_token"],
        device_name="Worker VPS",
        device_platform="linux",
        device_key="worker-vps",
    )

    assert result["session_token"]
    assert result["worker"]["kind"] == "remote"
    assert result["worker"]["display_name"] == "Remote Worker"
    assert result["desktop"]["desktop_id"] != manager_login["desktop"]["desktop_id"]

    with pytest.raises(ValueError):
        store.complete_worker_enrollment(
            enrollment_token=enrollment["enrollment_token"],
            device_name="Worker Again",
            device_platform="linux",
            device_key="worker-vps-2",
        )


def test_remote_control_store_fleet_enrollment_requires_worker_device_key(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="enroll-key@example.com", password="CorrectHorse!2026", display_name="Enroll Key")
    manager_login = store.login(
        email="enroll-key@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Manager",
        device_platform="desktop",
        device_key="manager-key",
    )
    enrollment = store.create_worker_enrollment(
        user_id=user["user_id"],
        desktop_id=manager_login["desktop"]["desktop_id"],
        display_name="Remote Worker",
    )

    with pytest.raises(ValueError, match="stable device_key"):
        store.complete_worker_enrollment(
            enrollment_token=enrollment["enrollment_token"],
            device_name="Worker VPS",
            device_platform="linux",
            device_key=None,
        )


def test_remote_control_store_fleet_enrollment_ttl_is_bounded(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="enroll-ttl@example.com", password="CorrectHorse!2026", display_name="Enroll TTL")
    manager_login = store.login(
        email="enroll-ttl@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Manager",
        device_platform="desktop",
        device_key="manager-ttl",
    )

    short = store.create_worker_enrollment(
        user_id=user["user_id"],
        desktop_id=manager_login["desktop"]["desktop_id"],
        ttl_seconds=1,
    )
    long = store.create_worker_enrollment(
        user_id=user["user_id"],
        desktop_id=manager_login["desktop"]["desktop_id"],
        ttl_seconds=999999,
    )

    assert short["expires_in_seconds"] == MIN_FLEET_ENROLLMENT_TTL_SECONDS
    assert long["expires_in_seconds"] == MAX_FLEET_ENROLLMENT_TTL_SECONDS


def test_remote_control_store_fleet_enrollment_rejects_manager_device_key(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="enroll-manager-key@example.com", password="CorrectHorse!2026", display_name="Enroll Manager Key")
    manager_login = store.login(
        email="enroll-manager-key@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Manager",
        device_platform="desktop",
        device_key="same-machine-key",
    )
    enrollment = store.create_worker_enrollment(
        user_id=user["user_id"],
        desktop_id=manager_login["desktop"]["desktop_id"],
        display_name="Remote Worker",
    )

    with pytest.raises(ValueError, match="worker-specific"):
        store.complete_worker_enrollment(
            enrollment_token=enrollment["enrollment_token"],
            device_name="Worker VPS",
            device_platform="linux",
            device_key="same-machine-key",
        )


def test_remote_control_store_fleet_enrollment_rejects_expired_token(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="enroll-expired@example.com", password="CorrectHorse!2026", display_name="Enroll Expired")
    manager_login = store.login(
        email="enroll-expired@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Manager",
        device_platform="desktop",
        device_key="manager-expired",
    )
    enrollment = store.create_worker_enrollment(
        user_id=user["user_id"],
        desktop_id=manager_login["desktop"]["desktop_id"],
        display_name="Remote Worker",
    )
    store._conn.execute(
        "UPDATE fleet_enrollments SET expires_at = ? WHERE enrollment_id = ?",
        (time.time() - 1, enrollment["enrollment_id"]),
    )
    store._conn.commit()

    with pytest.raises(ValueError, match="expired"):
        store.complete_worker_enrollment(
            enrollment_token=enrollment["enrollment_token"],
            device_name="Worker VPS",
            device_platform="linux",
            device_key="worker-expired",
        )


def test_remote_control_store_fleet_workspace_binding_and_tool_grant(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="grant@example.com", password="CorrectHorse!2026", display_name="Grant")
    login = store.login(
        email="grant@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Manager",
        device_platform="desktop",
        device_key="grant-manager",
    )
    worker = store.create_local_worker(user_id=user["user_id"], desktop_id=login["desktop"]["desktop_id"])
    binding = store.upsert_workspace_binding(
        user_id=user["user_id"],
        workspace_id="workspace-client",
        machine_id=login["desktop"]["desktop_id"],
        local_path="C:/Work/Client",
        label="Client",
    )
    assert binding["workspace_id"] == "workspace-client"
    assert binding["local_path"] == "C:/Work/Client"

    grant = store.request_tool_grant(
        user_id=user["user_id"],
        target_kind="worker",
        target_id=worker["worker_id"],
        tool_pack_id="interactive_desktop",
        reason="Verify result visually",
        requested_turns=99,
        requested_by="manager",
    )
    assert grant["status"] == "requested"
    assert grant["requested_turns"] == 10

    decided = store.decide_tool_grant(
        user_id=user["user_id"],
        grant_id=grant["grant_id"],
        approved=True,
        approved_turns=5,
        approved_by="manager",
    )
    assert decided["status"] == "approved"
    assert decided["remaining_turns"] == 5


def test_remote_control_store_fleet_resource_locks_enforce_owner_and_expiry(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="locks@example.com", password="CorrectHorse!2026", display_name="Locks")
    login = store.login(
        email="locks@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Manager",
        device_platform="desktop",
        device_key="locks-manager",
    )
    worker = store.create_local_worker(user_id=user["user_id"], desktop_id=login["desktop"]["desktop_id"])

    first = store.claim_fleet_lock(
        user_id=user["user_id"],
        resource_kind="workspace",
        resource_id="workspace-alpha",
        owner_kind="worker",
        owner_id=worker["worker_id"],
        ttl_seconds=120,
        metadata={"reason": "write"},
    )
    refreshed = store.claim_fleet_lock(
        user_id=user["user_id"],
        resource_kind="workspace",
        resource_id="workspace-alpha",
        owner_kind="worker",
        owner_id=worker["worker_id"],
        ttl_seconds=240,
        metadata={"reason": "still-writing"},
    )

    assert refreshed["lock_id"] == first["lock_id"]
    assert refreshed["metadata"]["reason"] == "still-writing"
    snapshot = store.get_fleet_snapshot(user_id=user["user_id"], desktop_id=login["desktop"]["desktop_id"])
    assert snapshot["locks"][0]["lock_id"] == first["lock_id"]

    with pytest.raises(ValueError, match="already locked"):
        store.claim_fleet_lock(
            user_id=user["user_id"],
            resource_kind="workspace",
            resource_id="workspace-alpha",
            owner_kind="worker",
            owner_id="other-worker",
        )

    store._conn.execute(
        "UPDATE fleet_locks SET expires_at = ? WHERE lock_id = ?",
        (time.time() - 1, first["lock_id"]),
    )
    store._conn.commit()
    replacement = store.claim_fleet_lock(
        user_id=user["user_id"],
        resource_kind="workspace",
        resource_id="workspace-alpha",
        owner_kind="worker",
        owner_id="other-worker",
    )
    assert replacement["lock_id"] != first["lock_id"]
    assert store.release_fleet_lock(user_id=user["user_id"], lock_id=replacement["lock_id"]) is True
    snapshot = store.get_fleet_snapshot(user_id=user["user_id"], desktop_id=login["desktop"]["desktop_id"])
    assert snapshot["locks"] == []


def test_remote_control_store_records_worker_preview_request(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="preview-store@example.com", password="CorrectHorse!2026", display_name="Preview Store")
    login = store.login(
        email="preview-store@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Manager",
        device_platform="desktop",
        device_key="preview-manager",
    )
    worker = store.create_local_worker(user_id=user["user_id"], desktop_id=login["desktop"]["desktop_id"])

    result = store.record_worker_preview_request(
        user_id=user["user_id"],
        worker_id=worker["worker_id"],
        preview_id="fpv_test",
        status="local_placeholder",
        requested_by="desktop",
        command_id="cmd_preview",
        detail="Preview recorded.",
    )

    assert result["preview"]["preview_id"] == "fpv_test"
    assert result["worker"]["metadata"]["latest_preview_request"]["command_id"] == "cmd_preview"
    snapshot = store.get_fleet_snapshot(user_id=user["user_id"], desktop_id=login["desktop"]["desktop_id"])
    assert snapshot["workers"][0]["metadata"]["latest_preview_request"]["status"] == "local_placeholder"
    assert any(event["event_type"] == "worker_preview_requested" for event in snapshot["audit_events"])


def test_remote_control_store_remote_desktop_command_queue_lifecycle(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="broker@example.com", password="CorrectHorse!2026", display_name="Broker")
    login = store.login(
        email="broker@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Worker Desktop",
        device_platform="desktop",
        device_key="broker-worker",
    )
    desktop_id = login["desktop"]["desktop_id"]

    queued = store.enqueue_remote_desktop_command(
        user_id=user["user_id"],
        desktop_id=desktop_id,
        command_type="http_request",
        payload={"path": "/api/app/health"},
        wants_reply=True,
        ttl_seconds=30,
    )
    claimed = store.claim_remote_desktop_commands(
        user_id=user["user_id"],
        desktop_id=desktop_id,
        instance_id="instance-a",
    )

    assert [item["command_id"] for item in claimed] == [queued["command_id"]]
    assert claimed[0]["payload"] == {"path": "/api/app/health"}
    assert store.get_remote_desktop_command_result(command_id=queued["command_id"], user_id=user["user_id"])["status"] == "claimed"

    completed = store.complete_remote_desktop_command(
        command_id=queued["command_id"],
        user_id=user["user_id"],
        desktop_id=desktop_id,
        ok=True,
        payload={"ok": True, "result": {"status_code": 200}},
    )
    result = store.get_remote_desktop_command_result(command_id=queued["command_id"], user_id=user["user_id"])

    assert completed is True
    assert result["status"] == "completed"
    assert result["payload"] == {"ok": True, "result": {"status_code": 200}}
    assert store.claim_remote_desktop_commands(user_id=user["user_id"], desktop_id=desktop_id, instance_id="instance-b") == []


def test_remote_control_store_archives_and_restores_automation(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="archive@example.com", password="CorrectHorse!2026", display_name="Archive")

    automation = store.upsert_automation(
        user_id=user["user_id"],
        name="Daily summary",
        prompt="Summarize new reports",
        schedule="every 1 hour",
        enabled=True,
        metadata={"created_from": "test"},
    )
    assert store.delete_automation(user_id=user["user_id"], automation_id=automation["automation_id"])

    archived = store.list_archived_items(user_id=user["user_id"])
    assert len(archived) == 1
    assert archived[0]["object_kind"] == "automation"
    assert archived[0]["display_name"] == "Daily summary"

    restored = store.restore_archived_item(user_id=user["user_id"], archive_id=archived[0]["archive_id"])
    assert restored["status"] == "restored"
    assert store.get_automation(user_id=user["user_id"], automation_id=automation["automation_id"])["name"] == "Daily summary"


def test_remote_control_store_archives_and_restores_group(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="group-archive@example.com", password="CorrectHorse!2026", display_name="Group Archive")
    login = store.login(
        email="group-archive@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Desk",
        device_platform="desktop",
    )
    worker = store.create_local_worker(user_id=user["user_id"], desktop_id=login["desktop"]["desktop_id"], display_name="Worker-001")
    group = store.create_or_update_group(
        user_id=user["user_id"],
        display_name="Finance",
        worker_ids=[worker["worker_id"]],
    )

    store.delete_group(user_id=user["user_id"], group_id=group["group_id"])
    archived = [item for item in store.list_archived_items(user_id=user["user_id"]) if item["object_kind"] == "group"]
    assert archived
    assert archived[0]["display_name"] == "Finance"

    restored = store.restore_archived_item(user_id=user["user_id"], archive_id=archived[0]["archive_id"])
    assert restored["status"] == "restored"
    snapshot = store.get_fleet_snapshot(user_id=user["user_id"])
    restored_group = next(item for item in snapshot["groups"] if item["group_id"] == group["group_id"])
    assert restored_group["worker_ids"] == [worker["worker_id"]]


def test_remote_control_store_restores_archived_worker_task_history(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="worker-archive@example.com", password="CorrectHorse!2026", display_name="Worker Archive")
    login = store.login(
        email="worker-archive@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Desk",
        device_platform="desktop",
    )
    worker = store.create_local_worker(user_id=user["user_id"], desktop_id=login["desktop"]["desktop_id"], display_name="Worker-001")
    task = store.assign_worker_task(
        user_id=user["user_id"],
        worker_id=worker["worker_id"],
        prompt="Write the weekly report",
        source="manager",
    )

    store.delete_worker(user_id=user["user_id"], worker_id=worker["worker_id"], wipe_state=True)
    archived = [item for item in store.list_archived_items(user_id=user["user_id"]) if item["object_kind"] == "worker"]
    assert archived
    assert archived[0]["payload"]["tasks"][0]["task_id"] == task["task_id"]

    store.restore_archived_item(user_id=user["user_id"], archive_id=archived[0]["archive_id"])
    snapshot = store.get_fleet_snapshot(user_id=user["user_id"])
    restored_task = next(item for item in snapshot["tasks"] if item["task_id"] == task["task_id"])
    assert restored_task["status"] == "stopped"
    assert restored_task["metadata"]["archived_restore_original_status"] == "queued"


def test_remote_control_store_event_run_process_wait_and_planner_actions(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="runtime-actions@example.com", password="CorrectHorse!2026", display_name="Runtime")

    run = store.create_or_update_event_run(
        user_id=user["user_id"],
        automation_id="auto-test",
        status="failed",
        error="network failed",
    )
    retrying = store.update_event_run_status(
        user_id=user["user_id"],
        event_run_id=run["event_run_id"],
        status="retrying",
        metadata={"reason": "transient"},
    )
    assert retrying["status"] == "retrying"
    assert retrying["attempt"] == 2
    active = store.find_active_event_run(user_id=user["user_id"], automation_id="auto-test")
    assert active["event_run_id"] == run["event_run_id"]
    claimed = store.claim_due_event_runs()
    assert claimed[0]["event_run_id"] == run["event_run_id"]
    assert claimed[0]["status"] == "dispatching"
    canceled = store.cancel_event_runs_for_session(user_id=user["user_id"], session_id="sess-1")
    assert canceled == []

    wait = store.upsert_process_wait(
        user_id=user["user_id"],
        command_id="cmd-1",
        pid=12345,
        command="npm run dev",
        status="waiting_on_process",
    )
    stopped = store.update_process_wait(
        user_id=user["user_id"],
        process_wait_id=wait["process_wait_id"],
        status="stopped",
        persistent=False,
    )
    assert stopped["status"] == "stopped"
    assert stopped["completed_at"]

    queued_run = store.create_or_update_event_run(
        user_id=user["user_id"],
        automation_id="auto-session",
        status="queued",
        target_chat_id="sess-1",
    )
    waiting = store.upsert_process_wait(
        user_id=user["user_id"],
        command_id="cmd-2",
        session_id="sess-1",
        status="waiting_on_process",
    )
    assert store.cancel_event_runs_for_session(user_id=user["user_id"], session_id="sess-1")[0]["event_run_id"] == queued_run["event_run_id"]
    assert store.stop_process_waits_for_session(user_id=user["user_id"], session_id="sess-1")[0]["process_wait_id"] == waiting["process_wait_id"]

    contract = store.upsert_planner_contract(
        user_id=user["user_id"],
        session_id="sess-1",
        turn_id="1",
        status="injected",
        action="inject",
        contract={"success_criteria": ["Done"]},
    )
    satisfied = store.update_planner_contract_status(
        user_id=user["user_id"],
        contract_id=contract["contract_id"],
        status="satisfied",
    )
    assert satisfied["status"] == "satisfied"


def test_remote_control_store_persistent_loop_guard(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="loop@example.com", password="CorrectHorse!2026", display_name="Loop")

    first = store.record_loop_guard_event(user_id=user["user_id"], guard_key="global", max_events_per_hour=1)
    second = store.record_loop_guard_event(user_id=user["user_id"], guard_key="global", max_events_per_hour=1)
    assert first["allowed"] is True
    assert second["allowed"] is False
    assert second["reason"] == "max_events_per_hour"

    fail_one = store.record_loop_guard_event(user_id=user["user_id"], guard_key="failure:x", failed=True)
    fail_two = store.record_loop_guard_event(user_id=user["user_id"], guard_key="failure:x", failed=True)
    assert fail_one["allowed"] is True
    assert fail_two["allowed"] is False
    assert fail_two["reason"] == "repeated_failure_cooldown"


def test_remote_control_store_updates_shared_snapshot_and_groups_sessions(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="sync@example.com", password="CorrectHorse!2026", display_name="Sync")
    desktop_login = store.login(
        email="sync@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Desk",
        device_platform="desktop-electron",
        device_key="desk-key",
    )
    desktop_id = desktop_login["desktop"]["desktop_id"]

    state = store.update_shared_snapshot(
        user_id=user["user_id"],
        desktop_id=desktop_id,
        snapshot={
            "desktop_id": desktop_id,
            "desktop_name": "Desk",
            "current_session_id": "sess-1",
            "current_model": "gpt-5",
            "current_variant": "standard",
            "sessions": [
                {
                    "id": "sess-1",
                    "name": "Alpha",
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
                    "name": "Alpha",
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

    assert state["current_session_id"] == "sess-1"
    assert state["current_model"] == "gpt-5"
    assert state["sync_version"] >= 1
    assert state["project_groups"][0]["label"] == "ProjectA"
    assert state["desktop_connection"]["status"] == "connected"


def test_remote_control_store_stale_offline_presence_does_not_clobber_current_desktop(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="presence@example.com", password="CorrectHorse!2026", display_name="Presence")
    first_login = store.login(
        email="presence@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Desk A",
        device_platform="desktop-electron",
        device_key="desk-a-key",
    )
    second_login = store.login(
        email="presence@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Desk B",
        device_platform="desktop-electron",
        device_key="desk-b-key",
    )
    first_desktop_id = first_login["desktop"]["desktop_id"]
    second_desktop_id = second_login["desktop"]["desktop_id"]

    store.mark_desktop_connection(
        user_id=user["user_id"],
        desktop_id=second_desktop_id,
        status="connected",
        detail="desk b connected",
    )
    store.mark_desktop_connection(
        user_id=user["user_id"],
        desktop_id=first_desktop_id,
        status="connected",
        detail="desk a connected",
    )

    stale_desktop = store.mark_desktop_connection(
        user_id=user["user_id"],
        desktop_id=second_desktop_id,
        status="offline",
        detail="desk b disconnected late",
    )
    state = store.get_shared_state(user_id=user["user_id"])

    assert stale_desktop["status"] == "offline"
    assert state["current_desktop_id"] == first_desktop_id
    assert state["desktop_connection"]["desktop_id"] == first_desktop_id
    assert state["desktop_connection"]["status"] == "connected"
    assert state["desktop_connection"]["detail"] == "desk a connected"

    store.mark_desktop_connection(
        user_id=user["user_id"],
        desktop_id=first_desktop_id,
        status="offline",
        detail="desk a disconnected",
    )
    state = store.get_shared_state(user_id=user["user_id"])

    assert state["current_desktop_id"] == first_desktop_id
    assert state["desktop_connection"]["desktop_id"] == first_desktop_id
    assert state["desktop_connection"]["status"] == "offline"
    assert state["desktop_connection"]["detail"] == "desk a disconnected"


def test_remote_control_store_hashes_tokens_and_revokes_current_session(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="tokens@example.com", password="CorrectHorse!2026", display_name="Tokens")
    first_login = store.login(
        email="tokens@example.com",
        password="CorrectHorse!2026",
        actor_kind="mobile",
        device_name="Phone",
        device_platform="android",
        device_key="phone-key",
    )
    second_login = store.login(
        email="tokens@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Desk",
        device_platform="desktop",
        device_key="desk-key",
    )
    pairing = store.create_pairing(user_id=user["user_id"], desktop_id=second_login["desktop"]["desktop_id"])

    database_bytes = (tmp_path / REMOTE_CONTROL_DB_FILENAME).read_bytes()
    assert first_login["session_token"].encode("utf-8") not in database_bytes
    assert second_login["session_token"].encode("utf-8") not in database_bytes
    assert pairing["pairing_token"].encode("utf-8") not in database_bytes

    with sqlite3.connect(tmp_path / REMOTE_CONTROL_DB_FILENAME) as conn:
        session_columns = {row[1] for row in conn.execute("PRAGMA table_info(remote_sessions)")}
        pairing_columns = {row[1] for row in conn.execute("PRAGMA table_info(pairings)")}
    assert "token_value" not in session_columns
    assert "pairing_token" not in pairing_columns

    first_payload = store.resolve_session_token(first_login["session_token"])
    assert first_payload["session_token_hash"]
    assert store.is_session_token_hash_active(
        token_hash=first_payload["session_token_hash"],
        user_id=user["user_id"],
        actor_kind="mobile",
        mobile_id=first_login["mobile"]["mobile_id"],
    )
    assert not store.is_session_token_hash_active(
        token_hash=first_payload["session_token_hash"],
        user_id=user["user_id"],
        actor_kind="desktop",
        desktop_id=second_login["desktop"]["desktop_id"],
    )

    assert store.revoke_session_token(first_login["session_token"]) is True
    assert store.resolve_session_token(first_login["session_token"]) is None
    assert not store.is_session_token_hash_active(
        token_hash=first_payload["session_token_hash"],
        user_id=user["user_id"],
        actor_kind="mobile",
        mobile_id=first_login["mobile"]["mobile_id"],
    )
    assert store.resolve_session_token(second_login["session_token"]) is not None


def test_remote_control_store_otp_signup_login_and_password_strength(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)

    with pytest.raises(ValueError):
        store.begin_signup_otp(
            email="otp@example.com",
            password="weakpassword",
            display_name="OTP",
            actor_kind="mobile",
        )

    signup = store.begin_signup_otp(
        email="otp@example.com",
        password="BetterPass!2026",
        display_name="OTP",
        actor_kind="mobile",
        device_name="Phone",
        device_platform="android",
        device_key="otp-phone",
    )
    assert signup["status"] == "otp_required"
    assert signup["purpose"] == "signup_verify"
    assert signup["otp_code"].isdigit()
    assert len(signup["otp_code"]) == 6

    with pytest.raises(ValueError, match="Finish account verification"):
        store.begin_login_otp(
            email="otp@example.com",
            password="BetterPass!2026",
            actor_kind="desktop",
        )

    with pytest.raises(ValueError, match="Finish account verification"):
        store.login(
            email="otp@example.com",
            password="BetterPass!2026",
            actor_kind="desktop",
        )

    with pytest.raises(ValueError):
        store.verify_auth_otp(challenge_id=signup["challenge_id"], code="000000")

    verified = store.verify_auth_otp(challenge_id=signup["challenge_id"], code=signup["otp_code"])
    assert verified["session_token"]
    assert verified["remember_me"] is False
    assert verified["user"]["email"] == "otp@example.com"
    assert store.resolve_session_token(verified["session_token"])["user_id"] == verified["user"]["user_id"]
    assert store.get_user(verified["user"]["user_id"])["email_verified_at"]

    login = store.begin_login_otp(
        email="otp@example.com",
        password="BetterPass!2026",
        actor_kind="desktop",
        device_name="Desk",
        device_platform="desktop",
        device_key="otp-desk",
        remember_me=True,
    )
    assert login["purpose"] == "login_verify"
    logged_in = store.verify_auth_otp(challenge_id=login["challenge_id"], code=login["otp_code"])
    assert logged_in["remember_me"] is True
    assert store.resolve_session_token(logged_in["session_token"])["actor_kind"] == "desktop"


def test_remote_control_store_unverified_signup_can_be_reclaimed(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)

    first = store.begin_signup_otp(
        email="otp-reclaim@example.com",
        password="FirstBetterPass!2026",
        display_name="First Pending",
        actor_kind="mobile",
        device_name="First Phone",
        device_platform="android",
        device_key="otp-reclaim-first",
    )
    first_user_row = store._conn.execute(
        "SELECT user_id FROM users WHERE email = ?",
        ("otp-reclaim@example.com",),
    ).fetchone()
    assert first_user_row is not None
    user_id = int(first_user_row["user_id"])

    second = store.begin_signup_otp(
        email="otp-reclaim@example.com",
        password="SecondBetterPass!2026",
        display_name="Second Pending",
        actor_kind="desktop",
        device_name="Second Desk",
        device_platform="desktop",
        device_key="otp-reclaim-second",
    )

    second_user_row = store._conn.execute(
        "SELECT user_id FROM users WHERE email = ?",
        ("otp-reclaim@example.com",),
    ).fetchone()
    assert int(second_user_row["user_id"]) == user_id
    with pytest.raises(ValueError, match="expired"):
        store.verify_auth_otp(challenge_id=first["challenge_id"], code=first["otp_code"])

    verified = store.verify_auth_otp(challenge_id=second["challenge_id"], code=second["otp_code"])
    assert verified["user"]["display_name"] == "Second Pending"
    assert verified["desktop"]["device_key"] == "otp-reclaim-second"
    assert store.begin_login_otp(
        email="otp-reclaim@example.com",
        password="SecondBetterPass!2026",
        actor_kind="mobile",
    )
    with pytest.raises(ValueError, match="Invalid email or password"):
        store.begin_login_otp(
            email="otp-reclaim@example.com",
            password="FirstBetterPass!2026",
            actor_kind="mobile",
        )


def test_remote_control_store_otp_exhaustion_invalidates_challenge(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    signup = store.begin_signup_otp(
        email="otp-lock@example.com",
        password="BetterPass!2026",
        display_name="OTP Lock",
        actor_kind="mobile",
        device_name="Phone",
        device_platform="android",
        device_key="otp-lock-phone",
    )
    wrong_code = "000000" if signup["otp_code"] != "000000" else "111111"

    for attempt in range(AUTH_OTP_MAX_ATTEMPTS):
        with pytest.raises(ValueError) as exc_info:
            store.verify_auth_otp(challenge_id=signup["challenge_id"], code=wrong_code)
        if attempt < AUTH_OTP_MAX_ATTEMPTS - 1:
            assert "attempt" in str(exc_info.value).lower()
        else:
            assert "too many" in str(exc_info.value).lower()

    with pytest.raises(ValueError, match="expired"):
        store.verify_auth_otp(challenge_id=signup["challenge_id"], code=signup["otp_code"])

    with pytest.raises(ValueError, match="expired"):
        store.resend_auth_otp(challenge_id=signup["challenge_id"])
    assert store._conn.execute(
        "SELECT user_id FROM users WHERE email = ?",
        ("otp-lock@example.com",),
    ).fetchone() is None


def test_remote_control_store_can_invalidate_undelivered_otp_challenge(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    signup = store.begin_signup_otp(
        email="otp-undelivered@example.com",
        password="BetterPass!2026",
        display_name="OTP Undelivered",
        actor_kind="mobile",
        device_name="Phone",
        device_platform="android",
        device_key="otp-undelivered-phone",
    )

    assert store.invalidate_auth_otp_challenge(challenge_id=signup["challenge_id"]) is True
    assert store.invalidate_auth_otp_challenge(challenge_id=signup["challenge_id"]) is False

    with pytest.raises(ValueError, match="expired"):
        store.verify_auth_otp(challenge_id=signup["challenge_id"], code=signup["otp_code"])

    with pytest.raises(ValueError, match="expired"):
        store.resend_auth_otp(challenge_id=signup["challenge_id"])


def test_remote_control_store_updates_sidebar_state(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="sidebar@example.com", password="CorrectHorse!2026", display_name="Sidebar")
    sidebar_state = {
        "version": 1,
        "projectOrder": ["C:/Work/App"],
        "projects": {"C:/Work/App": {"displayName": "App", "collapsed": False}},
        "sessionMeta": {"sess-1": {"pinned": True, "order": 1}},
        "selectedProjectPath": "C:/Work/App",
    }

    shared_state = store.update_sidebar_state(user_id=user["user_id"], sidebar_state=sidebar_state)

    assert shared_state["sidebar_state"] == sidebar_state
    assert store.get_sidebar_state(user_id=user["user_id"]) == sidebar_state


def test_remote_control_store_persists_sanitized_user_profile(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="profile@example.com", password="CorrectHorse!2026", display_name="Profile")

    default_profile = store.get_user_profile(user_id=user["user_id"])

    assert default_profile["schema_version"] == 1
    assert default_profile["preferences"]["interrupt_policy_default"] == "none"
    assert default_profile["integrations"]["telegram"]["allowed_user_ids"] == []

    updated = store.update_user_profile(
        user_id=user["user_id"],
        profile={
            "preferences": {
                "verbose_mode": True,
                "interrupt_policy_default": "after_tool",
                "planner_model": "gpt-5",
            },
            "integrations": {
                "telegram": {
                    "enabled": True,
                    "allowed_user_ids": ["12345", "+67890", "not-a-number", "12345"],
                    "bots": [
                        {
                            "id": "bot-main",
                            "label": "Main bot",
                            "bot_token": "should-never-persist",
                            "credential_ref": "telegram/main",
                        }
                    ],
                }
            },
            "metadata": {
                "startup": "complete",
                "api_key": "should-never-persist",
            },
        },
    )

    assert updated["preferences"]["verbose_mode"] is True
    assert updated["preferences"]["interrupt_policy_default"] == "after_tool"
    assert updated["integrations"]["telegram"]["allowed_user_ids"] == ["12345", "67890"]
    assert updated["integrations"]["telegram"]["bots"][0]["bot_config_id"] == "bot-main"
    assert "bot_token" not in updated["integrations"]["telegram"]["bots"][0]
    assert "api_key" not in updated["metadata"]

    reopened = RemoteControlPlaneStore(root_path=tmp_path)
    assert reopened.get_user_profile(user_id=user["user_id"]) == updated
    database_bytes = (tmp_path / REMOTE_CONTROL_DB_FILENAME).read_bytes()
    assert b"should-never-persist" not in database_bytes


def test_remote_control_store_deletes_user_account_data_without_deleting_account(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPLOAI_REMOTE_SECRETS_KEY", base64.urlsafe_b64encode(b"3" * 32).decode("ascii"))
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="reset@example.com", password="CorrectHorse!2026", display_name="Reset")
    desktop_login = store.login(
        email="reset@example.com",
        password="CorrectHorse!2026",
        actor_kind="desktop",
        device_name="Desk",
        device_platform="desktop-electron",
        device_key="desk-reset",
    )
    mobile_login = store.login(
        email="reset@example.com",
        password="CorrectHorse!2026",
        actor_kind="mobile",
        device_name="Phone",
        device_platform="android",
        device_key="phone-reset",
    )
    pairing = store.create_pairing(user_id=user["user_id"], desktop_id=desktop_login["desktop"]["desktop_id"])
    store.complete_pairing(
        user_id=user["user_id"],
        pairing_token=pairing["pairing_token"],
        mobile_id=mobile_login["mobile"]["mobile_id"],
    )
    store.create_pairing(user_id=user["user_id"], desktop_id=desktop_login["desktop"]["desktop_id"])
    store.update_user_profile(
        user_id=user["user_id"],
        profile={"preferences": {"verbose_mode": True}, "integrations": {"telegram": {"allowed_user_ids": ["123"]}}},
    )
    store.upsert_user_secrets(
        user_id=user["user_id"],
        namespace="setup",
        secrets_payload={"OPENAI_API_KEY": "sk-reset-secret"},
    )
    store.update_shared_snapshot(
        user_id=user["user_id"],
        desktop_id=desktop_login["desktop"]["desktop_id"],
        snapshot={"current_session_id": "sess-1", "sessions": [{"id": "sess-1"}]},
    )
    mobile_auth = store.resolve_session_token(mobile_login["session_token"])

    result = store.delete_user_account_data(
        user_id=user["user_id"],
        preserve_session_token_hash=mobile_auth["session_token_hash"],
    )

    assert result["deleted_secrets"] == 1
    assert result["revoked_sessions"] == 1
    assert result["revoked_pairings"] == 1
    assert result["unpaired_mobiles"] == 1
    assert result["reset_desktops"] == 1
    assert result["profile_reset"] is True
    assert store.get_user(user["user_id"])["email"] == "reset@example.com"
    assert store.get_user_profile(user_id=user["user_id"])["preferences"]["verbose_mode"] is False
    assert store.list_user_secrets(user_id=user["user_id"]) == []
    assert store.resolve_session_token(desktop_login["session_token"]) is None
    refreshed_mobile_auth = store.resolve_session_token(mobile_login["session_token"])
    assert refreshed_mobile_auth is not None
    assert refreshed_mobile_auth["paired_desktop_id"] is None
    desktop = store.list_desktops(user_id=user["user_id"])[0]
    assert desktop["status"] == "offline"
    assert desktop["paired_mobile_ids"] == []
    shared_state = store.get_shared_state(user_id=user["user_id"])
    assert shared_state["sessions"] == []
    assert shared_state["current_session_id"] is None


def test_remote_control_store_google_oauth_links_existing_user_and_consumes_once(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="google@example.com", password="CorrectHorse!2026", display_name="Google User")
    login_request = store.create_oauth_login_request(
        provider="google",
        actor_kind="mobile",
        device_name="Pixel",
        device_platform="android",
        device_key="phone-google",
    )

    completed = store.complete_oauth_login_request(
        provider="google",
        state=login_request["state"],
        subject="google-sub-1",
        email="google@example.com",
        email_verified=True,
        display_name="Google Person",
        avatar_url="https://example.invalid/avatar.png",
    )
    consumed = store.consume_oauth_login_request(
        request_id=login_request["request_id"],
        poll_token=login_request["poll_token"],
    )
    consumed_again = store.consume_oauth_login_request(
        request_id=login_request["request_id"],
        poll_token=login_request["poll_token"],
    )

    assert completed["user_id"] == user["user_id"]
    assert consumed["status"] == "complete"
    assert consumed["user"]["user_id"] == user["user_id"]
    assert consumed["mobile"]["device_name"] == "Pixel"
    assert store.resolve_session_token(consumed["session_token"])["user_id"] == user["user_id"]
    assert consumed_again["status"] == "expired"

    database_bytes = (tmp_path / REMOTE_CONTROL_DB_FILENAME).read_bytes()
    assert login_request["poll_token"].encode("utf-8") not in database_bytes
    assert login_request["state"].encode("utf-8") not in database_bytes


def test_remote_control_store_google_oauth_creates_user(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    login_request = store.create_oauth_login_request(
        provider="google",
        actor_kind="desktop",
        device_name="Desk",
        device_platform="desktop-electron",
        device_key="desk-google",
    )

    completed = store.complete_oauth_login_request(
        provider="google",
        state=login_request["state"],
        subject="google-sub-2",
        email="new-google@example.com",
        email_verified=True,
        display_name="New Google",
    )
    consumed = store.consume_oauth_login_request(
        request_id=login_request["request_id"],
        poll_token=login_request["poll_token"],
    )

    assert completed["user_id"] > 0
    assert consumed["status"] == "complete"
    assert consumed["user"]["email"] == "new-google@example.com"
    assert consumed["desktop"]["display_name"] == "Desk"


def test_remote_control_store_google_account_prompts_google_for_email_auth(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    login_request = store.create_oauth_login_request(
        provider="google",
        actor_kind="desktop",
        device_name="Desk",
        device_platform="desktop-electron",
        device_key="desk-google-auth-hint",
    )

    store.complete_oauth_login_request(
        provider="google",
        state=login_request["state"],
        subject="google-sub-auth-hint",
        email="google-auth-hint@example.com",
        email_verified=True,
        display_name="Google Auth Hint",
    )

    with pytest.raises(ValueError, match="registered with Google"):
        store.begin_login_otp(
            email="google-auth-hint@example.com",
            password="CorrectHorse!2026",
            actor_kind="desktop",
        )

    with pytest.raises(ValueError, match="registered with Google"):
        store.login(
            email="google-auth-hint@example.com",
            password="CorrectHorse!2026",
            actor_kind="desktop",
        )

    with pytest.raises(ValueError, match="already exists"):
        store.begin_signup_otp(
            email="google-auth-hint@example.com",
            password="DifferentHorse!2026",
            display_name="Duplicate Google",
            actor_kind="desktop",
        )

    consumed = store.consume_oauth_login_request(
        request_id=login_request["request_id"],
        poll_token=login_request["poll_token"],
    )
    assert consumed["status"] == "complete"
    assert consumed["user"]["email"] == "google-auth-hint@example.com"


def test_remote_control_store_encrypts_user_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPLOAI_REMOTE_SECRETS_KEY", base64.urlsafe_b64encode(b"1" * 32).decode("ascii"))
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="vault@example.com", password="CorrectHorse!2026", display_name="Vault")

    items = store.upsert_user_secrets(
        user_id=user["user_id"],
        namespace="setup",
        secrets_payload={
            "OPENAI_API_KEY": "sk-test-secret-value",
            "TELEGRAM_BOT_TOKEN": "123456:telegram-secret",
        },
        metadata={"OPENAI_API_KEY": {"label": "OpenAI API key", "api_key": "must-strip"}},
    )
    listed = store.list_user_secrets(user_id=user["user_id"], namespace="setup")
    revealed = store.reveal_user_secrets(
        user_id=user["user_id"],
        namespace="setup",
        names=["OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN"],
    )

    assert len(items) == 2
    assert {item["name"] for item in listed} == {"OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN"}
    assert listed[0]["redacted_value"]
    assert "api_key" not in next(item for item in listed if item["name"] == "OPENAI_API_KEY")["metadata"]
    assert revealed["OPENAI_API_KEY"] == "sk-test-secret-value"
    assert revealed["TELEGRAM_BOT_TOKEN"] == "123456:telegram-secret"

    database_bytes = (tmp_path / REMOTE_CONTROL_DB_FILENAME).read_bytes()
    assert b"sk-test-secret-value" not in database_bytes
    assert b"telegram-secret" not in database_bytes

    reopened = RemoteControlPlaneStore(root_path=tmp_path)
    assert reopened.reveal_user_secrets(user_id=user["user_id"], namespace="setup", names=["OPENAI_API_KEY"]) == {
        "OPENAI_API_KEY": "sk-test-secret-value"
    }


def test_remote_control_store_encrypts_telegram_bot_and_login_credential_namespaces(tmp_path, monkeypatch):
    monkeypatch.setenv("EMPLOAI_REMOTE_SECRETS_KEY", base64.urlsafe_b64encode(b"2" * 32).decode("ascii"))
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="bot-vault@example.com", password="CorrectHorse!2026", display_name="Vault")

    telegram_items = store.upsert_user_secrets(
        user_id=user["user_id"],
        namespace="telegram_bots",
        secrets_payload={"bot_abc123": "987654:secondary-telegram-secret"},
        metadata={"bot_abc123": {"label": "Secondary Bot", "kind": "telegram_bot_token"}},
    )
    credential_items = store.upsert_user_secrets(
        user_id=user["user_id"],
        namespace="login_credentials",
        secrets_payload={
            "GMAIL_EMAIL": "person@example.com",
            "GMAIL_PASSWORD": "gmail-password-secret",
        },
        metadata={"GMAIL_PASSWORD": {"label": "Gmail password", "kind": "login_password"}},
    )

    assert telegram_items[0]["namespace"] == "telegram_bots"
    assert credential_items[0]["namespace"] == "login_credentials"
    assert store.reveal_user_secrets(user_id=user["user_id"], namespace="telegram_bots") == {
        "bot_abc123": "987654:secondary-telegram-secret"
    }
    assert store.reveal_user_secrets(
        user_id=user["user_id"],
        namespace="login_credentials",
        names=["GMAIL_EMAIL", "GMAIL_PASSWORD"],
    ) == {
        "GMAIL_EMAIL": "person@example.com",
        "GMAIL_PASSWORD": "gmail-password-secret",
    }

    database_bytes = (tmp_path / REMOTE_CONTROL_DB_FILENAME).read_bytes()
    assert b"secondary-telegram-secret" not in database_bytes
    assert b"gmail-password-secret" not in database_bytes


def test_remote_control_store_rejects_oversized_secret_payloads(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="limit@example.com", password="CorrectHorse!2026", display_name="Limit")

    with pytest.raises(ValueError, match="Too many secrets"):
        store.upsert_user_secrets(
            user_id=user["user_id"],
            namespace="telegram_bots",
            secrets_payload={f"bot_{index:03d}": "123456:token" for index in range(101)},
        )

    with pytest.raises(ValueError, match="Secret value is too large"):
        store.upsert_user_secrets(
            user_id=user["user_id"],
            namespace="telegram_bots",
            secrets_payload={"bot_large": "x" * 20_001},
        )

    with pytest.raises(ValueError, match="Too many secrets requested"):
        store.reveal_user_secrets(
            user_id=user["user_id"],
            namespace="telegram_bots",
            names=[f"bot_{index:03d}" for index in range(101)],
        )


def test_remote_control_store_confirmation_lifecycle_and_execution_audit(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="confirm@example.com", password="CorrectHorse!2026", display_name="Confirm")

    confirmation = store.create_confirmation(
        user_id=user["user_id"],
        action_kind="recovery_permanent_delete",
        title="Delete forever",
        message="Delete archived item forever.",
        risk_tier="danger",
        origin_surface="desktop",
        origin_identity_id="manager",
        origin_chat_id="chat_1",
        payload={"archive_id": "arc_1"},
        ttl_seconds=300,
    )

    assert confirmation["status"] == "pending"
    assert confirmation["payload"]["archive_id"] == "arc_1"
    assert store.list_pending_confirmations(user_id=user["user_id"])[0]["confirmation_id"] == confirmation["confirmation_id"]

    approved = store.decide_confirmation(
        user_id=user["user_id"],
        confirmation_id=confirmation["confirmation_id"],
        approved=True,
        decided_by_surface="telegram",
        decided_by_actor="123",
    )
    assert approved["status"] == "approved"
    assert approved["decided_by_surface"] == "telegram"

    executed = store.record_confirmation_executed(
        user_id=user["user_id"],
        confirmation_id=confirmation["confirmation_id"],
        executed_by_surface="desktop",
        metadata={"archive_id": "arc_1"},
    )
    assert executed["status"] == "executed"
    assert store.list_pending_confirmations(user_id=user["user_id"]) == []

    audit_types = {
        item["event_type"]
        for item in store.get_fleet_snapshot(user_id=user["user_id"]).get("audit_events", [])
    }
    assert "confirmation_created" in audit_types
    assert "confirmation_approved" in audit_types
    assert "confirmation_executed" in audit_types


def test_remote_control_store_cloud_session_snapshot_archive(tmp_path):
    store = RemoteControlPlaneStore(root_path=tmp_path)
    user = store.register_user(email="snapshot@example.com", password="CorrectHorse!2026", display_name="Snapshot")

    snapshot = store.upsert_cloud_session_snapshot(
        user_id=user["user_id"],
        session_id="chat_1",
        payload={"id": "chat_1", "messages": [{"role": "user", "content": "hello"}]},
        metadata={"reason": "chat_turn"},
    )
    assert snapshot["status"] == "active"
    assert snapshot["payload"]["messages"][0]["content"] == "hello"

    archived = store.archive_cloud_session_snapshot(
        user_id=user["user_id"],
        session_id="chat_1",
        metadata={"archive_reason": "chat_delete"},
    )
    assert archived["status"] == "archived"
    assert archived["metadata"]["archive_reason"] == "chat_delete"
    assert store.list_cloud_session_snapshots(user_id=user["user_id"], status="archived")[0]["session_id"] == "chat_1"
