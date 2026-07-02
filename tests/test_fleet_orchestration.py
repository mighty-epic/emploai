from __future__ import annotations

from app_backend.fleet_orchestration import (
    fleet_selected_chat_for_worker,
    fleet_task_target_session_id,
    task_requires_workspace_write,
    workspace_binding_blocker_for_task,
    workspace_id_for_task,
)


def test_fleet_selected_chat_for_worker_uses_instance_then_identity_mapping():
    snapshot = {
        "selected_chat_by_identity": {
            "instance-a": "chat-instance",
            "identity-a": "chat-identity",
        },
        "identities": [{"identity_id": "identity-a", "worker_id": "worker-a"}],
    }

    assert fleet_selected_chat_for_worker(snapshot, {"worker_id": "worker-a", "instance_id": "instance-a"}) == "chat-instance"
    assert fleet_selected_chat_for_worker(snapshot, {"worker_id": "worker-a"}) == "chat-identity"
    assert fleet_selected_chat_for_worker({"selected_chat_by_identity": []}, {"worker_id": "worker-a"}) is None


def test_fleet_task_target_session_id_prefers_explicit_and_respects_manual_mode():
    snapshot = {
        "selected_chat_by_identity": {"identity-a": "chat-identity"},
        "identities": [{"identity_id": "identity-a", "worker_id": "worker-a"}],
    }
    worker = {"worker_id": "worker-a"}

    assert fleet_task_target_session_id(
        snapshot=snapshot,
        worker=worker,
        target_session_id="chat-explicit",
        metadata={"target_session_id": "chat-metadata"},
    ) == "chat-explicit"
    assert fleet_task_target_session_id(
        snapshot=snapshot,
        worker=worker,
        metadata={"target_session_id": "chat-metadata"},
    ) == "chat-metadata"
    assert fleet_task_target_session_id(snapshot=snapshot, worker=worker, target_mode="manual") is None
    assert fleet_task_target_session_id(snapshot=snapshot, worker=worker, target_mode="auto") == "chat-identity"


def test_task_requires_workspace_write_detects_explicit_metadata_and_prompt():
    assert task_requires_workspace_write("Summarize this thread", {}, False) is False
    assert task_requires_workspace_write("Summarize this thread", {}, True) is True
    assert task_requires_workspace_write("Summarize this thread", {"file_write_required": True}, False) is True
    assert task_requires_workspace_write("Create a file in the project workspace", {}, False) is True


def test_workspace_id_for_task_uses_request_metadata_then_session_resolver():
    assert workspace_id_for_task(workspace_id=" workspace-a ") == "workspace-a"
    assert workspace_id_for_task(metadata={"workspace_id": "workspace-meta"}) == "workspace-meta"
    assert workspace_id_for_task(
        target_session_id="chat-a",
        resolve_workspace_id_for_session=lambda session_id: f"workspace-for-{session_id}",
    ) == "workspace-for-chat-a"
    assert workspace_id_for_task(target_session_id="chat-a") is None


def test_workspace_binding_blocker_returns_missing_workspace_for_file_work():
    blocker = workspace_binding_blocker_for_task(
        worker={"worker_id": "worker-a"},
        prompt="Create a file in the project workspace",
        workspace_bindings=[],
    )

    assert blocker == {
        "reason": "workspace_id_missing",
        "message": "This task appears to need workspace file-writing, but no workspace identity was attached.",
    }


def test_workspace_binding_blocker_requires_active_binding_for_target_machine():
    worker = {"worker_id": "worker-a", "machine_desktop_id": "desktop-a"}
    bindings = [
        {"workspace_id": "workspace-a", "machine_id": "desktop-a", "status": "inactive"},
        {"workspace_id": "workspace-a", "machine_id": "desktop-b", "status": "active"},
    ]

    blocker = workspace_binding_blocker_for_task(
        worker=worker,
        prompt="Create a file in the project workspace",
        workspace_id="workspace-a",
        workspace_bindings=bindings,
    )

    assert blocker is not None
    assert blocker["reason"] == "workspace_binding_missing_or_inactive"
    assert blocker["workspace_id"] == "workspace-a"
    assert blocker["machine_id"] == "desktop-a"
    assert blocker["bindings"] == [bindings[0]]

    assert workspace_binding_blocker_for_task(
        worker=worker,
        prompt="Create a file in the project workspace",
        workspace_id="workspace-a",
        workspace_bindings=[{**bindings[0], "status": "active"}],
    ) is None


def test_workspace_binding_blocker_ignores_tasks_without_write_requirement():
    assert workspace_binding_blocker_for_task(
        worker={"worker_id": "worker-a"},
        prompt="Summarize the latest report",
        workspace_bindings=[],
    ) is None
