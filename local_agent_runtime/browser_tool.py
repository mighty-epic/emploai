"""
Browser Tool - Selenium wrapper with ARIA snapshots.
Inspired by Moltbot's pw-role-snapshot.ts
Supports headless/headed mode via HEADLESS env var.
"""

from __future__ import annotations

import base64
import os
import time
from typing import Any, Dict, List, Optional

from local_agent_runtime.browser_actions import browser_error, browser_success, stable_snapshot_hash

try:
    from selenium import webdriver
    from selenium.common.exceptions import NoSuchElementException, WebDriverException
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select, WebDriverWait
    from webdriver_manager.chrome import ChromeDriverManager

    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


ARIA_SNAPSHOT_JS = r"""
function getAriaSnapshot() {
    const INTERACTIVE_ROLES = [
        'button', 'link', 'textbox', 'checkbox', 'radio', 'menuitem',
        'menuitemcheckbox', 'menuitemradio', 'option', 'tab', 'treeitem',
        'searchbox', 'spinbutton', 'switch', 'combobox', 'slider', 'input'
    ];
    const INTERACTIVE_TAGS = new Set(['BUTTON', 'A', 'INPUT', 'TEXTAREA', 'SELECT']);

    const results = [];
    let refCounter = 1;

    function isVisible(node) {
        if (!(node instanceof Element)) return false;
        const style = window.getComputedStyle(node);
        return style.display !== 'none' &&
               style.visibility !== 'hidden' &&
               style.opacity !== '0' &&
               node.offsetWidth > 0 &&
               node.offsetHeight > 0;
    }

    function getAccessibleName(node) {
        const labelledBy = (node.getAttribute('aria-labelledby') || '')
            .split(/\s+/)
            .filter(Boolean)
            .map(id => document.getElementById(id))
            .filter(Boolean)
            .map(el => el.innerText || el.textContent || '');

        const candidates = [
            node.getAttribute('aria-label'),
            labelledBy.join(' '),
            node.innerText,
            node.textContent,
            node.getAttribute('placeholder'),
            node.getAttribute('value'),
            node.getAttribute('title'),
            node.getAttribute('name'),
            node.getAttribute('alt'),
            node.id
        ];

        for (const candidate of candidates) {
            const clean = String(candidate || '').replace(/\\s+/g, ' ').trim();
            if (clean) {
                return clean.substring(0, 100);
            }
        }

        return '';
    }

    function traverse(node, depth = 0) {
        if (!node || depth > 50) return;

        if (node instanceof Element) {
            const role = node.getAttribute('role') || node.tagName.toLowerCase();
            const isInteractive = INTERACTIVE_ROLES.includes(role) || INTERACTIVE_TAGS.has(node.tagName);

            if (isInteractive && isVisible(node)) {
                const cleanText = getAccessibleName(node);

                if (cleanText || INTERACTIVE_TAGS.has(node.tagName)) {
                    const ref = refCounter++;
                    node.setAttribute('data-aria-ref', ref.toString());

                    results.push({
                        ref: ref,
                        role: role,
                        name: cleanText,
                        enabled: !node.disabled,
                        checked: node.checked || false
                    });
                }
            }

            if (node.shadowRoot) {
                traverse(node.shadowRoot, depth + 1);
            }
        }

        const children = node.children || [];
        for (const child of children) {
            if (child instanceof Element || child instanceof ShadowRoot) {
                traverse(child, depth + 1);
            }
        }
    }

    traverse(document.body);
    return results;
}

return getAriaSnapshot();
"""


class BrowserTool:
    """Selenium-based browser tool with ARIA snapshots."""

    def __init__(self, headless: Optional[bool] = None):
        self.driver: Optional[webdriver.Chrome] = None
        self.headless = self._get_headless_mode(headless)
        self.snapshot_cache: Optional[List[Dict[str, Any]]] = None
        self.last_url: Optional[str] = None

    def _get_headless_mode(self, headless: Optional[bool]) -> bool:
        if headless is not None:
            return headless

        env_headless = os.getenv("HEADLESS", "").lower()
        if env_headless in ("true", "1", "yes", "on"):
            return True
        if env_headless in ("false", "0", "no", "off"):
            return False
        return True

    def _configure_mode(self, headless: Optional[bool]) -> None:
        if headless is None:
            return
        desired = bool(headless)
        if desired == self.headless:
            return
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
        self.headless = desired

    def start(self) -> Dict[str, Any]:
        """Start the browser driver."""
        if not SELENIUM_AVAILABLE:
            return browser_error(
                "selenium",
                "Selenium not available. Install: pip install selenium webdriver-manager",
                error_type="command",
            )

        if self.driver:
            return {"status": "already_running", "backend": "selenium"}

        try:
            options = Options()
            if self.headless:
                options.add_argument("--headless=new")

            options.add_argument("--no-sandbox")
            options.add_argument("--start-maximized")
            options.add_argument("--log-level=3")
            options.add_argument("--disable-logging")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_experimental_option("excludeSwitches", ["enable-logging"])

            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            return {"status": "started", "backend": "selenium", "mode": self.get_current_mode()}
        except Exception as exc:
            return browser_error("selenium", str(exc), error_type="command")

    def stop(self) -> Dict[str, Any]:
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
        return {"status": "stopped", "backend": "selenium"}

    def _ensure_driver(self, *, headless: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        self._configure_mode(headless)
        if self.driver:
            return None
        result = self.start()
        if "error" in result:
            return result
        return None

    def _wait_for_ready(self, timeout: float = 10.0):
        if not self.driver:
            return
        WebDriverWait(self.driver, timeout).until(
            lambda driver: driver.execute_script("return document.readyState") in ("interactive", "complete")
        )

    def _switch_to_tab(self, tab_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not self.driver:
            return browser_error("selenium", "No browser open", error_type="command")

        if tab_id is None:
            return None

        try:
            handles = self.driver.window_handles
            if tab_id not in handles:
                return browser_error("selenium", f"Tab id {tab_id} not found.", error_type="command")
            self.driver.switch_to.window(tab_id)
            return None
        except Exception as exc:
            return browser_error("selenium", str(exc), error_type="command")

    def _format_snapshot(self, elements: List[Dict[str, Any]]) -> str:
        lines = [f"- {el['role']} \"{el['name']}\" [ref={el['ref']}]" for el in elements if el.get("name")]
        return "\n".join(lines) if lines else "No interactive elements found"

    def _snapshot_elements(self) -> List[Dict[str, Any]]:
        if not self.driver:
            return []
        elements = self.driver.execute_script(ARIA_SNAPSHOT_JS) or []
        self.snapshot_cache = elements
        return elements

    def _get_focused_ref(self) -> Optional[int]:
        if not self.driver:
            return None
        try:
            focused_ref = self.driver.execute_script(
                """
                const active = document.activeElement;
                if (!active) return null;
                const ref = active.getAttribute('data-aria-ref');
                return ref ? Number(ref) : null;
                """
            )
            return int(focused_ref) if focused_ref is not None else None
        except Exception:
            return None

    def _get_state(self, tab_id: Optional[str] = None) -> Dict[str, Any]:
        setup_error = self._ensure_driver()
        if setup_error:
            return setup_error

        switch_error = self._switch_to_tab(tab_id)
        if switch_error:
            return switch_error

        if not self.driver:
            return browser_error("selenium", "No browser open", error_type="command")

        try:
            self._wait_for_ready(timeout=5.0)
        except Exception:
            pass

        elements: List[Dict[str, Any]] = []
        formatted = ""
        snapshot_hash = None
        try:
            elements = self._snapshot_elements()
            formatted = self._format_snapshot(elements)
            snapshot_hash = stable_snapshot_hash(formatted, elements)
        except Exception:
            pass

        try:
            current_handle = self.driver.current_window_handle
        except Exception as exc:
            return browser_error("selenium", str(exc), error_type="command")

        try:
            url = self.driver.current_url
        except Exception:
            url = None

        try:
            title = self.driver.title
        except Exception:
            title = ""

        return {
            "tab_id": current_handle,
            "window_id": current_handle,
            "url": url,
            "title": title,
            "mode": self.get_current_mode(),
            "snapshot_hash": snapshot_hash,
            "interactive_count": len(elements),
            "focused_ref": self._get_focused_ref(),
            "formatted": formatted,
            "elements": elements,
        }

    def _detect_state_change(self, before: Dict[str, Any], after: Dict[str, Any]) -> Optional[str]:
        if after.get("tab_id") != before.get("tab_id"):
            return "tab_replaced"
        if after.get("url") != before.get("url"):
            return "url_changed"
        if after.get("title") != before.get("title"):
            return "title_changed"
        if after.get("snapshot_hash") != before.get("snapshot_hash"):
            return "snapshot_changed"
        return None

    def _wait_for_observed_change(self, before: Dict[str, Any], tab_id: Optional[str], timeout_seconds: float = 10.0) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        last_state = before

        while time.monotonic() < deadline:
            state = self._get_state(tab_id)
            if "error" in state:
                return state

            last_state = state
            wait_reason = self._detect_state_change(before, state)
            if wait_reason:
                state["wait_reason"] = wait_reason
                return state
            time.sleep(0.25)

        last_state = dict(last_state)
        last_state["wait_reason"] = "timeout_no_change"
        return last_state

    def _find_ref_element(self, ref: int):
        if not self.driver:
            raise NoSuchElementException("No browser open")

        selector = f"[data-aria-ref='{ref}']"
        try:
            return self.driver.find_element(By.CSS_SELECTOR, selector)
        except NoSuchElementException:
            self._snapshot_elements()
            return self.driver.find_element(By.CSS_SELECTOR, selector)

    def _focus_ref(self, ref: int, tab_id: Optional[str] = None):
        switch_error = self._switch_to_tab(tab_id)
        if switch_error:
            raise NoSuchElementException(switch_error["error"])

        element = self._find_ref_element(ref)
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'}); arguments[0].focus();",
            element,
        )
        time.sleep(0.1)
        return element

    def _extract_element_value(self, element) -> Optional[str]:
        if not element:
            return None

        try:
            tag_name = (element.tag_name or "").lower()
            if tag_name in {"input", "textarea", "select"}:
                return element.get_attribute("value") or ""

            if element.get_attribute("contenteditable") is not None:
                return element.get_attribute("textContent") or ""

            return element.text or ""
        except Exception:
            return None

    def _get_page_text(
        self,
        tab_id: Optional[str] = None,
        *,
        selector: Optional[str] = None,
        max_chars: int = 50000,
    ) -> Dict[str, Any]:
        setup_error = self._ensure_driver()
        if setup_error:
            return setup_error

        switch_error = self._switch_to_tab(tab_id)
        if switch_error:
            return switch_error

        try:
            payload = self.driver.execute_script(
                """
                const selector = arguments[0];
                const maxChars = Number(arguments[1]) || 50000;

                function extractText(node) {
                    if (!node) return "";
                    if (node instanceof HTMLInputElement || node instanceof HTMLTextAreaElement || node instanceof HTMLSelectElement) {
                        return node.value || "";
                    }
                    return node.innerText || node.textContent || "";
                }

                let target = document.body;
                let matched = true;
                if (selector) {
                    target = document.querySelector(selector);
                    matched = Boolean(target);
                }

                const rawText = extractText(target);
                const text = String(rawText || "").slice(0, maxChars);
                return {
                    text,
                    selector: selector || null,
                    matched,
                    truncated: String(rawText || "").length > text.length,
                    full_length: String(rawText || "").length,
                };
                """,
                selector,
                max_chars,
            ) or {}
            return {
                "page_text": str(payload.get("text") or ""),
                "selector": payload.get("selector"),
                "matched": bool(payload.get("matched", True)),
                "truncated": bool(payload.get("truncated", False)),
                "full_length": int(payload.get("full_length") or 0),
            }
        except Exception as exc:
            return browser_error("selenium", str(exc), error_type="command")

    def navigate(self, url: str, tab_id: Optional[str] = None, headless: Optional[bool] = None) -> Dict[str, Any]:
        setup_error = self._ensure_driver(headless=headless)
        if setup_error:
            return setup_error

        switch_error = self._switch_to_tab(tab_id)
        if switch_error:
            return switch_error

        try:
            self.driver.get(url)
            self._wait_for_ready(timeout=15.0)
            self.last_url = self.driver.current_url
            state = self._get_state(self.driver.current_window_handle)
            if "error" in state:
                return state
            return browser_success(
                "selenium",
                tab_id=state.get("tab_id"),
                window_id=state.get("window_id"),
                url=state.get("url"),
                title=state.get("title", ""),
                wait_reason="navigation_complete",
                snapshot_hash=state.get("snapshot_hash"),
                interactive_count=state.get("interactive_count"),
                focused_ref=state.get("focused_ref"),
                extras={"mode": self.get_current_mode()},
            )
        except Exception as exc:
            return browser_error("selenium", str(exc), error_type="command")

    def snapshot(self, tab_id: Optional[str] = None) -> Dict[str, Any]:
        state = self._get_state(tab_id)
        if "error" in state:
            return state
        return browser_success(
            "selenium",
            tab_id=state.get("tab_id"),
            window_id=state.get("window_id"),
            url=state.get("url"),
            title=state.get("title", ""),
            wait_reason="snapshot_captured",
            snapshot_hash=state.get("snapshot_hash"),
            interactive_count=state.get("interactive_count"),
            focused_ref=state.get("focused_ref"),
            extras={
                "elements": state.get("elements", []),
                "formatted": state.get("formatted", "No interactive elements found"),
                "count": state.get("interactive_count", 0),
                "mode": self.get_current_mode(),
            },
        )

    def screenshot(self, tab_id: Optional[str] = None) -> Dict[str, Any]:
        state = self._get_state(tab_id)
        if "error" in state:
            return state

        try:
            screenshot_png = self.driver.get_screenshot_as_png()
            image_base64 = base64.b64encode(screenshot_png).decode("utf-8")
            return browser_success(
                "selenium",
                tab_id=state.get("tab_id"),
                window_id=state.get("window_id"),
                url=state.get("url"),
                title=state.get("title", ""),
                wait_reason="screenshot_captured",
                extras={
                    "image_captured": True,
                    "image_base64": image_base64,
                    "description": "Browser screenshot captured successfully.",
                    "mode": self.get_current_mode(),
                },
            )
        except Exception as exc:
            return browser_error("selenium", str(exc), error_type="command")

    def read_text(
        self,
        *,
        selector: Optional[str] = None,
        max_chars: int = 4000,
        tab_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        state = self._get_state(tab_id)
        if "error" in state:
            return state

        text_result = self._get_page_text(
            state.get("tab_id"),
            selector=selector,
            max_chars=max_chars,
        )
        if "error" in text_result:
            return text_result
        if selector and not text_result.get("matched", True):
            return browser_error(
                "selenium",
                f"No element matched selector: {selector}",
                error_type="command",
                tab_id=state.get("tab_id"),
                window_id=state.get("window_id"),
                url=state.get("url"),
                title=state.get("title"),
                extras={"selector": selector, "mode": self.get_current_mode()},
            )

        return browser_success(
            "selenium",
            tab_id=state.get("tab_id"),
            window_id=state.get("window_id"),
            url=state.get("url"),
            title=state.get("title", ""),
            wait_reason="text_read",
            snapshot_hash=state.get("snapshot_hash"),
            interactive_count=state.get("interactive_count"),
            focused_ref=state.get("focused_ref"),
            extras={
                "mode": self.get_current_mode(),
                "text": text_result.get("page_text", ""),
                "selector": text_result.get("selector"),
                "truncated": bool(text_result.get("truncated", False)),
                "full_length": int(text_result.get("full_length") or 0),
            },
        )

    def click_by_ref(self, ref: int, tab_id: Optional[str] = None) -> Dict[str, Any]:
        before = self._get_state(tab_id)
        if "error" in before:
            return before

        try:
            element = self._focus_ref(ref, before.get("tab_id"))
            element.click()
            after = self._wait_for_observed_change(before, before.get("tab_id"), timeout_seconds=10.0)
            if "error" in after:
                return after
            return browser_success(
                "selenium",
                tab_id=after.get("tab_id"),
                window_id=after.get("window_id"),
                url=after.get("url"),
                title=after.get("title", ""),
                wait_reason=after.get("wait_reason", "click_completed"),
                snapshot_hash=after.get("snapshot_hash"),
                interactive_count=after.get("interactive_count"),
                focused_ref=after.get("focused_ref"),
                extras={"clicked_ref": ref},
            )
        except Exception as exc:
            return browser_error("selenium", f"Failed to click ref={ref}: {exc}", error_type="command")

    def click(self, target: str) -> Dict[str, Any]:
        setup_error = self._ensure_driver()
        if setup_error:
            return setup_error

        if not self.driver:
            return browser_error("selenium", "No browser open", error_type="command")

        try:
            try:
                element = self.driver.find_element(By.CSS_SELECTOR, target)
                if element.is_displayed():
                    before = self._get_state(self.driver.current_window_handle)
                    element.click()
                    after = self._wait_for_observed_change(before, before.get("tab_id"), timeout_seconds=10.0)
                    if "error" in after:
                        return after
                    return browser_success(
                        "selenium",
                        tab_id=after.get("tab_id"),
                        window_id=after.get("window_id"),
                        url=after.get("url"),
                        title=after.get("title", ""),
                        wait_reason=after.get("wait_reason", "click_completed"),
                        snapshot_hash=after.get("snapshot_hash"),
                        interactive_count=after.get("interactive_count"),
                        focused_ref=after.get("focused_ref"),
                        extras={"method": "css_selector", "target": target},
                    )
            except Exception:
                pass

            xpath = (
                f"//*[contains(text(), '{target}') or "
                f"contains(@aria-label, '{target}') or "
                f"contains(@placeholder, '{target}') or "
                f"contains(@title, '{target}') or "
                f"contains(@value, '{target}') or "
                f"@id='{target}' or "
                f"@name='{target}']"
            )
            elements = self.driver.find_elements(By.XPATH, xpath)
            before = self._get_state(self.driver.current_window_handle)
            for element in elements:
                if not element.is_displayed():
                    continue
                element.click()
                after = self._wait_for_observed_change(before, before.get("tab_id"), timeout_seconds=10.0)
                if "error" in after:
                    return after
                return browser_success(
                    "selenium",
                    tab_id=after.get("tab_id"),
                    window_id=after.get("window_id"),
                    url=after.get("url"),
                    title=after.get("title", ""),
                    wait_reason=after.get("wait_reason", "click_completed"),
                    snapshot_hash=after.get("snapshot_hash"),
                    interactive_count=after.get("interactive_count"),
                    focused_ref=after.get("focused_ref"),
                    extras={"method": "xpath", "target": target},
                )

            return browser_error("selenium", f"Element not found: '{target}'", error_type="command")
        except Exception as exc:
            return browser_error("selenium", str(exc), error_type="command")

    def type(self, text: str, clear_first: bool = False, ref: Optional[int] = None, tab_id: Optional[str] = None) -> Dict[str, Any]:
        setup_error = self._ensure_driver()
        if setup_error:
            return setup_error

        try:
            switch_error = self._switch_to_tab(tab_id)
            if switch_error:
                return switch_error

            if ref is not None:
                self._focus_ref(ref, tab_id)

            active = self.driver.switch_to.active_element
            if clear_first:
                try:
                    active.clear()
                except Exception:
                    active.send_keys(Keys.CONTROL, "a")
                    active.send_keys(Keys.DELETE)
            active.send_keys(text)

            field_value = self._extract_element_value(active)

            state = self._get_state(tab_id)
            if "error" in state:
                return state
            return browser_success(
                "selenium",
                tab_id=state.get("tab_id"),
                window_id=state.get("window_id"),
                url=state.get("url"),
                title=state.get("title", ""),
                wait_reason="typed",
                snapshot_hash=state.get("snapshot_hash"),
                interactive_count=state.get("interactive_count"),
                focused_ref=state.get("focused_ref"),
                extras={
                    "typed": text,
                    "ref": ref,
                    "clear_first": clear_first,
                    "field_value": field_value,
                    "typed_verified": field_value is None or text in field_value,
                },
            )
        except Exception as exc:
            return browser_error("selenium", str(exc), error_type="command")

    def clear_ref(self, ref: int, tab_id: Optional[str] = None) -> Dict[str, Any]:
        before = self._get_state(tab_id)
        if "error" in before:
            return before

        try:
            element = self._focus_ref(ref, before.get("tab_id"))
            tag_name = (element.tag_name or "").lower()
            is_contenteditable = element.get_attribute("contenteditable") is not None

            if tag_name in {"input", "textarea"}:
                try:
                    element.clear()
                except Exception:
                    element.send_keys(Keys.CONTROL, "a")
                    element.send_keys(Keys.DELETE)
            elif is_contenteditable:
                self.driver.execute_script(
                    """
                    arguments[0].textContent = '';
                    arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                    arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                    """,
                    element,
                )
            else:
                return browser_error(
                    "selenium",
                    f"ref={ref} is not a clearable input.",
                    error_type="command",
                    tab_id=before.get("tab_id"),
                    window_id=before.get("window_id"),
                    url=before.get("url"),
                    title=before.get("title"),
                )

            field_value = self._extract_element_value(element)
            state = self._get_state(before.get("tab_id"))
            if "error" in state:
                return state

            return browser_success(
                "selenium",
                tab_id=state.get("tab_id"),
                window_id=state.get("window_id"),
                url=state.get("url"),
                title=state.get("title", ""),
                wait_reason="field_cleared",
                snapshot_hash=state.get("snapshot_hash"),
                interactive_count=state.get("interactive_count"),
                focused_ref=state.get("focused_ref"),
                extras={
                    "ref": ref,
                    "field_value": field_value,
                    "cleared": field_value in {"", None},
                },
            )
        except Exception as exc:
            return browser_error("selenium", f"Failed to clear ref={ref}: {exc}", error_type="command")

    def select_option_by_ref(
        self,
        ref: int,
        *,
        text: Optional[str] = None,
        value: Optional[str] = None,
        index: Optional[int] = None,
        tab_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        before = self._get_state(tab_id)
        if "error" in before:
            return before

        selectors = [text is not None, value is not None, index is not None]
        if sum(1 for enabled in selectors if enabled) != 1:
            return browser_error(
                "selenium",
                "select_option_by_ref requires exactly one of text, value, or index.",
                error_type="command",
                tab_id=before.get("tab_id"),
                window_id=before.get("window_id"),
                url=before.get("url"),
                title=before.get("title"),
            )

        try:
            element = self._focus_ref(ref, before.get("tab_id"))
            if (element.tag_name or "").lower() != "select":
                return browser_error(
                    "selenium",
                    f"ref={ref} is not a <select> element.",
                    error_type="command",
                    tab_id=before.get("tab_id"),
                    window_id=before.get("window_id"),
                    url=before.get("url"),
                    title=before.get("title"),
                )

            selector = Select(element)
            if text is not None:
                selector.select_by_visible_text(text)
            elif value is not None:
                selector.select_by_value(str(value))
            else:
                selector.select_by_index(int(index))

            selected_value = element.get_attribute("value")
            selected_text = self.driver.execute_script(
                """
                const element = arguments[0];
                return element.options[element.selectedIndex]
                    ? element.options[element.selectedIndex].text
                    : '';
                """,
                element,
            )

            state = self._get_state(before.get("tab_id"))
            if "error" in state:
                return state

            return browser_success(
                "selenium",
                tab_id=state.get("tab_id"),
                window_id=state.get("window_id"),
                url=state.get("url"),
                title=state.get("title", ""),
                wait_reason="option_selected",
                snapshot_hash=state.get("snapshot_hash"),
                interactive_count=state.get("interactive_count"),
                focused_ref=state.get("focused_ref"),
                extras={
                    "ref": ref,
                    "selected_text": selected_text,
                    "selected_value": selected_value,
                },
            )
        except Exception as exc:
            return browser_error("selenium", f"Failed to select option on ref={ref}: {exc}", error_type="command")

    def wait_for(
        self,
        *,
        url_contains: Optional[str] = None,
        title_contains: Optional[str] = None,
        text_contains: Optional[str] = None,
        timeout_seconds: float = 10.0,
        tab_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not any([url_contains, title_contains, text_contains]):
            return browser_error(
                "selenium",
                "browser_wait_for requires url_contains, title_contains, or text_contains.",
                error_type="command",
            )

        deadline = time.monotonic() + timeout_seconds
        last_state = self._get_state(tab_id)
        if "error" in last_state:
            return last_state

        while time.monotonic() < deadline:
            state = self._get_state(tab_id)
            if "error" in state:
                return state

            matched_conditions = []
            if url_contains and url_contains.lower() in (state.get("url") or "").lower():
                matched_conditions.append("url_contains")
            if title_contains and title_contains.lower() in (state.get("title") or "").lower():
                matched_conditions.append("title_contains")
            page_text = None
            if text_contains:
                text_result = self._get_page_text(state.get("tab_id"))
                if "error" in text_result:
                    return text_result
                page_text = text_result.get("page_text") or ""
                if text_contains.lower() in page_text.lower():
                    matched_conditions.append("text_contains")

            if matched_conditions:
                extras = {"matched_conditions": matched_conditions}
                if page_text is not None:
                    extras["text_contains"] = text_contains
                return browser_success(
                    "selenium",
                    tab_id=state.get("tab_id"),
                    window_id=state.get("window_id"),
                    url=state.get("url"),
                    title=state.get("title", ""),
                    wait_reason="wait_condition_met",
                    snapshot_hash=state.get("snapshot_hash"),
                    interactive_count=state.get("interactive_count"),
                    focused_ref=state.get("focused_ref"),
                    extras=extras,
                )

            last_state = state
            time.sleep(0.25)

        return browser_error(
            "selenium",
            "Wait condition not met before timeout.",
            error_type="command",
            tab_id=last_state.get("tab_id"),
            window_id=last_state.get("window_id"),
            url=last_state.get("url"),
            title=last_state.get("title"),
            extras={
                "url_contains": url_contains,
                "title_contains": title_contains,
                "text_contains": text_contains,
            },
        )

    def press_key(self, key: str, tab_id: Optional[str] = None) -> Dict[str, Any]:
        before = self._get_state(tab_id)
        if "error" in before:
            return before

        key_map = {
            "enter": Keys.ENTER,
            "tab": Keys.TAB,
            "escape": Keys.ESCAPE,
            "backspace": Keys.BACKSPACE,
            "delete": Keys.DELETE,
            "arrow_up": Keys.ARROW_UP,
            "arrow_down": Keys.ARROW_DOWN,
            "arrow_left": Keys.ARROW_LEFT,
            "arrow_right": Keys.ARROW_RIGHT,
        }

        try:
            active = self.driver.switch_to.active_element
            active.send_keys(key_map.get(str(key).lower(), key))
            after = self._wait_for_observed_change(before, before.get("tab_id"), timeout_seconds=2.0)
            if "error" in after:
                after = before
            return browser_success(
                "selenium",
                tab_id=after.get("tab_id"),
                window_id=after.get("window_id"),
                url=after.get("url"),
                title=after.get("title", ""),
                wait_reason=after.get("wait_reason", "key_dispatched"),
                snapshot_hash=after.get("snapshot_hash"),
                interactive_count=after.get("interactive_count"),
                focused_ref=after.get("focused_ref"),
                extras={"pressed": key},
            )
        except Exception as exc:
            return browser_error("selenium", str(exc), error_type="command")

    def scroll(self, direction: str = "down", amount: int = 300, tab_id: Optional[str] = None) -> Dict[str, Any]:
        before = self._get_state(tab_id)
        if "error" in before:
            return before

        try:
            scroll_amount = -amount if direction == "up" else amount
            self.driver.execute_script("window.scrollBy(0, arguments[0])", scroll_amount)
            state = self._get_state(before.get("tab_id"))
            if "error" in state:
                state = before
            return browser_success(
                "selenium",
                tab_id=state.get("tab_id"),
                window_id=state.get("window_id"),
                url=state.get("url"),
                title=state.get("title", ""),
                wait_reason="scrolled",
                snapshot_hash=state.get("snapshot_hash"),
                interactive_count=state.get("interactive_count"),
                focused_ref=state.get("focused_ref"),
                extras={"direction": direction, "amount": amount},
            )
        except Exception as exc:
            return browser_error("selenium", str(exc), error_type="command")

    def get_page_info(self, tab_id: Optional[str] = None) -> Dict[str, Any]:
        state = self._get_state(tab_id)
        if "error" in state:
            return state
        return {
            "backend": "selenium",
            "tab_id": state.get("tab_id"),
            "window_id": state.get("window_id"),
            "url": state.get("url"),
            "title": state.get("title", ""),
            "snapshot_hash": state.get("snapshot_hash"),
            "interactive_count": state.get("interactive_count"),
            "focused_ref": state.get("focused_ref"),
        }

    def list_tabs(self) -> Dict[str, Any]:
        setup_error = self._ensure_driver()
        if setup_error:
            return setup_error

        try:
            handles = self.driver.window_handles
            current_handle = self.driver.current_window_handle
            tabs = []
            for index, handle in enumerate(handles):
                self.driver.switch_to.window(handle)
                tabs.append(
                    {
                        "tab_id": handle,
                        "index": index,
                        "title": self.driver.title,
                        "url": self.driver.current_url,
                        "active": handle == current_handle,
                        "window_id": handle,
                    }
                )

            self.driver.switch_to.window(current_handle)
            return {
                "backend": "selenium",
                "tabs": tabs,
                "count": len(tabs),
                "active_index": handles.index(current_handle),
            }
        except Exception as exc:
            return browser_error("selenium", str(exc), error_type="command")

    def activate_tab(
        self,
        index: Optional[int] = None,
        title_contains: Optional[str] = None,
        url_contains: Optional[str] = None,
        tab_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        tabs_result = self.list_tabs()
        if "error" in tabs_result:
            return tabs_result

        tabs = tabs_result["tabs"]
        target = None

        if index is not None:
            if index < 0 or index >= len(tabs):
                return browser_error("selenium", f"Tab index {index} out of range. Only {len(tabs)} tabs open.", error_type="command")
            target = tabs[index]
        elif tab_id is not None:
            target = next((tab for tab in tabs if tab["tab_id"] == tab_id), None)
            if not target:
                return browser_error("selenium", f"Tab id {tab_id} not found.", error_type="command")
        else:
            title_query = (title_contains or "").strip().lower()
            url_query = (url_contains or "").strip().lower()
            if not title_query and not url_query:
                return browser_error(
                    "selenium",
                    "activate_tab requires index, tab_id, title_contains, or url_contains.",
                    error_type="command",
                )

            matches = []
            for tab in tabs:
                tab_title = (tab.get("title") or "").lower()
                tab_url = (tab.get("url") or "").lower()
                if title_query and title_query not in tab_title:
                    continue
                if url_query and url_query not in tab_url:
                    continue
                matches.append(tab)

            if not matches:
                return browser_error("selenium", "No tab matched the requested title/url filter.", error_type="command")
            if len(matches) > 1:
                preview = "; ".join(f"[{tab['index']}] {tab.get('title') or tab.get('url')}" for tab in matches[:5])
                return browser_error("selenium", f"Multiple tabs matched. Refine the request. Matches: {preview}", error_type="command")
            target = matches[0]

        try:
            self.driver.switch_to.window(target["tab_id"])
            state = self._get_state(target["tab_id"])
            if "error" in state:
                return state
            return browser_success(
                "selenium",
                tab_id=state.get("tab_id"),
                window_id=state.get("window_id"),
                url=state.get("url"),
                title=state.get("title", ""),
                wait_reason="tab_activated",
                snapshot_hash=state.get("snapshot_hash"),
                interactive_count=state.get("interactive_count"),
                focused_ref=state.get("focused_ref"),
                extras={"index": target["index"], "active": True},
            )
        except Exception as exc:
            return browser_error("selenium", str(exc), error_type="command")

    def back(self, tab_id: Optional[str] = None) -> Dict[str, Any]:
        before = self._get_state(tab_id)
        if "error" in before:
            return before

        try:
            self.driver.back()
            after = self._wait_for_observed_change(before, before.get("tab_id"), timeout_seconds=10.0)
            if "error" in after:
                return after
            return browser_success(
                "selenium",
                tab_id=after.get("tab_id"),
                window_id=after.get("window_id"),
                url=after.get("url"),
                title=after.get("title", ""),
                wait_reason=after.get("wait_reason", "history_back"),
                snapshot_hash=after.get("snapshot_hash"),
                interactive_count=after.get("interactive_count"),
                focused_ref=after.get("focused_ref"),
            )
        except Exception as exc:
            return browser_error("selenium", str(exc), error_type="command")

    def forward(self, tab_id: Optional[str] = None) -> Dict[str, Any]:
        before = self._get_state(tab_id)
        if "error" in before:
            return before

        try:
            self.driver.forward()
            after = self._wait_for_observed_change(before, before.get("tab_id"), timeout_seconds=10.0)
            if "error" in after:
                return after
            return browser_success(
                "selenium",
                tab_id=after.get("tab_id"),
                window_id=after.get("window_id"),
                url=after.get("url"),
                title=after.get("title", ""),
                wait_reason=after.get("wait_reason", "history_forward"),
                snapshot_hash=after.get("snapshot_hash"),
                interactive_count=after.get("interactive_count"),
                focused_ref=after.get("focused_ref"),
            )
        except Exception as exc:
            return browser_error("selenium", str(exc), error_type="command")

    def switch_tab(self, index: int) -> Dict[str, Any]:
        return self.activate_tab(index=index)

    def close_tab(self, tab_id: Optional[str] = None) -> Dict[str, Any]:
        tabs_result = self.list_tabs()
        if "error" in tabs_result:
            return tabs_result

        tabs = tabs_result["tabs"]
        target = next((tab for tab in tabs if tab["tab_id"] == tab_id), None) if tab_id else next(
            (tab for tab in tabs if tab["active"]),
            None,
        )
        if not target:
            return browser_error("selenium", "No matching tab to close.", error_type="command")

        try:
            target_index = target["index"]
            self.driver.switch_to.window(target["tab_id"])
            self.driver.close()

            remaining_handles = self.driver.window_handles
            if remaining_handles:
                next_index = min(target_index, len(remaining_handles) - 1)
                next_handle = remaining_handles[next_index]
                self.driver.switch_to.window(next_handle)
                state = self._get_state(next_handle)
                if "error" in state:
                    state = {"tab_id": next_handle, "window_id": next_handle, "url": None, "title": ""}
            else:
                state = {"tab_id": None, "window_id": None, "url": None, "title": ""}

            return browser_success(
                "selenium",
                tab_id=state.get("tab_id"),
                window_id=state.get("window_id"),
                url=state.get("url"),
                title=state.get("title", ""),
                wait_reason="tab_closed",
                snapshot_hash=state.get("snapshot_hash"),
                interactive_count=state.get("interactive_count"),
                focused_ref=state.get("focused_ref"),
                extras={"closed_tab_id": target["tab_id"]},
            )
        except WebDriverException as exc:
            return browser_error("selenium", str(exc), error_type="command")

    def wait_for_element(self, selector: str, timeout: int = 10) -> Dict[str, Any]:
        setup_error = self._ensure_driver()
        if setup_error:
            return setup_error

        try:
            WebDriverWait(self.driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
            return {"success": True, "found": selector, "backend": "selenium"}
        except Exception as exc:
            return browser_error("selenium", f"Timeout waiting for {selector}: {exc}", error_type="command")

    def execute_script(self, script: str) -> Dict[str, Any]:
        setup_error = self._ensure_driver()
        if setup_error:
            return setup_error

        try:
            result = self.driver.execute_script(script)
            return {"success": True, "backend": "selenium", "result": result}
        except Exception as exc:
            return browser_error("selenium", str(exc), error_type="command")

    def get_current_mode(self) -> str:
        return "headless" if self.headless else "headed"


BROWSER_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navigate browser to a URL. Auto-starts browser if not running. Optionally choose headless or headed Selenium mode on navigation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"},
                    "headless": {
                        "type": "boolean",
                        "description": "When provided, explicitly choose Selenium mode for this browser task. Use true for isolated/headless browser work, false only when you intentionally need the Selenium window visible on the live desktop.",
                    },
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_snapshot",
            "description": "Get an ARIA snapshot of interactive elements on the page. Best for clickable refs and interactive structure, not full page text extraction.",
            "parameters": {"type": "object", "properties": {}}
        }
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
                        "description": "Optional CSS selector for a specific element to read text from. Omit to read visible page text from the whole page body.",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Maximum characters of text to return.",
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
            "description": "Click element by its ARIA reference ID (e.g., ref=5). Use after snapshot to reliably click elements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ref": {"type": "integer", "description": "Reference ID from snapshot"}
                },
                "required": ["ref"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type",
            "description": "Type text into the focused element, or target a specific ref if provided.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "ref": {"type": "integer", "description": "Optional input ref from browser_snapshot."},
                    "clear_first": {"type": "boolean", "default": False}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_clear_ref",
            "description": "Clear a specific input field by its ARIA ref.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ref": {"type": "integer", "description": "Input ref from browser_snapshot."}
                },
                "required": ["ref"]
            }
        }
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
                    "index": {"type": "integer", "description": "Zero-based option index to select."}
                },
                "required": ["ref"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_wait_for",
            "description": "Wait for a page condition such as URL, title, or page text to appear on the current task tab.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url_contains": {"type": "string"},
                    "title_contains": {"type": "string"},
                    "text_contains": {"type": "string"},
                    "timeout_seconds": {"type": "number", "default": 10}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Capture a screenshot of the current browser page for proof and artifacts. When you need visual interpretation, ask a precise question about what should be visible. Do not rely on this alone for exact text extraction inside the same turn.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Optional precise visual question about the current browser page, file, dialog, or error state."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_press_key",
            "description": "Press a key (enter, tab, escape, arrow_up, arrow_down, etc).",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scroll",
            "description": "Scroll the page up or down.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down"], "default": "down"},
                    "amount": {"type": "integer", "default": 300}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_back",
            "description": "Navigate back in browser history.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_forward",
            "description": "Navigate forward in browser history.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_switch_tab",
            "description": "Switch to a browser tab by index (0-based).",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"}
                },
                "required": ["index"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_list_tabs",
            "description": "List open browser tabs with indices, titles, URLs, and which one is active.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_activate_tab",
            "description": "Activate an existing tab by title substring, URL substring, tab id, or index.",
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer", "description": "Tab index if already known."},
                    "title_contains": {"type": "string", "description": "Substring of the tab title to match."},
                    "url_contains": {"type": "string", "description": "Substring of the tab URL to match."},
                    "tab_id": {"type": "string", "description": "Specific tab identifier if already known."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_close_tab",
            "description": "Close the current browser tab.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_stop",
            "description": "Stop and close the browser.",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]


def create_browser_tool(headless: Optional[bool] = None) -> BrowserTool:
    """Factory function to create a BrowserTool instance."""
    return BrowserTool(headless=headless)
