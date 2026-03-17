import os
import platform
import subprocess
import logging

logger = logging.getLogger(__name__)

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
                cpu_raw = subprocess.check_output("wmic cpu get Name /Value", shell=True, text=True)
                for line in cpu_raw.splitlines():
                    if "Name=" in line:
                        cpu_info = line.split("=", 1)[1].strip()
                        break
                
                # RAM Info
                ram_raw = subprocess.check_output("wmic computerSystem get totalPhysicalMemory /Value", shell=True, text=True)
                for line in ram_raw.splitlines():
                    if "TotalPhysicalMemory=" in line:
                        bytes_val = int(line.split("=", 1)[1].strip())
                        ram_info = f"{bytes_val // (1024**3)} GB"
                        break
                
                # Model Info
                model_raw = subprocess.check_output("wmic computerSystem get model /Value", shell=True, text=True)
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

        active_windows = "Unknown"
        if platform.system() == "Windows":
            try:
                from pywinauto import Desktop
                windows = Desktop(backend="uia").windows()
                window_titles = [w.window_text() for w in windows if w.window_text()]
                if window_titles:
                    # Filter out duplicates and small useless titles
                    seen = set()
                    filtered = []
                    for t in window_titles:
                        if t not in seen and len(t) > 2:
                            filtered.append(t)
                            seen.add(t)
                    active_windows = ", ".join(filtered[:15]) # Limit to top 15
            except Exception:
                active_windows = "Unavailable"
        elif platform.system() == "Linux":
            try:
                from telegram_bot.linux.system_info_ext import get_linux_active_windows
                active_windows = get_linux_active_windows()
            except ImportError:
                active_windows = "Unavailable (linux module not found)"

        return (
            f"OS: {os_info}\n"
            f"Hardware: {cpu_info} | {ram_info}{model_info}\n"
            f"Shell: {'PowerShell/CMD' if platform.system() == 'Windows' else 'Bash/Zsh'}\n"
            f"Active Windows: {active_windows}"
        )

    except Exception as e:
        logger.warning(f"Failed to gather system info: {e}")
        return f"OS: {platform.system()} | Hardware: Unknown"
