import importlib
import sys

from telegram_bot.linux import desktop_tools


def _reload_telegram_unified_agent():
    for module_name in (
        "telegram_bot.telegram_unified_agent",
        "telegram_bot.linux.desktop_tools",
        "telegram_bot.linux",
        "linux.desktop_tools",
        "linux",
    ):
        sys.modules.pop(module_name, None)
    return importlib.import_module("telegram_bot.telegram_unified_agent")


def test_telegram_unified_agent_imports_as_package(monkeypatch):
    monkeypatch.delenv("PLATFORM", raising=False)

    module = _reload_telegram_unified_agent()

    assert callable(module.get_auto_mode_tool_handlers)
    assert callable(module.create_unified_agent_for_task)


def test_platform_override_enables_linux_desktop_handlers(monkeypatch):
    monkeypatch.setenv("PLATFORM", "linux")

    module = _reload_telegram_unified_agent()
    handlers = module.get_auto_mode_tool_handlers(session=None)

    assert module.LINUX_MODE is True
    for tool_name in ("observe_desktop", "focus_window", "open_app"):
        assert tool_name in handlers


def test_linux_open_app_maps_common_chrome_alias(monkeypatch):
    launched = {}

    monkeypatch.setattr(desktop_tools, "_has_command", lambda cmd: cmd == "google-chrome")
    monkeypatch.setattr(
        desktop_tools.subprocess,
        "Popen",
        lambda args, stdout=None, stderr=None: launched.setdefault("args", args),
    )
    monkeypatch.setattr(desktop_tools.time, "sleep", lambda *_args, **_kwargs: None)

    result = desktop_tools._execute_open_app(None, {"name": "chrome"})

    assert launched["args"] == ["google-chrome"]
    assert result == "Launched: google-chrome"


def test_linux_open_app_splits_command_arguments(monkeypatch):
    launched = {}

    monkeypatch.setattr(desktop_tools, "_has_command", lambda cmd: cmd == "google-chrome")
    monkeypatch.setattr(
        desktop_tools.subprocess,
        "Popen",
        lambda args, stdout=None, stderr=None: launched.setdefault("args", args),
    )
    monkeypatch.setattr(desktop_tools.time, "sleep", lambda *_args, **_kwargs: None)

    result = desktop_tools._execute_open_app(None, {"name": "google-chrome --incognito"})

    assert launched["args"] == ["google-chrome", "--incognito"]
    assert result == "Launched: google-chrome --incognito"
