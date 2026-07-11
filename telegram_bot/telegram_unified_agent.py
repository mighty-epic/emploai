"""
Unified agent helpers for the Telegram agent.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List

try:
    from telegram_bot import telegram_browser_tools as _browser_tools
    from telegram_bot import telegram_runtime_tools as _runtime_tools
except ImportError:
    import telegram_browser_tools as _browser_tools
    import telegram_runtime_tools as _runtime_tools

_BROWSER_TOOL_NAMES = (
    "FAILOVER_ERROR_TYPES",
    "_bridge_enabled",
    "ensure_extension_bridge",
    "_get_selenium_tool",
    "_configured_selenium_mode",
    "_get_browser_tool",
    "_extension_status_ready",
    "get_browser_bridge_status",
    "build_browser_runtime_prompt",
    "_should_failover_browser_result",
    "_browser_tools_blocked_for_user_chrome_task",
    "_blocked_user_chrome_browser_result",
    "_run_browser_action",
    "_browser_action_error",
    "_browser_result_summary",
    "_execute_browser_extension_toggle",
    "_execute_browser_navigate",
    "_execute_browser_click",
    "_execute_browser_type",
    "_execute_browser_clear_ref",
    "_execute_browser_select_option_ref",
    "_execute_browser_press_key",
    "_execute_browser_wait_for",
    "_execute_browser_scroll",
    "_execute_browser_screenshot",
    "_execute_browser_snapshot",
    "_execute_browser_read_text",
    "_execute_observe_browser",
    "_execute_browser_click_ref",
    "_execute_browser_back",
    "_execute_browser_forward",
    "_execute_browser_switch_tab",
    "_execute_browser_list_tabs",
    "_execute_browser_activate_tab",
    "_execute_browser_close_tab",
    "_execute_browser_stop",
)
for _browser_name in _BROWSER_TOOL_NAMES:
    globals()[_browser_name] = getattr(_browser_tools, _browser_name)

_RUNTIME_DIRECT_TOOL_NAMES = (
    "_execute_search_memory",
    "_execute_update_memory",
    "_execute_change_directory",
    "_execute_spawn_sub_agent",
    "_execute_list_sub_agents",
    "_execute_schedule_job",
    "_execute_list_scheduled_jobs",
    "_execute_get_scheduled_job",
    "_execute_update_scheduled_job",
    "_execute_run_scheduled_job_now",
    "_execute_remove_scheduled_job",
    "_execute_enable_job",
    "_execute_disable_job",
)
for _runtime_name in _RUNTIME_DIRECT_TOOL_NAMES:
    globals()[_runtime_name] = getattr(_runtime_tools, _runtime_name)

pyautogui = _runtime_tools.pyautogui
PYAUTOGUI_AVAILABLE = _runtime_tools.PYAUTOGUI_AVAILABLE
PYAUTOGUI_IMPORT_ERROR = _runtime_tools.PYAUTOGUI_IMPORT_ERROR
Desktop = _runtime_tools.Desktop
PYWINAUTO_AVAILABLE = _runtime_tools.PYWINAUTO_AVAILABLE
PYWINAUTO_IMPORT_ERROR = _runtime_tools.PYWINAUTO_IMPORT_ERROR
mss = _runtime_tools.mss
Image = _runtime_tools.Image
SCREEN_CAPTURE_AVAILABLE = _runtime_tools.SCREEN_CAPTURE_AVAILABLE
pytesseract = _runtime_tools.pytesseract
OCR_AVAILABLE = _runtime_tools.OCR_AVAILABLE
TESSERACT_AVAILABLE = _runtime_tools.TESSERACT_AVAILABLE
pyperclip = getattr(_runtime_tools, "pyperclip", None)
PYPERCLIP_AVAILABLE = _runtime_tools.PYPERCLIP_AVAILABLE

_RUNTIME_GLOBAL_NAMES = (
    "pyautogui",
    "PYAUTOGUI_AVAILABLE",
    "PYAUTOGUI_IMPORT_ERROR",
    "Desktop",
    "PYWINAUTO_AVAILABLE",
    "PYWINAUTO_IMPORT_ERROR",
    "mss",
    "Image",
    "SCREEN_CAPTURE_AVAILABLE",
    "pytesseract",
    "OCR_AVAILABLE",
    "TESSERACT_AVAILABLE",
    "pyperclip",
    "PYPERCLIP_AVAILABLE",
)


def _sync_runtime_tool_globals() -> None:
    for name in _RUNTIME_GLOBAL_NAMES:
        setattr(_runtime_tools, name, globals()[name])


def _runtime_desktop_tool(name: str, session, args: Dict):
    _sync_runtime_tool_globals()
    return getattr(_runtime_tools, name)(session, args)


def _execute_describe_screen(session, args: Dict) -> Dict:
    return _runtime_desktop_tool("_execute_describe_screen", session, args)


def _execute_ocr_screen(session, args: Dict) -> str:
    return _runtime_desktop_tool("_execute_ocr_screen", session, args)


def _execute_observe_desktop(session, args: Dict) -> str:
    return _runtime_desktop_tool("_execute_observe_desktop", session, args)


def _execute_click(session, args: Dict) -> str:
    return _runtime_desktop_tool("_execute_click", session, args)


def _execute_right_click(session, args: Dict) -> str:
    return _runtime_desktop_tool("_execute_right_click", session, args)


def _execute_double_click(session, args: Dict) -> str:
    return _runtime_desktop_tool("_execute_double_click", session, args)


def _execute_type_text(session, args: Dict) -> str:
    return _runtime_desktop_tool("_execute_type_text", session, args)


def _execute_press_key(session, args: Dict) -> str:
    return _runtime_desktop_tool("_execute_press_key", session, args)


def _execute_hotkey(session, args: Dict) -> str:
    return _runtime_desktop_tool("_execute_hotkey", session, args)


def _execute_scroll(session, args: Dict) -> str:
    return _runtime_desktop_tool("_execute_scroll", session, args)


def _execute_open_app(session, args: Dict) -> str:
    return _runtime_desktop_tool("_execute_open_app", session, args)


def _execute_focus_window(session, args: Dict) -> str:
    return _runtime_desktop_tool("_execute_focus_window", session, args)


def _execute_get_clipboard(session, args: Dict) -> str:
    return _runtime_desktop_tool("_execute_get_clipboard", session, args)


def _execute_set_clipboard(session, args: Dict) -> str:
    return _runtime_desktop_tool("_execute_set_clipboard", session, args)

from telegram.constants import ParseMode
from cli.agent_tools.web_tools import duckduckgo_search
from shared import (
    create_unified_agent,
    get_heartbeat_manager,
)
from shared.task_board import TASK_BOARD_INTERNAL_TOOL_NAME, build_task_board_prompt, get_active_task_board
from shared.prompt_layers import (
    active_skills_section,
    assistant_response_policy_section,
    join_prompt_sections,
    local_custom_instructions_section,
    memory_context_section,
    project_onboarding_section,
    skills_index_section,
)
from shared.project_onboarding import project_onboarding_prompt_for_session
from shared.tool_packs import (
    PACK_BROWSER_ISOLATED,
    PACK_INTERACTIVE_DESKTOP,
    PACK_SCHEDULER,
    build_tool_pack_prompt,
)
from local_agent_runtime.cron_scheduler import CRON_TOOL_DEFINITIONS


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
- Match command syntax to the actual platform and selected shell. On Windows, use PowerShell cmdlets with shell='powershell' and cmd.exe built-ins with shell='cmd'; on macOS/Linux use native `open`, `which`, `ps`, and `find` style equivalents instead of Windows shell commands.
- Command tools run hidden by default. Use visible_terminal=true only when the user explicitly asks to see or interact with a terminal window.
- Use the workspace/root path from the WORKSPACE/PATH RUNTIME STATUS section for file-grounding. Relative paths from file tools are workspace-relative; native desktop Open/Save dialogs usually are not.
- Before typing a path into a desktop file picker or opening a saved file through a host app, resolve the exact absolute path with available file or command tools. Do not guess locations such as Downloads or `C:\\Users\\Public`.
- If the current directory is uncertain, inspect it first with available tools such as `list_dir('.')`, `find_files`, or a shell-specific command. With run_command on Windows, set shell='powershell' for `Get-Location` or `Resolve-Path`, and shell='cmd' for `dir`.
- For desktop launches, window switches, clicks, typing, and other physical desktop actions, treat the action as an attempt until the resulting state is visually verified.
- App launches do not prove an app opened. If command tools are available, use run_command or run_background_command with the shell that matches the syntax, then verify. If a launch produces an error dialog, the wrong window, or no target window, treat that as failure and recover.
- Do not terminate broad process names to clean up a task. Prefer kill_command for commands you started, an exact PID known to belong to the task, an exact window title, or a visible cancel/escape path.
- Do not final-answer while the task is incomplete and a safe next route exists; take the next safe route instead of saying you can try it.
- For failed app, file, browser, or desktop actions, discover alternatives from current state and available surfaces such as existing windows, taskbar/dock icons, OS launcher/search, full paths, file associations, workspace files, installed commands, browser tabs, and trusted web equivalents.
- The user may move focus, click, or type while you work. Do not panic or stop. Re-observe, correct the state, and continue the task.
- Use the chain of escalation and degradation for tools. If a task is naturally browser-first, stay in the browser toolchain until browser-native methods genuinely stop being sufficient, then fall back to desktop vision and interactive tools only as needed.
- Native desktop apps, including third-party apps, require interactive desktop tools and visual verification. Do not assume a hidden app-specific control path.
- Any GUI without a dedicated tool path should be treated as a vision-and-interaction task. For Chrome or browser tasks, use browser tools when the runtime says that path is valid; otherwise fall back to desktop vision and interactive tools.
- When you open an app, browser window, or file in a visually-presented way, verify that the exact requested target actually became visible. Opening a host app like Notepad is not proof that the requested file opened inside it, and a blank window, wrong document, wrong tab, wrong chat, or generic host UI is not success.
- For desktop-visible opens and window changes, prefer describe_screen to confirm that the intended target actually appeared. For browser-visible results, prefer browser-native verification and use browser_screenshot as proof when it is available and the task still needs visual confirmation.
- Browser-native evidence proves browser state only. Native desktop apps, Electron apps, local file-open state, and physical focus require desktop/window/file evidence such as describe_screen, observe_desktop, OCR, open_file, or exact OS command output.
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
            "- If the current directory or target file path is uncertain, use available workspace or command tools to inspect it before typing into a GUI. With run_command on Windows, set shell='powershell' for `Get-Location` or `Resolve-Path <relative-path>`, and shell='cmd' for `dir`.",
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


AUTO_MODE_MEMORY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "Search local MEMORY.md, recent daily logs, and mirrored local memory facts for durable context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for durable local memory."},
                    "max_results": {"type": "integer", "description": "Maximum number of results to return."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_memory",
            "description": "Append a durable reusable fact, preference, workflow lesson, or project note to local MEMORY.md. Do not store secrets or one-off transient state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "section": {"type": "string", "description": "MEMORY.md section to update, such as User Preferences, Context, or Lessons Learned."},
                    "content": {"type": "string", "description": "Markdown content to append. Prefer a concise bullet beginning with '-'."},
                },
                "required": ["section", "content"],
            },
        },
    },
]


def get_auto_mode_extra_tools() -> List[Dict[str, Any]]:
    return list(AUTO_MODE_BROWSER_TOOLS) + list(AUTO_MODE_MEMORY_TOOLS) + list(CRON_TOOL_DEFINITIONS)


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
        "search_memory": lambda args: _execute_search_memory(session, args),
        "update_memory": lambda args: _execute_update_memory(session, args),
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
            "- App launches only submit launch requests until verified. If command tools are available, use run_command or run_background_command with the matching shell, then visually verify the resulting app/window.",
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
    custom_prompt_append = ""
    live_config = getattr(session, "live_config", None)
    if live_config:
        custom_prompt_append = str(live_config.get("agent.custom_system_prompt_append", "") or "").strip()
    project_onboarding_prompt = project_onboarding_prompt_for_session(session)
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
        assistant_response_policy_section(),
        project_onboarding_section(project_onboarding_prompt) if project_onboarding_prompt else "",
        local_custom_instructions_section(custom_prompt_append) if custom_prompt_append else "",
        workspace_context.strip() if workspace_context else "",
        memory_context_section(memory_context) if memory_context else "",
        skills_index_section(skills_index) if skills_index else "",
        active_skills_section(active_skills_context) if active_skills_context else "",
    ]
    system_prompt = join_prompt_sections(sections)
    return system_prompt.replace("{{SYSTEM_INFO}}", session.system_info)
