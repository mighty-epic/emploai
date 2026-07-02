from pathlib import Path
from types import SimpleNamespace

from cli.session_manager import SessionManager
from app_backend import session_bridge


def test_session_index_rebuild_preserves_security_permission_mode(tmp_path: Path):
    manager = SessionManager(base_path=tmp_path / "state")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    created = manager.create_session(
        name="Full access chat",
        workspace=workspace,
        security_permission_mode="full_permissions",
    )
    (manager.sessions_dir / "index.json").unlink()

    summaries = manager.list_sessions()

    assert summaries[0].id == created.id
    assert summaries[0].security_permission_mode == "full_permissions"


def test_app_session_bridge_new_chat_inherits_permission_mode_from_same_workspace(monkeypatch, tmp_path: Path):
    state_root = tmp_path / "state"
    target_workspace = tmp_path / "project"
    other_workspace = tmp_path / "other"
    target_workspace.mkdir()
    other_workspace.mkdir()

    manager = SessionManager(base_path=state_root)
    manager.create_session(
        name="Existing project chat",
        workspace=target_workspace,
        security_permission_mode="full_permissions",
    )
    manager.create_session(
        name="Other current chat",
        workspace=other_workspace,
        security_permission_mode="standard",
    )

    dummy_orchestrator = SimpleNamespace(
        _running={},
        _workers={},
        _default_bot_config_id=lambda: None,
    )
    monkeypatch.setattr(session_bridge, "user_state_root", lambda user_id: state_root)
    monkeypatch.setattr(session_bridge, "get_user_orchestrator", lambda **kwargs: dummy_orchestrator)
    monkeypatch.setattr(session_bridge, "user_sessions", {})

    bridge = session_bridge.AppSessionBridge(user_id=7, workspace=other_workspace)
    created = bridge.create_session("New project chat", workspace=target_workspace)

    assert created.workspace == str(target_workspace.resolve())
    assert created.security_permission_mode == "full_permissions"
