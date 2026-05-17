import inspect
from pathlib import Path

from cli.chat_processor_core import build_tui_auto_system_prompt
from cli.tui_constants import UNIFIED_AGENT_PROMPT
from mobile_app.backend import runtime as app_runtime


def test_unified_prompt_blocks_browser_tools_for_user_chrome_without_extension():
    assert (
        "If the current task is about the user's existing Chrome tab, page, or logged-in browser session "
        "and that block says Real Chrome available now is NO, then browser_* tools are unavailable for that task."
    ) in UNIFIED_AGENT_PROMPT
    assert (
        "Selenium controls only the agent-owned browser instance. It never represents the user's current Chrome page "
        "unless the extension-backed real Chrome path is active."
    ) in UNIFIED_AGENT_PROMPT
    assert (
        "If the bridge is unavailable and the task does NOT depend on the user's current Chrome session, "
        "use Selenium-backed browser_* tools for the agent-owned browser until the bridge is restored or explicitly re-enabled."
    ) in UNIFIED_AGENT_PROMPT


def test_unified_prompt_adds_reflection_and_identity_safety_rules():
    assert "# PRE-FINAL REFLECTION" in UNIFIED_AGENT_PROMPT
    assert "Use `update_memory` only for durable reusable lessons" in UNIFIED_AGENT_PROMPT
    assert "Never store one-off page state, temporary coordinates, transient OCR output, or raw secrets." in UNIFIED_AGENT_PROMPT
    assert "## Identity-Sensitive Actions" in UNIFIED_AGENT_PROMPT
    assert (
        "Do NOT create accounts, send messages, make purchases, or submit other irreversible identity-sensitive actions "
        "unless the user explicitly asked for that outcome."
    ) in UNIFIED_AGENT_PROMPT


def test_kickstart_and_contract_remove_bad_defaults_and_add_browser_mode_rule():
    prelude = app_runtime._kickstart_prelude()
    user_kickstart = prelude[0]["content"]
    assistant_kickstart = prelude[1]["content"]
    contract = app_runtime._task_execution_contract()["content"]

    assert "Do not ask me for permission or credentials" not in user_kickstart
    assert "If you need to sign up for a service, open the browser and sign up." not in user_kickstart
    assert "do NOT use browser_* tools for that page" in user_kickstart
    assert "I will not pretend Selenium or browser_* tools control that page" in assistant_kickstart
    assert "Save only durable reusable lessons to memory." in contract


def test_telegram_chat_flow_keeps_same_browser_rule_in_startup_prompt():
    source = inspect.getsource(__import__("telegram_bot.telegram_chat_flow", fromlist=["run_chat_flow"]))

    assert "do NOT use browser_* tools for that page" in source
    assert "I will not pretend Selenium or browser_* tools control that page" in source
    assert "Save only durable reusable lessons to memory." in source


def test_tui_auto_prompt_resolves_runtime_blocks_and_system_info():
    class DummyProcessor:
        base_path = Path.cwd()

    prompt = build_tui_auto_system_prompt(DummyProcessor(), skills_index="\n\n## TEST SKILLS")

    assert prompt.startswith("# LIVE BROWSER RUNTIME STATUS")
    assert "# LIVE DESKTOP RUNTIME STATUS" in prompt
    assert "Real Chrome available now: NO" in prompt
    assert "{{SYSTEM_INFO}}" not in prompt
    assert "## TEST SKILLS" in prompt
