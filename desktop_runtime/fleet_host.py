from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from shared.atomic_io import atomic_write_text


FLEET_HOST_AUTOSTART_VALUE = "EmploAIFleetHost"
FLEET_HOST_REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
FLEET_HOST_DIRNAME = "fleet-host"
FLEET_HOST_LAUNCHER_FILENAME = "launch-fleet-host.vbs"
REMOTE_CONTROL_PID_FILENAME = "desktop_remote_control.pid.json"
FLEET_HOST_LOCK_FILENAME = "host.lock"


def _fleet_host_dir(home: Path) -> Path:
    return Path(home) / FLEET_HOST_DIRNAME


def fleet_host_launcher_path(home: Path) -> Path:
    return _fleet_host_dir(home) / FLEET_HOST_LAUNCHER_FILENAME


@contextmanager
def fleet_host_process_lock(home: Path) -> Iterator[bool]:
    lock_path = _fleet_host_dir(Path(home).resolve()) / FLEET_HOST_LOCK_FILENAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    acquired = False
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except (OSError, IOError):
            acquired = False
        yield acquired
    finally:
        if acquired:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except (OSError, IOError):
                pass
        handle.close()


def _backend_command(home: Path) -> list[str]:
    if getattr(sys, "frozen", False):
        executable = str(Path(sys.executable).resolve())
        return [executable, "run-remote-control-worker", "--home", str(Path(home).resolve())]

    executable = Path(sys.executable).resolve()
    if os.name == "nt":
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.exists():
            executable = pythonw
    return [
        str(executable),
        "-m",
        "desktop_runtime.backend",
        "run-remote-control-worker",
        "--home",
        str(Path(home).resolve()),
    ]


def _vbs_string(value: str) -> str:
    return f'"{str(value).replace(chr(34), chr(34) * 2)}"'


def _backend_working_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _launcher_text(command: Sequence[str], *, working_directory: Path | None = None) -> str:
    command_line = subprocess.list2cmdline([str(item) for item in command])
    cwd = Path(working_directory or _backend_working_directory()).resolve()
    return "\n".join(
        (
            "Option Explicit",
            "Dim shell",
            'Set shell = CreateObject("WScript.Shell")',
            f"shell.CurrentDirectory = {_vbs_string(str(cwd))}",
            f"shell.Run {_vbs_string(command_line)}, 0, False",
            "Set shell = Nothing",
            "",
        )
    )


def _registry_command(home: Path) -> str:
    launcher = fleet_host_launcher_path(home).resolve()
    system_root = Path(os.environ.get("SystemRoot") or r"C:\Windows")
    wscript = system_root / "System32" / "wscript.exe"
    return subprocess.list2cmdline(
        [str(wscript), "//B", "//Nologo", str(launcher)]
    )


def _read_autostart_value() -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, FLEET_HOST_REGISTRY_PATH) as key:
            value, _kind = winreg.QueryValueEx(key, FLEET_HOST_AUTOSTART_VALUE)
        return str(value or "").strip()
    except (FileNotFoundError, OSError):
        return ""


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _host_pid(home: Path) -> int:
    path = Path(home) / REMOTE_CONTROL_PID_FILENAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        pid = int(payload.get("pid") or 0) if isinstance(payload, dict) else 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 0
    return pid if _process_exists(pid) else 0


def fleet_host_autostart_status(home: Path) -> dict[str, Any]:
    home = Path(home).resolve()
    supported = os.name == "nt"
    launcher = fleet_host_launcher_path(home)
    desired = _registry_command(home) if supported else ""
    registered_value = _read_autostart_value() if supported else ""
    registered = bool(
        supported
        and launcher.exists()
        and registered_value
        and os.path.normcase(registered_value) == os.path.normcase(desired)
    )
    pid = _host_pid(home)
    if pid:
        state = "running"
        detail = "The paired-computer host is running independently of the Electron window."
    elif registered:
        state = "registered"
        detail = "The paired-computer host will start automatically at the next Windows sign-in."
    elif supported:
        state = "not_registered"
        detail = "The paired-computer host is not registered for Windows sign-in."
    else:
        state = "unsupported"
        detail = "Persistent Fleet host registration is currently implemented for Windows."
    return {
        "supported": supported,
        "registered": registered,
        "state": state,
        "detail": detail,
        "processId": pid or None,
        "launcherPath": str(launcher) if supported else None,
    }


def ensure_fleet_host_autostart(home: Path) -> dict[str, Any]:
    home = Path(home).resolve()
    if os.name != "nt":
        return fleet_host_autostart_status(home)

    launcher = fleet_host_launcher_path(home)
    launcher.parent.mkdir(parents=True, exist_ok=True)
    desired_launcher = _launcher_text(
        _backend_command(home),
        working_directory=_backend_working_directory(),
    )
    try:
        current_launcher = launcher.read_text(encoding="utf-8")
    except OSError:
        current_launcher = ""
    if current_launcher != desired_launcher:
        atomic_write_text(launcher, desired_launcher)

    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, FLEET_HOST_REGISTRY_PATH) as key:
        winreg.SetValueEx(
            key,
            FLEET_HOST_AUTOSTART_VALUE,
            0,
            winreg.REG_SZ,
            _registry_command(home),
        )
    return fleet_host_autostart_status(home)


def remove_fleet_host_autostart(home: Path) -> dict[str, Any]:
    home = Path(home).resolve()
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                FLEET_HOST_REGISTRY_PATH,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, FLEET_HOST_AUTOSTART_VALUE)
        except (FileNotFoundError, OSError):
            pass
    try:
        fleet_host_launcher_path(home).unlink(missing_ok=True)
    except OSError:
        pass
    return fleet_host_autostart_status(home)
