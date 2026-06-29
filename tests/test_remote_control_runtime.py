import pytest

from mobile_app.backend import remote_control_runtime


def test_remote_control_routing_status_defaults_to_single_process(monkeypatch):
    monkeypatch.delenv("EMPLOAI_REMOTE_CONTROL_WORKERS", raising=False)
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    monkeypatch.delenv("UVICORN_WORKERS", raising=False)
    monkeypatch.delenv("EMPLOAI_REMOTE_CONTROL_ROUTING_MODE", raising=False)
    monkeypatch.delenv("EMPLOAI_REMOTE_CONTROL_ALLOW_UNSAFE_MULTIPROCESS", raising=False)

    status = remote_control_runtime.remote_control_routing_status()

    assert status["mode"] == "single_process"
    assert status["mode_valid"] is True
    assert status["supported_modes"] == ["single_process", "sqlite_broker"]
    assert status["supported"] is True
    assert status["requested_workers"] == 1
    assert status["requires_sticky_sessions_or_broker"] is False


def test_remote_control_routing_guard_rejects_multiple_workers(monkeypatch):
    monkeypatch.setenv("EMPLOAI_REMOTE_CONTROL_WORKERS", "2")
    monkeypatch.delenv("EMPLOAI_REMOTE_CONTROL_ALLOW_UNSAFE_MULTIPROCESS", raising=False)

    with pytest.raises(RuntimeError, match="in-process"):
        remote_control_runtime.assert_remote_control_routing_supported()


def test_remote_control_routing_guard_allows_explicit_unsafe_bypass(monkeypatch):
    monkeypatch.setenv("EMPLOAI_REMOTE_CONTROL_WORKERS", "2")
    monkeypatch.setenv("EMPLOAI_REMOTE_CONTROL_ALLOW_UNSAFE_MULTIPROCESS", "1")

    remote_control_runtime.assert_remote_control_routing_supported()
    status = remote_control_runtime.remote_control_routing_status()
    assert status["supported"] is False
    assert status["allow_unsafe_multiprocess"] is True


def test_remote_control_routing_status_supports_sqlite_broker(monkeypatch):
    monkeypatch.setenv("EMPLOAI_REMOTE_CONTROL_ROUTING_MODE", "sqlite_broker")
    monkeypatch.setenv("EMPLOAI_REMOTE_CONTROL_WORKERS", "3")
    monkeypatch.delenv("EMPLOAI_REMOTE_CONTROL_ALLOW_UNSAFE_MULTIPROCESS", raising=False)

    remote_control_runtime.assert_remote_control_routing_supported()
    status = remote_control_runtime.remote_control_routing_status()

    assert status["supported"] is True
    assert status["mode_valid"] is True
    assert status["broker"] == "sqlite"
    assert status["cross_process_command_routing"] is True
    assert status["requires_sticky_sessions_or_broker"] is False


def test_remote_control_routing_guard_rejects_unknown_mode(monkeypatch):
    monkeypatch.setenv("EMPLOAI_REMOTE_CONTROL_ROUTING_MODE", "sqlite-broker")
    monkeypatch.setenv("EMPLOAI_REMOTE_CONTROL_ALLOW_UNSAFE_MULTIPROCESS", "1")
    monkeypatch.setenv("EMPLOAI_REMOTE_CONTROL_WORKERS", "1")

    status = remote_control_runtime.remote_control_routing_status()

    assert status["mode"] == "sqlite-broker"
    assert status["mode_valid"] is False
    assert status["supported"] is False
    with pytest.raises(RuntimeError, match="Invalid EMPLOAI_REMOTE_CONTROL_ROUTING_MODE"):
        remote_control_runtime.assert_remote_control_routing_supported()
