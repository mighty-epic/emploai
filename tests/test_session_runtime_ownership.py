from __future__ import annotations

from types import SimpleNamespace

import pytest

from app_backend import session_bridge
from cli.models.session import Session


def _session(session_id: str, workspace) -> Session:
    return Session(
        id=session_id,
        name=session_id,
        created_at="2026-07-10T00:00:00",
        updated_at="2026-07-10T00:00:00",
        workspace=str(workspace),
        model="gpt-5.4",
        variant="standard",
        agent_mode="auto",
    )


def test_active_runtime_blocks_session_activation_without_moving_current_pointer(monkeypatch, tmp_path):
    current = _session("current", tmp_path)
    target = _session("target", tmp_path)

    class Manager:
        def __init__(self, _base_path):
            self.set_calls: list[str] = []

        def load_session(self, session_id: str, *, set_current: bool = True):
            assert session_id == target.id
            assert set_current is False
            return target

        def set_current_session(self, session_id: str):
            self.set_calls.append(session_id)

    manager = Manager(tmp_path)
    save_calls: list[str] = []
    runtime = SimpleNamespace(
        is_processing=True,
        session=current,
        session_manager=SimpleNamespace(get_current_session_id=lambda: current.id),
        save_session=lambda: save_calls.append("save"),
    )
    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)
    monkeypatch.setattr(session_bridge, "user_sessions", {91: runtime})

    bridge = session_bridge.AppSessionBridge(user_id=91, workspace=tmp_path)
    with pytest.raises(RuntimeError, match="Finish or stop"):
        bridge.activate_session(target.id)

    assert manager.set_calls == []
    assert save_calls == []


def test_active_runtime_blocks_activating_a_new_session(monkeypatch, tmp_path):
    current = _session("current", tmp_path)

    class Manager:
        def __init__(self, _base_path):
            self.create_calls = 0

        def create_session(self, **_kwargs):
            self.create_calls += 1
            raise AssertionError("create_session must not run while another session owns the runtime")

    manager = Manager(tmp_path)
    runtime = SimpleNamespace(
        is_processing=True,
        session=current,
        session_manager=SimpleNamespace(get_current_session_id=lambda: current.id),
        save_session=lambda: (_ for _ in ()).throw(AssertionError("active runtime must not be persisted as a switch")),
    )
    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)
    monkeypatch.setattr(session_bridge, "user_sessions", {92: runtime})

    bridge = session_bridge.AppSessionBridge(user_id=92, workspace=tmp_path)
    with pytest.raises(RuntimeError, match="Finish or stop"):
        bridge.create_session("New", workspace=tmp_path, activate=True)

    assert manager.create_calls == 0
