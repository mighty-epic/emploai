"""
Unified agent helpers for the Telegram agent.
"""

import asyncio
import os
import logging
import time
import base64
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Callable, List, Optional

PYAUTOGUI_IMPORT_ERROR = None
try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except Exception as exc:
    pyautogui = None
    PYAUTOGUI_AVAILABLE = False
    PYAUTOGUI_IMPORT_ERROR = exc

PYWINAUTO_IMPORT_ERROR = None
try:
    from pywinauto import Desktop
    PYWINAUTO_AVAILABLE = True
except Exception as exc:
    Desktop = None
    PYWINAUTO_AVAILABLE = False
    PYWINAUTO_IMPORT_ERROR = exc

try:
    import mss
    from PIL import Image
    SCREEN_CAPTURE_AVAILABLE = True
except Exception:
    mss = None
    Image = None
    SCREEN_CAPTURE_AVAILABLE = False

try:
    import pytesseract
    from shared.tesseract_runtime import configure_pytesseract_runtime, normalize_tesseract_error
    configure_pytesseract_runtime(pytesseract)
    OCR_AVAILABLE = SCREEN_CAPTURE_AVAILABLE
except Exception:
    pytesseract = None
    OCR_AVAILABLE = False

TESSERACT_AVAILABLE = OCR_AVAILABLE

try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except ImportError:
    PYPERCLIP_AVAILABLE = False

from telegram.constants import ParseMode
from cli.agent_tools.web_tools import duckduckgo_search
from shared.channel_sync import get_channel_sync_hub
from shared import (
    create_unified_agent,
    get_heartbeat_manager,
)
from shared.task_board import TASK_BOARD_INTERNAL_TOOL_NAME, build_task_board_prompt, get_active_task_board
from shared.tool_packs import (
    PACK_BROWSER_ISOLATED,
    PACK_INTERACTIVE_DESKTOP,
    PACK_SCHEDULER,
    build_tool_pack_prompt,
)
from single_agent.browser_tool import create_browser_tool
from single_agent.extension_tool import create_extension_tool
from single_agent.cron_scheduler import CRON_TOOL_DEFINITIONS, parse_schedule_with_error


logger = logging.getLogger(__name__)


PACK_SCOPED_UNIFIED_AGENT_CORE_PROMPT = """
You are an advanced AI assistant operating in AUTO MODE.

## CORE CONTRACT
- Execute the user's request using only the tool packs and tool names explicitly listed in the tool-pack authority block above.
- If a tool or pack is not listed there, it is unavailable in this chat. Do not mention it as available, do not plan around it, and do not hallucinate access.
- If the task needs a disabled capability, say that the capability is unavailable in the current tool-pack configuration and continue with the tools that are actually enabled.
- Prefer action and verification over long explanations.
- Keep working through normal failures. Only stop for a true blocker or a tool-pack limitation that the user must change.

## OPERATING STYLE
- Verify after every meaningful action.
- Prefer the lowest-risk tool that can prove progress.
- Do not assume a visually presented action succeeded. Verify the resulting state with the cheapest trustworthy observation tool for that environment. For desktop GUI state, prefer describe_screen. For browser-native state, prefer browser tools first, and use describe_screen only when the browser is headed and browser-native evidence is inconclusive.
- Do not chain clicks, typing, hotkeys, or other interactive GUI actions without first verifying that the previous step landed the way you intended.
- If a local dependency, runtime, app launch path, file association, or environment detail is broken but safely repairable, fix it and continue instead of treating it as a blocker.
- Prefer reversible, task-scoped repairs before broader machine changes. Avoid global installs, default-app changes, registry or PATH edits, deleting user data, killing unrelated processes, or closing the user's apps, tabs, or documents unless the task clearly requires it or the user asked for it.
- Prefer native file tools over shell-generated file edits whenever those tools are available.
- On Windows, prefer `py` before `python3` and avoid Unix shell assumptions such as `cat`, `pwd`, heredocs, `/tmp`, `/root`, or `/workspace`.
- Use the workspace/root path from the WORKSPACE/PATH RUNTIME STATUS section for file-grounding. Relative paths from file tools are workspace-relative; native desktop Open/Save dialogs usually are not.
- Before typing a path into a desktop file picker or opening a saved file through a host app, resolve the exact absolute path with available file or command tools. Do not guess locations such as Downloads or `C:\\Users\\Public`.
- If the current directory is uncertain, inspect it first with available tools such as `list_dir('.')`, `find_files`, or a Windows command like `Get-Location` or `Resolve-Path`.
- For desktop launches, window switches, clicks, typing, and other physical desktop actions, treat the action as an attempt until the resulting state is visually verified.
- `open_app` does not prove an app opened. If a launch produces an error dialog, the wrong window, or no target window, treat that as failure and recover.
- Do not final-answer while the task is incomplete and a safe next route exists; take the next safe route instead of saying you can try it.
- For failed app, file, browser, or desktop actions, discover alternatives from current state and available surfaces such as existing windows, taskbar/dock icons, OS launcher/search, full paths, file associations, workspace files, installed commands, browser tabs, and trusted web equivalents.
- The user may move focus, click, or type while you work. Do not panic or stop. Re-observe, correct the state, and continue the task.
- Use the chain of escalation and degradation for tools. If a task is naturally browser-first, stay in the browser toolchain until browser-native methods genuinely stop being sufficient, then fall back to desktop vision and interactive tools only as needed.
- Native desktop apps, including third-party apps, require interactive desktop tools and visual verification. Do not assume a hidden app-specific control path.
- Any GUI without a dedicated tool path should be treated as a vision-and-interaction task. For Chrome or browser tasks, use browser tools when the runtime says that path is valid; otherwise fall back to desktop vision and interactive tools.
- When you open an app, browser window, or file in a visually-presented way, verify that the exact requested target actually became visible. Opening a host app like Notepad is not proof that the requested file opened inside it, and a blank window, wrong document, wrong tab, wrong chat, or generic host UI is not success.
- For desktop-visible opens and window changes, prefer describe_screen to confirm that the intended target actually appeared. For browser-visible results, prefer browser-native verification and use browser_screenshot as proof when it is available and the task still needs visual confirmation.
- When you call describe_screen or browser_screenshot for visual interpretation, ask a precise question about what changed, what should now be visible, what error or dialog might be present, or what control you need to identify. Avoid vague prompts like 'what is on screen?' unless no narrower question exists.
- Before final-answering with partial, failed, or blocked status, check whether there is a safe, relevant next action you can take now. If yes, take it instead of saying you can try it.
- Prefer keyboard-first desktop interaction when a reliable shortcut, tab path, or confirm key can do the job more safely than clicking.
- Before using hotkeys, press_key, type_text, Enter, Escape, Tab, or any key combo that affects the visible UI, make sure the intended target window, dialog, or control is focused; if focus is uncertain or another window is active, re-observe and focus the correct target before sending keys.
- Treat a wrong click, stale observation, or user-caused focus change as a recoverable state problem. Re-observe, diagnose, correct, and continue.
- AGENTS.md, SOUL.md, USER.md, TOOLS.md, and MEMORY.md are already loaded into prompt context when available. Do not re-open them with file tools during normal execution.
- Do not read MEMORY.md just to start a task. Touch memory only when you are intentionally saving durable reusable information.
- Save durable reusable insights about websites, apps, and workflows to memory. Save durable account facts, usernames, emails, profile choices, login requirements, and persistent personal information that will help future tasks, but never store raw secrets such as passwords, tokens, API keys, or 2FA codes in MEMORY.md.
- When the injected skills index shows a relevant specialized skill for a complex or domain-specific request, use `pull_skill` before improvising a long workflow from scratch.
- Stop researching once the requested facts are verified from sufficient evidence, and do not broaden into adjacent categories unless the prompt explicitly asks for that.
- When you write a file or run code, report the verified result from stdout, file read-back, DOM text, or another observed output instead of from your intended content.
- When starting a local dev server only for task verification, bind it to `127.0.0.1` or `localhost` when supported unless the user requested LAN or public access.
- Treat the user's machine, files, and sessions carefully.
- Keep responses concise and grounded in what you actually observed or changed.
""".strip()

if PYAUTOGUI_IMPORT_ERROR is not None:
    logger.warning("pyautogui unavailable; desktop input tools disabled: %s", PYAUTOGUI_IMPORT_ERROR)


def build_current_time_prompt() -> str:
    now = datetime.now().astimezone()
    tz_name = now.tzname() or "local"
    offset = now.strftime("%z")
    offset_text = (
        f"{offset[:3]}:{offset[3:]}"
        if len(offset) == 5
        else offset or "unknown"
    )
    return "\n".join(
        [
            "# CURRENT DATE/TIME",
            f"- Local date/time now: {now.strftime('%Y-%m-%d %H:%M:%S')} {tz_name} (UTC{offset_text})",
            "- Use this for time-sensitive tasks such as 'now', 'today', 'in 5 minutes', scheduling, deadlines, and deciding whether a requested run time has already passed.",
        ]
    )


def build_workspace_path_runtime_prompt(session) -> str:
    raw_workspace = getattr(session, "workspace", None) or Path.cwd()
    try:
        workspace = str(Path(raw_workspace).expanduser().resolve())
    except Exception:
        workspace = str(raw_workspace)

    return "\n".join(
        [
            "# WORKSPACE/PATH RUNTIME STATUS",
            f"- Current workspace/root directory: {workspace}",
            "- File tools resolve relative paths against this workspace unless a tool says otherwise.",
            "- Native desktop file pickers and app Open/Save dialogs do not automatically start in this workspace. Use absolute paths when passing workspace files into GUI apps.",
            "- If the current directory or target file path is uncertain, use available workspace or command tools to inspect it before typing into a GUI. On Windows, a command like `Get-Location` or `Resolve-Path <relative-path>` is the right way to confirm.",
            "- Do not invent paths under Downloads, Desktop, Documents, or `C:\\Users\\Public`; use paths you created, listed, read, or resolved.",
        ]
    )

# Linux compatibility: host-authoritative detection only. Cross-OS env
# overrides are ignored so local Windows desktops never activate Linux tools
# and Linux deployments never fall back to the Windows desktop path.
try:
    from .linux import LINUX_MODE
    if LINUX_MODE:
        from .linux.desktop_tools import get_linux_desktop_overrides
except ImportError:
    from linux import LINUX_MODE
    if LINUX_MODE:
        from linux.desktop_tools import get_linux_desktop_overrides

if LINUX_MODE:
    _LINUX_DESKTOP_OVERRIDES = get_linux_desktop_overrides()
else:
    _LINUX_DESKTOP_OVERRIDES = {}

AUTO_MODE_BROWSER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "browser_extension_toggle",
            "description": "Toggle between Selenium and the native Chrome extension bridge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "enable": {
                        "type": "boolean",
                        "description": "True to use the native Chrome extension bridge, false to use Selenium.",
                    }
                },
                "required": ["enable"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navigate the browser to a URL. Works with Selenium or the native Chrome extension bridge. When you explicitly provide headless=true/false, that choice applies only to the Selenium-backed isolated browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"},
                    "headless": {
                        "type": "boolean",
                        "description": "Optional Selenium mode selector. Use true when you want isolated headless browser work. Use false only when you intentionally need the Selenium window visible on the live desktop.",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_snapshot",
            "description": "Get an ARIA snapshot of the current page with interactive [ref=N] IDs. Best for interactive structure and ref-based actions, not for full page text extraction.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_read_text",
            "description": "Read visible page text from the current browser page. Use this for static text, headings, rendered values, and exact text extraction on isolated browser pages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "Optional CSS selector for a specific element to read. Omit to read visible text from the whole page body.",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum number of characters to return.",
                        "default": 4000,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click_ref",
            "description": "Click an ARIA-tagged browser element by its [ref=N] id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ref": {"type": "integer", "description": "Reference id from browser_snapshot."},
                },
                "required": ["ref"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type",
            "description": "Type text into the focused input, or into a specific ref when provided. Prefer ref-based typing for reliable long tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type."},
                    "ref": {"type": "integer", "description": "Optional input ref from browser_snapshot."},
                    "clear_first": {"type": "boolean", "default": False},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_clear_ref",
            "description": "Clear a specific input field by its [ref=N] id before typing new content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ref": {"type": "integer", "description": "Input ref from browser_snapshot."},
                },
                "required": ["ref"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_select_option_ref",
            "description": "Select an option on a native <select> element by ref using visible text, value, or index.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ref": {"type": "integer", "description": "Select ref from browser_snapshot."},
                    "text": {"type": "string", "description": "Visible option text to select."},
                    "value": {"type": "string", "description": "Option value attribute to select."},
                    "index": {"type": "integer", "description": "Zero-based option index to select."},
                },
                "required": ["ref"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_press_key",
            "description": "Press a key inside the active browser page. Use this sparingly for browser navigation because synthetic key events are less reliable than ref-based actions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Key name such as enter, tab, escape, arrow_down."},
                },
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_wait_for",
            "description": "Wait for a page condition on the current task tab. Prefer this over blind sleep when waiting for navigation or status text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url_contains": {"type": "string", "description": "Substring expected in the current URL."},
                    "title_contains": {"type": "string", "description": "Substring expected in the page title."},
                    "text_contains": {"type": "string", "description": "Substring expected in visible page text."},
                    "timeout_seconds": {"type": "number", "default": 10},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scroll",
            "description": "Scroll the current browser page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down"], "default": "down"},
                    "amount": {"type": "integer", "default": 300},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Capture a screenshot of the current browser page for proof and stored artifacts. When you need visual interpretation, ask a precise question about what should be visible. Do not rely on this alone for exact text extraction inside the same turn.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Optional precise visual question for the browser screenshot sidecar, such as whether the expected page, file, dialog, or error is visibly open.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_back",
            "description": "Go back in browser history.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_forward",
            "description": "Go forward in browser history.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_switch_tab",
            "description": "Switch to a browser tab by index (0-based).",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "The tab index."},
                },
                "required": ["index"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_list_tabs",
            "description": "List currently open browser tabs with indices, titles, URLs, and the active tab.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_activate_tab",
            "description": "Activate an existing browser tab by title substring, URL substring, tab id, or index. Use this when asked to move to an already-open tab.",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "Tab index if already known."},
                    "title_contains": {"type": "string", "description": "Substring of the tab title to match."},
                    "url_contains": {"type": "string", "description": "Substring of the tab URL to match."},
                    "tab_id": {"type": "integer", "description": "Specific tab id if already known."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_close_tab",
            "description": "Close the current browser tab.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_stop",
            "description": "Stop the browser session or disconnect from the bridge.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def get_auto_mode_extra_tools() -> List[Dict[str, Any]]:
    return list(AUTO_MODE_BROWSER_TOOLS) + list(CRON_TOOL_DEFINITIONS)


def get_auto_mode_tool_handlers(session) -> Dict[str, Callable[[Dict[str, Any]], Any]]:
    handlers = {
        "browser_extension_toggle": lambda args: _execute_browser_extension_toggle(session, args),
        "browser_navigate": lambda args: _execute_browser_navigate(session, args),
        "browser_snapshot": lambda args: _execute_browser_snapshot(session, args),
        "browser_read_text": lambda args: _execute_browser_read_text(session, args),
        "browser_click_ref": lambda args: _execute_browser_click_ref(session, args),
        "browser_type": lambda args: _execute_browser_type(session, args),
        "browser_clear_ref": lambda args: _execute_browser_clear_ref(session, args),
        "browser_select_option_ref": lambda args: _execute_browser_select_option_ref(session, args),
        "browser_press_key": lambda args: _execute_browser_press_key(session, args),
        "browser_wait_for": lambda args: _execute_browser_wait_for(session, args),
        "browser_scroll": lambda args: _execute_browser_scroll(session, args),
        "browser_screenshot": lambda args: _execute_browser_screenshot(session, args),
        "browser_back": lambda args: _execute_browser_back(session, args),
        "browser_forward": lambda args: _execute_browser_forward(session, args),
        "browser_switch_tab": lambda args: _execute_browser_switch_tab(session, args),
        "browser_list_tabs": lambda args: _execute_browser_list_tabs(session, args),
        "browser_activate_tab": lambda args: _execute_browser_activate_tab(session, args),
        "browser_close_tab": lambda args: _execute_browser_close_tab(session, args),
        "browser_stop": lambda args: _execute_browser_stop(session, args),
        "schedule_job": lambda args: _execute_schedule_job(session, args),
        "list_scheduled_jobs": lambda args: _execute_list_scheduled_jobs(session, args),
        "get_scheduled_job": lambda args: _execute_get_scheduled_job(session, args),
        "update_scheduled_job": lambda args: _execute_update_scheduled_job(session, args),
        "run_scheduled_job_now": lambda args: _execute_run_scheduled_job_now(session, args),
        "remove_scheduled_job": lambda args: _execute_remove_scheduled_job(session, args),
        "enable_job": lambda args: _execute_enable_job(session, args),
        "disable_job": lambda args: _execute_disable_job(session, args),
        # Backwards-compatible aliases used by the legacy SingleAgent schema/prompt.
        "open_browser": lambda args: _execute_browser_navigate(
            session,
            {"url": args["url"], **({"headless": args["headless"]} if "headless" in args else {})},
        ),
        "observe_browser": lambda args: _execute_observe_browser(session, args),
        "switch_tab": lambda args: _execute_browser_switch_tab(session, {"index": args["index"]}),
        "close_tab": lambda args: _execute_browser_close_tab(session, args),
        "go_back": lambda args: _execute_browser_back(session, args),
        "go_forward": lambda args: _execute_browser_forward(session, args),
    }
    # Linux override: swap Windows-only desktop tools for Linux equivalents
    if LINUX_MODE:
        for name, func in _LINUX_DESKTOP_OVERRIDES.items():
            handlers[name] = lambda args, f=func: f(session, args)
    return handlers


def create_unified_agent_for_task(session, app, loop) -> None:
    """Create a unified agent that works with ANY model."""
    session._app = app
    session._loop = loop

    def logger_func(text: str):
        print(f"[AGENT] {text}")
        if session._app and session._loop:
            asyncio.run_coroutine_threadsafe(
                session._send_log(text), session._loop
            )

    client, provider = session.get_client_for_model()

    if not client:
        logger.error(f"No API key for provider: {provider}")
        raise ValueError(
            f"No API key configured for {provider}. Set {provider.upper()}_API_KEY environment variable."
        )

    # Build system prompt with skills index
    skills_index = ""
    if hasattr(session, "skill_registry") and session.skill_registry:
        skills_index = f"\n\n{session.skill_registry.get_skills_index()}"

    memory_context = ""
    if session.session_context.can_access_memory and session.memory_manager:
        current_session_id = (
            session.session_manager.current_session.id
            if session.session_manager and session.session_manager.current_session
            else None
        )
        prompt_memory = session.memory_manager.build_prompt_context(
            recent_days=2,
            recent_chars=2000,
            long_term_chars=4000,
            session_id=current_session_id,
        )
        if prompt_memory:
            memory_context = f"\n\n{prompt_memory}"

    system_prompt = build_unified_system_prompt(
        session,
        memory_context=memory_context,
        skills_index=skills_index,
    )

    session.unified_agent = create_unified_agent(
        model_name=session.current_model,
        client=client,
        tool_executor=_build_unified_tool_executor(session),
        workspace=session.workspace,
        logger_func=logger_func,
        system_prompt=system_prompt
    )

    if session.live_config.get('heartbeat.enabled', False):
        def heartbeat_agent_callback(prompt: str) -> str:
            return session.unified_agent.run(prompt, max_turns=10)

        def heartbeat_announcement(text: str):
            if session._app:
                asyncio.run_coroutine_threadsafe(
                    session._app.bot.send_message(
                        chat_id=session.user_id,
                        text=text,
                        parse_mode=ParseMode.MARKDOWN
                    ),
                    loop
                )

        session.heartbeat_manager = get_heartbeat_manager(
            workspace=session.workspace,
            interval_seconds=session.live_config.get('heartbeat.interval_seconds', 1800),
            announcement_callback=heartbeat_announcement,
            agent_callback=heartbeat_agent_callback
        )
        session.heartbeat_manager.start()


def _build_unified_tool_executor(session) -> Callable[[str, Dict], Any]:
    tool_map = {
        'read_file': lambda args: _execute_read_file(session, args),
        'write_file': lambda args: _execute_write_file(session, args),
        'edit_file': lambda args: _execute_edit_file(session, args),
        'list_files': lambda args: _execute_list_files(session, args),
        'execute_command': lambda args: _execute_command(session, args),
        'web_search': lambda args: _execute_web_search(session, args),
        'fetch_url': lambda args: _execute_fetch_url(session, args),
        'browser_navigate': lambda args: _execute_browser_navigate(session, args),
        # 'browser_click': lambda args: _execute_browser_click(session, args),  # DISABLED: use browser_click_ref
        'browser_type': lambda args: _execute_browser_type(session, args),
        'browser_clear_ref': lambda args: _execute_browser_clear_ref(session, args),
        'browser_select_option_ref': lambda args: _execute_browser_select_option_ref(session, args),
        'browser_press_key': lambda args: _execute_browser_press_key(session, args),
        'browser_wait_for': lambda args: _execute_browser_wait_for(session, args),
        'browser_scroll': lambda args: _execute_browser_scroll(session, args),
        'browser_screenshot': lambda args: _execute_browser_screenshot(session, args),
        'browser_snapshot': lambda args: _execute_browser_snapshot(session, args),
        'browser_read_text': lambda args: _execute_browser_read_text(session, args),
        'browser_click_ref': lambda args: _execute_browser_click_ref(session, args),
        'browser_back': lambda args: _execute_browser_back(session, args),
        'browser_forward': lambda args: _execute_browser_forward(session, args),
        'browser_switch_tab': lambda args: _execute_browser_switch_tab(session, args),
        'browser_list_tabs': lambda args: _execute_browser_list_tabs(session, args),
        'browser_activate_tab': lambda args: _execute_browser_activate_tab(session, args),
        'browser_close_tab': lambda args: _execute_browser_close_tab(session, args),
        'browser_stop': lambda args: _execute_browser_stop(session, args),
        'search_memory': lambda args: _execute_search_memory(session, args),
        'update_memory': lambda args: _execute_update_memory(session, args),
        'change_directory': lambda args: _execute_change_directory(session, args),
        'describe_screen': lambda args: _execute_describe_screen(session, args),
        'ocr_screen': lambda args: _execute_ocr_screen(session, args),
        'observe_desktop': lambda args: _execute_observe_desktop(session, args),
        'click': lambda args: _execute_click(session, args),
        'right_click': lambda args: _execute_right_click(session, args),
        'double_click': lambda args: _execute_double_click(session, args),
        'type_text': lambda args: _execute_type_text(session, args),
        'press_key': lambda args: _execute_press_key(session, args),
        'hotkey': lambda args: _execute_hotkey(session, args),
        'scroll': lambda args: _execute_scroll(session, args),
        'open_app': lambda args: _execute_open_app(session, args),
        'focus_window': lambda args: _execute_focus_window(session, args),
        'get_clipboard': lambda args: _execute_get_clipboard(session, args),
        'set_clipboard': lambda args: _execute_set_clipboard(session, args),
        'spawn_sub_agent': lambda args: _execute_spawn_sub_agent(session, args),
        'list_sub_agents': lambda args: _execute_list_sub_agents(session, args),
        'schedule_job': lambda args: _execute_schedule_job(session, args),
        'list_scheduled_jobs': lambda args: _execute_list_scheduled_jobs(session, args),
        'get_scheduled_job': lambda args: _execute_get_scheduled_job(session, args),
        'update_scheduled_job': lambda args: _execute_update_scheduled_job(session, args),
        'run_scheduled_job_now': lambda args: _execute_run_scheduled_job_now(session, args),
        'remove_scheduled_job': lambda args: _execute_remove_scheduled_job(session, args),
        'browser_extension_toggle': lambda args: _execute_browser_extension_toggle(session, args),
    }

    # Linux override: swap Windows-only desktop tools for Linux equivalents
    if LINUX_MODE:
        for name, func in _LINUX_DESKTOP_OVERRIDES.items():
            if name in tool_map:
                tool_map[name] = lambda args, f=func: f(session, args)

    def unified_tool_executor(tool_name: str, tool_args: Dict) -> Any:
        allowed_tool_names = getattr(session, "current_turn_allowed_tool_names", None)
        if allowed_tool_names is not None and tool_name not in allowed_tool_names:
            return {
                "error": f"Tool '{tool_name}' is not enabled for this chat's current tool-pack configuration.",
                "error_type": "policy",
            }
        executor = tool_map.get(tool_name)
        if executor:
            return executor(tool_args)
        return f"Unknown tool: {tool_name}"

    return unified_tool_executor


def _execute_read_file(session, args: Dict) -> str:
    try:
        path = Path(args['path'])
        if not path.is_absolute():
            path = (session.workspace / path).resolve()
            
        if not path.exists():
            return f"File not found: {path}"
        content = path.read_text(encoding='utf-8')
        if 'start_line' in args or 'end_line' in args:
            lines = content.split('\n')
            start = args.get('start_line', 1) - 1
            end = args.get('end_line', len(lines))
            content = '\n'.join(lines[start:end])
        return content
    except Exception as e:
        return f"Error reading file: {str(e)}"


def _execute_write_file(session, args: Dict) -> str:
    try:
        path = Path(args['path'])
        if not path.is_absolute():
            path = (session.workspace / path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args['content'], encoding='utf-8')
        return f"Wrote {len(args['content'])} chars to {path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"


def _execute_edit_file(session, args: Dict) -> str:
    try:
        path = Path(args['path'])
        if not path.is_absolute():
            path = (session.workspace / path).resolve()
            
        if not path.exists():
            return f"File not found: {path}"
        content = path.read_text(encoding='utf-8')
        old_text = args['old_text']
        new_text = args['new_text']
        if old_text not in content:
            return f"Text not found in file: {old_text[:50]}..."
        new_content = content.replace(old_text, new_text)
        path.write_text(new_content, encoding='utf-8')
        return f"Edited {path}"
    except Exception as e:
        return f"Error editing file: {str(e)}"


def _execute_list_files(session, args: Dict) -> str:
    try:
        path = Path(args['path'])
        if not path.is_absolute():
            path = (session.workspace / path).resolve()
        if not path.exists():
            return f"Directory not found: {path}"
        if not path.is_dir():
            return f"Not a directory: {path}"
        recursive = args.get('recursive', False)
        pattern = '**/*' if recursive else '*'
        files = list(path.glob(pattern))
        if len(files) > 100:
            files = files[:100]
            result = '\n'.join(str(f) for f in files)
            result += f"\n... and {len(files) - 100} more files"
            return result
        return '\n'.join(str(f) for f in files)
    except Exception as e:
        return f"Error listing files: {str(e)}"


def _execute_command(session, args: Dict) -> str:
    try:
        import subprocess
        result = subprocess.run(
            args['command'],
            shell=True,
            cwd=args.get('cwd') or str(session.workspace),
            capture_output=True,
            text=True,
            timeout=600
        )
        output = result.stdout or result.stderr or "(no output)"
        return output[:5000]
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds"
    except Exception as e:
        return f"Error executing command: {str(e)}"


def _execute_web_search(session, args: Dict) -> str:
    query = str(args.get("query", "")).strip()
    if not query:
        return "Error: 'query' is required"

    max_results = args.get("max_results", 5)
    try:
        max_results = max(1, min(int(max_results), 10))
    except (TypeError, ValueError):
        max_results = 5

    result = duckduckgo_search(query, max_results=max_results)
    if result.get("error"):
        return f"DuckDuckGo search error for '{query}': {result['error']}"

    results = result.get("results") or []
    if not results:
        return f"No DuckDuckGo results found for '{query}'."

    lines = [f"DuckDuckGo results for '{query}':"]
    for index, item in enumerate(results, start=1):
        title = str(item.get("title") or "(untitled result)").strip()
        url = str(item.get("url") or "").strip()
        snippet = str(item.get("snippet") or "").strip()

        lines.append(f"{index}. {title}")
        if url:
            lines.append(f"   URL: {url}")
        if snippet:
            lines.append(f"   Snippet: {snippet}")

    return "\n".join(lines)


def _execute_fetch_url(session, args: Dict) -> str:
    try:
        import requests
        response = requests.get(args['url'], timeout=10)
        response.raise_for_status()
        return response.text[:5000]
    except Exception as e:
        return f"Error fetching URL: {str(e)}"


FAILOVER_ERROR_TYPES = {"connection", "protocol", "timeout"}


def _bridge_enabled(session) -> bool:
    return bool(session.live_config.get("browser.use_extension", True))


def ensure_extension_bridge(session):
    """Ensure the localhost bridge server is running without pinning a backend."""
    if not hasattr(session, "extension_tool") or not session.extension_tool:
        session.extension_tool = create_extension_tool()
    session.extension_tool.start_server()
    return session.extension_tool


def _get_selenium_tool(session):
    if hasattr(session, "browser_tool") and session.browser_tool:
        return session.browser_tool

    if session.refined_agent and hasattr(session.refined_agent, "browser") and session.refined_agent.browser:
        session.browser_tool = session.refined_agent.browser
        return session.browser_tool

    # Respect the HEADLESS environment setting so VPS deployments can keep
    # fallback Selenium visible on the persistent desktop when desired.
    session.browser_tool = create_browser_tool()
    return session.browser_tool


def _configured_selenium_mode(session) -> str:
    browser_tool = getattr(session, "browser_tool", None)
    if browser_tool and hasattr(browser_tool, "get_current_mode"):
        return str(browser_tool.get_current_mode() or "headless")

    if session.refined_agent and hasattr(session.refined_agent, "browser") and session.refined_agent.browser:
        browser = session.refined_agent.browser
        if hasattr(browser, "get_current_mode"):
            return str(browser.get_current_mode() or "headless")

    env_headless = str(os.getenv("HEADLESS", "") or "").strip().lower()
    if env_headless in {"false", "0", "no", "off"}:
        return "headed"
    return "headless"


def _get_browser_tool(session):
    """Return the current preferred browser tool for compatibility callers."""
    context = session.get_browser_task_context()
    if context.backend == "selenium" or not _bridge_enabled(session):
        return _get_selenium_tool(session)
    return ensure_extension_bridge(session)


def _extension_status_ready(extension_status: Optional[Dict[str, Any]]) -> bool:
    return bool(
        extension_status
        and extension_status.get("connected")
        and extension_status.get("healthy")
    )


def get_browser_bridge_status(session) -> Dict[str, Any]:
    context = session.get_browser_task_context()
    extension_status = None
    if _bridge_enabled(session):
        extension_status = ensure_extension_bridge(session).get_status()
    elif hasattr(session, "extension_tool") and session.extension_tool:
        extension_status = session.extension_tool.get_status()

    extension_connected = bool(extension_status and extension_status.get("connected"))
    extension_healthy = bool(extension_status and extension_status.get("healthy"))
    extension_ready = _extension_status_ready(extension_status)
    desired_backend = "extension" if _bridge_enabled(session) else "selenium"
    effective_backend = "selenium"
    if desired_backend == "extension" and context.backend != "selenium" and extension_ready:
        effective_backend = "extension"

    return {
        "desired_backend": desired_backend,
        "effective_backend": effective_backend,
        "selenium_mode": _configured_selenium_mode(session),
        "task_backend": context.backend,
        "task_id": context.task_id,
        "healthy": context.healthy,
        "requires_real_chrome": bool(getattr(context, "requires_real_chrome", False)),
        "primary_tab_id": context.primary_tab_id,
        "primary_window_id": context.primary_window_id,
        "owned_tab_ids": list(context.owned_tab_ids),
        "task_tab_available": context.primary_tab_id is not None,
        "last_url": context.last_url,
        "last_title": context.last_title,
        "last_snapshot_hash": context.last_snapshot_hash,
        "extension_connected": extension_connected,
        "extension_healthy": extension_healthy,
        "extension_ready": extension_ready,
        "real_browser_available": extension_ready,
        "extension": extension_status,
    }


def build_browser_runtime_prompt(session, *, has_interactive_desktop: bool) -> str:
    status = get_browser_bridge_status(session)
    selenium_mode = str(status.get("selenium_mode") or "headless")
    heartbeat_age = (status.get("extension") or {}).get("heartbeat_age_seconds")
    heartbeat_text = f"{heartbeat_age}s" if heartbeat_age is not None else "unknown"
    last_title = status.get("last_title")
    last_url = status.get("last_url")
    if last_title or last_url:
        last_page = f"{last_title or '(no title)'} - {last_url or '(no url)'}"
    else:
        last_page = "unknown"

    if status["desired_backend"] == "extension":
        if status["real_browser_available"]:
            availability_rule = (
                "Real Chrome is available now. Standard browser_* tools may use "
                "the extension-backed real Chrome path."
            )
        else:
            availability_rule = (
                "Real Chrome is NOT available now. Do NOT assume browser_* tools "
                "can use the extension or the user's Chrome. Selenium-backed "
                "browser_* tools control only the agent-owned browser instance."
            )
    else:
        availability_rule = (
            "Extension mode is disabled. Use Selenium-backed browser_* tools and "
            "do NOT rely on the user's Chrome until the bridge is enabled again. "
            "Selenium is never the same thing as the user's current Chrome page or session."
        )

    user_chrome_rule = (
        "If the task is about the user's existing Chrome tab, page, or logged-in session and "
        "Real Chrome available now is NO, browser_* tools are unavailable for that task. "
        + (
            "Do NOT use Selenium as a substitute. Use describe_screen, ocr_screen, click, "
            "type_text, hotkey, and other desktop actions instead."
            if has_interactive_desktop
            else "Do NOT use Selenium as a substitute. You do not have live-desktop fallback in this chat unless the interactive desktop pack is enabled."
        )
    )

    if status["task_tab_available"]:
        task_tab_rule = "A task tab is already pinned for this task. Reuse it."
    else:
        task_tab_rule = (
            "No task tab is pinned yet. If you need real Chrome, call "
            "browser_navigate before browser_snapshot, browser_click_ref, "
            "browser_type, browser_clear_ref, browser_select_option_ref, "
            "browser_press_key, browser_wait_for, browser_scroll, "
            "browser_screenshot, browser_back, browser_forward, or "
            "browser_close_tab."
        )

    return "\n".join(
        [
            "# LIVE BROWSER RUNTIME STATUS (Overrides browser preference below)",
            f"- Desired backend preference: {status['desired_backend']}",
            f"- Effective backend right now: {status['effective_backend']}",
            f"- Isolated Selenium mode configured now: {selenium_mode}",
            f"- Task backend pin: {status.get('task_backend') or 'unassigned'}",
            f"- Task depends on user's Chrome: {'YES' if status['requires_real_chrome'] else 'NO'}",
            f"- Real Chrome available now: {'YES' if status['real_browser_available'] else 'NO'}",
            f"- Extension connected: {'YES' if status['extension_connected'] else 'NO'}",
            f"- Extension healthy: {'YES' if status['extension_healthy'] else 'NO'}",
            f"- Extension heartbeat age: {heartbeat_text}",
            f"- Task tab ready: {'YES' if status['task_tab_available'] else 'NO'}",
            f"- Primary task tab id: {status.get('primary_tab_id') or 'none'}",
            f"- Owned task tab count: {len(status.get('owned_tab_ids', []))}",
            f"- Last known page: {last_page}",
            "Rules:",
            f"- {availability_rule}",
            f"- {user_chrome_rule}",
            f"- {task_tab_rule}",
            "- Never claim the extension is active unless Real Chrome available now is YES.",
            "- browser_snapshot and observe_browser mainly report interactive structure, refs, title, URL, and high-level page state. They are not full page-text extraction tools.",
            "- For static content, headings, rendered text, and exact values on the current browser page, prefer browser_read_text. Use browser_wait_for(text_contains=...) to confirm appearance before reading when needed.",
            "- browser_screenshot captures proof and stored artifacts. Do NOT claim exact text or numeric values from browser_screenshot alone unless another tool extracted that text.",
            "- browser_read_text is the primary browser-native tool for visible page text, headings, labels, and exact rendered values.",
            "- browser_wait_for is for confirming that expected text, selectors, navigation, or load state appeared before you act or read.",
            "- open_browser controls the isolated browser instance and its headless/headed mode. It does not prove anything about the user's live Chrome session.",
            "- If you opened or navigated a browser page and the task depends on that visual result, verify the intended page state with browser_read_text, browser_snapshot, browser_wait_for, or browser_screenshot before assuming the page is ready.",
            "- If a browser window, page, or file should now be visibly open and browser-native evidence is still inconclusive, use browser_screenshot as visual proof before you assume that the intended browser result actually appeared.",
            "- If a browser snapshot, tab list, or other browser-native result already answers the question, do not escalate to screenshots, OCR, or desktop tools just to restate it.",
            "- If the task is naturally browser-first, stay in browser-native tools as long as they can still produce trustworthy evidence before falling back to desktop vision or desktop interaction.",
            "- If one browser-native method is inconclusive, try another browser-native method such as browser_read_text, browser_wait_for, browser_snapshot, or observe_browser before leaving the browser environment.",
            "- If isolated browser automation is blocked and the task depends on a real authenticated browser session, prefer the extension-backed real Chrome path when it is available before dropping to desktop-only interaction.",
            (
                "- If isolated Selenium is headless, describe_screen and ocr_screen cannot inspect that browser page. Do not use desktop vision/OCR to reason about headless Selenium output."
                if has_interactive_desktop
                else "- When live Chrome is unavailable, stay inside the isolated browser toolchain and do not imply live-desktop fallback."
            ),
            (
                "- If isolated Selenium is headed, desktop vision/OCR may only be used for that browser page after you have verified the Selenium window is actually the visible target on the live desktop."
                if has_interactive_desktop
                else "- When the isolated browser is the active path, prefer browser-native text and DOM tools over any desktop fallback wording."
            ),
            (
                "- If a major headed-browser action still needs visual confirmation after browser-native tools were inconclusive, verify that the Selenium window is the visible desktop target first, then use desktop vision/OCR only for that visible window."
                if has_interactive_desktop
                else "- If browser-native tools are inconclusive, prefer another browser-native method before implying any desktop fallback."
            ),
        ]
    )


def build_desktop_runtime_prompt(session) -> str:
    system_info = str(getattr(session, "system_info", "") or "")
    window_lines = [
        line.strip()
        for line in system_info.splitlines()
        if "active window" in line.lower() or "active windows" in line.lower()
    ]

    if not window_lines:
        window_lines = ["Active windows snapshot unavailable in SYSTEM_INFO."]

    return "\n".join(
        [
            "# LIVE DESKTOP RUNTIME STATUS (Overrides redundant desktop re-checks below)",
            *[f"- {line}" for line in window_lines],
            "- The startup SYSTEM_INFO already contains the initial desktop/window snapshot for this turn.",
            "- Do NOT spend a turn on observe_desktop or focus_window if that snapshot already identifies the target window and nothing has changed yet.",
            "- Re-check the desktop only after an action changed state, the user may have changed it, or the target window is still uncertain.",
            "- open_app only submits a launch request. It does not prove the app opened successfully.",
            "- After major desktop actions such as app launches, window switches, clicks, typing, hotkeys, or send/submit actions, visually verify the resulting state before assuming success.",
            "- Do not chain desktop clicks, typing, hotkeys, or other interactive GUI actions without first verifying that the previous action landed correctly.",
            "- If a launch attempt shows a Windows error dialog, the wrong window, or leaves the target missing, treat that as a failed launch and recover instead of pretending success.",
            "- Do not final-answer while the task is incomplete and a safe next route exists; take the next safe route instead of saying you can try it.",
            "- For failed app, file, browser, or desktop actions, discover alternatives from current state and available surfaces such as existing windows, taskbar/dock icons, OS launcher/search, full paths, file associations, workspace files, installed commands, browser tabs, and trusted web equivalents.",
            "- Native desktop apps, including third-party apps, require interactive desktop tools and visual verification. Do not assume a browser or DOM control path for them.",
            "- The user may move focus, click, or type while you work. If that happens, re-observe, correct the state, and continue instead of treating it as a blocker.",
            "- Any GUI without a dedicated tool path should be handled as a vision-and-interaction task.",
            "- describe_screen is the primary desktop verification and layout-understanding tool. Use it to confirm visible state, identify controls, and understand what changed.",
            "- ocr_screen is for exact visible text and coordinates. Prefer describe_screen first, then OCR when exact text or coordinate fallback is required.",
            "- observe_desktop tells you which windows exist and which one is active. It does not replace visual verification of on-screen controls.",
            "- If you opened an app, switched windows, or tried to open a file visually, verify that the exact requested target window and content actually appeared. Opening a host app alone is not proof that the requested file is open inside it, and a blank window, wrong document, wrong tab, wrong chat, or generic host UI is not success.",
            "- For desktop-visible opens and window changes, prefer describe_screen to confirm that the intended target actually appeared before you continue.",
            "- Prefer keyboard-first desktop interaction when a reliable shortcut or tab path exists. Use hotkey, press_key, Enter, Escape, Tab, Shift+Tab, Ctrl+L, Ctrl+S, and similar keys before coordinate clicking when they accomplish the same task more safely.",
            "- Do not use broad close shortcuts such as Alt+F4 for ambiguous cleanup. Use close_window with an exact target title, Escape/Cancel for a visible modal, or another targeted route.",
            "- Before physical typing, hotkeys, or key combos that affect the visible UI, make sure the intended target window, dialog, or control is still active. If focus is uncertain or another window is active, re-observe and focus the correct target before sending keys.",
            "- Before final-answering with partial, failed, or blocked status, check whether there is a safe, relevant next action you can take now. If yes, take it instead of saying you can try it.",
            "- A wrong click, stale desktop observation, or user-caused focus change is a recoverable state problem. Re-observe, diagnose, correct, and continue.",
            "- If a local launch path, file association, or other safely repairable desktop/runtime detail is broken, repair it and continue instead of treating it as a blocker.",
            "- Prefer reversible, task-scoped repairs before broader machine changes. Do not change global defaults, install software system-wide, kill unrelated processes, delete user data, or close the user's windows unless that is clearly necessary for the requested task or the user asked for it.",
        ]
    )


def build_unified_system_prompt(
    session,
    *,
    memory_context: str = "",
    skills_index: str = "",
    active_skills_context: str = "",
) -> str:
    workspace_context = ""
    if getattr(session, "context_loader", None):
        workspace_context = session.context_loader.build_system_prompt_context()
    active_tool_packs = list(
        getattr(session, "_active_tool_packs_for_current_run", None)
        or getattr(session, "enabled_tool_packs", [])
        or []
    )
    has_interactive_desktop = PACK_INTERACTIVE_DESKTOP in active_tool_packs
    has_browser_pack = has_interactive_desktop or PACK_BROWSER_ISOLATED in active_tool_packs

    cron_prompt = """
## SCHEDULING TOOLS
You can manage recurring scheduled jobs with these tools:
- schedule_job(name, prompt, schedule): create a recurring job
- list_scheduled_jobs(): list all jobs and their status
- get_scheduled_job(job_id): inspect one job in detail
- update_scheduled_job(job_id, ...): change name, prompt, schedule, or enabled state
- run_scheduled_job_now(job_id): queue a job to run on the next scheduler check
- remove_scheduled_job(job_id): delete a job
- enable_job(job_id): enable a disabled job
- disable_job(job_id): disable a job without deleting it
Supported schedules include: 'every 30 seconds', 'every 5 minutes', 'every 1 hour', and 'every day at 08:00'.
""".strip()

    sections = [
        build_task_board_prompt(session) if get_active_task_board(session) else "",
        build_browser_runtime_prompt(session, has_interactive_desktop=has_interactive_desktop) if has_browser_pack else "",
        build_desktop_runtime_prompt(session) if has_interactive_desktop else "",
        build_workspace_path_runtime_prompt(session),
        build_current_time_prompt(),
        cron_prompt if PACK_SCHEDULER in active_tool_packs else "",
        build_tool_pack_prompt(active_tool_packs),
        PACK_SCOPED_UNIFIED_AGENT_CORE_PROMPT,
        workspace_context.strip() if workspace_context else "",
        memory_context.strip() if memory_context else "",
        skills_index.strip() if skills_index else "",
        active_skills_context.strip() if active_skills_context else "",
    ]
    system_prompt = "\n\n".join(section for section in sections if section)
    return system_prompt.replace("{{SYSTEM_INFO}}", session.system_info)


def _should_failover_browser_result(result: Dict[str, Any]) -> bool:
    return bool(result.get("error")) and result.get("error_type") in FAILOVER_ERROR_TYPES


def _browser_tools_blocked_for_user_chrome_task(context) -> bool:
    return bool(getattr(context, "requires_real_chrome", False))


def _blocked_user_chrome_browser_result(reason: str) -> Dict[str, Any]:
    return {
        "error": (
            "browser_* tools are blocked for this task because it targets the user's current Chrome. "
            f"{reason} Use describe_screen, click, type_text, hotkey, and other desktop tools instead."
        ),
        "error_type": "policy",
    }


def _run_browser_action(
    session,
    extension_action,
    selenium_action,
    *,
    own_tab: bool = False,
    force_selenium: bool = False,
) -> Dict[str, Any]:
    context = session.get_browser_task_context()
    use_extension = (not force_selenium) and _bridge_enabled(session) and context.backend != "selenium"

    if _browser_tools_blocked_for_user_chrome_task(context):
        if not _bridge_enabled(session):
            return _blocked_user_chrome_browser_result(
                "The extension bridge is not enabled."
            )

        extension_tool = ensure_extension_bridge(session)
        extension_status = extension_tool.get_status()
        if not _extension_status_ready(extension_status):
            return _blocked_user_chrome_browser_result(
                "The extension bridge is not connected and healthy."
            )

        result = extension_action(extension_tool, context)
        if _should_failover_browser_result(result):
            context.healthy = False
            session.update_browser_task_context(result, owned_tab=own_tab)
            return _blocked_user_chrome_browser_result(
                result.get("error") or "The extension bridge failed."
            )

        context.backend = "extension"
        session.update_browser_task_context(result, owned_tab=own_tab)
        return result

    if use_extension:
        extension_tool = ensure_extension_bridge(session)
        extension_status = extension_tool.get_status()
        if not _extension_status_ready(extension_status):
            fallback = selenium_action(_get_selenium_tool(session), context)
            fallback = dict(fallback)
            fallback.setdefault(
                "bridge_fallback_reason",
                "Extension bridge unavailable; using Selenium instead.",
            )
            fallback.setdefault("extension_connected", bool(extension_status.get("connected")))
            fallback.setdefault("extension_healthy", bool(extension_status.get("healthy")))
            context.backend = "selenium"
            session.update_browser_task_context(fallback, owned_tab=own_tab)
            return fallback
        result = extension_action(extension_tool, context)
        if _should_failover_browser_result(result):
            context.backend = "selenium"
            context.healthy = False
            fallback = selenium_action(_get_selenium_tool(session), context)
            fallback = dict(fallback)
            fallback.setdefault(
                "bridge_fallback_reason",
                result.get("error") or "Extension bridge failed; using Selenium instead.",
            )
            context.backend = "selenium"
            session.update_browser_task_context(fallback, owned_tab=own_tab)
            return fallback

        context.backend = "extension"
        session.update_browser_task_context(result, owned_tab=own_tab)
        return result

    result = selenium_action(_get_selenium_tool(session), context)
    context.backend = "selenium"
    session.update_browser_task_context(result, owned_tab=own_tab)
    return result


def _browser_action_error(prefix: str, result: Dict[str, Any]) -> str:
    url = result.get("url")
    title = result.get("title")
    location = []
    if title:
        location.append(title)
    if url:
        location.append(url)
    suffix = f" [{' | '.join(location)}]" if location else ""
    return f"{prefix}: {result.get('error', 'Unknown browser error')}{suffix}"


def _browser_result_summary(action: str, result: Dict[str, Any], *, detail: Optional[str] = None) -> str:
    title = result.get("title") or "(no title)"
    url = result.get("url") or "(no url)"
    state_bits = []
    if result.get("backend"):
        state_bits.append(f"backend={result['backend']}")
    if result.get("mode"):
        state_bits.append(f"mode={result['mode']}")
    if result.get("tab_id") is not None:
        state_bits.append(f"tab={result['tab_id']}")
    if result.get("wait_reason"):
        state_bits.append(f"wait={result['wait_reason']}")

    lines = [f"{action}: {title} - {url}"]
    if detail:
        lines.append(detail)
    if result.get("bridge_fallback_reason"):
        lines.append(f"Bridge fallback: {result['bridge_fallback_reason']}")
    if state_bits:
        lines.append(f"State: {', '.join(state_bits)}")
    if result.get("field_value") is not None:
        lines.append(f"Field value: {result.get('field_value')}")
    if result.get("selected_text") or result.get("selected_value") is not None:
        lines.append(
            f"Selected: text={result.get('selected_text')!r}, value={result.get('selected_value')!r}"
        )
    if result.get("matched_conditions"):
        lines.append(f"Matched: {', '.join(result.get('matched_conditions', []))}")
    return "\n".join(lines)


def _execute_browser_extension_toggle(session, args: Dict) -> str:
    """Explicit tool to toggle browser extension mode."""
    enable = args.get("enable", True)
    if isinstance(enable, str):
        enable = enable.strip().lower() in {"true", "1", "yes", "on"}
    session.live_config.set("browser.use_extension", enable, session.user_id)
    session.live_config.save_config()
    session.reset_browser_task_context(session.current_task_id)

    if enable:
        ensure_extension_bridge(session)

    mode = "Extension" if enable else "Selenium"
    return f"Browser mode changed to: {mode}. The browser backend will be re-evaluated on the next task."


def _execute_browser_navigate(session, args: Dict) -> str:
    force_selenium = "headless" in args
    result = _run_browser_action(
        session,
        lambda browser, context: browser.navigate(args["url"], tab_id=context.primary_tab_id),
        lambda browser, context: browser.navigate(
            args["url"],
            tab_id=context.primary_tab_id,
            headless=args.get("headless"),
        ),
        own_tab=True,
        force_selenium=force_selenium,
    )
    if "error" in result:
        return _browser_action_error("Browser error", result)
    detail = "Task tab ready for the next verified step."
    return _browser_result_summary("Navigated", result, detail=detail)


def _execute_browser_click(session, args: Dict) -> str:
    result = _run_browser_action(
        session,
        lambda browser, context: browser.click(args["target"]),
        lambda browser, context: browser.click(args["target"]),
    )
    if "error" in result:
        return _browser_action_error("Click error", result)
    return "Clicked successfully"


def _execute_browser_type(session, args: Dict) -> str:
    result = _run_browser_action(
        session,
        lambda browser, context: browser.type(
            args["text"],
            clear_first=args.get("clear_first", False),
            ref=args.get("ref"),
            tab_id=context.primary_tab_id,
        ),
        lambda browser, context: browser.type(
            args["text"],
            clear_first=args.get("clear_first", False),
            ref=args.get("ref"),
            tab_id=context.primary_tab_id,
        ),
    )
    if "error" in result:
        return _browser_action_error("Type error", result)
    target = f"ref={args['ref']}" if args.get("ref") is not None else "focused element"
    return _browser_result_summary(
        "Typed",
        result,
        detail=f"Target: {target}; clear_first={bool(args.get('clear_first', False))}",
    )


def _execute_browser_clear_ref(session, args: Dict) -> str:
    result = _run_browser_action(
        session,
        lambda browser, context: browser.clear_ref(args["ref"], tab_id=context.primary_tab_id),
        lambda browser, context: browser.clear_ref(args["ref"], tab_id=context.primary_tab_id),
    )
    if "error" in result:
        return _browser_action_error("Clear error", result)
    return _browser_result_summary("Cleared field", result, detail=f"Target: ref={args['ref']}")


def _execute_browser_select_option_ref(session, args: Dict) -> str:
    result = _run_browser_action(
        session,
        lambda browser, context: browser.select_option_by_ref(
            args["ref"],
            text=args.get("text"),
            value=args.get("value"),
            index=args.get("index"),
            tab_id=context.primary_tab_id,
        ),
        lambda browser, context: browser.select_option_by_ref(
            args["ref"],
            text=args.get("text"),
            value=args.get("value"),
            index=args.get("index"),
            tab_id=context.primary_tab_id,
        ),
    )
    if "error" in result:
        return _browser_action_error("Select option error", result)
    return _browser_result_summary("Selected option", result, detail=f"Target: ref={args['ref']}")


def _execute_browser_press_key(session, args: Dict) -> str:
    result = _run_browser_action(
        session,
        lambda browser, context: browser.press_key(args["key"], tab_id=context.primary_tab_id),
        lambda browser, context: browser.press_key(args["key"], tab_id=context.primary_tab_id),
    )
    if "error" in result:
        return _browser_action_error("Key error", result)
    return _browser_result_summary(
        "Pressed browser key",
        result,
        detail=f"Key: {args['key']} (synthetic DOM event; prefer ref-based actions when possible)",
    )


def _execute_browser_wait_for(session, args: Dict) -> str:
    result = _run_browser_action(
        session,
        lambda browser, context: browser.wait_for(
            url_contains=args.get("url_contains"),
            title_contains=args.get("title_contains"),
            text_contains=args.get("text_contains"),
            timeout_seconds=args.get("timeout_seconds", 10),
            tab_id=context.primary_tab_id,
        ),
        lambda browser, context: browser.wait_for(
            url_contains=args.get("url_contains"),
            title_contains=args.get("title_contains"),
            text_contains=args.get("text_contains"),
            timeout_seconds=args.get("timeout_seconds", 10),
            tab_id=context.primary_tab_id,
        ),
    )
    if "error" in result:
        return _browser_action_error("Wait error", result)
    detail = "Observed requested page condition."
    return _browser_result_summary("Wait complete", result, detail=detail)


def _execute_browser_scroll(session, args: Dict) -> str:
    direction = args.get("direction", "down")
    amount = args.get("amount", 300)
    result = _run_browser_action(
        session,
        lambda browser, context: browser.scroll(direction, amount, tab_id=context.primary_tab_id),
        lambda browser, context: browser.scroll(direction, amount, tab_id=context.primary_tab_id),
    )
    if "error" in result:
        return _browser_action_error("Scroll error", result)
    return _browser_result_summary("Scrolled browser", result, detail=f"Direction: {direction}; amount={amount}")


def _execute_browser_screenshot(session, args: Dict) -> Dict:
    result = _run_browser_action(
        session,
        lambda browser, context: browser.screenshot(tab_id=context.primary_tab_id),
        lambda browser, context: browser.screenshot(tab_id=context.primary_tab_id),
    )
    if "error" in result:
        return {"error": f"Screenshot error: {result['error']}"}
    question = str(args.get("question") or "").strip()
    if question:
        enriched = dict(result)
        enriched["question"] = question
        return enriched
    return result


def _execute_browser_snapshot(session, args: Dict) -> str:
    result = _run_browser_action(
        session,
        lambda browser, context: browser.snapshot(tab_id=context.primary_tab_id),
        lambda browser, context: browser.snapshot(tab_id=context.primary_tab_id),
    )
    if "error" in result:
        return _browser_action_error("Snapshot error", result)
    metadata = f"Snapshot: {(result.get('title') or '(no title)')} - {(result.get('url') or '(no url)')}"
    return (
        f"{metadata}\n"
        f"Browser ARIA Snapshot:\n{result.get('formatted', 'No interactive elements found')}\n"
        "Snapshot semantics: interactive structure and refs only. Use browser_read_text for full visible page text or exact rendered values."
    )


def _execute_browser_read_text(session, args: Dict) -> str:
    selector = str(args.get("selector") or "").strip() or None
    try:
        max_chars = int(args.get("max_chars") or 4000)
    except Exception:
        max_chars = 4000
    max_chars = max(200, min(max_chars, 12000))

    result = _run_browser_action(
        session,
        lambda browser, context: browser.read_text(
            selector=selector,
            max_chars=max_chars,
            tab_id=context.primary_tab_id,
        ),
        lambda browser, context: browser.read_text(
            selector=selector,
            max_chars=max_chars,
            tab_id=context.primary_tab_id,
        ),
    )
    if "error" in result:
        return _browser_action_error("Read text error", result)

    extracted_text = str(result.get("text") or "").strip()
    selector_detail = f"Selector: {selector}" if selector else "Selector: <page body>"
    truncation_detail = ""
    if result.get("truncated"):
        truncation_detail = f"\nTruncated: yes (full_length={int(result.get('full_length') or len(extracted_text))})"
    return (
        f"Browser text: {(result.get('title') or '(no title)')} - {(result.get('url') or '(no url)')}\n"
        f"{selector_detail}\n"
        f"Mode: {result.get('mode') or result.get('backend') or 'unknown'}{truncation_detail}\n"
        "Visible page text:\n"
        f"{extracted_text or '(no visible text extracted)'}"
    )


def _execute_observe_browser(session, args: Dict) -> str:
    result = _run_browser_action(
        session,
        lambda browser, context: browser.snapshot(tab_id=context.primary_tab_id),
        lambda browser, context: browser.snapshot(tab_id=context.primary_tab_id),
    )
    if "error" in result:
        return _browser_action_error("Observe browser error", result)

    title = result.get("title") or "(no title)"
    url = result.get("url") or "(no url)"
    interactive_count = result.get("interactive_count", result.get("count", 0))
    lines = [
        f"Browser state: {title} - {url}",
        f"Interactive elements detected: {interactive_count}",
        "Key elements:",
        result.get("formatted", "No interactive elements found"),
        "Observe-browser semantics: page state and interactive structure only. Use browser_read_text for full visible page text or exact rendered values.",
    ]
    if result.get("bridge_fallback_reason"):
        lines.append(f"Bridge fallback: {result['bridge_fallback_reason']}")
    return "\n".join(lines)


def _execute_browser_click_ref(session, args: Dict) -> str:
    result = _run_browser_action(
        session,
        lambda browser, context: browser.click_by_ref(args["ref"], tab_id=context.primary_tab_id),
        lambda browser, context: browser.click_by_ref(args["ref"], tab_id=context.primary_tab_id),
    )
    if "error" in result:
        return _browser_action_error("Click ref error", result)
    return _browser_result_summary("Clicked element", result, detail=f"Target: ref={args['ref']}")


def _execute_browser_back(session, args: Dict) -> str:
    result = _run_browser_action(
        session,
        lambda browser, context: browser.back(tab_id=context.primary_tab_id),
        lambda browser, context: browser.back(tab_id=context.primary_tab_id),
    )
    if "error" in result:
        return _browser_action_error("Back error", result)
    return _browser_result_summary("Went back", result)


def _execute_browser_forward(session, args: Dict) -> str:
    result = _run_browser_action(
        session,
        lambda browser, context: browser.forward(tab_id=context.primary_tab_id),
        lambda browser, context: browser.forward(tab_id=context.primary_tab_id),
    )
    if "error" in result:
        return _browser_action_error("Forward error", result)
    return _browser_result_summary("Went forward", result)


def _execute_browser_switch_tab(session, args: Dict) -> str:
    index = args.get("index")
    if isinstance(index, str) and index.isdigit():
        index = int(index)

    result = _run_browser_action(
        session,
        lambda browser, context: browser.activate_tab(index=index),
        lambda browser, context: browser.activate_tab(index=index),
    )
    if "error" in result:
        return _browser_action_error("Switch tab error", result)
    return _browser_result_summary("Switched tab", result, detail=f"Index: {result.get('index')}")


def _execute_browser_list_tabs(session, args: Dict) -> str:
    result = _run_browser_action(
        session,
        lambda browser, context: browser.list_tabs(),
        lambda browser, context: browser.list_tabs(),
    )
    if "error" in result:
        return _browser_action_error("Tab list error", result)

    tabs = result.get("tabs", [])
    if not tabs:
        return "No browser tabs are open."

    lines = [f"Open browser tabs ({result.get('count', len(tabs))} total):"]
    for tab in tabs[:20]:
        marker = "*" if tab.get("active") else " "
        title = tab.get("title") or "(no title)"
        url = tab.get("url") or ""
        lines.append(f"{marker} [{tab.get('index')}] {title} - {url}")
    if len(tabs) > 20:
        lines.append(f"... and {len(tabs) - 20} more tabs")
    return "\n".join(lines)


def _execute_browser_activate_tab(session, args: Dict) -> str:
    index = args.get("index")
    if isinstance(index, str) and index.isdigit():
        index = int(index)

    tab_id = args.get("tab_id")
    if isinstance(tab_id, str) and tab_id.isdigit():
        tab_id = int(tab_id)

    result = _run_browser_action(
        session,
        lambda browser, context: browser.activate_tab(
            index=index,
            title_contains=args.get("title_contains"),
            url_contains=args.get("url_contains"),
            tab_id=tab_id,
        ),
        lambda browser, context: browser.activate_tab(
            index=index,
            title_contains=args.get("title_contains"),
            url_contains=args.get("url_contains"),
            tab_id=tab_id,
        ),
    )
    if "error" in result:
        return _browser_action_error("Activate tab error", result)

    return _browser_result_summary("Activated tab", result, detail=f"Index: {result.get('index')}")


def _execute_browser_close_tab(session, args: Dict) -> str:
    result = _run_browser_action(
        session,
        lambda browser, context: browser.close_tab(tab_id=context.primary_tab_id),
        lambda browser, context: browser.close_tab(tab_id=context.primary_tab_id),
    )
    if "error" in result:
        return _browser_action_error("Close tab error", result)
    return _browser_result_summary("Closed tab", result)


def _execute_browser_stop(session, args: Dict) -> str:
    browser = _get_browser_tool(session)
    result = browser.stop()
    if "error" in result:
        return _browser_action_error("Browser stop error", result)
    session.reset_browser_task_context(session.current_task_id)
    return "Browser stopped"


def _execute_search_memory(session, args: Dict) -> str:
    try:
        results = session.memory_manager.search_memory(
            args['query'],
            max_results=args.get('max_results', 5)
        )
        if not results:
            return f"No memory results found for: {args['query']}"
        output = []
        for r in results:
            location = f"{r['source']}:{r['line']}" if r.get("line") is not None else r["source"]
            output.append(f"**{location}**\n{r['content']}")
        return '\n\n---\n\n'.join(output)
    except Exception as e:
        return f"Error searching memory: {str(e)}"


def _execute_update_memory(session, args: Dict) -> str:
    try:
        updated = session.memory_manager.append_to_memory(args['section'], args['content'])
        if updated:
            return f"Updated {args['section']} in MEMORY.md"
        return f"No change made to {args['section']} in MEMORY.md"
    except Exception as e:
        return f"Error updating memory: {str(e)}"


def _execute_change_directory(session, args: Dict) -> str:
    try:
        path = Path(args['path'])
        if not path.is_absolute():
            path = (session.workspace / path).resolve()
        
        if not path.exists():
            return f"Directory not found: {path}"
        if not path.is_dir():
            return f"Not a directory: {path}"

        session.set_workspace(path)
        session.save_session()
        current_session_id = session.session_manager.get_current_session_id() if session.session_manager else None
        if current_session_id:
            origin_channel = "telegram" if getattr(session, "_app", None) else "app"
            get_channel_sync_hub().publish(
                user_id=int(session.user_id),
                event={
                    "type": "session_config",
                    "session_id": current_session_id,
                    "origin_channel": origin_channel,
                    "payload": {"setting": "workspace"},
                },
            )

        return f"Current working directory changed to: {path}"
    except Exception as e:
        return f"Error changing directory: {str(e)}"


def _execute_describe_screen(session, args: Dict) -> Dict:
    if not SCREEN_CAPTURE_AVAILABLE:
        return {"error": "Screenshot tools unavailable (missing mss/Pillow)"}
    
    try:
        with mss.mss() as sct:
            screenshot = sct.grab(sct.monitors[1])
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            
            # Save temp screenshot
            temp_dir = Path("temp")
            temp_dir.mkdir(exist_ok=True)
            path = temp_dir / f"screen_{int(time.time())}.png"
            img.save(path)
            
            with open(path, "rb") as f:
                base64_image = base64.b64encode(f.read()).decode('utf-8')
            
            return {
                "image_captured": True,
                "image_base64": base64_image,
                "description": "Screenshot captured successfully. I am now looking at the screen.",
                "metadata": {"path": str(path)}
            }
    except Exception as e:
        return {"error": f"Error describing screen: {str(e)}"}


def _execute_ocr_screen(session, args: Dict) -> str:
    if not OCR_AVAILABLE:
        return "OCR tools unavailable (missing pytesseract/Tesseract runtime)"
    
    try:
        with mss.mss() as sct:
            screenshot = sct.grab(sct.monitors[1])
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            elements = []
            for i in range(len(data['text'])):
                text = data['text'][i].strip()
                if text and int(data['conf'][i]) > 40:
                    elements.append({
                        "text": text,
                        "x": data['left'][i] + data['width'][i] // 2,
                        "y": data['top'][i] + data['height'][i] // 2
                    })
            
            text_summary = "\n".join([f"'{e['text']}' at ({e['x']}, {e['y']})" for e in elements[:100]])
            return f"OCR Elements found:\n{text_summary}"
    except Exception as e:
        return f"Error performing OCR: {normalize_tesseract_error(e, pytesseract_module=pytesseract)}"


def _execute_observe_desktop(session, args: Dict) -> str:
    if not PYWINAUTO_AVAILABLE:
        return "Desktop automation not available"
    
    try:
        desktop = Desktop(backend="uia")
        windows = []
        for win in desktop.windows():
            title = win.window_text()
            if title:
                windows.append(title)
        return "Open Windows:\n" + "\n".join(windows[:20])
    except Exception as e:
        return f"Error listing windows: {str(e)}"


def _execute_click(session, args: Dict) -> str:
    if not PYAUTOGUI_AVAILABLE: return "PyAutoGUI not available"
    try:
        # Robust parsing in case model sends strings or comma-separated values
        x_val = str(args['x']).split(',')[0].strip()
        y_val = str(args['y']).split(',')[0].strip()
        x, y = int(float(x_val)), int(float(y_val))
        
        pyautogui.click(x, y)
        return f"Clicked at ({x}, {y})"
    except Exception as e:
        return f"Error clicking: {str(e)}"


def _execute_right_click(session, args: Dict) -> str:
    if not PYAUTOGUI_AVAILABLE: return "PyAutoGUI not available"
    try:
        x_val = str(args['x']).split(',')[0].strip()
        y_val = str(args['y']).split(',')[0].strip()
        x, y = int(float(x_val)), int(float(y_val))
        pyautogui.rightClick(x, y)
        return f"Right-clicked at ({x}, {y})"
    except Exception as e:
        return f"Error right-clicking: {str(e)}"


def _execute_double_click(session, args: Dict) -> str:
    if not PYAUTOGUI_AVAILABLE: return "PyAutoGUI not available"
    try:
        x_val = str(args['x']).split(',')[0].strip()
        y_val = str(args['y']).split(',')[0].strip()
        x, y = int(float(x_val)), int(float(y_val))
        pyautogui.doubleClick(x, y)
        return f"Double-clicked at ({x}, {y})"
    except Exception as e:
        return f"Error double-clicking: {str(e)}"


def _execute_type_text(session, args: Dict) -> str:
    if not PYAUTOGUI_AVAILABLE: return "PyAutoGUI not available"
    try:
        pyautogui.write(args['text'], interval=0.01)
        return f"Typed: {args['text']}"
    except Exception as e:
        return f"Error typing: {str(e)}"


def _execute_press_key(session, args: Dict) -> str:
    if not PYAUTOGUI_AVAILABLE: return "PyAutoGUI not available"
    try:
        pyautogui.press(args['key'])
        return f"Pressed key: {args['key']}"
    except Exception as e:
        return f"Error pressing key: {str(e)}"


def _execute_hotkey(session, args: Dict) -> str:
    if not PYAUTOGUI_AVAILABLE: return "PyAutoGUI not available"
    try:
        keys = args['keys'].split('+')
        pyautogui.hotkey(*keys)
        return f"Pressed hotkey: {args['keys']}"
    except Exception as e:
        return f"Error pressing hotkey: {str(e)}"


def _execute_scroll(session, args: Dict) -> str:
    if not PYAUTOGUI_AVAILABLE: return "PyAutoGUI not available"
    try:
        amount = args.get('amount', 3)
        clicks = -amount if args['direction'] == 'up' else amount
        pyautogui.scroll(clicks)
        return f"Scrolled {args['direction']} {amount} units"
    except Exception as e:
        return f"Error scrolling: {str(e)}"


def _execute_open_app(session, args: Dict) -> str:
    if not PYAUTOGUI_AVAILABLE: return "PyAutoGUI not available"
    try:
        pyautogui.hotkey('win', 'r')
        time.sleep(0.5)
        pyautogui.write(args['name'])
        pyautogui.press('enter')
        return (
            f"Launch request sent for: {args['name']}. "
            "This does not confirm success; verify the resulting window or error state visually before assuming the app opened."
        )
    except Exception as e:
        return f"Error opening app: {str(e)}"


def _execute_focus_window(session, args: Dict) -> str:
    if not PYWINAUTO_AVAILABLE: return "pywinauto not available"
    try:
        desktop = Desktop(backend="uia")
        matches = [w for w in desktop.windows() if args['title'].lower() in w.window_text().lower()]
        if matches:
            matches[0].set_focus()
            return f"Focused window: {matches[0].window_text()}"
        return f"Window not found: {args['title']}"
    except Exception as e:
        return f"Error focusing window: {str(e)}"


def _execute_get_clipboard(session, args: Dict) -> str:
    if not PYPERCLIP_AVAILABLE: return "pyperclip not available"
    try:
        return f"Clipboard content: {pyperclip.paste()}"
    except Exception as e:
        return f"Error reading clipboard: {str(e)}"


def _execute_set_clipboard(session, args: Dict) -> str:
    if not PYPERCLIP_AVAILABLE: return "pyperclip not available"
    try:
        session.memory_manager.copy_to_clipboard(args['text'])
        return "Clipboard updated"
    except Exception as e:
        return f"Error setting clipboard: {str(e)}"


def _execute_spawn_sub_agent(session, args: Dict) -> str:
    if not session.spawn_tool:
        return "Spawn tool not initialized"
    try:
        prompt = args['prompt']
        headless = args.get('headless', True)
        # Use our session's loop to run the async spawn
        future = asyncio.run_coroutine_threadsafe(
            session.spawn_tool.spawn(prompt, headless=headless, max_turns=50, announce_on_complete=True),
            session._loop
        )
        task_id = future.result(timeout=10)
        return f"Spawned sub-agent task {task_id}. I'll announce when it completes."
    except Exception as e:
        return f"Error spawning sub-agent: {str(e)}"


def _execute_list_sub_agents(session, args: Dict) -> str:
    if not session.spawn_tool:
        return "Spawn tool not initialized"
    try:
        tasks = session.spawn_tool.list_tasks()
        if not tasks:
            return "No background tasks running"
        lines = []
        for t in tasks:
            lines.append(f"Task {t.id}: {t.status} - {t.prompt[:50]}...")
        return "Running Tasks:\n" + "\n".join(lines)
    except Exception as e:
        return f"Error listing tasks: {str(e)}"


def _execute_schedule_job(session, args: Dict) -> Dict[str, Any]:
    if not session.cron_scheduler:
        return {"error": "Cron scheduler not initialized"}
    try:
        interval, error = parse_schedule_with_error(args["schedule"])
        if error:
            return {"error": error}

        job_id = session.cron_scheduler.add_job(
            name=args["name"],
            prompt=args["prompt"],
            interval_seconds=interval,
            schedule_text=args["schedule"],
            timezone_offset_hours=2,
        )
        job = session.cron_scheduler.get_job(job_id)
        return {
            "success": True,
            "job_id": job_id,
            "job": job.to_dict() if job else None,
            "message": f"Job '{args['name']}' scheduled: {args['schedule']} (ID: {job_id})",
        }
    except Exception as e:
        return {"error": f"Error scheduling job: {str(e)}"}


def _execute_list_scheduled_jobs(session, args: Dict) -> Dict[str, Any]:
    if not session.cron_scheduler:
        return {"error": "Cron scheduler not initialized"}
    try:
        return session.cron_scheduler.get_status()
    except Exception as e:
        return {"error": f"Error listing jobs: {str(e)}"}


def _execute_get_scheduled_job(session, args: Dict) -> Dict[str, Any]:
    if not session.cron_scheduler:
        return {"error": "Cron scheduler not initialized"}
    try:
        job = session.cron_scheduler.get_job(args["job_id"])
        if not job:
            return {"error": f"Job {args['job_id']} not found"}
        return {"success": True, "job": job.to_dict()}
    except Exception as e:
        return {"error": f"Error getting job: {str(e)}"}


def _execute_update_scheduled_job(session, args: Dict) -> Dict[str, Any]:
    if not session.cron_scheduler:
        return {"error": "Cron scheduler not initialized"}
    try:
        interval = None
        schedule = args.get("schedule")
        if schedule is not None:
            interval, error = parse_schedule_with_error(schedule)
            if error:
                return {"error": error}

        success = session.cron_scheduler.update_job(
            args["job_id"],
            name=args.get("name"),
            prompt=args.get("prompt"),
            schedule_text=schedule,
            interval_seconds=interval,
            enabled=args.get("enabled"),
            timezone_offset_hours=2,
        )
        if not success:
            return {"error": f"Job {args['job_id']} not found"}
        job = session.cron_scheduler.get_job(args["job_id"])
        return {"success": True, "job": job.to_dict() if job else None}
    except Exception as e:
        return {"error": f"Error updating job: {str(e)}"}


def _execute_run_scheduled_job_now(session, args: Dict) -> Dict[str, Any]:
    if not session.cron_scheduler:
        return {"error": "Cron scheduler not initialized"}
    try:
        success = session.cron_scheduler.run_job_now(args["job_id"])
        if not success:
            return {"error": f"Job {args['job_id']} not found"}
        return {"success": True, "job_id": args["job_id"]}
    except Exception as e:
        return {"error": f"Error triggering job: {str(e)}"}


def _execute_remove_scheduled_job(session, args: Dict) -> Dict[str, Any]:
    if not session.cron_scheduler:
        return {"error": "Cron scheduler not initialized"}
    try:
        deleted = session.cron_scheduler.remove_job(args["job_id"])
        if not deleted:
            return {"error": f"Job {args['job_id']} not found"}
        return {"success": True, "job_id": args["job_id"]}
    except Exception as e:
        return {"error": f"Error removing job: {str(e)}"}


def _execute_enable_job(session, args: Dict) -> Dict[str, Any]:
    if not session.cron_scheduler:
        return {"error": "Cron scheduler not initialized"}
    try:
        success = session.cron_scheduler.enable_job(args["job_id"])
        if not success:
            return {"error": f"Job {args['job_id']} not found"}
        job = session.cron_scheduler.get_job(args["job_id"])
        return {"success": True, "job": job.to_dict() if job else None}
    except Exception as e:
        return {"error": f"Error enabling job: {str(e)}"}


def _execute_disable_job(session, args: Dict) -> Dict[str, Any]:
    if not session.cron_scheduler:
        return {"error": "Cron scheduler not initialized"}
    try:
        success = session.cron_scheduler.disable_job(args["job_id"])
        if not success:
            return {"error": f"Job {args['job_id']} not found"}
        job = session.cron_scheduler.get_job(args["job_id"])
        return {"success": True, "job": job.to_dict() if job else None}
    except Exception as e:
        return {"error": f"Error disabling job: {str(e)}"}
