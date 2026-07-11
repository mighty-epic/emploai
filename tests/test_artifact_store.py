from __future__ import annotations

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from app_backend import session_bridge
from shared import channel_runtime
from shared.artifact_store import ChatArtifactStore


class _DummyOrchestrator:
    def _session_summary_live_fields(self, _session) -> dict:
        return {}

    def runtime_status_view(self) -> dict:
        return {}


def test_artifact_store_builds_index_and_retrieval(monkeypatch, tmp_path: Path) -> None:
    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    monkeypatch.setenv("EMPLOAI_HOME", str(runtime_home))

    store = ChatArtifactStore(user_id=77, session_id="sess-a")
    first = store.create_text_artifact(
        artifact_kind="command_output",
        title="Command output: py hello.py",
        text="$ py hello.py\n\n[stdout]\nhello world",
        source_kind="agent",
    )
    second = store.create_text_artifact(
        artifact_kind="file_snapshot",
        title="File snapshot: notes.txt",
        text="Brussels is the capital of Belgium.\nexample.com is reserved.",
        source_kind="agent",
    )
    other_store = ChatArtifactStore(user_id=77, session_id="sess-b")
    other_store.create_text_artifact(
        artifact_kind="file_snapshot",
        title="File snapshot: other.txt",
        text="Should never appear in sess-a retrieval.",
        source_kind="agent",
    )

    messages = store.build_prompt_messages(user_message="what did the command print and what is the capital of Belgium?")

    assert len(messages) == 2
    combined = "\n".join(item["content"] for item in messages)
    assert first.artifact_id in combined
    assert second.artifact_id in combined
    assert "Brussels is the capital of Belgium" in combined
    assert "Should never appear" not in combined


def test_generated_artifacts_are_cloud_mirrored_with_quota_metadata(monkeypatch, tmp_path: Path) -> None:
    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    monkeypatch.setenv("EMPLOAI_HOME", str(runtime_home))
    monkeypatch.setenv("EMPLOAI_CLOUD_BACKEND_ENABLED", "1")

    store = ChatArtifactStore(user_id=77, session_id="sess-cloud")
    record = store.create_text_artifact(
        artifact_kind="command_output",
        title="Command output",
        text="important generated output",
        source_kind="agent",
    )

    assert record.metadata["cloud_sync_status"] == "synced"
    assert record.metadata["cloud_object_key"]
    assert record.metadata["cloud_storage_backend"] == "vps_object_store"

    upload = store.create_text_artifact(
        artifact_kind="upload",
        title="Upload: private.txt",
        text="user supplied file",
        source_kind="upload",
    )
    assert "cloud_sync_status" not in upload.metadata


def test_concurrent_artifact_creates_do_not_lose_index_entries(monkeypatch, tmp_path: Path) -> None:
    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    monkeypatch.setenv("EMPLOAI_HOME", str(runtime_home))

    store = ChatArtifactStore(user_id=77, session_id="sess-concurrent")

    def create(index: int) -> str:
        return store.create_text_artifact(
            artifact_kind="note",
            title=f"Note {index}",
            text=f"payload {index}",
            source_kind="agent",
        ).artifact_id

    with ThreadPoolExecutor(max_workers=8) as executor:
        artifact_ids = set(executor.map(create, range(24)))

    assert len(artifact_ids) == 24
    assert {record.artifact_id for record in store.list_records()} == artifact_ids


def test_screen_artifact_uses_sidecar_vision_summary(monkeypatch, tmp_path: Path) -> None:
    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    monkeypatch.setenv("EMPLOAI_HOME", str(runtime_home))

    store = ChatArtifactStore(user_id=77, session_id="sess-vision")
    artifact_ids = channel_runtime._capture_tool_artifact_ids(
        SimpleNamespace(workspace=str(tmp_path)),
        store=store,
        tool_name="describe_screen",
        tool_args={"question": "Did the requested file open?"},
        tool_result={
            "image_base64": "ZmFrZQ==",
            "description": "Screenshot captured successfully.",
            "question": "Did the requested file open?",
            "vision_question": "Did the requested file open?",
            "vision_summary": "Notepad is visible with the exact requested file content.",
        },
        task_id=1,
    )

    assert len(artifact_ids) == 1
    record = store.get_record(artifact_ids[0])
    assert record is not None
    assert "Vision summary: Notepad is visible" in record.summary_text
    assert "Question: Did the requested file open?" in record.summary_text
    assert record.metadata["tool_result"]["image_base64"].startswith("[omitted image data")


def test_touched_file_snapshot_preserves_workspace_id(monkeypatch, tmp_path: Path) -> None:
    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    monkeypatch.setenv("EMPLOAI_HOME", str(runtime_home))

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    touched = workspace / "notes.txt"
    touched.write_text("snapshot proof", encoding="utf-8")

    store = ChatArtifactStore(user_id=77, session_id="sess-snapshot")
    artifact_ids = channel_runtime._snapshot_touched_file_artifact_ids(
        SimpleNamespace(workspace=str(workspace), workspace_id="workspace-123"),
        store=store,
        touched_file_paths={touched},
        task_id=9,
    )

    assert len(artifact_ids) == 1
    record = store.get_record(artifact_ids[0])
    assert record is not None
    assert record.metadata["workspace_id"] == "workspace-123"
    assert record.metadata["path"] == "notes.txt"


def test_session_bridge_upload_creates_chat_artifact(monkeypatch, tmp_path: Path) -> None:
    runtime_home = tmp_path / "runtime"
    runtime_home.mkdir()
    monkeypatch.setenv("EMPLOAI_HOME", str(runtime_home))
    monkeypatch.setattr(session_bridge, "get_user_orchestrator", lambda **_kwargs: _DummyOrchestrator())

    bridge = session_bridge.AppSessionBridge(user_id=12, workspace=tmp_path)
    runtime = SimpleNamespace(
        pending_files=[],
        save_session=lambda: None,
        session_manager=SimpleNamespace(get_current_session_id=lambda: "sess-upload"),
        session=SimpleNamespace(id="sess-upload"),
        workspace=tmp_path,
    )

    bridge.attach_pending_file(
        runtime=runtime,
        filename="notes.txt",
        content_type="text/plain",
        data=b"artifact proof text",
    )

    artifacts = bridge.list_session_artifacts("sess-upload")
    assert len(artifacts) == 1
    assert artifacts[0]["artifact_kind"] == "upload"
    assert artifacts[0]["title"] == "Upload: notes.txt"

    detail = bridge.get_session_artifact("sess-upload", artifacts[0]["artifact_id"])
    assert detail["inline_text"] == "artifact proof text"
