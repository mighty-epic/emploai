from __future__ import annotations

from pathlib import Path

from cli.agent_tools.executor import ToolExecutor
from shared.security_policy import LOW_PERMISSION, SecurityContext


def test_tool_executor_blocks_secret_path_reads(tmp_path: Path):
    executor = ToolExecutor(workspace_path=tmp_path)
    result = executor.execute("read_file", {"path": str(tmp_path / ".ssh" / "id_rsa")})

    assert result["error_type"] == "security_policy"
    assert result["risk"] == "secret_access"


def test_tool_executor_blocks_custom_browser_handler_before_execution(tmp_path: Path):
    executor = ToolExecutor(workspace_path=tmp_path)
    called = False

    def handler(_args):
        nonlocal called
        called = True
        return {"ok": True}

    executor.custom_tool_handlers["browser_navigate"] = handler
    result = executor.execute("browser_navigate", {"url": "https://xvideos.example"})

    assert called is False
    assert result["error_type"] == "security_policy"
    assert result["risk"] == "explicit_or_illegal_destination"


def test_tool_executor_low_permission_requires_confirmation_without_callback(tmp_path: Path):
    executor = ToolExecutor(workspace_path=tmp_path)
    executor.security_context_provider = lambda: SecurityContext(permission_mode=LOW_PERMISSION)

    result = executor.execute("browser_navigate", {"url": "https://example.com"})

    assert result["error_type"] == "security_confirmation_required"
    assert result["risk"] == "browser_control"


def test_tool_executor_low_permission_confirmation_can_allow(tmp_path: Path):
    approvals = []
    executor = ToolExecutor(workspace_path=tmp_path, confirm_callback=lambda prompt: approvals.append(prompt) or True)
    executor.security_context_provider = lambda: LOW_PERMISSION
    executor.custom_tool_handlers["browser_navigate"] = lambda _args: {"url": "https://example.com", "ok": True}

    result = executor.execute("browser_navigate", {"url": "https://example.com"})

    assert result["ok"] is True
    assert approvals
