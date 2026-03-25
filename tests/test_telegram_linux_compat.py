import base64
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

from telegram_bot.linux import desktop_tools
from telegram_bot import linux


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
    for tool_name in (
        "describe_screen",
        "ocr_screen",
        "observe_desktop",
        "click",
        "type_text",
        "focus_window",
        "open_app",
    ):
        assert tool_name in handlers


def test_headed_linux_runtime_error_requires_non_root(monkeypatch):
    monkeypatch.setattr(linux, "LINUX_MODE", True)
    monkeypatch.setenv("HEADLESS", "false")
    monkeypatch.setattr(linux.os, "geteuid", lambda: 0, raising=False)

    error = linux.headed_linux_runtime_error()

    assert error is not None
    assert "cannot run as root" in error


def test_headed_linux_runtime_error_allows_non_root(monkeypatch):
    monkeypatch.setattr(linux, "LINUX_MODE", True)
    monkeypatch.setenv("HEADLESS", "false")
    monkeypatch.setattr(linux.os, "geteuid", lambda: 1000, raising=False)

    assert linux.headed_linux_runtime_error() is None


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

    assert launched["args"] == [
        "google-chrome",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
    ]
    assert result == "Launched: google-chrome --no-first-run --no-default-browser-check --disable-session-crashed-bubble"


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

    assert launched["args"] == [
        "google-chrome",
        "--incognito",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
    ]
    assert result == (
        "Launched: google-chrome --incognito --no-first-run --no-default-browser-check "
        "--disable-session-crashed-bubble"
    )


def test_linux_open_app_rejects_root_chrome_launch(monkeypatch):
    popen_called = False

    monkeypatch.setattr(desktop_tools, "_has_command", lambda cmd: cmd == "google-chrome")
    monkeypatch.setattr(desktop_tools.os, "geteuid", lambda: 0, raising=False)

    def fake_popen(*_args, **_kwargs):
        nonlocal popen_called
        popen_called = True
        raise AssertionError("chrome launch should have been blocked")

    monkeypatch.setattr(desktop_tools.subprocess, "Popen", fake_popen)

    result = desktop_tools._execute_open_app(None, {"name": "chrome"})

    assert "cannot be launched as root" in result
    assert popen_called is False


def test_linux_click_uses_xdotool_and_parses_coordinates(monkeypatch):
    calls = []

    monkeypatch.setattr(desktop_tools, "_has_command", lambda cmd: cmd == "xdotool")
    monkeypatch.setattr(desktop_tools, "_display_geometry", lambda: (1920, 1080))

    def fake_run(args, check=False, timeout=None, **_kwargs):
        calls.append((args, check, timeout))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(desktop_tools.subprocess, "run", fake_run)

    result = desktop_tools._execute_click(None, {"x": "1467, 25", "y": "25"})

    assert result["success"] is True
    assert result["backend"] == "xdotool"
    assert calls[0][0] == ["xdotool", "mousemove", "--sync", "1467", "25"]
    assert calls[1][0] == ["xdotool", "click", "1"]


def test_linux_ocr_screen_returns_structured_result(monkeypatch, tmp_path):
    screenshot_path = tmp_path / "ocr.png"
    screenshot_path.write_bytes(b"fake-image")

    monkeypatch.setattr(desktop_tools, "_has_command", lambda cmd: cmd == "scrot")
    monkeypatch.setattr(desktop_tools, "_capture_screenshot_path", lambda prefix="ocr": screenshot_path)
    monkeypatch.setattr(desktop_tools, "_load_image", lambda path: SimpleNamespace(width=640, height=480))
    monkeypatch.setattr(
        desktop_tools,
        "_extract_best_ocr",
        lambda image: {
            "elements": [{"text": "EMPLO SMOKE TARGET", "x": 500, "y": 300, "confidence": 92.5}],
            "unfiltered_text": "EMPLO SMOKE TARGET\nWAITING FOR CLICK",
            "plain_text": "EMPLO SMOKE TARGET\nWAITING FOR CLICK",
            "total_elements": 1,
            "variant": "contrast",
            "average_confidence": 92.5,
        },
    )

    result = desktop_tools._execute_ocr_screen(None, {})

    assert result["total_elements"] == 1
    assert result["elements"][0]["text"] == "EMPLO SMOKE TARGET"
    assert result["metadata"]["backend"] == "scrot"
    assert result["metadata"]["width"] == 640


def test_linux_describe_screen_returns_base64_image(monkeypatch, tmp_path):
    screenshot_path = tmp_path / "screen.png"
    screenshot_path.write_bytes(b"png-bytes")

    monkeypatch.setattr(desktop_tools, "_has_command", lambda cmd: cmd == "scrot")
    monkeypatch.setattr(desktop_tools, "_capture_screenshot_path", lambda prefix="screen": screenshot_path)
    monkeypatch.setattr(desktop_tools, "_load_image", lambda path: SimpleNamespace(width=800, height=600))

    result = desktop_tools._execute_describe_screen(None, {"question": "What is on screen?"})

    assert result["image_captured"] is True
    assert result["question"] == "What is on screen?"
    assert result["image_base64"] == base64.b64encode(b"png-bytes").decode("utf-8")
    assert result["metadata"]["backend"] == "scrot"


def test_vps_agent_service_supports_both_env_file_locations():
    service_path = Path(__file__).resolve().parents[1] / "deploy" / "vps" / "linux" / "emploai-agent.service"
    content = service_path.read_text(encoding="utf-8")

    assert "User=emploai" in content
    assert "EnvironmentFile=-/opt/emploai/.env" in content
    assert "EnvironmentFile=-/etc/emploai/agent.env" in content
