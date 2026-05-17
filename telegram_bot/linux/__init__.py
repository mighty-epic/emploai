"""
Linux compatibility layer for the Telegram agent.

This module only enables Linux desktop overrides when the host OS is actually
Linux. Cross-OS environment overrides are intentionally ignored so a Windows
desktop runtime cannot accidentally activate Linux-only handlers, and a Linux
runtime cannot accidentally fall back to the Windows tool path.
"""

import logging
import os
import platform

logger = logging.getLogger(__name__)

HOST_PLATFORM = (platform.system() or "").strip().lower()
REQUESTED_PLATFORM = os.getenv("PLATFORM", "").strip().lower()
PLATFORM_OVERRIDE_IGNORED = bool(REQUESTED_PLATFORM and REQUESTED_PLATFORM != HOST_PLATFORM)

if PLATFORM_OVERRIDE_IGNORED:
    logger.warning(
        "Ignoring PLATFORM=%s on %s host; cross-OS platform overrides are disabled.",
        REQUESTED_PLATFORM,
        HOST_PLATFORM or "unknown",
    )

EFFECTIVE_PLATFORM = HOST_PLATFORM or REQUESTED_PLATFORM
LINUX_MODE = EFFECTIVE_PLATFORM == "linux"

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
