"""
Linux replacements for Windows-only desktop automation tools.

Replaces:
- pywinauto (observe_desktop, focus_window, minimize/maximize/close_window) -> xdotool/wmctrl
- Win+R open_app -> direct command execution / xdg-open

All functions follow the same signature as their Windows counterparts
in telegram_unified_agent.py: func(session, args: Dict) -> str/Dict

These are injected via get_auto_mode_tool_handlers() and
_build_unified_tool_executor() when LINUX_MODE is True.
"""

import subprocess
import shutil
import shlex
import time
from typing import Any, Dict


def _has_command(cmd: str) -> bool:
    """Check if a system command is available on PATH."""
    return shutil.which(cmd) is not None


_APP_ALIASES = {
    "browser": ["xdg-open"],
    "chrome": ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"],
    "google chrome": ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"],
    "chromium": ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable"],
    "terminal": ["x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal", "lxterminal", "xterm"],
}


def _resolve_launch_command(name: str) -> list[str] | None:
    """Resolve a user/model-provided app name to an executable command."""
    try:
        parts = shlex.split(name)
    except ValueError:
        parts = [name]

    if not parts:
        return None

    base = parts[0]
    if _has_command(base):
        return parts

    alias_keys = [name.strip().lower()]
    if base.lower() not in alias_keys:
        alias_keys.append(base.lower())

    for key in alias_keys:
        for candidate in _APP_ALIASES.get(key, []):
            if _has_command(candidate):
                return [candidate, *parts[1:]]

    return None


# ==========================================================================
# OBSERVE DESKTOP — replaces pywinauto Desktop().windows()
# ==========================================================================

def _execute_observe_desktop(session, args: Dict) -> str:
    """List open windows using wmctrl or xdotool."""
    try:
        if _has_command("wmctrl"):
            output = subprocess.check_output(
                ["wmctrl", "-l"], text=True, timeout=5
            )
            lines = output.strip().splitlines()
            titles = []
            for line in lines:
                # wmctrl -l format: <window_id> <desktop> <host> <title>
                parts = line.split(None, 3)
                if len(parts) >= 4:
                    titles.append(parts[3])
            if titles:
                return "Open Windows:\n" + "\n".join(titles[:20])
            return "No windows found."

        if _has_command("xdotool"):
            output = subprocess.check_output(
                ["xdotool", "search", "--name", ""],
                text=True, timeout=5
            )
            window_ids = output.strip().splitlines()[:20]
            titles = []
            for wid in window_ids:
                try:
                    name = subprocess.check_output(
                        ["xdotool", "getwindowname", wid],
                        text=True, timeout=2
                    ).strip()
                    if name and len(name) > 2:
                        titles.append(name)
                except Exception:
                    pass
            if titles:
                return "Open Windows:\n" + "\n".join(titles[:20])
            return "No windows found."

        return "Desktop observation unavailable (install wmctrl or xdotool)"
    except Exception as e:
        return f"Error listing windows: {str(e)}"


# ==========================================================================
# FOCUS WINDOW — replaces pywinauto set_focus()
# ==========================================================================

def _execute_focus_window(session, args: Dict) -> str:
    """Focus a window by title using wmctrl or xdotool."""
    title = args.get("title", "")
    if not title:
        return "Error: 'title' argument is required"

    try:
        if _has_command("wmctrl"):
            result = subprocess.run(
                ["wmctrl", "-a", title],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return f"Focused window matching: {title}"
            return f"Window not found: {title}"

        if _has_command("xdotool"):
            result = subprocess.run(
                ["xdotool", "search", "--name", title],
                capture_output=True, text=True, timeout=5
            )
            window_ids = result.stdout.strip().splitlines()
            if window_ids:
                subprocess.run(
                    ["xdotool", "windowactivate", window_ids[0]],
                    timeout=5
                )
                return f"Focused window: {title}"
            return f"Window not found: {title}"

        return "Window focus unavailable (install wmctrl or xdotool)"
    except Exception as e:
        return f"Error focusing window: {str(e)}"


# ==========================================================================
# MINIMIZE WINDOW — replaces pywinauto minimize()
# ==========================================================================

def _execute_minimize_window(session, args: Dict) -> str:
    """Minimize a window by title."""
    title = args.get("title", "")
    if not title:
        return "Error: 'title' argument is required"

    try:
        if _has_command("xdotool"):
            result = subprocess.run(
                ["xdotool", "search", "--name", title],
                capture_output=True, text=True, timeout=5
            )
            window_ids = result.stdout.strip().splitlines()
            if window_ids:
                subprocess.run(
                    ["xdotool", "windowminimize", window_ids[0]],
                    timeout=5
                )
                return f"Minimized window: {title}"
            return f"Window not found: {title}"

        return "Window minimize unavailable (install xdotool)"
    except Exception as e:
        return f"Error minimizing window: {str(e)}"


# ==========================================================================
# MAXIMIZE WINDOW — replaces pywinauto maximize()
# ==========================================================================

def _execute_maximize_window(session, args: Dict) -> str:
    """Maximize a window by title."""
    title = args.get("title", "")
    if not title:
        return "Error: 'title' argument is required"

    try:
        if _has_command("wmctrl"):
            # wmctrl can maximize by removing then adding maximized state
            subprocess.run(
                ["wmctrl", "-r", title, "-b", "add,maximized_vert,maximized_horz"],
                capture_output=True, text=True, timeout=5
            )
            return f"Maximized window: {title}"

        if _has_command("xdotool"):
            result = subprocess.run(
                ["xdotool", "search", "--name", title],
                capture_output=True, text=True, timeout=5
            )
            window_ids = result.stdout.strip().splitlines()
            if window_ids:
                # Use wmctrl-style maximize via key simulation
                subprocess.run(
                    ["xdotool", "windowactivate", window_ids[0]],
                    timeout=5
                )
                subprocess.run(
                    ["xdotool", "key", "super+Up"],
                    timeout=5
                )
                return f"Maximized window: {title}"
            return f"Window not found: {title}"

        return "Window maximize unavailable (install wmctrl or xdotool)"
    except Exception as e:
        return f"Error maximizing window: {str(e)}"


# ==========================================================================
# CLOSE WINDOW — replaces pywinauto close()
# ==========================================================================

def _execute_close_window(session, args: Dict) -> str:
    """Close a window by title."""
    title = args.get("title", "")
    if not title:
        return "Error: 'title' argument is required"

    try:
        if _has_command("wmctrl"):
            result = subprocess.run(
                ["wmctrl", "-c", title],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return f"Closed window: {title}"
            return f"Window not found: {title}"

        if _has_command("xdotool"):
            result = subprocess.run(
                ["xdotool", "search", "--name", title],
                capture_output=True, text=True, timeout=5
            )
            window_ids = result.stdout.strip().splitlines()
            if window_ids:
                subprocess.run(
                    ["xdotool", "windowclose", window_ids[0]],
                    timeout=5
                )
                return f"Closed window: {title}"
            return f"Window not found: {title}"

        return "Window close unavailable (install wmctrl or xdotool)"
    except Exception as e:
        return f"Error closing window: {str(e)}"


# ==========================================================================
# OPEN APP — replaces Win+R hotkey approach
# ==========================================================================

def _execute_open_app(session, args: Dict) -> str:
    """Open an application using direct command or xdg-open."""
    # Support both 'name' (from telegram_unified_agent) and 'app_name' (from SingleAgent)
    name = args.get("name") or args.get("app_name", "")
    if not name:
        return "Error: 'name' argument is required"

    try:
        launch_cmd = _resolve_launch_command(name)
        if launch_cmd:
            subprocess.Popen(
                launch_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(1)
            return f"Launched: {' '.join(launch_cmd)}"

        # Try xdg-open (for URLs, file types, etc.)
        if _has_command("xdg-open"):
            subprocess.Popen(
                ["xdg-open", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(1)
            return f"Attempted to open: {name}"

        return f"Cannot open '{name}' — command not found and xdg-open unavailable"
    except Exception as e:
        return f"Error opening app: {str(e)}"


# ==========================================================================
# EXPORT: All Linux desktop overrides
# ==========================================================================

def get_linux_desktop_overrides():
    """Return a dict of tool_name -> handler_function for Linux.

    Each function has the signature: func(session, args: Dict) -> str
    These override the Windows-only implementations.
    """
    return {
        "observe_desktop": _execute_observe_desktop,
        "focus_window": _execute_focus_window,
        "minimize_window": _execute_minimize_window,
        "maximize_window": _execute_maximize_window,
        "close_window": _execute_close_window,
        "open_app": _execute_open_app,
    }
