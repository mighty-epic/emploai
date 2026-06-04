from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from shared.multi_chat_orchestrator import UserMultiChatOrchestrator


def _create_orchestrator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> UserMultiChatOrchestrator:
    monkeypatch.setattr("shared.multi_chat_orchestrator.user_state_root", lambda _user_id: tmp_path)
    return UserMultiChatOrchestrator(user_id=9001, workspace=tmp_path)


def _create_session(
    orchestrator: UserMultiChatOrchestrator,
    *,
    name: str,
    workspace: Path,
    bot_config_id: str | None = None,
) -> object:
    session = orchestrator.session_manager.create_session(name=name, workspace=workspace, model="gpt-5.4-mini")
    session.telegram_bot_config_id = bot_config_id
    orchestrator.session_manager.save_session(session)
    return session


def _fake_worker_for(session: object, *, enabled_tool_packs: list[str]):
    return SimpleNamespace(
        is_processing=False,
        session=session,
        enabled_tool_packs=list(enabled_tool_packs),
        telegram_bot_config_id=getattr(session, "telegram_bot_config_id", None),
        current_turn_allowed_tool_names=None,
        _active_tool_packs_for_current_run=[],
    )


def test_runtime_status_view_exposes_sleep_mapping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    orchestrator = _create_orchestrator(tmp_path, monkeypatch)
    default_bot = orchestrator.telegram_bots.ensure_default_from_env(bot_token="123456:AAA")
    session = _create_session(
        orchestrator,
        name="Sleep Chat",
        workspace=tmp_path / "workspace-a",
        bot_config_id=default_bot["id"],
    )

    orchestrator.telegram_bots.set_sleep_session(bot_config_id=default_bot["id"], session_id=session.id)
    status = orchestrator.runtime_status_view()

    assert status["default_sleep_session_by_bot"][default_bot["id"]] == session.id


@pytest.mark.asyncio
async def test_prepare_turn_blocks_nondesignated_sleep_chat_in_headless_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    orchestrator = _create_orchestrator(tmp_path, monkeypatch)
    default_bot = orchestrator.telegram_bots.ensure_default_from_env(bot_token="123456:AAA")
    session_allowed = _create_session(
        orchestrator,
        name="Allowed Sleep Chat",
        workspace=tmp_path / "workspace-a",
        bot_config_id=default_bot["id"],
    )
    session_blocked = _create_session(
        orchestrator,
        name="Blocked Chat",
        workspace=tmp_path / "workspace-b",
        bot_config_id=default_bot["id"],
    )

    orchestrator._settings["headless_mode_enabled"] = True
    orchestrator.telegram_bots.set_sleep_session(bot_config_id=default_bot["id"], session_id=session_allowed.id)
    monkeypatch.setattr(
        orchestrator,
        "get_worker",
        lambda session_id: _fake_worker_for(
            session_allowed if session_id == session_allowed.id else session_blocked,
            enabled_tool_packs=["interactive_desktop", "workspace_read"],
        ),
    )

    lease = await orchestrator.prepare_turn(session_blocked.id)

    assert lease.acquired is False
    assert lease.busy is True
    assert "designated sleep chats" in str(lease.error)


@pytest.mark.asyncio
async def test_prepare_turn_removes_interactive_pack_for_nondefault_sleep_bot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    orchestrator = _create_orchestrator(tmp_path, monkeypatch)
    default_bot = orchestrator.telegram_bots.ensure_default_from_env(bot_token="123456:AAA")
    secondary_bot = orchestrator.telegram_bots.create_config(label="Secondary Bot", bot_token="999999:BBB")
    session = _create_session(
        orchestrator,
        name="Secondary Bot Sleep Chat",
        workspace=tmp_path / "workspace-b",
        bot_config_id=secondary_bot["id"],
    )

    orchestrator._settings["headless_mode_enabled"] = True
    orchestrator.telegram_bots.set_sleep_session(bot_config_id=secondary_bot["id"], session_id=session.id)
    monkeypatch.setattr(
        orchestrator,
        "get_worker",
        lambda _session_id: _fake_worker_for(
            session,
            enabled_tool_packs=["interactive_desktop", "workspace_read", "workspace_write"],
        ),
    )

    lease = await orchestrator.prepare_turn(session.id)
    try:
        assert lease.acquired is True
        assert "interactive_desktop" not in lease.active_tool_packs
        assert "workspace_read" in lease.active_tool_packs
        assert "workspace_write" in lease.active_tool_packs
    finally:
        await orchestrator.complete_turn(lease)


def test_update_session_tool_packs_refreshes_worker_session_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    orchestrator = _create_orchestrator(tmp_path, monkeypatch)
    session = _create_session(
        orchestrator,
        name="Pack Sync Chat",
        workspace=tmp_path / "workspace-a",
    )
    session.enabled_tool_packs = ["workspace_read", "workspace_write"]
    worker = _fake_worker_for(session, enabled_tool_packs=["workspace_read", "workspace_write"])
    orchestrator._workers[session.id] = worker

    updated = orchestrator.update_session_tool_packs(session.id, ["workspace_read"])

    assert updated.enabled_tool_packs == ["workspace_read"]
    assert worker.enabled_tool_packs == ["workspace_read"]
    assert worker.session.enabled_tool_packs == ["workspace_read"]
