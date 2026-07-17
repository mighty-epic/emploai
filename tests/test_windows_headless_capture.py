from __future__ import annotations

from types import SimpleNamespace

from app_backend.windows_headless_capture import (
    HEADLESS_CAPTURE_ENV,
    ensure_windows_console_capture_session,
    windows_headless_capture_policy,
)


def test_headless_capture_defaults_on_for_windows_server():
    policy = windows_headless_capture_policy(
        platform_name="nt",
        environment={},
        windows_server=True,
    )

    assert policy == {
        "enabled": True,
        "mode": "auto",
        "windowsServer": True,
        "reason": "windows_server_default",
    }


def test_headless_capture_defaults_off_for_windows_client():
    policy = windows_headless_capture_policy(
        platform_name="nt",
        environment={},
        windows_server=False,
    )

    assert policy["enabled"] is False
    assert policy["reason"] == "windows_client_default"


def test_headless_capture_environment_override_is_explicit():
    enabled = windows_headless_capture_policy(
        platform_name="nt",
        environment={HEADLESS_CAPTURE_ENV: "console"},
        windows_server=False,
    )
    disabled = windows_headless_capture_policy(
        platform_name="nt",
        environment={HEADLESS_CAPTURE_ENV: "off"},
        windows_server=True,
    )

    assert enabled["enabled"] is True
    assert enabled["reason"] == "explicitly_enabled"
    assert disabled["enabled"] is False
    assert disabled["reason"] == "explicitly_disabled"


def test_console_session_is_already_capture_ready():
    result = ensure_windows_console_capture_session(
        status={"state": "active", "protocol": "console", "sessionId": 3},
        platform_name="nt",
        environment={HEADLESS_CAPTURE_ENV: "on"},
    )

    assert result["ok"] is True
    assert result["attempted"] is False
    assert result["transitioned"] is False
    assert result["code"] == "console_ready"


def test_rdp_session_handoff_waits_for_active_console():
    calls: list[int] = []
    states = iter(
        [
            {"state": "disconnected", "protocol": "rdp", "sessionId": 2},
            {"state": "active", "protocol": "console", "sessionId": 2},
        ]
    )

    result = ensure_windows_console_capture_session(
        status={"state": "disconnected", "protocol": "rdp", "sessionId": 2},
        platform_name="nt",
        environment={HEADLESS_CAPTURE_ENV: "on"},
        runner=lambda session_id: calls.append(session_id) or SimpleNamespace(returncode=0, stdout="", stderr=""),
        status_reader=lambda: next(states),
        sleep=lambda _seconds: None,
    )

    assert calls == [2]
    assert result["ok"] is True
    assert result["attempted"] is True
    assert result["transitioned"] is True
    assert result["protocol"] == "console"
    assert result["code"] == "console_handoff_complete"


def test_console_handoff_failure_is_structured():
    result = ensure_windows_console_capture_session(
        status={"state": "active", "protocol": "rdp", "sessionId": 2},
        platform_name="nt",
        environment={HEADLESS_CAPTURE_ENV: "on"},
        runner=lambda _session_id: SimpleNamespace(returncode=5, stdout="", stderr="Access is denied."),
    )

    assert result["ok"] is False
    assert result["attempted"] is True
    assert result["transitioned"] is False
    assert result["code"] == "console_handoff_failed"
    assert result["detail"] == "Access is denied."


def test_unrelated_session_state_is_never_transferred():
    result = ensure_windows_console_capture_session(
        status={"state": "down", "protocol": "rdp", "sessionId": 2},
        platform_name="nt",
        environment={HEADLESS_CAPTURE_ENV: "on"},
        runner=lambda _session_id: (_ for _ in ()).throw(AssertionError("must not run")),
    )

    assert result["ok"] is False
    assert result["attempted"] is False
    assert result["code"] == "session_not_transferable"
