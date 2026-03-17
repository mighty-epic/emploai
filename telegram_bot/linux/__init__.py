"""
Linux compatibility layer for the Telegram agent.

When running on Linux (auto-detected or via PLATFORM=linux env var),
this module provides replacement implementations for Windows-only tools
(pywinauto, Win+R hotkey, etc.) using Linux equivalents (xdotool, wmctrl).

Cross-platform tools (pyautogui, mss, pytesseract, pyperclip) work as-is
on Linux with Xvfb and appropriate system packages installed.

Usage:
    Set PLATFORM=linux in .env (or auto-detected from platform.system()).
"""

import os
import platform

LINUX_MODE = os.getenv("PLATFORM", platform.system()).lower() == "linux"
