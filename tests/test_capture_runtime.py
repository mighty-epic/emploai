from __future__ import annotations

import pytest

from app_backend import capture_runtime
from app_backend.capture_runtime import _capture_backend_error
from app_backend.windows_capture_session import (
    DesktopCaptureUnavailableError,
    capture_session_unavailable,
)


def test_windows_bitblt_access_error_explains_rdp_recovery():
    error = _capture_backend_error(
        RuntimeError("Windows graphics function failed: BitBlt: Access is denied."),
        platform_name="nt",
    )

    assert "interactive display cannot be captured" in str(error)
    assert "Unlock the desktop" in str(error)
    assert "automatically move" in str(error)


def test_other_capture_errors_keep_their_specific_detail():
    error = _capture_backend_error(RuntimeError("monitor not found"), platform_name="posix")
    assert str(error) == "monitor not found"


def test_disconnected_windows_session_has_structured_recovery():
    error = capture_session_unavailable(
        status={"available": False, "state": "disconnected", "protocol": "rdp"},
    )

    assert isinstance(error, DesktopCaptureUnavailableError)
    assert error.capability() == {
        "available": False,
        "code": "display_disconnected",
        "state": "disconnected",
        "recovery": "Unlock or sign in to the Windows desktop, then retry. Windows Server headless capture never bypasses the lock screen.",
        "retryable": True,
    }


def test_disconnected_session_is_handed_to_console_before_capture(monkeypatch: pytest.MonkeyPatch):
    statuses = iter(
        [
            {"available": False, "state": "disconnected", "protocol": "rdp", "sessionId": 2},
            {"available": True, "state": "active", "protocol": "console", "sessionId": 2},
        ]
    )
    context: dict[str, object] = {}
    monkeypatch.setattr(capture_runtime, "_windows_platform", lambda: True)
    monkeypatch.setattr(capture_runtime, "windows_capture_session_status", lambda: next(statuses))
    monkeypatch.setattr(
        capture_runtime,
        "ensure_windows_console_capture_session",
        lambda **_kwargs: {
            "ok": True,
            "attempted": True,
            "transitioned": True,
            "sessionId": 2,
        },
    )

    status = capture_runtime._prepare_capture_session(context)

    assert status["protocol"] == "console"
    assert context["session_handoff"] == {
        "type": "rdp_to_console",
        "automatic": True,
        "sessionId": 2,
    }


def test_minimized_rdp_capture_retries_once_after_console_handoff(monkeypatch: pytest.MonkeyPatch):
    expected_image = object()
    attempts = iter(
        [
            RuntimeError("Windows graphics function failed: BitBlt: Access is denied."),
            expected_image,
        ]
    )
    context: dict[str, object] = {}

    def grab():
        result = next(attempts)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(capture_runtime, "_windows_platform", lambda: True)
    monkeypatch.setattr(capture_runtime, "_grab_with_mss", grab)
    monkeypatch.setattr(
        capture_runtime,
        "_capture_backend_error",
        lambda _exc: DesktopCaptureUnavailableError(
            "Windows desktop preview is unavailable.",
            code="framebuffer_unavailable",
            state="interactive_display_unavailable",
            recovery="Unlock and retry.",
        ),
    )
    monkeypatch.setattr(
        capture_runtime,
        "windows_capture_session_status",
        lambda: {"available": True, "state": "active", "protocol": "rdp", "sessionId": 2},
    )
    monkeypatch.setattr(
        capture_runtime,
        "ensure_windows_console_capture_session",
        lambda **_kwargs: {
            "ok": True,
            "attempted": True,
            "transitioned": True,
            "sessionId": 2,
        },
    )

    image = capture_runtime._capture_with_mss(context)

    assert image is expected_image
    assert context["session_handoff"] == {
        "type": "rdp_to_console",
        "automatic": True,
        "sessionId": 2,
    }
