from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Any, Callable, Mapping

from app_backend.windows_capture_session import windows_capture_session_status


HEADLESS_CAPTURE_ENV = "EMPLOAI_WINDOWS_HEADLESS_CAPTURE"
_ENABLED_VALUES = frozenset({"1", "true", "yes", "on", "console", "enabled"})
_DISABLED_VALUES = frozenset({"0", "false", "no", "off", "disabled"})


def _windows_server_installation() -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
        ) as key:
            product_name = str(winreg.QueryValueEx(key, "ProductName")[0] or "")
            try:
                installation_type = str(winreg.QueryValueEx(key, "InstallationType")[0] or "")
            except OSError:
                installation_type = ""
        marker = f"{product_name} {installation_type}".strip().lower()
        return "server" in marker
    except (ImportError, OSError, ValueError):
        return False


def windows_headless_capture_policy(
    *,
    platform_name: str | None = None,
    environment: Mapping[str, str] | None = None,
    windows_server: bool | None = None,
) -> dict[str, Any]:
    platform = str(platform_name or os.name).strip().lower()
    env = environment if environment is not None else os.environ
    configured = str(env.get(HEADLESS_CAPTURE_ENV, "auto") or "auto").strip().lower()
    server = _windows_server_installation() if windows_server is None else bool(windows_server)

    if platform != "nt":
        enabled = False
        reason = "not_windows"
    elif configured in _ENABLED_VALUES:
        enabled = True
        reason = "explicitly_enabled"
    elif configured in _DISABLED_VALUES:
        enabled = False
        reason = "explicitly_disabled"
    else:
        configured = "auto"
        enabled = server
        reason = "windows_server_default" if server else "windows_client_default"

    return {
        "enabled": enabled,
        "mode": configured,
        "windowsServer": server,
        "reason": reason,
    }


def _run_console_handoff(session_id: int) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("tscon.exe") or shutil.which("tscon") or "tscon.exe"
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "check": False,
        "timeout": 4,
    }
    if os.name == "nt":
        kwargs["creationflags"] = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return subprocess.run(
        [executable, str(session_id), "/dest:console"],
        **kwargs,
    )


def ensure_windows_console_capture_session(
    *,
    status: Mapping[str, Any] | None = None,
    platform_name: str | None = None,
    environment: Mapping[str, str] | None = None,
    windows_server: bool | None = None,
    runner: Callable[[int], Any] | None = None,
    status_reader: Callable[[], Mapping[str, Any]] = windows_capture_session_status,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Move a Windows Server RDP session to its console for headless capture.

    The handoff is intentionally limited to the current process session. It
    never signs in, unlocks Windows, or captures another user's session.
    """

    policy = windows_headless_capture_policy(
        platform_name=platform_name,
        environment=environment,
        windows_server=windows_server,
    )
    current = dict(status or status_reader())
    state = str(current.get("state") or "unknown").strip().lower()
    protocol = str(current.get("protocol") or "unknown").strip().lower()
    session_id = current.get("sessionId")

    base = {
        "enabled": bool(policy["enabled"]),
        "attempted": False,
        "transitioned": False,
        "state": state,
        "protocol": protocol,
        "sessionId": session_id,
        "policy": policy,
    }
    if not policy["enabled"]:
        return {
            **base,
            "ok": False,
            "code": "headless_capture_disabled",
            "detail": "Persistent console capture is not enabled on this Windows installation.",
        }
    if state == "active" and protocol == "console":
        return {
            **base,
            "ok": True,
            "code": "console_ready",
            "detail": "The Windows console desktop is active.",
        }
    if protocol != "rdp" or state not in {"active", "disconnected"}:
        return {
            **base,
            "ok": False,
            "code": "session_not_transferable",
            "detail": f"The current Windows session cannot be handed to the console ({protocol}/{state}).",
        }
    try:
        resolved_session_id = int(session_id)
    except (TypeError, ValueError):
        return {
            **base,
            "ok": False,
            "code": "session_id_unavailable",
            "detail": "Windows did not report the current desktop session ID.",
        }

    execute = runner or _run_console_handoff
    try:
        completed = execute(resolved_session_id)
    except (OSError, subprocess.SubprocessError, TimeoutError) as exc:
        return {
            **base,
            "attempted": True,
            "ok": False,
            "code": "console_handoff_failed",
            "detail": f"Windows console handoff failed: {type(exc).__name__}: {exc}",
        }

    return_code = int(getattr(completed, "returncode", completed if isinstance(completed, int) else 1))
    if return_code != 0:
        detail = str(getattr(completed, "stderr", "") or getattr(completed, "stdout", "")).strip()
        return {
            **base,
            "attempted": True,
            "ok": False,
            "code": "console_handoff_failed",
            "detail": detail or f"Windows console handoff exited with code {return_code}.",
        }

    latest = current
    for _ in range(8):
        latest = dict(status_reader())
        if (
            str(latest.get("state") or "").strip().lower() == "active"
            and str(latest.get("protocol") or "").strip().lower() == "console"
        ):
            return {
                **base,
                "attempted": True,
                "transitioned": True,
                "ok": True,
                "code": "console_handoff_complete",
                "state": "active",
                "protocol": "console",
                "detail": "Windows moved the logged-in session to the console for persistent Fleet capture.",
            }
        sleep(0.25)

    return {
        **base,
        "attempted": True,
        "ok": False,
        "code": "console_handoff_unconfirmed",
        "state": str(latest.get("state") or state),
        "protocol": str(latest.get("protocol") or protocol),
        "detail": "Windows accepted the console handoff but did not expose an active console desktop in time.",
    }
