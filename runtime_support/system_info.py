import platform
import subprocess
import logging
from typing import Dict, List, Optional

from shared.subprocess_utils import hidden_subprocess_kwargs

logger = logging.getLogger(__name__)


def _foreground_window_title() -> str:
    if platform.system() != "Windows":
        return ""
    try:
        import win32gui  # type: ignore

        hwnd = win32gui.GetForegroundWindow()
        return str(win32gui.GetWindowText(hwnd) or "").strip()
    except Exception:
        return ""


def get_active_windows_snapshot(limit: int = 30) -> List[Dict[str, Optional[object]]]:
    """Return a lightweight live window snapshot for prompt/context use."""
    try:
        if platform.system() == "Windows":
            from pywinauto import Desktop

            foreground_title = _foreground_window_title()
            seen = set()
            snapshot: List[Dict[str, Optional[object]]] = []
            for win in Desktop(backend="uia").windows():
                title = str(win.window_text() or "").strip()
                if not title or len(title) <= 2 or title in seen:
                    continue
                seen.add(title)
                snapshot.append(
                    {
                        "title": title,
                        "is_active": title == foreground_title if foreground_title else None,
                    }
                )
                if len(snapshot) >= max(1, int(limit or 30)):
                    break
            return snapshot

        if platform.system() == "Linux":
            try:
                from telegram_bot.linux.system_info_ext import get_linux_active_windows

                titles = [
                    part.strip()
                    for part in str(get_linux_active_windows() or "").replace("\n", ",").split(",")
                    if part.strip()
                ]
                return [
                    {"title": title, "is_active": None}
                    for title in titles[: max(1, int(limit or 30))]
                ]
            except Exception:
                return []
    except Exception:
        logger.debug("Failed to gather active window snapshot", exc_info=True)
    return []


def format_active_windows_snapshot(limit: int = 30) -> str:
    windows = get_active_windows_snapshot(limit=limit)
    if not windows:
        return "Unavailable"
    lines = []
    for index, item in enumerate(windows, start=1):
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        active = item.get("is_active")
        state = "active" if active is True else "inactive" if active is False else "unknown"
        lines.append(f"{index}. [{state}] {title}")
    return "\n".join(lines) if lines else "Unavailable"


def get_system_info() -> str:
    """Gather system hardware and OS information for the agent prompt."""
    try:
        os_info = f"{platform.system()} {platform.release()} ({platform.version()})"
        
        cpu_info = "Unknown CPU"
        ram_info = "Unknown RAM"
        model_info = ""

        if platform.system() == "Windows":
            try:
                # CPU Info
                cpu_raw = subprocess.check_output(
                    "wmic cpu get Name /Value",
                    shell=True,
                    text=True,
                    **hidden_subprocess_kwargs(),
                )
                for line in cpu_raw.splitlines():
                    if "Name=" in line:
                        cpu_info = line.split("=", 1)[1].strip()
                        break
                
                # RAM Info
                ram_raw = subprocess.check_output(
                    "wmic computerSystem get totalPhysicalMemory /Value",
                    shell=True,
                    text=True,
                    **hidden_subprocess_kwargs(),
                )
                for line in ram_raw.splitlines():
                    if "TotalPhysicalMemory=" in line:
                        bytes_val = int(line.split("=", 1)[1].strip())
                        ram_info = f"{bytes_val // (1024**3)} GB"
                        break
                
                # Model Info
                model_raw = subprocess.check_output(
                    "wmic computerSystem get model /Value",
                    shell=True,
                    text=True,
                    **hidden_subprocess_kwargs(),
                )
                for line in model_raw.splitlines():
                    if "Model=" in line:
                        model_info = f" | Model: {line.split('=', 1)[1].strip()}"
                        break
            except Exception:
                pass
        
        elif platform.system() == "Linux":
            try:
                # CPU Info
                cpu_info = subprocess.check_output("grep 'model name' /proc/cpuinfo | head -n1 | cut -d: -f2", shell=True, text=True).strip()
                # RAM Info
                ram_info = subprocess.check_output("free -h | grep Mem | awk '{print $2}'", shell=True, text=True).strip()
            except Exception:
                pass
        
        elif platform.system() == "Darwin": # macOS
            try:
                cpu_info = subprocess.check_output("sysctl -n machdep.cpu.brand_string", shell=True, text=True).strip()
                ram_info = subprocess.check_output("sysctl -n hw.memsize", shell=True, text=True).strip()
                ram_info = f"{int(ram_info) // (1024**3)} GB"
            except Exception:
                pass

        active_windows = format_active_windows_snapshot(limit=15)

        return (
            f"OS: {os_info}\n"
            f"Hardware: {cpu_info} | {ram_info}{model_info}\n"
            f"Shell: {'PowerShell/CMD' if platform.system() == 'Windows' else 'Bash/Zsh'}\n"
            f"Active Windows: {active_windows}"
        )

    except Exception as e:
        logger.warning(f"Failed to gather system info: {e}")
        return f"OS: {platform.system()} | Hardware: Unknown"
