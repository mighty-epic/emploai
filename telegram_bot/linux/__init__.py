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
