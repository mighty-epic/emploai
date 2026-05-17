from telegram_bot.telegram_session_state import BrowserTaskContext
from telegram_bot.telegram_unified_agent import (
    _execute_browser_activate_tab,
    _execute_browser_navigate,
    _execute_observe_browser,
    _execute_browser_snapshot,
    build_unified_system_prompt,
)
from single_agent.browser_actions import browser_error, browser_success


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
        self.system_info = "OS: Test\nActive Windows: none"

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
        if result.get("closed_tab_id") in context.owned_tab_ids:
            context.owned_tab_ids = [tab for tab in context.owned_tab_ids if tab != result.get("closed_tab_id")]
        return context


class FakeExtensionBrowser:
    def __init__(self, *, fail_first_navigate=False):
        self.fail_first_navigate = fail_first_navigate
        self.navigate_calls = []
        self.activate_calls = []
        self.snapshot_calls = []
        self.started = 0

    def start_server(self):
        self.started += 1

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
        if self.fail_first_navigate and len(self.navigate_calls) == 1:
            return browser_error("extension", "bridge timeout", error_type="timeout")

        return browser_success(
            "extension",
            tab_id=tab_id or 101,
            window_id=1,
            url=url,
            title="Extension Page",
        )

    def activate_tab(self, index=None, title_contains=None, url_contains=None, tab_id=None):
        self.activate_calls.append({"index": index, "title": title_contains, "url": url_contains, "tab_id": tab_id})
        return browser_success(
            "extension",
            tab_id=tab_id or 202,
            window_id=1,
            url="https://active.example",
            title="Active Tab",
            extras={"index": index if index is not None else 0, "active": True},
        )

    def snapshot(self, tab_id=None):
        self.snapshot_calls.append(tab_id)
        return browser_success(
            "extension",
            tab_id=tab_id or 101,
            window_id=1,
            url="https://snapshot.example",
            title="Snapshot",
            snapshot_hash="deadbeef",
            interactive_count=3,
            extras={
                "formatted": '- button "Run" [ref=1]',
                "elements": [{"ref": 1, "role": "button", "name": "Run"}],
                "count": 3,
            },
        )


class FakeSeleniumBrowser:
    def __init__(self):
        self.navigate_calls = []

    def navigate(self, url, tab_id=None):
        self.navigate_calls.append(tab_id)
        return browser_success(
            "selenium",
            tab_id=tab_id or "selenium-1",
            window_id="selenium-1",
            url=url,
            title="Selenium Page",
        )

    def activate_tab(self, index=None, title_contains=None, url_contains=None, tab_id=None):
        return browser_success(
            "selenium",
            tab_id=tab_id or "selenium-2",
            window_id="selenium-2",
            url="https://selenium-active.example",
            title="Selenium Active",
            extras={"index": index if index is not None else 0, "active": True},
        )

    def snapshot(self, tab_id=None):
        return browser_success(
            "selenium",
            tab_id=tab_id or "selenium-1",
            window_id="selenium-1",
            url="https://selenium-snapshot.example",
            title="Selenium Snapshot",
            snapshot_hash="beadfeed",
            interactive_count=1,
            extras={"formatted": "No interactive elements found", "elements": [], "count": 0},
        )


class FakeOfflineExtensionBrowser(FakeExtensionBrowser):
    def get_status(self):
        return {
            "backend": "extension",
            "server_running": True,
            "connected": False,
            "healthy": False,
            "heartbeat_age_seconds": None,
        }

    def navigate(self, url, tab_id=None):
        raise AssertionError("extension navigate should not be called while the bridge is offline")


def test_first_navigate_creates_task_owned_extension_tab_and_pins_backend():
    session = DummySession()
    session.extension_tool = FakeExtensionBrowser()

    message = _execute_browser_navigate(session, {"url": "https://example.com"})

    context = session.get_browser_task_context()
    assert "https://example.com" in message
    assert context.backend == "extension"
    assert context.primary_tab_id == 101
    assert context.owned_tab_ids == [101]


def test_subsequent_navigate_reuses_primary_tab():
    session = DummySession()
    session.extension_tool = FakeExtensionBrowser()

    _execute_browser_navigate(session, {"url": "https://example.com"})
    _execute_browser_navigate(session, {"url": "https://second.example"})

    assert session.extension_tool.navigate_calls == [None, 101]
    assert session.get_browser_task_context().owned_tab_ids == [101]


def test_activate_tab_updates_primary_tab_without_marking_it_owned():
    session = DummySession()
    session.extension_tool = FakeExtensionBrowser()

    _execute_browser_navigate(session, {"url": "https://example.com"})
    _execute_browser_activate_tab(session, {"index": 2})

    context = session.get_browser_task_context()
    assert context.primary_tab_id == 202
    assert context.owned_tab_ids == [101]


def test_snapshot_updates_last_snapshot_hash():
    session = DummySession()
    session.extension_tool = FakeExtensionBrowser()

    _execute_browser_navigate(session, {"url": "https://example.com"})
    result = _execute_browser_snapshot(session, {})

    assert "Browser ARIA Snapshot" in result
    assert session.get_browser_task_context().last_snapshot_hash == "deadbeef"


def test_observe_browser_reports_page_state_and_interactive_count():
    session = DummySession()
    session.extension_tool = FakeExtensionBrowser()

    _execute_browser_navigate(session, {"url": "https://example.com"})
    result = _execute_observe_browser(session, {})

    assert "Browser state:" in result
    assert "Interactive elements detected: 3" in result
    assert "Run" in result


def test_extension_timeout_falls_back_to_selenium_and_sticks_for_task():
    session = DummySession()
    session.extension_tool = FakeExtensionBrowser(fail_first_navigate=True)
    session.browser_tool = FakeSeleniumBrowser()

    first = _execute_browser_navigate(session, {"url": "https://fallback.example"})
    second = _execute_browser_navigate(session, {"url": "https://second.example"})

    context = session.get_browser_task_context()
    assert "fallback.example" in first
    assert "second.example" in second
    assert context.backend == "selenium"
    assert session.extension_tool.navigate_calls == [None]
    assert session.browser_tool.navigate_calls == [None, "selenium-1"]


def test_offline_extension_preflights_directly_to_selenium():
    session = DummySession()
    session.extension_tool = FakeOfflineExtensionBrowser()
    session.browser_tool = FakeSeleniumBrowser()

    message = _execute_browser_navigate(session, {"url": "https://offline.example"})

    context = session.get_browser_task_context()
    assert "offline.example" in message
    assert "Bridge fallback" in message
    assert context.backend == "selenium"
    assert session.browser_tool.navigate_calls == [None]


def test_user_chrome_task_with_disabled_bridge_blocks_browser_tools_instead_of_falling_back():
    session = DummySession(use_extension=False)
    session.browser_tool = FakeSeleniumBrowser()
    session.browser_task_context.requires_real_chrome = True

    message = _execute_browser_navigate(session, {"url": "https://blocked.example"})

    assert "browser_* tools are blocked for this task" in message
    assert "desktop tools instead" in message
    assert session.browser_tool.navigate_calls == []
    assert session.get_browser_task_context().backend is None


def test_user_chrome_task_with_offline_bridge_blocks_browser_tools_instead_of_falling_back():
    session = DummySession()
    session.extension_tool = FakeOfflineExtensionBrowser()
    session.browser_tool = FakeSeleniumBrowser()
    session.browser_task_context.requires_real_chrome = True

    message = _execute_browser_navigate(session, {"url": "https://blocked.example"})

    assert "browser_* tools are blocked for this task" in message
    assert "not connected and healthy" in message
    assert session.browser_tool.navigate_calls == []
    assert session.get_browser_task_context().backend is None


def test_system_prompt_starts_with_live_browser_runtime_status():
    session = DummySession()
    session.extension_tool = FakeOfflineExtensionBrowser()

    prompt = build_unified_system_prompt(session)

    assert prompt.startswith("# LIVE BROWSER RUNTIME STATUS")
    assert "# LIVE DESKTOP RUNTIME STATUS" in prompt
    assert "- Active Windows: none" in prompt
    assert "Task depends on user's Chrome: NO" in prompt
    assert "Real Chrome available now: NO" in prompt
    assert "Do NOT assume browser_* tools can use the extension" in prompt
    assert "Do NOT spend a turn on observe_desktop or focus_window" in prompt
