from pathlib import Path

from cli.config_manager import ConfigManager
from cli.session_manager import SessionManager
from app_backend.auth_store import AppAuthStore
from shared.channel_sync import ChannelSyncHub


def test_packaged_defaults_use_runtime_home_scoped_storage(monkeypatch, tmp_path: Path):
    runtime_home = tmp_path / "runtime-home"
    monkeypatch.setenv("EMPLOAI_HOME", str(runtime_home))

    session_manager = SessionManager()
    auth_store = AppAuthStore()
    config_manager = ConfigManager()
    sync_hub = ChannelSyncHub()

    assert session_manager.base_path == runtime_home.resolve() / "data"
    assert auth_store.root_path == runtime_home.resolve() / "data"
    assert config_manager.base_path == runtime_home.resolve() / "data"
    assert config_manager.keyring_service != "agentshell"
    assert sync_hub._event_root() == runtime_home.resolve() / "channel_sync"
