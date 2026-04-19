from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from cli.models.session import Session
from mobile_app.backend import app_server, session_bridge
from telegram_bot.telegram_session_state import TelegramSession


def test_resolve_pairing_user_id_prefers_pairing_creator(monkeypatch):
    class DummyStore:
        def get_pairing(self, pairing_id: str):
            assert pairing_id == "pair-1"
            return {"created_by": "user:77"}

    monkeypatch.setattr(app_server, "_get_auth_store", lambda: DummyStore())
    monkeypatch.setattr(app_server, "_default_user_id", lambda: 11)

    assert app_server._resolve_pairing_user_id("pair-1") == 77


def test_resolve_pairing_user_id_falls_back_to_default(monkeypatch):
    class DummyStore:
        def get_pairing(self, pairing_id: str):
            assert pairing_id == "pair-2"
            return {"created_by": "service:bootstrap"}

    monkeypatch.setattr(app_server, "_get_auth_store", lambda: DummyStore())
    monkeypatch.setattr(app_server, "_default_user_id", lambda: 11)

    assert app_server._resolve_pairing_user_id("pair-2") == 11


def test_app_session_bridge_uses_shared_telegram_runtime(monkeypatch, tmp_path: Path):
    captured = {}
    runtime = object()

    class DummySessionManager:
        def __init__(self, base_path: Path):
            self.base_path = base_path

    def fake_get_session(user_id: int, *, workspace: Path | None = None, create_new_session: bool = True):
        captured["user_id"] = user_id
        captured["workspace"] = workspace
        captured["create_new_session"] = create_new_session
        return runtime

    monkeypatch.setattr(session_bridge, "SessionManager", DummySessionManager)
    monkeypatch.setattr(session_bridge, "get_session", fake_get_session)

    bridge = session_bridge.AppSessionBridge(user_id=5, workspace=tmp_path)

    assert bridge.get_or_create_runtime_session() is runtime
    assert captured == {
        "user_id": 5,
        "workspace": tmp_path,
        "create_new_session": False,
    }


def test_app_session_bridge_create_session_does_not_switch_busy_runtime(monkeypatch, tmp_path: Path):
    created = Session(
        id="busy1234",
        name="Busy",
        created_at="2026-04-18T00:00:00",
        updated_at="2026-04-18T00:00:00",
        workspace=str(tmp_path),
        model="gpt-5.2",
        variant="standard",
        agent_mode="auto",
    )

    class DummySessionManager:
        def __init__(self, base_path: Path):
            self.base_path = base_path
            self.set_calls: list[str] = []

        def create_session(self, **_kwargs):
            return created

        def set_current_session(self, session_id: str):
            self.set_calls.append(session_id)

    runtime = SimpleNamespace(is_processing=True, load_session_by_id=lambda _session_id: None)
    manager = DummySessionManager(tmp_path)

    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)
    monkeypatch.setattr(session_bridge, "user_sessions", {9: runtime})

    bridge = session_bridge.AppSessionBridge(user_id=9, workspace=tmp_path)

    assert bridge.create_session("Busy") is created
    assert manager.set_calls == []


def test_load_session_by_id_rejects_switch_during_active_task():
    class DummySessionManager:
        def __init__(self):
            self.load_calls: list[str] = []

        def get_current_session_id(self):
            return "current"

        def load_session(self, session_id: str):
            self.load_calls.append(session_id)
            raise AssertionError("load_session should not run while the task is active")

    runtime = object.__new__(TelegramSession)
    runtime.session_manager = DummySessionManager()
    runtime.is_processing = True
    runtime.tool_executor = None
    runtime.single_agent = None
    runtime.refined_agent = None
    runtime.unified_agent = None

    TelegramSession.load_session_by_id(runtime, "current")
    assert runtime.session_manager.load_calls == []

    with pytest.raises(RuntimeError, match="Cannot switch sessions"):
        TelegramSession.load_session_by_id(runtime, "other")


def test_load_session_by_id_updates_tool_executor_workspace_path(tmp_path: Path):
    new_workspace = tmp_path / "workspace"
    new_workspace.mkdir()

    loaded_session = Session(
        id="sess1234",
        name="Loaded",
        created_at="2026-04-18T00:00:00",
        updated_at="2026-04-18T00:00:00",
        workspace=str(new_workspace),
        model="gpt-test",
        variant="thinking",
        agent_mode="auto",
        chat_history=[{"role": "user", "content": "hello"}],
        active_skills=["skill-a"],
    )

    class DummySessionManager:
        def get_current_session_id(self):
            return "old"

        def load_session(self, session_id: str):
            assert session_id == "sess1234"
            return loaded_session

    runtime = object.__new__(TelegramSession)
    runtime.session_manager = DummySessionManager()
    runtime.is_processing = False
    runtime.workspace = tmp_path / "old"
    runtime.active_skills = []
    runtime.skill_registry = None
    runtime.tool_executor = SimpleNamespace(
        workspace_path=runtime.workspace,
        single_agent=None,
        skill_registry=None,
        active_skills=[],
    )
    runtime.single_agent = None
    runtime.refined_agent = None
    runtime.unified_agent = None

    TelegramSession.load_session_by_id(runtime, "sess1234")

    assert runtime.workspace == new_workspace.resolve()
    assert runtime.tool_executor.workspace_path == new_workspace.resolve()
    assert runtime.current_model == "gpt-test"
    assert runtime.current_variant == "thinking"
    assert runtime.active_skills == ["skill-a"]
