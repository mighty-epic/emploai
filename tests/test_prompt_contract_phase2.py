import inspect
import json
from pathlib import Path
from types import SimpleNamespace

from cli.chat_processor_core import build_tui_auto_system_prompt
from cli.tui_constants import UNIFIED_AGENT_PROMPT
from app_backend import runtime as app_runtime
from shared import channel_runtime
from shared.task_board import TASK_BOARD_INTERNAL_TOOL_NAME
from shared.task_intent import request_requires_tool_evidence
from shared.tool_packs import PACK_BROWSER_ISOLATED, PACK_INTERACTIVE_DESKTOP, PACK_WORKSPACE_READ
from telegram_bot.telegram_unified_agent import build_unified_system_prompt


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


def test_current_task_contract_is_compact_and_restates_observable_goal():
    session = SimpleNamespace(
        last_user_message="Send 'running late' to Alex on WhatsApp",
        enabled_tool_packs=[PACK_INTERACTIVE_DESKTOP],
        current_turn_allowed_tool_names={"run_command", "describe_screen", "type_text"},
    )

    message = channel_runtime._task_contract_context_message(session)

    assert message is not None
    content = message["content"]
    assert "CURRENT TASK CONTRACT" in content
    assert "User request: Send 'running late' to Alex on WhatsApp" in content
    assert "observable end state is true and verified" in content
    assert "prefer open_file or a direct OS/app file-open command" in content
    assert "switch method family/tool surface" in content
    assert "Match proof to the surface" in content
    assert "browser tools prove browser/DOM state" in content
    assert "Match command syntax to the platform and shell" in content
    assert "Do not terminate broad process names as a convenience" in content
    assert "WhatsApp, Gmail, Microsoft apps" in content
    assert "personal-account or communication context by itself is not a blocker" in content


def test_planner_retry_reinjects_user_request_and_method_switch(monkeypatch):
    def fake_planner_completion(_session, *, prompt_payload):
        assert prompt_payload["original_user_request"] == "Open the saved stock research file visibly"
        return json.dumps(
            {
                "action": "retry",
                "reason": "file was created but not visibly opened",
                "failed_obligation": "visible file open",
                "evidence_gap": "no window title or visible content for the file",
                "retry_instruction": "Open the exact file and verify the window title.",
                "must_use_tool": True,
            }
        )

    monkeypatch.setattr(channel_runtime, "_planner_final_completion", fake_planner_completion)

    verdict = channel_runtime._planner_final_verdict(
        SimpleNamespace(),
        {
            "user_request": "Open the saved stock research file visibly",
            "assistant_final": "Done.",
            "tool_trace": [],
        },
    )

    instruction = verdict["continuation_instruction"]
    assert verdict["action"] == "continue"
    assert verdict["must_use_tool"] is True
    assert "Original user request still active: Open the saved stock research file visibly" in instruction
    assert "visible file open" in instruction
    assert "Do not repeat the same failed method loop" in instruction
    assert "switch method family/tool surface" in instruction


def test_planner_verifier_skips_answer_only_questions(monkeypatch):
    def fake_planner_completion(_session, *, prompt_payload):
        raise AssertionError("answer-only questions should not call the planner verifier")

    monkeypatch.setattr(channel_runtime, "_planner_final_completion", fake_planner_completion)

    verdict = channel_runtime._planner_final_verdict(
        SimpleNamespace(chat_history=[]),
        {
            "user_request": "Can you explain how sleep mode works in one sentence?",
            "assistant_final": "Sleep mode closes the desktop UI while the backend remains available through Telegram.",
            "tool_trace": [],
        },
    )

    assert verdict["action"] == "allow"
    assert verdict["must_use_tool"] is False
    assert verdict["reason"] == "planner_skipped_answer_only_turn"


def test_tool_evidence_intent_is_narrower_than_task_like():
    assert request_requires_tool_evidence("Can you explain how sleep mode works in one sentence?") is False
    assert request_requires_tool_evidence("What is two plus two?") is False
    assert request_requires_tool_evidence("How do we fix the desktop app behavior without overfitting?") is False
    assert request_requires_tool_evidence("Can you explain how to open Chrome from PowerShell?") is False
    assert request_requires_tool_evidence("What do you see on the screen now?") is True
    assert request_requires_tool_evidence("What's in this current directory") is True
    assert request_requires_tool_evidence("Open Spotify and play my liked songs") is True
    assert request_requires_tool_evidence("Build and run a small Electron calculator app") is True


def test_planner_verifier_uses_preserved_original_task_on_continue_turn(monkeypatch):
    captured_payloads = []

    def fake_planner_completion(_session, *, prompt_payload):
        captured_payloads.append(prompt_payload)
        return json.dumps({"action": "allow", "reason": "verified"})

    monkeypatch.setattr(channel_runtime, "_planner_final_completion", fake_planner_completion)

    session = SimpleNamespace(
        chat_history=[
            {"role": "user", "content": "Build and run a small Electron calculator app"},
            {"role": "assistant", "content": "Working on it."},
            {"role": "user", "content": "continue"},
        ],
    )

    verdict = channel_runtime._planner_final_verdict(
        session,
        {
            "user_request": "continue",
            "assistant_final": "Done and verified.",
            "tool_trace": [{"tool": "run_command", "output": {"exit_code": 0, "stdout": "started"}}],
        },
    )

    assert verdict["action"] == "allow"
    assert captured_payloads[-1]["original_user_request"] == "Build and run a small Electron calculator app"


def test_planner_verifier_forces_retry_for_unverified_coding_runtime_final(monkeypatch):
    def fake_planner_completion(_session, *, prompt_payload):
        assert prompt_payload["original_user_request"] == "Build and run a small Electron calculator app"
        return json.dumps({"action": "allow", "reason": "seems_fine"})

    monkeypatch.setattr(channel_runtime, "_planner_final_completion", fake_planner_completion)

    verdict = channel_runtime._planner_final_verdict(
        SimpleNamespace(chat_history=[]),
        {
            "user_request": "Build and run a small Electron calculator app",
            "assistant_final": "Node is missing. If you want, I can keep going.",
            "tool_trace": [
                {
                    "tool": "run_command",
                    "output": {
                        "exit_code": 1,
                        "stderr": "'node' is not recognized as an internal or external command",
                    },
                }
            ],
        },
    )

    assert verdict["action"] == "continue"
    assert verdict["must_use_tool"] is True
    assert "coding_task_premature_final" in verdict["reason"]
    assert "Do not ask whether to continue" in verdict["continuation_instruction"]


def test_planner_verifier_prompt_distinguishes_latest_state_and_evidence_source():
    prompt = channel_runtime._planner_verifier_system_prompt()

    assert "Judge the latest verified state" in prompt
    assert "earlier failed tool call" in prompt
    assert "Match evidence source to obligation" in prompt
    assert "browser_snapshot, browser_read_text, browser_wait_for, and browser_screenshot prove browser context only" in prompt
    assert "native desktop apps, local file-open state, active windows" in prompt
    assert "Broad process cleanup by app/process name is not valid progress" in prompt


def test_kickstart_and_contract_are_pack_aware_for_read_only_chat():
    prelude = app_runtime._kickstart_prelude([PACK_WORKSPACE_READ])
    user_kickstart = prelude[0]["content"]
    assistant_kickstart = prelude[1]["content"]
    session = SimpleNamespace(task_history=[], active_task_id=None, workspace=Path.cwd())
    contract = app_runtime._task_execution_contract(session, [PACK_WORKSPACE_READ])["content"]

    assert "Do not ask me for permission or credentials" not in user_kickstart
    assert "If you need to sign up for a service, open the browser and sign up." not in user_kickstart
    assert "browser_*" not in user_kickstart
    assert "describe_screen" not in user_kickstart
    assert "Missing interpreters, missing PATH entries, missing packages, missing CLIs" in user_kickstart
    assert "Prefer native file tools over shell-generated files" in user_kickstart
    assert "On Windows, prefer py before python3" in user_kickstart
    assert "Prefer reversible, task-scoped repairs before broader machine changes." in user_kickstart
    assert "I will not claim access to disabled packs or tools." in assistant_kickstart
    assert "I will treat missing tools, PATH problems, safe local dependency issues, and other safely repairable runtime problems as things to solve" in assistant_kickstart
    assert "prefer local, reversible repairs over broader machine changes" in assistant_kickstart
    assert "browser_wait_for" not in contract
    assert "OCR" not in contract
    assert TASK_BOARD_INTERNAL_TOOL_NAME not in contract
    assert "task-board-only tools are unavailable" not in contract
    assert "managed task board is runtime-owned" not in contract.lower()
    assert "Save only durable reusable lessons to memory." in contract
    assert "Prefer reversible, task-scoped repairs before broader machine changes." in contract
    assert "Avoid global installs, default-app changes, registry or PATH edits" in contract
    assert "prefer py before python3" in contract.lower()
    assert "stop searching once the requested facts are verified" in contract.lower()
    assert "Choose tools by evidence source" in contract
    assert f"Current workspace/root directory: {Path.cwd()}" in contract
    assert "native desktop file pickers usually do not" in contract
    assert "shell='powershell' for Get-Location or Resolve-Path" in contract
    assert "Match command syntax to the actual platform" in contract
    assert "bind it to 127.0.0.1 or localhost" in contract
    assert "do not final-answer while a safe next route exists" in contract
    assert "permission-sensitive identity confirmation" in contract
    assert "completion requires the exact saved artifact to be visibly open" in contract
    assert "Preserve user-provided identifiers exactly" in contract
    assert "Report the actual completion state" in contract


def test_kickstart_and_contract_add_browser_and_desktop_fallback_only_when_enabled():
    prelude = app_runtime._kickstart_prelude([PACK_BROWSER_ISOLATED, PACK_INTERACTIVE_DESKTOP])
    user_kickstart = prelude[0]["content"]
    assistant_kickstart = prelude[1]["content"]
    session = SimpleNamespace(
        task_history=[{"task_id": "task-1", "state": "active", "display_mode": "active", "status": "active"}],
        active_task_id="task-1",
        workspace=Path.cwd(),
    )
    contract = app_runtime._task_execution_contract(session, [PACK_BROWSER_ISOLATED, PACK_INTERACTIVE_DESKTOP])["content"]

    assert "Do not assume a visually presented action succeeded." in user_kickstart
    assert "Do not chain clicks, typing, or other interactive GUI actions" in user_kickstart
    assert "The user may move focus, click, or type while you work." in user_kickstart
    assert "Use browser DOM tools only when they are actually available" in user_kickstart
    assert "switch to live observation and atomic desktop actions" in user_kickstart
    assert "For browser-native state, prefer browser tools first" in user_kickstart
    assert "prefer browser_read_text or browser_wait_for(text_contains=...)" in user_kickstart
    assert "When you call describe_screen or browser_screenshot for visual interpretation, ask a precise question" in user_kickstart
    assert "Do not use describe_screen or ocr_screen to reason about a headless isolated browser page." in user_kickstart
    assert "Treat app launches as attempts, not proof." in user_kickstart
    assert "Do not final-answer while the task is incomplete and a safe next route exists" in user_kickstart
    assert "discover alternatives from current state and available surfaces" in user_kickstart
    assert "If one browser-native method is inconclusive, try another browser-native method" in user_kickstart
    assert "Browser evidence proves browser state, not native desktop app state" in user_kickstart
    assert "browser_screenshot as visual proof" in user_kickstart
    assert "Prefer keyboard-first desktop interaction" in user_kickstart
    assert "make sure the intended target window, dialog, or control is focused" in user_kickstart
    assert "there is no hidden app-specific control layer" in user_kickstart
    assert "For desktop-visible opens and window changes, prefer describe_screen" in user_kickstart
    assert "blank window, wrong document, wrong tab, wrong chat, or generic host UI is not success" in user_kickstart
    assert "use pull_skill before you improvise a long workflow" in user_kickstart
    assert "I will switch to live observation and atomic desktop actions" in assistant_kickstart
    assert "I will treat app launches as attempts" in assistant_kickstart
    assert "I will not assume a visual action succeeded" in assistant_kickstart
    assert "If the user changes the screen state while I work" in assistant_kickstart
    assert "I will confirm the intended target window, dialog, or control is focused" in assistant_kickstart
    assert "I will discover safe alternate routes and take them" in assistant_kickstart
    assert "I will avoid closing the user's windows, killing unrelated processes, or making broad machine changes" in assistant_kickstart
    assert TASK_BOARD_INTERNAL_TOOL_NAME in contract
    assert "browser_wait_for" in contract
    assert "browser_read_text" in contract
    assert "If the task is naturally browser-first" in contract
    assert "browser_screenshot as proof/artifact" in contract
    assert "browser_screenshot as visual proof" in contract
    assert "When you call browser_screenshot for visual interpretation, ask a precise question" in contract
    assert "browser_read_text is the primary browser-native tool" in contract
    assert "browser_wait_for is for confirming that expected text" in contract
    assert "Browser-native evidence proves the browser context only" in contract
    assert "headless, desktop vision/OCR cannot inspect that page" in contract
    assert "Do not chain clicks, typing, hotkeys, or other interactive GUI actions" in contract
    assert "App launches are attempts until verified" in contract
    assert "Do not ask the user to try an obvious next route; try it yourself." in contract
    assert "Windows error dialog" in contract
    assert "The user may move focus, click, or type while you work." in contract
    assert "describe_screen is the primary desktop verification and layout-understanding tool" in contract
    assert "Prefer keyboard-first desktop interaction" in contract
    assert "if focus is uncertain or another window is active, re-observe and focus the correct target before sending keys" in contract
    assert "trusted web equivalents" in contract
    assert "blank window, wrong document, wrong tab, wrong chat, or generic host UI is not success" in contract
    assert "Avoid global installs, default-app changes, registry or PATH edits" in contract
    assert "Save durable account facts, usernames, emails, profile choices, login requirements" in contract
    assert "use pull_skill before you improvise a long workflow" in contract
    assert "Do not claim an exact visible value unless a tool path actually returned or verified that exact value." in contract
    assert "exact-text OCR" in contract
    assert "do not switch to screenshots, OCR, or desktop tools just to restate it" in contract
    assert "Safety means careful completion, not avoidance." in contract
    assert "keep one controlled lifecycle" in contract
    assert "'I can try X' is not a valid final answer" in contract
    assert "Prefer open_file with the exact resolved path" in contract
    assert "not a blank app launch" in contract
    assert f"Current workspace/root directory: {Path.cwd()}" in contract
    assert "do not guess Downloads, Public, or another user directory." in contract
    assert "bind it to 127.0.0.1 or localhost" in contract
    assert "Do not terminate broad process names to clean up a task" in contract
    assert "Do not silently substitute a similar identifier." in contract


def test_unified_prompt_includes_desktop_verification_and_context_rules():
    browser_context = SimpleNamespace(
        backend="selenium",
        task_id=1,
        healthy=True,
        requires_real_chrome=False,
        primary_tab_id=None,
        primary_window_id=None,
        owned_tab_ids=[],
        last_url=None,
        last_title=None,
        last_snapshot_hash=None,
    )
    session = SimpleNamespace(
        enabled_tool_packs=[PACK_BROWSER_ISOLATED, PACK_INTERACTIVE_DESKTOP],
        system_info="OS: Windows\nActive Windows: Codex",
        context_loader=None,
        live_config={"browser.use_extension": False},
        session_context=None,
        memory_manager=None,
        workspace=Path.cwd(),
        current_model="gpt-5.4-mini",
        current_variant="standard",
        _active_tool_packs_for_current_run=[],
        get_browser_task_context=lambda: browser_context,
        extension_tool=None,
        refined_agent=None,
        browser_tool=None,
    )

    prompt = build_unified_system_prompt(session)

    assert "App launches do not prove an app opened" in prompt
    assert "Do not read MEMORY.md just to start a task." in prompt
    assert "Native desktop apps, including third-party apps, require interactive desktop tools" in prompt
    assert "Do not assume a visually presented action succeeded." in prompt
    assert "Do not chain clicks, typing, hotkeys, or other interactive GUI actions" in prompt
    assert "# CURRENT DATE/TIME" in prompt
    assert "Local date/time now:" in prompt
    assert "# WORKSPACE/PATH RUNTIME STATUS" in prompt
    assert f"Current workspace/root directory: {Path.cwd()}" in prompt
    assert "Native desktop file pickers and app Open/Save dialogs do not automatically start in this workspace." in prompt
    assert "Do not invent paths under Downloads, Desktop, Documents, or `C:\\Users\\Public`" in prompt
    assert "The user may move focus, click, or type while you work." in prompt
    assert "Any GUI without a dedicated tool path should be treated as a vision-and-interaction task." in prompt
    assert "For desktop-visible opens and window changes, prefer describe_screen" in prompt
    assert "Do not final-answer while the task is incomplete and a safe next route exists" in prompt
    assert "discover alternatives from current state and available surfaces" in prompt
    assert "blank window, wrong document, wrong tab, wrong chat, or generic host UI is not success" in prompt
    assert "When you call describe_screen or browser_screenshot for visual interpretation, ask a precise question" in prompt
    assert "Prefer keyboard-first desktop interaction when a reliable shortcut" in prompt
    assert "make sure the intended target window, dialog, or control is focused" in prompt
    assert "browser_read_text is the primary browser-native tool" in prompt
    assert "browser_screenshot as visual proof" in prompt
    assert "Browser-native evidence proves browser state only" in prompt
    assert "Before final-answering with partial, failed, or blocked status" in prompt
    assert "use `pull_skill` before improvising a long workflow" in prompt


def test_telegram_chat_flow_filters_tools_and_enforces_allowed_names():
    source = inspect.getsource(__import__("telegram_bot.telegram_chat_flow", fromlist=["run_chat_flow"]))

    assert "build_pack_aware_kickstart_prelude" in source
    assert "build_pack_aware_task_execution_contract" in source
    assert "filter_openai_tools_by_enabled_packs" in source
    assert "session.current_turn_allowed_tool_names = tools_for_enabled_packs(active_tool_packs)" in source


def test_unified_system_prompt_only_lists_enabled_tool_packs():
    session = SimpleNamespace(
        enabled_tool_packs=[PACK_WORKSPACE_READ],
        system_info="Active Windows: EmploAI App",
        context_loader=None,
        live_config={},
        session_context=None,
        memory_manager=None,
        workspace=Path.cwd(),
        current_model="gpt-5.4-mini",
        current_variant="standard",
        _active_tool_packs_for_current_run=[],
    )

    prompt = build_unified_system_prompt(session)

    assert "## Enabled Pack: Workspace Read" in prompt
    assert "## Enabled Pack: Interactive Desktop" not in prompt
    assert "## Enabled Pack: Workspace Write" not in prompt
    assert "## Enabled Pack: Web Research" not in prompt
    assert "# MANAGED TASK BOARD RUNTIME" not in prompt


def test_unified_system_prompt_appends_local_custom_instructions_after_core_prompt():
    session = SimpleNamespace(
        enabled_tool_packs=[PACK_WORKSPACE_READ],
        system_info="Active Windows: EmploAI App",
        context_loader=None,
        live_config={"agent.custom_system_prompt_append": "Prefer concise answers for this account."},
        session_context=None,
        memory_manager=None,
        workspace=Path.cwd(),
        current_model="gpt-5.4-mini",
        current_variant="standard",
        _active_tool_packs_for_current_run=[],
    )

    prompt = build_unified_system_prompt(session)

    assert "## CORE CONTRACT" in prompt
    assert "## LOCAL CUSTOM INSTRUCTIONS - APPEND ONLY (managed local section)\nPrefer concise answers for this account." in prompt
    assert prompt.index("## CORE CONTRACT") < prompt.index("## LOCAL CUSTOM INSTRUCTIONS")


def test_unified_system_prompt_includes_task_board_only_when_active():
    session = SimpleNamespace(
        enabled_tool_packs=[PACK_WORKSPACE_READ],
        system_info="Active Windows: EmploAI App",
        context_loader=None,
        live_config={},
        session_context=None,
        memory_manager=None,
        workspace=Path.cwd(),
        current_model="gpt-5.4-mini",
        current_variant="standard",
        _active_tool_packs_for_current_run=[],
        task_history=[{"task_id": "task-1", "state": "active", "display_mode": "active", "status": "active", "main_goal": "Inspect folder"}],
        active_task_id="task-1",
    )

    prompt = build_unified_system_prompt(session)

    assert "# ACTIVE MANAGED TASK BOARD" in prompt


def test_run_app_chat_turn_excludes_workspace_tools_when_workspace_read_is_disabled(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_begin_chat_turn(*_args, **_kwargs):
        return SimpleNamespace(
            busy=False,
            task_id=1,
            session_id="sess-pack-off",
            context_compressed=False,
            context_compaction=None,
        )

    async def fake_run_reserved_chat_turn(session, _reservation, **_kwargs):
        captured["allowed_names"] = set(session.current_turn_allowed_tool_names or set())
        captured["allowed_definition_names"] = [
            str(tool.get("name") or tool.get("function", {}).get("name") or "")
            for tool in list(session.current_turn_allowed_tool_definitions or [])
        ]
        extra_tools_builder = _kwargs.get("extra_tools_builder")
        extra_tools = extra_tools_builder(session) if extra_tools_builder else []
        captured["extra_tool_names"] = [
            str(tool.get("function", {}).get("name") or tool.get("name") or "")
            for tool in list(extra_tools or [])
        ]
        captured["system_messages"] = list(_kwargs.get("system_messages") or [])
        return SimpleNamespace(
            ok=True,
            busy=False,
            session_id="sess-pack-off",
            assistant_text="Done",
            raw_response="Done",
            duration_seconds=0.0,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            context_compressed=False,
            context_compaction=None,
        )

    monkeypatch.setattr(app_runtime, "begin_chat_turn", fake_begin_chat_turn)
    monkeypatch.setattr(app_runtime, "run_reserved_chat_turn", fake_run_reserved_chat_turn)

    runtime = SimpleNamespace(
        enabled_tool_packs=[PACK_INTERACTIVE_DESKTOP],
        _active_tool_packs_for_current_run=[],
        chat_history=[],
        current_model="gpt-5.4-mini",
        current_variant="standard",
    )

    app_runtime_async_result = app_runtime.run_app_chat_turn(
        runtime,
        user_message="ok can you tell me whats in this workspace ?",
        source_format="app_text",
        interrupt_policy="none",
    )

    import asyncio

    result = asyncio.run(app_runtime_async_result)

    assert result["ok"] is True
    allowed_names = captured["allowed_names"]
    assert isinstance(allowed_names, set)
    assert "describe_screen" in allowed_names
    assert "read_file" not in allowed_names
    assert "list_dir" not in allowed_names
    assert "find_files" not in allowed_names
    assert "grep_search" not in allowed_names
    assert "write_file" not in allowed_names
    assert "run_command" not in allowed_names

    definition_names = captured["allowed_definition_names"]
    assert isinstance(definition_names, list)
    assert "read_file" not in definition_names
    assert "list_dir" not in definition_names
    assert "find_files" not in definition_names
    assert "write_file" not in definition_names
    assert "run_command" not in definition_names
    extra_tool_names = captured["extra_tool_names"]
    assert isinstance(extra_tool_names, list)
    assert TASK_BOARD_INTERNAL_TOOL_NAME not in extra_tool_names
    system_messages = captured["system_messages"]
    assert isinstance(system_messages, list)
    assert all(TASK_BOARD_INTERNAL_TOOL_NAME not in str(message.get("content", "")) for message in system_messages)
    assert all("task-board-only tools are unavailable" not in str(message.get("content", "")) for message in system_messages)


def test_run_app_chat_turn_includes_workspace_read_tools_when_enabled(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_begin_chat_turn(*_args, **_kwargs):
        return SimpleNamespace(
            busy=False,
            task_id=1,
            session_id="sess-pack-on",
            context_compressed=False,
            context_compaction=None,
        )

    async def fake_run_reserved_chat_turn(session, _reservation, **_kwargs):
        captured["allowed_names"] = set(session.current_turn_allowed_tool_names or set())
        captured["allowed_definition_names"] = [
            str(tool.get("name") or tool.get("function", {}).get("name") or "")
            for tool in list(session.current_turn_allowed_tool_definitions or [])
        ]
        return SimpleNamespace(
            ok=True,
            busy=False,
            session_id="sess-pack-on",
            assistant_text="Done",
            raw_response="Done",
            duration_seconds=0.0,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            context_compressed=False,
            context_compaction=None,
        )

    monkeypatch.setattr(app_runtime, "begin_chat_turn", fake_begin_chat_turn)
    monkeypatch.setattr(app_runtime, "run_reserved_chat_turn", fake_run_reserved_chat_turn)

    runtime = SimpleNamespace(
        enabled_tool_packs=[PACK_WORKSPACE_READ],
        _active_tool_packs_for_current_run=[],
        chat_history=[],
        current_model="gpt-5.4-mini",
        current_variant="standard",
    )

    app_runtime_async_result = app_runtime.run_app_chat_turn(
        runtime,
        user_message="ok can you tell me whats in this workspace ?",
        source_format="app_text",
        interrupt_policy="none",
    )

    import asyncio

    result = asyncio.run(app_runtime_async_result)

    assert result["ok"] is True
    allowed_names = captured["allowed_names"]
    assert isinstance(allowed_names, set)
    assert "read_file" in allowed_names
    assert "list_dir" in allowed_names
    assert "find_files" in allowed_names
    assert "grep_search" in allowed_names
    assert "write_file" not in allowed_names
    assert "run_command" not in allowed_names

    definition_names = captured["allowed_definition_names"]
    assert isinstance(definition_names, list)
    assert "read_file" in definition_names
    assert "list_dir" in definition_names
    assert "find_files" in definition_names
    assert "grep_search" in definition_names
    assert "write_file" not in definition_names
    assert "run_command" not in definition_names


def test_run_app_chat_turn_keeps_enabled_tools_on_non_task_like_turn(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_begin_chat_turn(*_args, **_kwargs):
        return SimpleNamespace(
            busy=False,
            task_id=1,
            session_id="sess-convo-tools",
            context_compressed=False,
            context_compaction=None,
        )

    async def fake_run_reserved_chat_turn(session, _reservation, **_kwargs):
        captured["allowed_names"] = set(session.current_turn_allowed_tool_names or set())
        captured["allowed_definition_names"] = [
            str(tool.get("name") or tool.get("function", {}).get("name") or "")
            for tool in list(session.current_turn_allowed_tool_definitions or [])
        ]
        captured["system_messages"] = list(_kwargs.get("system_messages") or [])
        return SimpleNamespace(
            ok=True,
            busy=False,
            session_id="sess-convo-tools",
            assistant_text="Done",
            raw_response="Done",
            duration_seconds=0.0,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            context_compressed=False,
            context_compaction=None,
        )

    monkeypatch.setattr(app_runtime, "begin_chat_turn", fake_begin_chat_turn)
    monkeypatch.setattr(app_runtime, "run_reserved_chat_turn", fake_run_reserved_chat_turn)

    runtime = SimpleNamespace(
        enabled_tool_packs=[PACK_WORKSPACE_READ],
        _active_tool_packs_for_current_run=[],
        chat_history=[],
        current_model="gpt-5.4-mini",
        current_variant="standard",
    )

    import asyncio

    result = asyncio.run(
        app_runtime.run_app_chat_turn(
            runtime,
            user_message="whats in this current directory",
            source_format="app_text",
            interrupt_policy="none",
        )
    )

    assert result["ok"] is True
    allowed_names = captured["allowed_names"]
    assert isinstance(allowed_names, set)
    assert "read_file" in allowed_names
    assert "list_dir" in allowed_names
    assert "find_files" in allowed_names
    assert "grep_search" in allowed_names

    definition_names = captured["allowed_definition_names"]
    assert isinstance(definition_names, list)
    assert "read_file" in definition_names
    assert "list_dir" in definition_names
    assert "find_files" in definition_names
    assert "grep_search" in definition_names

    system_messages = captured["system_messages"]
    assert isinstance(system_messages, list)
    combined = "\n".join(str(message.get("content", "")) for message in system_messages)
    assert "TASK EXECUTION CONTRACT" in combined
    assert "All enabled tools remain available on this turn." in combined
    assert "already injected when available" in combined
    assert "Do not execute tools" not in combined


def test_tui_auto_prompt_resolves_runtime_blocks_and_system_info():
    class DummyProcessor:
        base_path = Path.cwd()

    prompt = build_tui_auto_system_prompt(DummyProcessor(), skills_index="\n\n## TEST SKILLS")

    assert "# LIVE BROWSER RUNTIME STATUS" in prompt
    assert "# MANAGED TASK BOARD RUNTIME" not in prompt
    assert "# LIVE DESKTOP RUNTIME STATUS" in prompt
    assert "# TOOL-PACK AUTHORITY" in prompt
    assert "## Enabled Pack: Interactive Desktop" in prompt
    assert "Real Chrome available now: NO" in prompt
    assert "Missing interpreter / PATH / package issue" not in prompt
    assert "{{SYSTEM_INFO}}" not in prompt
    assert "## TEST SKILLS" in prompt
    assert "Do not assume a visually presented action succeeded." in prompt
    assert "Do not chain clicks, typing, hotkeys, or other interactive GUI actions" in prompt
    assert "make sure the intended target window, dialog, or control is focused" in prompt
    assert "The user may move focus, click, or type while you work." in prompt
    assert "use `pull_skill` before improvising a long workflow from scratch" in prompt
