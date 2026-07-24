import json

from shared.fleet_manager_connection import (
    manager_connection_status,
    reconcile_manager_connection_config,
)


def _write_config(home, *, host="127.0.0.1", enabled=False):
    payload = {
        "channels": {
            "desktop": {"enabled": True, "host": host, "port": 8787},
            "app": {"enabled": True, "host": host, "port": 8787},
        },
        "fleet": {"manager_enabled": enabled},
    }
    (home / "config.json").write_text(json.dumps(payload), encoding="utf-8")


def test_manager_refresh_persists_mode_and_yggdrasil_bind(tmp_path):
    _write_config(tmp_path)

    result = reconcile_manager_connection_config(tmp_path, enable=True)
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))

    assert result == {"enabled": True, "marker_changed": True, "bind_changed": True}
    assert saved["fleet"]["manager_enabled"] is True
    assert saved["channels"]["desktop"]["host"] == "::"
    assert saved["channels"]["app"]["host"] == "::"


def test_startup_prepare_is_inert_until_manager_mode_was_enabled(tmp_path):
    _write_config(tmp_path)

    result = reconcile_manager_connection_config(tmp_path, enable=False)
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))

    assert result["enabled"] is False
    assert result["bind_changed"] is False
    assert saved["channels"]["desktop"]["host"] == "127.0.0.1"


def test_startup_prepare_migrates_an_existing_ipv6_manager_bind(tmp_path):
    _write_config(tmp_path, host="::", enabled=False)

    result = reconcile_manager_connection_config(tmp_path, enable=False)
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))

    assert result["enabled"] is True
    assert result["marker_changed"] is True
    assert result["bind_changed"] is False
    assert saved["fleet"]["manager_enabled"] is True


def test_manager_status_requires_transport_bind_and_backend(tmp_path):
    _write_config(tmp_path, host="::", enabled=True)

    ready = manager_connection_status(
        tmp_path,
        yggdrasil={"available": True, "running": True, "address": "200::1"},
        runtime={"ok": True, "state": "ready"},
    )
    broken = manager_connection_status(
        tmp_path,
        yggdrasil={"available": True, "running": False, "address": "200::1"},
        runtime={"ok": True, "state": "ready"},
    )

    assert ready["ready"] is True
    assert ready["state"] == "online"
    assert ready["persistent"] is True
    assert broken["ready"] is False
    assert broken["state"] == "offline"


def test_manager_status_rejects_loopback_runtime_behind_ipv6_config(tmp_path):
    _write_config(tmp_path, host="::", enabled=True)

    status = manager_connection_status(
        tmp_path,
        yggdrasil={"available": True, "running": True, "address": "200::1"},
        runtime={"ok": True, "state": "ready", "bind_host": "127.0.0.1", "bind_port": 8787},
    )

    assert status["ready"] is False
    assert status["state"] == "needs_repair"
    assert status["configured_bind_ready"] is True
    assert status["runtime_bind_ready"] is False
    assert status["bind_ready"] is False
