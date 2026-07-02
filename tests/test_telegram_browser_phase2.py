from telegram_bot.telegram_session_state import BrowserTaskContext
from telegram_bot.telegram_unified_agent import (
    _execute_browser_clear_ref,
    _execute_browser_navigate,
    _execute_browser_select_option_ref,
    _execute_browser_wait_for,
)
from local_agent_runtime.browser_actions import browser_error, browser_success


class DummyConfig(dict):
    def get(self, key, default=None):
        return super().get(key, default)

    def set(self, key, value, _user_id=None):
        self[key] = value

    def save_config(self):
        return None


class DummySession:
    def __init__(self, *, use_extension=True):
        self.live_config = DummyConfig({"browser.use_extension": use_extension})
        self.user_id = 1
        self.refined_agent = None
        self.browser_tool = None
        self.extension_tool = None
        self.current_task_id = 1
        self.browser_task_context = BrowserTaskContext(task_id=1)

    def get_browser_task_context(self):
        if self.browser_task_context.task_id != self.current_task_id:
            self.browser_task_context = BrowserTaskContext(task_id=self.current_task_id)
        return self.browser_task_context

    def reset_browser_task_context(self, task_id=None):
        self.browser_task_context = BrowserTaskContext(task_id=self.current_task_id if task_id is None else task_id)
        return self.browser_task_context

    def update_browser_task_context(self, result, *, owned_tab=False):
        context = self.get_browser_task_context()
        if not result:
            return context

        if result.get("backend"):
            context.backend = result.get("backend")

        if result.get("error"):
            if result.get("error_type") in {"connection", "protocol", "timeout"}:
                context.healthy = False
            return context

        context.healthy = bool(result.get("success", True))
        if result.get("tab_id") is not None:
            context.primary_tab_id = result.get("tab_id")
            if owned_tab and result.get("tab_id") not in context.owned_tab_ids:
                context.owned_tab_ids.append(result.get("tab_id"))
        if result.get("window_id") is not None:
            context.primary_window_id = result.get("window_id")
        if result.get("url") is not None:
            context.last_url = result.get("url")
        if result.get("title") is not None:
            context.last_title = result.get("title")
        if result.get("snapshot_hash") is not None:
            context.last_snapshot_hash = result.get("snapshot_hash")
        return context


class FakeExtensionBrowser:
    def __init__(self, *, wait_error=False):
        self.wait_error = wait_error
        self.navigate_calls = []
        self.clear_calls = []
        self.select_calls = []
        self.wait_calls = []

    def start_server(self):
        return None

    def get_status(self):
        return {
            "backend": "extension",
            "server_running": True,
            "connected": True,
            "healthy": True,
            "heartbeat_age_seconds": 0.0,
        }

    def navigate(self, url, tab_id=None):
        self.navigate_calls.append(tab_id)
        return browser_success(
            "extension",
            tab_id=tab_id or 101,
            window_id=1,
            url=url,
            title="Task Tab",
            wait_reason="navigation_complete",
        )

    def clear_ref(self, ref, tab_id=None):
        self.clear_calls.append((ref, tab_id))
        return browser_success(
            "extension",
            tab_id=tab_id or 101,
            window_id=1,
            url="https://example.com/form",
            title="Form",
            wait_reason="field_cleared",
            extras={"ref": ref, "field_value": "", "cleared": True},
        )

    def select_option_by_ref(self, ref, *, text=None, value=None, index=None, tab_id=None):
        self.select_calls.append({"ref": ref, "text": text, "value": value, "index": index, "tab_id": tab_id})
        return browser_success(
            "extension",
            tab_id=tab_id or 101,
            window_id=1,
            url="https://example.com/form",
            title="Form",
            wait_reason="option_selected",
            extras={"ref": ref, "selected_text": text or "Canada", "selected_value": value or "ca"},
        )

    def wait_for(self, *, url_contains=None, title_contains=None, text_contains=None, timeout_seconds=10, tab_id=None):
        self.wait_calls.append(
            {
                "url_contains": url_contains,
                "title_contains": title_contains,
                "text_contains": text_contains,
                "timeout_seconds": timeout_seconds,
                "tab_id": tab_id,
            }
        )
        if self.wait_error:
            return browser_error(
                "extension",
                "Wait condition not met before timeout.",
                error_type="command",
                tab_id=tab_id or 101,
                window_id=1,
                url="https://example.com/form",
                title="Form",
            )

        return browser_success(
            "extension",
            tab_id=tab_id or 101,
            window_id=1,
            url="https://example.com/done",
            title="Done",
            wait_reason="wait_condition_met",
            extras={"matched_conditions": ["url_contains", "text_contains"]},
        )


class FakeSeleniumBrowser:
    def __init__(self):
        self.wait_calls = []

    def wait_for(self, **kwargs):
        self.wait_calls.append(kwargs)
        return browser_success("selenium", tab_id="selenium-1", window_id="selenium-1", url="https://selenium.example", title="Selenium")


def test_clear_ref_uses_task_owned_tab_and_reports_field_state():
    session = DummySession()
    session.extension_tool = FakeExtensionBrowser()

    _execute_browser_navigate(session, {"url": "https://example.com/form"})
    message = _execute_browser_clear_ref(session, {"ref": 7})

    assert session.extension_tool.clear_calls == [(7, 101)]
    assert "Cleared field" in message
    assert "Field value:" in message
    assert session.get_browser_task_context().primary_tab_id == 101


def test_select_option_ref_reports_selected_choice():
    session = DummySession()
    session.extension_tool = FakeExtensionBrowser()

    _execute_browser_navigate(session, {"url": "https://example.com/form"})
    message = _execute_browser_select_option_ref(session, {"ref": 5, "text": "Canada"})

    assert session.extension_tool.select_calls == [{"ref": 5, "text": "Canada", "value": None, "index": None, "tab_id": 101}]
    assert "Selected option" in message
    assert "Canada" in message


def test_wait_for_keeps_extension_backend_on_command_error():
    session = DummySession()
    session.extension_tool = FakeExtensionBrowser(wait_error=True)
    session.browser_tool = FakeSeleniumBrowser()

    _execute_browser_navigate(session, {"url": "https://example.com/form"})
    message = _execute_browser_wait_for(session, {"text_contains": "Success", "timeout_seconds": 1})

    assert "Wait error" in message
    assert session.browser_tool.wait_calls == []
    assert session.get_browser_task_context().backend == "extension"
