from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from cli.models.session import Session
from cli.session_manager import SessionManager
from mobile_app.backend import app_server, session_bridge
from shared.task_board import create_task_board
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


def test_app_session_bridge_create_session_rejects_busy_runtime(monkeypatch, tmp_path: Path):
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
            self.create_calls: list[dict] = []

        def create_session(self, **kwargs):
            self.create_calls.append(kwargs)
            return created

        def set_current_session(self, session_id: str):
            self.set_calls.append(session_id)

    runtime = SimpleNamespace(
        is_processing=True,
        load_session_by_id=lambda _session_id: None,
        save_session=lambda: None,
        session_manager=SimpleNamespace(get_current_session_id=lambda: "current"),
    )
    manager = DummySessionManager(tmp_path)

    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)
    monkeypatch.setattr(session_bridge, "user_sessions", {9: runtime})

    bridge = session_bridge.AppSessionBridge(user_id=9, workspace=tmp_path)

    with pytest.raises(RuntimeError, match="Finish or stop the current task"):
        bridge.create_session("Busy")

    assert manager.create_calls == []
    assert manager.set_calls == []


def test_app_session_bridge_create_session_inherits_runtime_defaults(monkeypatch, tmp_path: Path):
    created = Session(
        id="new12345",
        name="New Session",
        created_at="2026-04-18T00:00:00",
        updated_at="2026-04-18T00:00:00",
        workspace=str(tmp_path / "created"),
        model="gpt-5.4",
        variant="thinking",
        agent_mode="auto",
    )

    class DummySessionManager:
        def __init__(self, base_path: Path):
            self.base_path = base_path
            self.create_kwargs: dict | None = None
            self.set_calls: list[str] = []

        def create_session(self, **kwargs):
            self.create_kwargs = kwargs
            return created

        def set_current_session(self, session_id: str):
            self.set_calls.append(session_id)

        def load_session(self, session_id: str, *, set_current: bool = True):
            assert session_id == created.id
            return created

    load_calls: list[str] = []
    saved: list[str] = []
    runtime = SimpleNamespace(
        is_processing=False,
        workspace=tmp_path / "runtime-workspace",
        current_model="gpt-5.4",
        current_variant="thinking",
        planner_model="gpt-4o-mini",
        save_session=lambda: saved.append("saved"),
        load_session_by_id=lambda session_id: load_calls.append(session_id),
        session=created,
    )
    manager = DummySessionManager(tmp_path)

    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)
    monkeypatch.setattr(session_bridge, "user_sessions", {9: runtime})

    bridge = session_bridge.AppSessionBridge(user_id=9, workspace=tmp_path)
    result = bridge.create_session("Fresh")

    assert result is created
    assert manager.create_kwargs == {
        "name": "Fresh",
        "workspace": runtime.workspace,
        "model": "gpt-5.4",
        "variant": "thinking",
        "planner_model": "gpt-4o-mini",
        "agent_mode": "auto",
    }
    assert saved == ["saved"]
    assert manager.set_calls == [created.id]
    assert load_calls == [created.id]


def test_app_session_bridge_create_session_uses_explicit_workspace_override(monkeypatch, tmp_path: Path):
    created = Session(
        id="new12347",
        name="New Session",
        created_at="2026-04-18T00:00:00",
        updated_at="2026-04-18T00:00:00",
        workspace=str(tmp_path / "created"),
        model="gpt-5.4",
        variant="thinking",
        agent_mode="auto",
    )

    class DummySessionManager:
        def __init__(self, base_path: Path):
            self.base_path = base_path
            self.create_kwargs: dict | None = None
            self.set_calls: list[str] = []

        def create_session(self, **kwargs):
            self.create_kwargs = kwargs
            return created

        def set_current_session(self, session_id: str):
            self.set_calls.append(session_id)

        def load_session(self, session_id: str, *, set_current: bool = True):
            assert session_id == created.id
            return created

    explicit_workspace = (tmp_path / "chosen-workspace").resolve()
    explicit_workspace.mkdir()
    load_calls: list[str] = []
    saved: list[str] = []
    runtime = SimpleNamespace(
        is_processing=False,
        workspace=tmp_path / "runtime-workspace",
        current_model="gpt-5.4",
        current_variant="thinking",
        planner_model="gpt-4o-mini",
        save_session=lambda: saved.append("saved"),
        load_session_by_id=lambda session_id: load_calls.append(session_id),
        session=created,
    )
    manager = DummySessionManager(tmp_path)

    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)
    monkeypatch.setattr(session_bridge, "user_sessions", {9: runtime})

    bridge = session_bridge.AppSessionBridge(user_id=9, workspace=tmp_path)
    result = bridge.create_session("Fresh", workspace=explicit_workspace)

    assert result is created
    assert manager.create_kwargs == {
        "name": "Fresh",
        "workspace": explicit_workspace,
        "model": "gpt-5.4",
        "variant": "thinking",
        "planner_model": "gpt-4o-mini",
        "agent_mode": "auto",
    }
    assert saved == ["saved"]
    assert manager.set_calls == [created.id]
    assert load_calls == [created.id]


def test_app_session_bridge_create_session_uses_runtime_default_planner_when_session_is_automatic(monkeypatch, tmp_path: Path):
    created = Session(
        id="new12346",
        name="New Session",
        created_at="2026-04-18T00:00:00",
        updated_at="2026-04-18T00:00:00",
        workspace=str(tmp_path / "created"),
        model="gpt-5.4",
        variant="thinking",
        agent_mode="auto",
    )

    class DummySessionManager:
        def __init__(self, base_path: Path):
            self.base_path = base_path
            self.create_kwargs: dict | None = None
            self.set_calls: list[str] = []

        def create_session(self, **kwargs):
            self.create_kwargs = kwargs
            return created

        def set_current_session(self, session_id: str):
            self.set_calls.append(session_id)

        def load_session(self, session_id: str, *, set_current: bool = True):
            assert session_id == created.id
            return created

    load_calls: list[str] = []
    saved: list[str] = []
    runtime = SimpleNamespace(
        is_processing=False,
        workspace=tmp_path / "runtime-workspace",
        current_model="gpt-5.4",
        current_variant="thinking",
        planner_model=None,
        default_planner_model="gpt-5.4-mini",
        save_session=lambda: saved.append("saved"),
        load_session_by_id=lambda session_id: load_calls.append(session_id),
        session=created,
    )
    manager = DummySessionManager(tmp_path)

    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)
    monkeypatch.setattr(session_bridge, "user_sessions", {9: runtime})

    bridge = session_bridge.AppSessionBridge(user_id=9, workspace=tmp_path)
    result = bridge.create_session("Fresh")

    assert result is created
    assert manager.create_kwargs == {
        "name": "Fresh",
        "workspace": runtime.workspace,
        "model": "gpt-5.4",
        "variant": "thinking",
        "planner_model": "gpt-5.4-mini",
        "agent_mode": "auto",
    }
    assert saved == ["saved"]
    assert manager.set_calls == [created.id]
    assert load_calls == [created.id]


def test_app_session_bridge_activate_session_persists_runtime_before_switch(monkeypatch, tmp_path: Path):
    existing = Session(
        id="sess4321",
        name="Existing",
        created_at="2026-04-18T00:00:00",
        updated_at="2026-04-18T00:00:00",
        workspace=str(tmp_path),
        model="gpt-5.4",
        variant="standard",
        agent_mode="auto",
    )

    class DummySessionManager:
        def __init__(self, base_path: Path):
            self.base_path = base_path
            self.set_calls: list[str] = []

        def load_session(self, session_id: str, *, set_current: bool = True):
            assert session_id == existing.id
            return existing

        def set_current_session(self, session_id: str):
            self.set_calls.append(session_id)

    load_calls: list[str] = []
    saved: list[str] = []
    runtime = SimpleNamespace(
        is_processing=False,
        save_session=lambda: saved.append("saved"),
        load_session_by_id=lambda session_id: load_calls.append(session_id),
        session=existing,
    )
    manager = DummySessionManager(tmp_path)

    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)
    monkeypatch.setattr(session_bridge, "user_sessions", {42: runtime})

    bridge = session_bridge.AppSessionBridge(user_id=42, workspace=tmp_path)
    result = bridge.activate_session(existing.id)

    assert result is existing
    assert saved == ["saved"]
    assert manager.set_calls == [existing.id]
    assert load_calls == [existing.id]


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


def test_set_workspace_refreshes_workspace_scoped_runtime_managers(monkeypatch, tmp_path: Path):
    import shared.heartbeat as heartbeat_module

    old_workspace = (tmp_path / "old").resolve()
    new_workspace = (tmp_path / "new").resolve()
    old_workspace.mkdir()
    new_workspace.mkdir()

    memory_calls: list[Path] = []
    context_calls: list[Path] = []

    class DummyLiveConfig:
        def __init__(self, path: Path):
            self.path = path
            self.imported = False

        def import_from_env(self):
            self.imported = True

    class DummyHeartbeat:
        def __init__(self, workspace: Path, *, enabled: bool = False):
            self.workspace = workspace
            self.enabled = enabled
            self.interval_seconds = 900
            self.announcement_callback = "announce"
            self.agent_callback = "agent"
            self.stop_calls = 0
            self.start_calls = 0

        def stop(self):
            self.stop_calls += 1

        def start(self):
            self.start_calls += 1

    new_heartbeat_instances: list[DummyHeartbeat] = []

    def fake_get_memory_manager(path: Path):
        memory_calls.append(path)
        return f"memory:{path}"

    def fake_get_context_loader(path: Path):
        context_calls.append(path)
        return f"context:{path}"

    def fake_get_heartbeat_manager(*, workspace: Path, interval_seconds: int, announcement_callback, agent_callback):
        heartbeat = DummyHeartbeat(workspace, enabled=False)
        heartbeat.interval_seconds = interval_seconds
        heartbeat.announcement_callback = announcement_callback
        heartbeat.agent_callback = agent_callback
        new_heartbeat_instances.append(heartbeat)
        return heartbeat

    monkeypatch.setattr("telegram_bot.telegram_session_state.get_memory_manager", fake_get_memory_manager)
    monkeypatch.setattr("telegram_bot.telegram_session_state.get_context_loader", fake_get_context_loader)
    monkeypatch.setattr("telegram_bot.telegram_session_state.LiveConfig", DummyLiveConfig)
    monkeypatch.setattr(heartbeat_module, "get_heartbeat_manager", fake_get_heartbeat_manager)

    runtime = object.__new__(TelegramSession)
    runtime.workspace = old_workspace
    runtime.is_processing = False
    runtime.memory_manager = None
    runtime.context_loader = None
    runtime.live_config = None
    runtime.skill_registry = "skills"
    runtime.active_skills = ["skill-a"]
    runtime.single_agent = "single-agent"
    runtime.tool_executor = SimpleNamespace(
        workspace_path=old_workspace,
        single_agent=None,
        skill_registry=None,
        active_skills=[],
    )
    runtime.heartbeat_manager = DummyHeartbeat(old_workspace, enabled=True)
    runtime.unified_agent = SimpleNamespace(workspace=old_workspace)

    resolved = TelegramSession.set_workspace(runtime, new_workspace)

    assert resolved == new_workspace
    assert runtime.workspace == new_workspace
    assert memory_calls == [new_workspace]
    assert context_calls == [new_workspace]
    assert runtime.memory_manager == f"memory:{new_workspace}"
    assert runtime.context_loader == f"context:{new_workspace}"
    assert isinstance(runtime.live_config, DummyLiveConfig)
    assert runtime.live_config.path == new_workspace / "config.json"
    assert runtime.live_config.imported is True
    assert runtime.tool_executor.workspace_path == new_workspace
    assert runtime.tool_executor.single_agent == "single-agent"
    assert runtime.tool_executor.skill_registry == "skills"
    assert runtime.tool_executor.active_skills == ["skill-a"]
    assert runtime.unified_agent.workspace == new_workspace
    assert len(new_heartbeat_instances) == 1
    assert new_heartbeat_instances[0].workspace == new_workspace
    assert new_heartbeat_instances[0].start_calls == 1


def test_session_manager_load_session_can_skip_current_pointer_update(tmp_path: Path):
    manager = SessionManager(base_path=tmp_path)
    first = manager.create_session(name="First", workspace=tmp_path, model="gpt-5.2")
    second = manager.create_session(name="Second", workspace=tmp_path, model="gpt-5.4")
    manager.set_current_session(first.id)

    loaded = manager.load_session(second.id, set_current=False)

    assert loaded.id == second.id
    assert manager.get_current_session_id() == first.id


def test_app_session_bridge_list_sessions_does_not_switch_current_session(tmp_path: Path, monkeypatch):
    manager = SessionManager(base_path=tmp_path)
    current = manager.create_session(name="Current", workspace=tmp_path, model="gpt-5.4")
    manager.set_current_session(current.id)
    manager.create_session(name="Older", workspace=tmp_path, model="claude-haiku-4.5")
    manager.set_current_session(current.id)

    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)

    bridge = session_bridge.AppSessionBridge(user_id=101, workspace=tmp_path)
    sessions = bridge.list_sessions()

    assert {session.id for session in sessions} == {summary.id for summary in manager.list_sessions()}
    assert manager.get_current_session_id() == current.id


def test_session_round_trips_event_timeline():
    session = Session(
        id="sess1",
        name="Timeline",
        created_at="2026-05-08T10:00:00",
        updated_at="2026-05-08T10:00:00",
        workspace="C:/tmp",
        model="gpt-5.4",
        variant="standard",
        agent_mode="auto",
        event_timeline=[
            {
                "id": "evt1",
                "kind": "command",
                "title": "Command · /verbose on",
                "content": "Verbose tool logging enabled.",
                "tone": "accent",
                "timestamp": "2026-05-08T10:00:01",
                "channel": "app",
                "source_format": "app_system",
                "metadata": {"command": "/verbose on"},
            }
        ],
    )

    restored = Session.from_dict(session.to_dict())

    assert restored.event_timeline == session.event_timeline


def test_sync_event_to_realtime_event_maps_timeline_event():
    event = {
        "type": "timeline_event",
        "session_id": "sess1",
        "payload": {
            "event": {
                "id": "evt1",
                "kind": "tool",
                "title": "Tool · click",
                "content": "click(x: 100, y: 200)",
            }
        },
    }

    realtime = app_server._sync_event_to_realtime_event(
        event,
        active_session_id="sess1",
        client_id=None,
        verbose_mode=False,
    )

    assert realtime is not None
    assert realtime.type == "timeline_event"
    assert realtime.payload == event["payload"]


def test_app_session_bridge_append_timeline_event_persists(tmp_path: Path):
    manager = SessionManager(base_path=tmp_path)
    session = manager.create_session(name="Timeline", workspace=tmp_path, model="gpt-5.4")

    bridge = session_bridge.AppSessionBridge(user_id=7, workspace=tmp_path)
    bridge.session_manager = manager

    event = bridge.append_timeline_event(
        session_id=session.id,
        kind="command",
        title="Command · /verbose on",
        content="Verbose tool logging enabled.",
        tone="accent",
        channel="app",
        source_format="app_system",
        metadata={"command": "/verbose on"},
    )

    reloaded = manager.load_session(session.id, set_current=False)

    assert event["kind"] == "command"
    assert len(reloaded.event_timeline) == 1
    assert reloaded.event_timeline[0]["title"] == "Command · /verbose on"


def test_app_session_bridge_detailed_session_view_includes_task_board(tmp_path: Path, monkeypatch):
    manager = SessionManager(base_path=tmp_path)
    session = manager.create_session(name="Tasked", workspace=tmp_path, model="gpt-5.4")
    create_task_board(session, user_message="Open Spotify and play a song")
    manager.save_session(session)

    monkeypatch.setattr(session_bridge, "SessionManager", lambda base_path: manager)

    bridge = session_bridge.AppSessionBridge(user_id=55, workspace=tmp_path)
    loaded = bridge.get_session(session.id)
    detail = bridge.detailed_session_view(loaded)

    assert detail["task_board"] is not None
    assert detail["task_board"]["main_goal"] == "Open Spotify and play a song"
    assert detail["completed_task_boards"] == []
