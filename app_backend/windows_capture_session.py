from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Any, Mapping


WTS_CURRENT_SERVER_HANDLE = wintypes.HANDLE(0)
WTS_CONNECT_STATE = 8
WTS_CLIENT_PROTOCOL_TYPE = 16
WTS_STATE_NAMES = {
    0: "active",
    1: "connected",
    2: "connecting",
    3: "shadowing",
    4: "disconnected",
    5: "idle",
    6: "listening",
    7: "resetting",
    8: "down",
    9: "initializing",
}


class DesktopCaptureUnavailableError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        state: str,
        recovery: str,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.code = str(code)
        self.state = str(state)
        self.recovery = str(recovery)
        self.retryable = bool(retryable)

    def capability(self) -> dict[str, Any]:
        return {
            "available": False,
            "code": self.code,
            "state": self.state,
            "recovery": self.recovery,
            "retryable": self.retryable,
        }


def _current_process_session_id() -> int | None:
    session_id = wintypes.DWORD()
    try:
        process_id = ctypes.windll.kernel32.GetCurrentProcessId()
        ok = ctypes.windll.kernel32.ProcessIdToSessionId(
            process_id,
            ctypes.byref(session_id),
        )
    except (AttributeError, OSError):
        return None
    return int(session_id.value) if ok else None


def _query_wts_value(session_id: int, info_class: int, value_type: Any) -> int | None:
    buffer = ctypes.c_void_p()
    returned = wintypes.DWORD()
    try:
        ok = ctypes.windll.wtsapi32.WTSQuerySessionInformationW(
            WTS_CURRENT_SERVER_HANDLE,
            wintypes.DWORD(session_id),
            info_class,
            ctypes.byref(buffer),
            ctypes.byref(returned),
        )
        if not ok or not buffer.value:
            return None
        return int(ctypes.cast(buffer, ctypes.POINTER(value_type)).contents.value)
    except (AttributeError, OSError, ValueError):
        return None
    finally:
        if buffer.value:
            try:
                ctypes.windll.wtsapi32.WTSFreeMemory(buffer)
            except (AttributeError, OSError):
                pass


def windows_capture_session_status() -> dict[str, Any]:
    if os.name != "nt":
        return {
            "available": True,
            "state": "active",
            "protocol": "local",
            "sessionId": None,
        }

    session_id = _current_process_session_id()
    if session_id is None:
        return {
            "available": True,
            "state": "unknown",
            "protocol": "unknown",
            "sessionId": None,
        }

    state_value = _query_wts_value(session_id, WTS_CONNECT_STATE, ctypes.c_int)
    protocol_value = _query_wts_value(
        session_id,
        WTS_CLIENT_PROTOCOL_TYPE,
        ctypes.c_ushort,
    )
    state = WTS_STATE_NAMES.get(state_value, "unknown")
    protocol = {0: "console", 2: "rdp"}.get(protocol_value, "unknown")
    available = state in {"active", "unknown"}
    return {
        "available": available,
        "state": state,
        "protocol": protocol,
        "sessionId": session_id,
    }


def capture_session_unavailable(
    *,
    status: Mapping[str, Any] | None = None,
) -> DesktopCaptureUnavailableError | None:
    current = dict(status or windows_capture_session_status())
    if bool(current.get("available", True)):
        return None
    state = str(current.get("state") or "unavailable")
    if state == "disconnected":
        return DesktopCaptureUnavailableError(
            "The computer is connected to Fleet, but its Windows desktop session is disconnected and is not producing a capturable frame.",
            code="display_disconnected",
            state=state,
            recovery="Reconnect or attach a persistent interactive/virtual display, then retry. The Windows lock screen remains protected.",
        )
    return DesktopCaptureUnavailableError(
        "The computer is connected to Fleet, but its Windows desktop is not currently capturable.",
        code="display_unavailable",
        state=state,
        recovery="Sign in to an interactive Windows desktop and retry.",
    )


def capture_backend_unavailable(
    exc: BaseException,
    *,
    platform_name: str | None = None,
) -> DesktopCaptureUnavailableError | None:
    platform = str(platform_name or os.name).strip().lower()
    if platform != "nt":
        return None
    session_error = capture_session_unavailable()
    if session_error:
        return session_error
    detail = str(exc or "").strip().lower()
    access_denied = "access is denied" in detail or "access denied" in detail
    if "bitblt" in detail or access_denied or "screen shot failed" in detail:
        return DesktopCaptureUnavailableError(
            "Windows desktop preview is unavailable because the interactive display cannot be captured. "
            "The computer remains connected to Fleet, but Windows is not exposing a desktop frame. "
            "Restore and unlock the RDP/desktop session; if it is minimized, keep an interactive or virtual display attached, then retry.",
            code="framebuffer_unavailable",
            state="interactive_display_unavailable",
            recovery="Restore and unlock the desktop. On a VPS, keep an interactive or virtual display attached before enabling screenshots-per-minute.",
        )
    return None


def assert_capture_session_available() -> dict[str, Any]:
    status = windows_capture_session_status()
    error = capture_session_unavailable(status=status)
    if error:
        raise error
    return status
