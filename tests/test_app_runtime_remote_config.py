import json
from pathlib import Path

from app_backend import runtime as app_runtime


def test_remote_api_config_uses_env_values_with_encrypted_session_file(monkeypatch, tmp_path: Path):
    (tmp_path / app_runtime.REMOTE_CONTROL_SESSION_FILENAME).write_text(
        json.dumps({"version": 2, "storage": "electron_safe_storage", "ciphertext": "opaque"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(app_runtime, "runtime_home", lambda: tmp_path)
    monkeypatch.setenv(app_runtime.REMOTE_CONTROL_BASE_URL_ENV, "https://api.kraitos.app/")
    monkeypatch.setenv(app_runtime.REMOTE_CONTROL_SESSION_TOKEN_ENV, "session-token")
    monkeypatch.setenv(app_runtime.REMOTE_CONTROL_DESKTOP_ID_ENV, "desktop-abc")

    config = app_runtime._remote_api_config()

    assert config == {
        "base_url": "https://api.kraitos.app",
        "token": "session-token",
        "desktop_id": "desktop-abc",
    }
