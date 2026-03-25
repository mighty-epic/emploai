"""
Linux compatibility layer for the Telegram agent.

When running on Linux (auto-detected or via PLATFORM=linux env var),
this module provides replacement implementations for the Windows-centric
desktop path using Linux/X11 equivalents (`xdotool`, `wmctrl`, `scrot`).

Usage:
    Set PLATFORM=linux in .env (or auto-detected from platform.system()).
"""

import os
import platform

LINUX_MODE = os.getenv("PLATFORM", platform.system()).lower() == "linux"

_HEADLESS_FALSE_VALUES = {"false", "0", "no", "off"}


def headed_linux_runtime_error() -> str | None:
    """Return a deployment error when headed Linux is started as root.

    Headed Chrome and the extension bridge are expected to run inside a real
    X11 session owned by a non-root user. Running the Telegram bot as root in
    headed mode leads to Chrome launch failures and a broken bridge path.
    """
    if not LINUX_MODE:
        return None

    headless_env = os.getenv("HEADLESS", "").strip().lower()
    if headless_env not in _HEADLESS_FALSE_VALUES:
        return None

    geteuid = getattr(os, "geteuid", None)
    if not callable(geteuid) or geteuid() != 0:
        return None

    return (
        "Headed Linux mode cannot run as root. Run the X11 display session and "
        "telegram agent under the same non-root user (for example, 'emploai')."
    )
