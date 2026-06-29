from __future__ import annotations

import json
import os
from pathlib import Path

from mobile_app.backend.session_bridge import AppSessionBridge
from shared.telegram_bot_config_store import TELEGRAM_BOT_TOKENS_JSON_ENV, TelegramBotConfigStore


def test_telegram_bot_tokens_are_runtime_only(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("shared.telegram_bot_config_store.user_state_root", lambda _user_id: tmp_path)
    monkeypatch.delenv(TELEGRAM_BOT_TOKENS_JSON_ENV, raising=False)

    store = TelegramBotConfigStore(user_id=7001)
    created = store.create_config(label="Cloud Bot", bot_token="123456:cloud-secret")
    payload = json.loads((tmp_path / "telegram-bot-configs.json").read_text(encoding="utf-8"))

    assert created["bot_token"] == "123456:cloud-secret"
    assert "bot_token" not in json.dumps(payload)
    assert "cloud-secret" not in json.dumps(payload)

    runtime_tokens = json.loads(os.environ[TELEGRAM_BOT_TOKENS_JSON_ENV])
    assert runtime_tokens[created["id"]] == "123456:cloud-secret"

    monkeypatch.delenv(TELEGRAM_BOT_TOKENS_JSON_ENV, raising=False)
    assert store.list_configs() == []

    monkeypatch.setenv(TELEGRAM_BOT_TOKENS_JSON_ENV, json.dumps({created["id"]: "123456:cloud-secret"}))
    restored = store.list_configs()
    assert restored[0]["id"] == created["id"]
    assert restored[0]["bot_token"] == "123456:cloud-secret"


def test_restore_telegram_bot_parenting_rebuilds_chat_assignments(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("shared.telegram_bot_config_store.user_state_root", lambda _user_id: tmp_path)
    monkeypatch.setattr("shared.multi_chat_orchestrator.user_state_root", lambda _user_id: tmp_path)
    monkeypatch.setattr("mobile_app.backend.session_bridge.user_state_root", lambda _user_id: tmp_path)
    monkeypatch.delenv(TELEGRAM_BOT_TOKENS_JSON_ENV, raising=False)

    bridge = AppSessionBridge(user_id=7002, workspace=tmp_path)
    bridge.orchestrator.telegram_bots.replace_configs(
        [
            {"id": "bot-a", "label": "Bot A", "bot_token": "111111:aaa"},
            {"id": "bot-b", "label": "Bot B", "bot_token": "222222:bbb"},
        ],
    )
    first = bridge.session_manager.create_session(name="First", workspace=tmp_path, model="gpt-5.4-mini")
    second = bridge.session_manager.create_session(name="Second", workspace=tmp_path, model="gpt-5.4-mini")
    first.telegram_bot_config_id = "bot-a"
    first.chat_history = [{"role": "user", "content": "keep first"}]
    second.telegram_bot_config_id = "bot-a"
    second.chat_history = [{"role": "user", "content": "keep second"}]
    bridge.session_manager.save_session(first)
    bridge.session_manager.save_session(second)

    result = bridge.restore_telegram_bot_parenting({first.id: "bot-b", second.id: "missing-bot"})

    assert result["updated"] == 1
    assert bridge._load_session(first.id, set_current=False).telegram_bot_config_id == "bot-b"
    assert bridge._load_session(second.id, set_current=False).telegram_bot_config_id == "bot-a"
