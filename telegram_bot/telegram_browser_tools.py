"""Browser bridge and browser tool handlers for Telegram auto mode."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from local_agent_runtime.browser_tool import create_browser_tool
from local_agent_runtime.extension_tool import create_extension_tool

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
            "- browser_snapshot mainly reports interactive structure, refs, title, URL, and high-level page state. It is not a full page-text extraction tool.",
            "- For static content, headings, rendered text, and exact values on the current browser page, prefer browser_read_text. Use browser_wait_for(text_contains=...) to confirm appearance before reading when needed.",
            "- browser_screenshot captures proof and stored artifacts. Do NOT claim exact text or numeric values from browser_screenshot alone unless another tool extracted that text.",
            "- browser_read_text is the primary browser-native tool for visible page text, headings, labels, and exact rendered values.",
            "- browser_wait_for is for confirming that expected text, selectors, navigation, or load state appeared before you act or read.",
            "- browser_navigate controls the isolated browser instance and its headless/headed mode. It does not prove anything about the user's live Chrome session.",
            "- If you opened or navigated a browser page and the task depends on that visual result, verify the intended page state with browser_read_text, browser_snapshot, browser_wait_for, or browser_screenshot before assuming the page is ready.",
            "- If a browser window, page, or file should now be visibly open and browser-native evidence is still inconclusive, use browser_screenshot as visual proof before you assume that the intended browser result actually appeared.",
            "- If a browser snapshot, tab list, or other browser-native result already answers the question, do not escalate to screenshots, OCR, or desktop tools just to restate it.",
            "- If the task is naturally browser-first, stay in browser-native tools as long as they can still produce trustworthy evidence before falling back to desktop vision or desktop interaction.",
            "- If one browser-native method is inconclusive, try another browser-native method such as browser_read_text, browser_wait_for, or browser_snapshot before leaving the browser environment.",
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
