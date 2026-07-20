from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from shared import subprocess_utils


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_hidden_subprocess_policy_combines_flags_and_hides_startup_window(monkeypatch):
    class StartupInfo:
        def __init__(self):
            self.dwFlags = 0
            self.wShowWindow = None

    fake_subprocess = SimpleNamespace(
        STARTUPINFO=StartupInfo,
        STARTF_USESHOWWINDOW=0x00000001,
        SW_HIDE=0,
        CREATE_NO_WINDOW=0x08000000,
    )
    monkeypatch.setattr(subprocess_utils, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(subprocess_utils, "subprocess", fake_subprocess)

    kwargs = subprocess_utils.hidden_subprocess_kwargs(creationflags=0x00000200)

    assert kwargs["creationflags"] == 0x08000200
    assert kwargs["startupinfo"].dwFlags & fake_subprocess.STARTF_USESHOWWINDOW
    assert kwargs["startupinfo"].wShowWindow == fake_subprocess.SW_HIDE


def test_desktop_background_command_layers_apply_the_hidden_process_policy():
    sources = {
        "system_info": _read("runtime_support/system_info.py"),
        "edit_summary": _read("shared/edit_summary.py"),
        "firewall": _read("shared/windows_fleet_firewall.py"),
        "event_routes": _read("app_backend/app_server_routes_events.py"),
        "task_commands": _read("cli/task_session_commands.py"),
        "tool_executor": _read("cli/agent_tools/executor.py"),
        "skills": _read("skills/__init__.py"),
        "telegram_agent": _read("telegram_bot/telegram_unified_agent.py"),
        "telegram_shell": _read("telegram_bot/telegram_shell.py"),
        "eval_harness": _read("shared/agent_eval_harness.py"),
    }

    for name, source in sources.items():
        assert "hidden_subprocess_kwargs" in source, f"{name} bypasses the Windows hidden-process policy"

    assert "CREATE_NEW_CONSOLE" not in sources["telegram_shell"]
    assert "**hidden_subprocess_kwargs()" in sources["system_info"]
    assert "**hidden_subprocess_kwargs()" in sources["firewall"]
    assert "**hidden_subprocess_kwargs()" in sources["event_routes"]


def test_background_desktop_launch_suppresses_a_console_but_visible_tool_terminals_remain_opt_in():
    fleet_host = _read("app_backend/fleet_host_control.py")
    executor = _read("cli/agent_tools/executor.py")

    assert 'getattr(subprocess, "CREATE_NO_WINDOW", 0)' in fleet_host
    assert "if visible_terminal:" in executor
    assert 'getattr(subprocess, "CREATE_NEW_CONSOLE", 0)' in executor
    assert 'getattr(subprocess, "CREATE_NO_WINDOW", 0)' in executor
