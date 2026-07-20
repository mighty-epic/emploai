from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


PACK_INTERACTIVE_DESKTOP = "interactive_desktop"
PACK_BROWSER_ISOLATED = "browser_isolated"
PACK_WORKSPACE_WRITE = "workspace_write"
PACK_WORKSPACE_READ = "workspace_read"
PACK_WEB_RESEARCH = "web_research"
PACK_SCHEDULER = "scheduler"
PACK_APP_RUNTIME = "app_runtime"
PACK_MANAGER_CORE = "manager_core"

MANAGER_CORE_FLEET_TOOLS = {
    "fleet_list_workers", "fleet_create_local_worker", "fleet_create_enrollment", "fleet_delegate",
    "fleet_context_search", "fleet_context_window", "fleet_list_computers", "fleet_delegate_computer",
    "fleet_create_worker_on_computer", "fleet_set_computer_manager_tools", "fleet_computer_host_status", "fleet_start_computer_runtime",
    "fleet_start_computer_desktop", "fleet_check_computer_update", "fleet_update_computer",
    "fleet_rename_worker", "fleet_reset_worker", "fleet_delete_worker", "fleet_list_groups",
    "fleet_create_group", "fleet_update_group", "fleet_delete_group", "fleet_assign_task",
    "fleet_assign_group_task", "fleet_send_worker_message", "fleet_send_group_message",
    "fleet_redirect_worker_task", "fleet_delete_queued_message", "fleet_steer_queued_message",
    "fleet_reorder_worker_queue", "fleet_continue_worker_queue", "fleet_update_task",
    "fleet_stop_worker", "fleet_stop_all", "fleet_inspect_worker", "fleet_search_reports",
    "fleet_read_report", "fleet_inspect_evidence", "fleet_open_worker_timeline",
    "fleet_request_worker_preview", "fleet_list_tool_grants", "fleet_decide_tool_grant",
    "fleet_check_workspace_binding", "fleet_request_workspace_reconnect",
}


@dataclass(frozen=True)
class ToolPackDefinition:
    id: str
    label: str
    description: str
    tool_names: Set[str]
    prompt_fragment: str
    interactive: bool = False
    workspace_write: bool = False


_CODING_DISCOVERY_CONTRACT = (
    "CODING CONTRACT - DISCOVERY\n"
    "- Read before editing or proposing code changes. Inspect the repository, relevant files, nearby call sites, configs, errors, docs, and tests before deciding what to do.\n"
    "- Use fast discovery tools first: grep_search, find_files, list_dir, read_file, or rg through command tools when command tools are enabled.\n"
    "- Follow the codebase's existing architecture, naming, helper APIs, style, and test patterns.\n"
    "- Identify the smallest safe change that satisfies the user request. Do not broaden into unrelated cleanup.\n"
    "- Before editing, think through what the change could break: routes, imports, callers, data flow, tests, UI state, public APIs, and persisted data.\n"
    "- Prefer structured parsers and existing helper APIs over fragile string manipulation.\n"
)


_CODING_EDIT_CONTRACT = (
    "CODING CONTRACT - EDITING\n"
    "- Keep changes focused and non-invasive. Do not perform unrelated refactors.\n"
    "- Avoid overcomplicating. Add an abstraction only when it removes real complexity, reduces meaningful duplication, or clearly matches an existing local pattern.\n"
    "- Separate new code or features when that keeps files clearer; do not overcrowd already-busy files.\n"
    "- Preserve user work. Never overwrite, revert, or discard unrelated changes, and do not assume dirty files are yours.\n"
    "- Avoid destructive commands unless the user explicitly asks for that operation.\n"
    "- Do not commit, push, create branches, or open PRs unless the user asks.\n"
)


_CODING_VERIFICATION_CONTRACT = (
    "CODING CONTRACT - VERIFICATION\n"
    "- Add or update focused tests when the risk or behavior change justifies it.\n"
    "- Run the most relevant available checks: targeted repros, tests, lint, typecheck, or build. If checks cannot be run, say so clearly.\n"
    "- Review the diff before reporting back. Look for broken imports, misrouted calls, stale routes, edge cases, and accidental unrelated changes.\n"
    "- When asked for review, prioritize bugs, regressions, missing tests, risky behavior, and file/line evidence.\n"
    "- Report what changed, what was verified, and any remaining risk or blocker.\n"
)


def _tool_name_from_definition(tool: Dict[str, Any]) -> str:
    if not isinstance(tool, dict):
        return ""
    if "function" in tool and isinstance(tool["function"], dict):
        return str(tool["function"].get("name") or "").strip()
    return str(tool.get("name") or "").strip()


_PACKS: Dict[str, ToolPackDefinition] = {
    PACK_INTERACTIVE_DESKTOP: ToolPackDefinition(
        id=PACK_INTERACTIVE_DESKTOP,
        label="Interactive Desktop",
        description="Vision, OCR, desktop input, window control, and user-Chrome/browser-extension tools.",
        tool_names={
            "describe_screen",
            "start_visual_monitor",
            "stop_visual_monitor",
            "ocr_screen",
            "observe_desktop",
            "open_file",
            "focus_window",
            "minimize_window",
            "maximize_window",
            "close_window",
            "click",
            "right_click",
            "double_click",
            "type_text",
            "press_key",
            "hotkey",
            "scroll",
            "drag_and_drop",
            "get_clipboard",
            "set_clipboard",
            "browser_extension_toggle",
            "browser_navigate",
            "browser_snapshot",
            "browser_read_text",
            "browser_click_ref",
            "browser_type",
            "browser_clear_ref",
            "browser_select_option_ref",
            "browser_press_key",
            "browser_wait_for",
            "browser_scroll",
            "browser_screenshot",
            "browser_back",
            "browser_forward",
            "browser_switch_tab",
            "browser_list_tabs",
            "browser_activate_tab",
            "browser_close_tab",
            "browser_stop",
            "wait",
        },
        prompt_fragment=(
            "PACK: Interactive Desktop\n"
            "- You are operating directly on the user's live desktop and browser contexts.\n"
            "- Always observe before acting, then verify after every mutating action.\n"
            "- App launches use run_command or run_background_command when workspace write/command tools are enabled; otherwise use visible desktop navigation/search. Verify the resulting window or error state before assuming the app opened.\n"
            "- For Windows app launches through run_command, choose the shell that matches the syntax: shell='powershell' for Start-Process, Get-Command, Resolve-Path, and Get-Location; shell='cmd' for start, where, and dir.\n"
            "- Match command syntax to the actual platform. On macOS/Linux use native open/which/ps/find-style equivalents instead of Windows shell commands, and on Windows avoid Unix shell assumptions unless that shell is explicitly selected.\n"
            "- For exact local file opening, prefer open_file(path, app?) with a resolved absolute path over manipulating a host app's Open dialog.\n"
            "- If a launch attempt shows a Windows error dialog, the wrong app, or no target window, treat that as failure and recover.\n"
            "- Use the current-user Chrome/extension path only when that environment is actually available.\n"
            "- Treat clicks, typing, and window changes as high-risk and verify each one immediately.\n"
            "- Do not chain interactive GUI actions without first verifying that the previous step landed correctly.\n"
            "- The user may move focus, click, or type while you work. Re-observe, correct the state, and continue.\n"
            "- Native desktop apps, including third-party apps, require interactive desktop tools and visual verification. Do not assume a hidden app-specific control path.\n"
            "- Any GUI without a dedicated tool path should be treated as a vision-and-interaction task.\n"
            "- For failed app, file, browser, or desktop actions, discover alternatives by inspecting available surfaces: existing windows, taskbar/dock icons, OS search/launcher, full paths or file associations, workspace files, installed commands, browser tabs, and trusted web equivalents.\n"
            "- Do not stop with an 'I can try next' final answer when a safe next route is available; take it and verify.\n"
            "- Prefer keyboard-first desktop interaction when a reliable shortcut or tab path can do the job more safely than clicking.\n"
            "- Before using hotkeys, press_key, type_text, Enter, Escape, Tab, or any key combo that affects the visible UI, make sure the intended target window, dialog, or control is focused; if focus is uncertain or another window is active, re-observe and focus the correct target before sending keys.\n"
            "- Do not use broad close shortcuts such as Alt+F4 for ambiguous cleanup. Use close_window with an exact target title, Escape/Cancel for a visible modal, or another targeted route.\n"
            "- Do not terminate broad process names to clean up a task. Prefer kill_command for agent-started background commands, an exact PID known to belong to this task, an exact window title, or a visible cancel/escape path.\n"
            "- Prefer broad visual observation before OCR, and use OCR mainly when exact text or coordinates are required.\n"
            "- describe_screen is the primary desktop verification and layout-understanding tool; use OCR after that when exact text or coordinates are needed.\n"
            "- For long uncertain visible waits, use start_visual_monitor with a fixed threshold preset instead of guessing or falsely reporting success. It is non-blocking: after starting it, you may keep working on other parts of the task or leave it running after your turn as a cheap wait handle.\n"
            "- If a visual monitor fires while you are still running, the runtime injects that event as system context on your next model turn; inspect with describe_screen before acting on it. If you are idle, it wakes you to continue.\n"
            "- No-change checkpoints are handled by the hidden runtime only while you are idle. Do not wait around just to service no-change checkpoints; continue useful work.\n"
            "- Stop a visual monitor only when the expected visual wait is no longer relevant. Only one visual monitor can be active at a time; starting a new monitor replaces the prior one.\n"
            "- When you call describe_screen for visual interpretation, ask a precise question about what changed, what should now be visible, what error or dialog might be present, or what control you need to identify.\n"
            "- observe_desktop tells you which windows exist and which one is active, but it does not replace visual verification of on-screen controls.\n"
            "- When you open an app or file visually, verify that the exact requested target actually appeared. Opening a host app alone is not proof that the requested file is open inside it, and a blank window, wrong document, wrong tab, wrong chat, or generic host UI is not success.\n"
            "- For desktop-visible opens and window changes, prefer describe_screen to confirm that the intended target actually appeared before you continue.\n"
            "- For isolated browser headings, static content, and exact rendered values, prefer browser_read_text over desktop OCR.\n"
            "- Browser-native evidence proves browser state only. Native desktop apps, Electron apps, local file-open state, and physical focus require desktop/window/file evidence.\n"
            "- Treat browser_screenshot as proof/artifact capture, not as exact text extraction inside the same turn.\n"
            "- Do not use desktop vision/OCR to reason about a headless isolated browser page.\n"
            "- If an isolated Selenium window is intentionally headed, use desktop vision/OCR on it only after verifying that window is actually the visible desktop target.\n"
        ),
        interactive=True,
    ),
    PACK_BROWSER_ISOLATED: ToolPackDefinition(
        id=PACK_BROWSER_ISOLATED,
        label="Browser Isolated",
        description="Isolated Selenium/browser automation without desktop interaction.",
        tool_names={
            "browser_navigate",
            "browser_snapshot",
            "browser_read_text",
            "browser_click_ref",
            "browser_type",
            "browser_clear_ref",
            "browser_select_option_ref",
            "browser_press_key",
            "browser_wait_for",
            "browser_scroll",
            "browser_screenshot",
            "browser_back",
            "browser_forward",
            "browser_switch_tab",
            "browser_list_tabs",
            "browser_activate_tab",
            "browser_close_tab",
            "browser_stop",
            "wait",
        },
        prompt_fragment=(
            "PACK: Browser Isolated\n"
            "- You are using the isolated automation browser only.\n"
            "- Prefer ref-based DOM interactions over synthetic keypresses.\n"
            "- Never assume control over the user's live Chrome unless the interactive desktop pack is also enabled.\n"
            "- If a task is naturally browser-first, stay in browser-native tools until they genuinely stop being sufficient.\n"
            "- browser_snapshot is mainly for interactive structure and page state, not full page-text extraction.\n"
            "- Prefer browser_read_text or browser_wait_for(text_contains=...) for static page text, headings, and exact rendered values.\n"
            "- browser_read_text is the primary browser-native tool for visible page text, headings, labels, and exact rendered values.\n"
            "- browser_wait_for is for confirming that expected text, selectors, navigation, or load state appeared before you act or read.\n"
            "- When you call browser_screenshot for visual interpretation, ask a precise question about what page, file, dialog, or error state you need verified instead of a vague screenshot request.\n"
            "- If you opened or navigated a browser page and the task depends on that visual result, verify the intended page state before assuming the page is ready.\n"
            "- If a browser page, browser-opened file, or browser window should now be visibly open and browser-native evidence is still inconclusive, use browser_screenshot as visual proof before assuming it appeared.\n"
            "- When the isolated Selenium browser is headless, desktop vision/OCR cannot inspect that page.\n"
            "- Browser-native evidence proves this browser context only. It does not prove that a native desktop app, separate Electron app, local file window, or desktop focus state changed.\n"
            "- browser_screenshot is for proof/artifacts; do not treat it as exact text extraction inside the same turn.\n"
            "- If a browser snapshot or DOM result already answers the question, do not escalate to screenshots or desktop tools.\n"
            "- If one browser-native method is inconclusive, try another browser-native method before leaving the browser environment.\n"
            "- Do not use run_command to spin side-channel browser scripts unless browser-native tools genuinely failed or are unavailable."
        ),
    ),
    PACK_WORKSPACE_WRITE: ToolPackDefinition(
        id=PACK_WORKSPACE_WRITE,
        label="Workspace Write",
        description="File editing and other workspace-mutating tools.",
        tool_names={
            "write_file",
            "edit_file",
            "append_file",
            "run_command",
            "run_background_command",
            "command_status",
            "send_input",
            "kill_command",
        },
        prompt_fragment=(
            "PACK: Workspace Write\n"
            "- You may change files and run mutating workspace commands.\n"
            "- Prefer write_file, edit_file, and append_file over shell-generated file edits when those tools are available.\n"
            "- run_command and run_background_command accept an optional shell parameter. On Windows, use shell='powershell' for PowerShell syntax such as Get-Location, Resolve-Path, Get-ChildItem, Get-Command, and Start-Process; use shell='cmd' for cmd.exe syntax such as dir, where, and start.\n"
            "- Use run_background_command for long-running or uncertain commands instead of blocking or guessing. You may leave task-owned background commands running after your turn so the runtime can wake you later.\n"
            "- The runtime can resume you on exit, readiness, meaningful output, or long-running no-progress checkpoints. The no-progress checkpoints happen at about 1 minute, 5 minutes, then every 10 minutes; a hidden planner decides whether to keep waiting or raise/wake the main agent.\n"
            "- Background command events follow the same principle as visual monitors: if you are already running, the runtime injects the command event as system context on your next model turn; if you are idle, it can resume the task.\n"
            "- Use command_status when you need current output now, and kill_command only for task-owned commands that should be stopped.\n"
            "- Match command syntax to the actual platform and selected shell; inspect the OS/current directory/available commands if uncertain.\n"
            "- To launch an app or open a file via command tools, use a direct full-path or app-specific command, then verify the visible result with desktop tools when available.\n"
            "- On Windows, prefer py before python3 and avoid Unix-specific shell patterns."
        ),
        workspace_write=True,
    ),
    PACK_WORKSPACE_READ: ToolPackDefinition(
        id=PACK_WORKSPACE_READ,
        label="Workspace Read",
        description="Read/search/diff/test and non-mutating workspace tools.",
        tool_names={
            "read_file",
            "list_dir",
            "find_files",
            "grep_search",
        },
        prompt_fragment=(
            "PACK: Workspace Read\n"
            "- You are in a read/inspect/test posture.\n"
            "- If the answer is already available from injected prompt context, do not spend file tools re-reading those context files."
        ),
    ),
    PACK_WEB_RESEARCH: ToolPackDefinition(
        id=PACK_WEB_RESEARCH,
        label="Web Research",
        description="Search and fetch web content.",
        tool_names={"web_search", "fetch_url"},
        prompt_fragment=(
            "PACK: Web Research\n"
            "- Focus on finding current source-backed information efficiently.\n"
            "- Summarize only what is relevant to the task at hand.\n"
            "- Stop once the requested facts are verified from sufficient evidence, and do not broaden into adjacent categories unless asked."
        ),
    ),
    PACK_SCHEDULER: ToolPackDefinition(
        id=PACK_SCHEDULER,
        label="Scheduler",
        description="Cron and recurring job operations.",
        tool_names={
            "schedule_job",
            "list_scheduled_jobs",
            "get_scheduled_job",
            "update_scheduled_job",
            "run_scheduled_job_now",
            "remove_scheduled_job",
            "enable_job",
            "disable_job",
        },
        prompt_fragment=(
            "PACK: Scheduler\n"
            "- You may create and manage recurring jobs.\n"
            "- Preserve the originating chat context and route outputs back to the correct cron feed and Telegram bot."
        ),
    ),
    PACK_APP_RUNTIME: ToolPackDefinition(
        id=PACK_APP_RUNTIME,
        label="App Runtime",
        description="Session/runtime coordination tools that are safe for the chat.",
        tool_names={
            "search_memory",
            "update_memory",
        },
        prompt_fragment=(
            "PACK: App Runtime\n"
            "- You may reason about app/runtime/session state, but still prefer task-local changes and explicit verification."
        ),
    ),
    PACK_MANAGER_CORE: ToolPackDefinition(
        id=PACK_MANAGER_CORE,
        label="Manager Core",
        description="Role-locked orchestration, memory, automation, and scheduler operations.",
        tool_names={
            "search_memory",
            "update_memory",
            "schedule_job",
            "list_scheduled_jobs",
            "get_scheduled_job",
            "update_scheduled_job",
            "run_scheduled_job_now",
            "remove_scheduled_job",
            "enable_job",
            "disable_job",
        } | MANAGER_CORE_FLEET_TOOLS,
        prompt_fragment=(
            "PACK: Manager Core\n"
            "- You coordinate work through explicit local or child-computer routes.\n"
            "- Answer conversational requests directly and delegate execution work when the required optional pack is not enabled on this manager or the user explicitly asks for a worker.\n"
            "- Every delegation tool request carries its route scope; never rely on a mutable ambient mode.\n"
            "- Workers remain the default execution identities; optional manager execution packs grant direct use of only their listed tools."
        ),
    ),
}

DEFAULT_TOOL_PACKS: List[str] = [pack_id for pack_id in _PACKS if pack_id != PACK_MANAGER_CORE]


def all_tool_packs() -> List[ToolPackDefinition]:
    return list(_PACKS.values())


def pack_ids() -> List[str]:
    return list(_PACKS.keys())


def get_tool_pack(pack_id: str) -> Optional[ToolPackDefinition]:
    return _PACKS.get(str(pack_id or "").strip())


def normalize_enabled_tool_packs(value: Optional[Sequence[str]]) -> List[str]:
    if not value:
        return []
    normalized: List[str] = []
    seen: Set[str] = set()
    for item in value:
        pack_id = str(item or "").strip()
        if not pack_id or pack_id not in _PACKS or pack_id in seen:
            continue
        normalized.append(pack_id)
        seen.add(pack_id)
    return normalized


def default_enabled_tool_packs() -> List[str]:
    return list(DEFAULT_TOOL_PACKS)


def _enabled_definitions(enabled_packs: Sequence[str]) -> List[ToolPackDefinition]:
    return [
        _PACKS[pack_id]
        for pack_id in normalize_enabled_tool_packs(enabled_packs)
        if pack_id in _PACKS
    ]


def tools_for_enabled_packs(enabled_packs: Sequence[str]) -> Set[str]:
    allowed: Set[str] = set()
    for definition in _enabled_definitions(enabled_packs):
        allowed.update(definition.tool_names)
    return allowed


def filter_openai_tools_by_enabled_packs(
    tools: Iterable[Dict[str, Any]],
    enabled_packs: Sequence[str],
) -> List[Dict[str, Any]]:
    return filter_tools_by_enabled_packs(tools, enabled_packs)


def filter_tools_by_enabled_packs(
    tools: Iterable[Dict[str, Any]],
    enabled_packs: Sequence[str],
) -> List[Dict[str, Any]]:
    allowed = tools_for_enabled_packs(enabled_packs)
    if not allowed:
        return []

    filtered: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for tool in tools:
        name = _tool_name_from_definition(tool)
        if not name or name in seen or name not in allowed:
            continue
        filtered.append(tool)
        seen.add(name)
    return filtered


def _prompt_fragment_lines(content: str) -> list[str]:
    return [line.strip() for line in str(content or "").splitlines() if line.strip()]


def build_tool_pack_prompt(enabled_packs: Sequence[str]) -> str:
    definitions = _enabled_definitions(enabled_packs)
    enabled_ids = {definition.id for definition in definitions}
    lines: List[str] = [
        "# TOOL-PACK AUTHORITY",
        "- The enabled packs listed below are the only pack-scoped tool capabilities available in this chat.",
        "- The runtime may separately attach contextual tools for the current identity or workflow, such as Fleet manager tools. A contextual tool is available only when it is present in your callable tool schema or explicitly described by another system contract.",
        "- If a pack or tool is neither listed below nor separately attached as a contextual tool, you do NOT have it here. Do not mention it as available, plan around it, or pretend you can use it.",
        "- If the user asks what tools you have, include the enabled packs and any separately attached contextual tools that are actually available.",
        "- When a task needs a disabled capability that is not separately attached, say it is unavailable in the current configuration instead of hallucinating access.",
        "- AGENTS.md, SOUL.md, USER.md, TOOLS.md, and MEMORY.md are already injected into prompt context when available. Do not spend file-search or file-read tool calls trying to rediscover them during normal execution.",
        "- Do not read MEMORY.md just to begin work. Touch memory only when you are intentionally saving durable reusable information.",
        "- If a local dependency, runtime, app launch path, file association, or other safely repairable environment detail is broken, repair it and continue instead of treating it as a blocker.",
        "- Prefer reversible, task-scoped repairs before broader machine changes. Avoid global installs, default-app changes, registry or PATH edits, deleting user data, killing unrelated processes, or closing the user's apps, tabs, or documents unless the task clearly requires it or the user asked for it.",
        "- Save durable reusable insights about websites, apps, and workflows to memory. Save durable account facts, usernames, emails, profile choices, login requirements, and persistent personal information that helps future tasks, but never store raw secrets such as passwords, tokens, API keys, or 2FA codes in MEMORY.md.",
        "- If the injected skills index lists a relevant specialized skill for a complex or domain-specific task, use pull_skill before improvising a long workflow from scratch.",
    ]

    if not definitions:
        lines.extend(
            [
                "",
                "## Enabled Packs",
                "- None. No callable tool packs are enabled for this chat right now.",
            ]
        )
        return "\n".join(lines)

    if PACK_WORKSPACE_WRITE in enabled_ids:
        lines.extend(["", "## Coding Agent Contract"])
        lines.extend(_prompt_fragment_lines(_CODING_DISCOVERY_CONTRACT))
        lines.extend(_prompt_fragment_lines(_CODING_EDIT_CONTRACT))
        lines.extend(_prompt_fragment_lines(_CODING_VERIFICATION_CONTRACT))
    elif PACK_WORKSPACE_READ in enabled_ids:
        lines.extend(["", "## Coding Agent Contract"])
        lines.extend(_prompt_fragment_lines(_CODING_DISCOVERY_CONTRACT))
        lines.append("- In this read-only tool-pack configuration, inspect and produce a decision-ready explanation, plan, or review instead of changing files.")
        lines.extend(_prompt_fragment_lines(_CODING_VERIFICATION_CONTRACT))

    for definition in definitions:
        tool_names = sorted(definition.tool_names)
        guidance_lines = _prompt_fragment_lines(definition.prompt_fragment)
        if guidance_lines and guidance_lines[0].startswith("PACK:"):
            guidance_lines = guidance_lines[1:]

        lines.extend(
            [
                "",
                f"## Enabled Pack: {definition.label}",
                f"- Description: {definition.description}",
                (
                    "- Callable tools: " + ", ".join(tool_names)
                    if tool_names
                    else "- Callable tools: none. This pack only changes runtime/session reasoning constraints."
                ),
            ]
        )
        lines.extend(guidance_lines)

    return "\n".join(lines)


def pack_requires_interactive(pack_id: str) -> bool:
    definition = _PACKS.get(pack_id)
    return bool(definition and definition.interactive)


def pack_requires_workspace_write(pack_id: str) -> bool:
    definition = _PACKS.get(pack_id)
    return bool(definition and definition.workspace_write)


def enabled_pack_requires_interactive(enabled_packs: Sequence[str]) -> bool:
    return any(pack_requires_interactive(pack_id) for pack_id in normalize_enabled_tool_packs(enabled_packs))


def enabled_pack_requires_workspace_write(enabled_packs: Sequence[str]) -> bool:
    return any(pack_requires_workspace_write(pack_id) for pack_id in normalize_enabled_tool_packs(enabled_packs))
