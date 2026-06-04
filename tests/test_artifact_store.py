from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from mobile_app.backend import session_bridge
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
