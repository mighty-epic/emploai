"""
Linux active windows listing for system_info.

Replaces the pywinauto-based window listing used on Windows (runtime_support/system_info.py).
Called via a flag switch in system_info.py when running on Linux.
"""

import subprocess
import shutil


def get_linux_active_windows() -> str:
    """Get list of active windows on Linux using wmctrl or xdotool.
    
    Returns a comma-separated string of window titles, matching the format
    used by the Windows implementation in runtime_support/system_info.py.
    """
    try:
        if shutil.which("wmctrl"):
            output = subprocess.check_output(
                ["wmctrl", "-l"], text=True, timeout=5
            )
            lines = output.strip().splitlines()
            titles = []
            seen = set()
            for line in lines:
                parts = line.split(None, 3)
                if len(parts) >= 4:
                    title = parts[3]
                    if title not in seen and len(title) > 2:
                        titles.append(title)
                        seen.add(title)
            if titles:
                return ", ".join(titles[:15])
            return "No windows found"

        if shutil.which("xdotool"):
            output = subprocess.check_output(
                ["xdotool", "search", "--name", ""],
                text=True, timeout=5
            )
            window_ids = output.strip().splitlines()[:15]
            titles = []
            seen = set()
            for wid in window_ids:
                try:
                    name = subprocess.check_output(
                        ["xdotool", "getwindowname", wid],
                        text=True, timeout=2
                    ).strip()
                    if name and name not in seen and len(name) > 2:
                        titles.append(name)
                        seen.add(name)
                except Exception:
                    pass
            if titles:
                return ", ".join(titles[:15])
            return "No windows found"

        return "Unavailable (install wmctrl or xdotool)"
    except Exception:
        return "Unavailable"
