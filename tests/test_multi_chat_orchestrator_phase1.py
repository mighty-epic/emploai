from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from shared.multi_chat_orchestrator import UserMultiChatOrchestrator


def _create_orchestrator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> UserMultiChatOrchestrator:
    monkeypatch.setattr("shared.multi_chat_orchestrator.user_state_root", lambda _user_id: tmp_path)
    monkeypatch.setattr("shared.telegram_bot_config_store.user_state_root", lambda _user_id: tmp_path)
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
    session.enabled_tool_packs = list(enabled_tool_packs)
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


def test_first_telegram_bot_is_named_and_deleteable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    orchestrator = _create_orchestrator(tmp_path, monkeypatch)
    first_bot = orchestrator.telegram_bots.ensure_default_from_env(bot_token="123456:AAA")
    secondary_bot = orchestrator.telegram_bots.create_config(label="Secondary Bot", bot_token="999999:BBB")

    assert first_bot["label"] == "Telegram bot 1"

    orchestrator.telegram_bots.delete_config(first_bot["id"])

    remaining = orchestrator.telegram_bots.list_configs()
    assert [item["id"] for item in remaining] == [secondary_bot["id"]]
    assert remaining[0]["is_default"] is True


def test_inbound_bot_claims_last_emitting_session_for_that_bot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    orchestrator = _create_orchestrator(tmp_path, monkeypatch)
    default_bot = orchestrator.telegram_bots.ensure_default_from_env(bot_token="123456:AAA")
    secondary_bot = orchestrator.telegram_bots.create_config(label="Secondary Bot", bot_token="999999:BBB")
    default_session = _create_session(
        orchestrator,
        name="Default Bot Chat",
        workspace=tmp_path / "workspace-a",
        bot_config_id=default_bot["id"],
    )
    secondary_session = _create_session(
        orchestrator,
        name="Secondary Bot Chat",
        workspace=tmp_path / "workspace-b",
        bot_config_id=secondary_bot["id"],
    )

    orchestrator.mark_last_emitting_session(
        session_id=secondary_session.id,
        bot_config_id=secondary_bot["id"],
    )

    assert orchestrator.resolve_session_for_inbound_bot(
        bot_config_id=secondary_bot["id"],
        focused_session_id=default_session.id,
    ) == secondary_session.id
    assert orchestrator.resolve_session_for_inbound_bot(
        bot_config_id=default_bot["id"],
        focused_session_id=default_session.id,
    ) == default_session.id


def test_inbound_bot_prefers_session_assigned_to_that_bot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    orchestrator = _create_orchestrator(tmp_path, monkeypatch)
    default_bot = orchestrator.telegram_bots.ensure_default_from_env(bot_token="123456:AAA")
    secondary_bot = orchestrator.telegram_bots.create_config(label="Secondary Bot", bot_token="999999:BBB")
    default_session = _create_session(
        orchestrator,
        name="Default Bot Chat",
        workspace=tmp_path / "workspace-a",
        bot_config_id=default_bot["id"],
    )
    secondary_session = _create_session(
        orchestrator,
        name="Secondary Bot Chat",
        workspace=tmp_path / "workspace-b",
        bot_config_id=secondary_bot["id"],
    )

    assert orchestrator.resolve_session_for_inbound_bot(
        bot_config_id=secondary_bot["id"],
        focused_session_id=default_session.id,
    ) == secondary_session.id


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
    assert "designated Telegram sleep chats" in str(lease.error)


@pytest.mark.asyncio
async def test_sleep_mode_allows_mobile_app_origin_for_any_chat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    orchestrator = _create_orchestrator(tmp_path, monkeypatch)
    default_bot = orchestrator.telegram_bots.ensure_default_from_env(bot_token="123456:AAA")
    session_allowed = _create_session(
        orchestrator,
        name="Telegram Sleep Chat",
        workspace=tmp_path / "workspace-a",
        bot_config_id=default_bot["id"],
    )
    mobile_session = _create_session(
        orchestrator,
        name="Mobile Chat",
        workspace=tmp_path / "workspace-b",
        bot_config_id=default_bot["id"],
    )

    orchestrator._settings["headless_mode_enabled"] = True
    orchestrator.telegram_bots.set_sleep_session(bot_config_id=default_bot["id"], session_id=session_allowed.id)
    monkeypatch.setattr(
        orchestrator,
        "get_worker",
        lambda session_id: _fake_worker_for(
            session_allowed if session_id == session_allowed.id else mobile_session,
            enabled_tool_packs=["interactive_desktop", "workspace_read"],
        ),
    )

    telegram_lease = await orchestrator.prepare_turn(mobile_session.id, origin_channel="telegram")
    mobile_lease = await orchestrator.prepare_turn(mobile_session.id, origin_channel="app")
    try:
        assert telegram_lease.acquired is False
        assert telegram_lease.busy is True
        assert "designated Telegram sleep chats" in str(telegram_lease.error)
        assert mobile_lease.acquired is True
        assert mobile_lease.busy is False
        assert mobile_lease.active_tool_packs == ["interactive_desktop", "workspace_read"]
    finally:
        await orchestrator.complete_turn(mobile_lease)


@pytest.mark.asyncio
async def test_enabling_sleep_mode_does_not_interrupt_mobile_origin_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    orchestrator = _create_orchestrator(tmp_path, monkeypatch)
    default_bot = orchestrator.telegram_bots.ensure_default_from_env(bot_token="123456:AAA")
    sleep_session = _create_session(
        orchestrator,
        name="Telegram Sleep Chat",
        workspace=tmp_path / "workspace-sleep",
        bot_config_id=default_bot["id"],
    )
    mobile_session = _create_session(
        orchestrator,
        name="Mobile Chat",
        workspace=tmp_path / "workspace-mobile",
        bot_config_id=default_bot["id"],
    )
    telegram_session = _create_session(
        orchestrator,
        name="Telegram Regular Chat",
        workspace=tmp_path / "workspace-telegram",
        bot_config_id=default_bot["id"],
    )
    workers = {
        sleep_session.id: _fake_worker_for(sleep_session, enabled_tool_packs=["workspace_read"]),
        mobile_session.id: _fake_worker_for(mobile_session, enabled_tool_packs=["workspace_read"]),
        telegram_session.id: _fake_worker_for(telegram_session, enabled_tool_packs=["workspace_read"]),
    }
    orchestrator._workers.update(workers)
    monkeypatch.setattr(orchestrator, "get_worker", lambda session_id: workers[session_id])

    mobile_lease = await orchestrator.prepare_turn(mobile_session.id, origin_channel="app")
    telegram_lease = await orchestrator.prepare_turn(telegram_session.id, origin_channel="telegram")
    try:
        orchestrator.configure_headless(
            enabled=True,
            default_sleep_session_by_bot={default_bot["id"]: sleep_session.id},
        )

        assert getattr(workers[mobile_session.id], "should_interrupt", False) is False
        assert getattr(workers[telegram_session.id], "should_interrupt", False) is True
    finally:
        await orchestrator.complete_turn(telegram_lease)
        await orchestrator.complete_turn(mobile_lease)


@pytest.mark.asyncio
async def test_same_workspace_concurrent_turn_blocks_lock_limited_packs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    orchestrator = _create_orchestrator(tmp_path, monkeypatch)
    workspace = tmp_path / "workspace-a"
    first = _create_session(orchestrator, name="First", workspace=workspace)
    second = _create_session(orchestrator, name="Second", workspace=workspace)
    enabled_packs = ["interactive_desktop", "workspace_write", "workspace_read"]
    workers = {
        first.id: _fake_worker_for(first, enabled_tool_packs=enabled_packs),
        second.id: _fake_worker_for(second, enabled_tool_packs=enabled_packs),
    }
    monkeypatch.setattr(orchestrator, "get_worker", lambda session_id: workers[session_id])

    first_lease = await orchestrator.prepare_turn(first.id)
    second_lease = await orchestrator.prepare_turn(second.id)
    try:
        assert first_lease.acquired is True
        assert second_lease.acquired is False
        assert second_lease.busy is True
        assert second_lease.active_tool_packs == []
        assert "interactive_desktop" in second_lease.lock_status["disabled_pack_reasons"]
        assert "workspace_write" in second_lease.lock_status["disabled_pack_reasons"]
        assert first.id in second_lease.lock_status["disabled_pack_reasons"]["workspace_write"]
        assert "locked by another active chat" in str(second_lease.error)
    finally:
        await orchestrator.complete_turn(second_lease)
        await orchestrator.complete_turn(first_lease)


@pytest.mark.asyncio
async def test_force_release_turn_clears_running_locks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    orchestrator = _create_orchestrator(tmp_path, monkeypatch)
    workspace = tmp_path / "workspace-a"
    session = _create_session(orchestrator, name="Running", workspace=workspace)
    enabled_packs = ["interactive_desktop", "workspace_write", "workspace_read"]
    worker = _fake_worker_for(session, enabled_tool_packs=enabled_packs)
    monkeypatch.setattr(orchestrator, "get_worker", lambda _session_id: worker)

    lease = await orchestrator.prepare_turn(session.id)

    assert lease.acquired is True
    assert orchestrator.runtime_status_view()["running_sessions"]

    released = await orchestrator.force_release_turn(session.id, worker=worker)

    assert released is True
    status = orchestrator.runtime_status_view()
    assert status["running_sessions"] == []
    assert status["locks"]["interactive_owner_session_id"] is None
    assert status["locks"]["workspace_write_owner_by_workspace"] == {}
    assert worker._active_tool_packs_for_current_run == []


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
