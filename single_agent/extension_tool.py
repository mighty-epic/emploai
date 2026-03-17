"""
Browser Extension Tool - WebSocket bridge for controlling a real browser extension.
Used for native browser control while logged into Google.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from threading import Thread
from typing import Any, Dict, Optional

from single_agent.browser_actions import browser_error, browser_success, stable_snapshot_hash

logger = logging.getLogger(__name__)

HEARTBEAT_STALE_SECONDS = 30.0


class ExtensionTool:
    """Controls a real browser via a WebSocket-connected extension."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.connection = None
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.server_thread: Optional[Thread] = None
        self.is_running = False
        self.keepalive_task = None
        self.last_heartbeat_at: Optional[float] = None
        self.server = None
        self._stop_event = None

    def start_server(self):
        """Start the WebSocket bridge server in a background thread."""
        if self.is_running:
            return

        self.last_heartbeat_at = time.monotonic()

        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            import websockets

            async def handler(websocket):
                print(f"[BRIDGE] Extension connected from {websocket.remote_address}")
                self.connection = websocket
                self.last_heartbeat_at = time.monotonic()
                keepalive_task = asyncio.create_task(self._keepalive_loop(websocket))
                self.keepalive_task = keepalive_task
                try:
                    async for message in websocket:
                        data = json.loads(message)
                        message_type = data.get("type")
                        if message_type in {"heartbeat", "pong"}:
                            self.last_heartbeat_at = time.monotonic()
                            if message_type == "heartbeat":
                                await websocket.send(
                                    json.dumps(
                                        {
                                            "type": "heartbeat_ack",
                                            "timestamp": data.get("timestamp"),
                                        }
                                    )
                                )
                            continue

                        request_id = data.get("id")
                        future = self.pending_requests.get(request_id)
                        if future and not future.done():
                            future.set_result(data)
                except Exception as exc:
                    print(f"[BRIDGE] Handler error: {exc}")
                finally:
                    if keepalive_task:
                        keepalive_task.cancel()
                    if self.keepalive_task is keepalive_task:
                        self.keepalive_task = None
                    if self.connection is websocket:
                        self.connection = None
                    for future in list(self.pending_requests.values()):
                        if not future.done():
                            future.set_result(
                                {
                                    "success": False,
                                    "error": "Extension bridge disconnected",
                                    "error_type": "connection",
                                }
                            )
                    print("[BRIDGE] Extension disconnected")

            async def start():
                self._stop_event = asyncio.Event()
                print(f"[BRIDGE] Starting server on {self.host}:{self.port}...")
                self.server = await websockets.serve(
                    handler,
                    self.host,
                    self.port,
                    ping_interval=20,
                    ping_timeout=20,
                )
                print(f"[BRIDGE] Server is listening on {self.host}:{self.port}")
                await self._stop_event.wait()
                self.server.close()
                await self.server.wait_closed()

            try:
                self.loop.run_until_complete(start())
            except Exception as exc:
                print(f"[BRIDGE] Server thread CRASHED: {exc}")
                self.is_running = False
            finally:
                pending = [task for task in asyncio.all_tasks(self.loop) if not task.done()]
                for task in pending:
                    task.cancel()
                if pending:
                    self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                self.loop.close()
                self.loop = None
                self.server = None
                self._stop_event = None
                self.connection = None
                self.is_running = False

        self.server_thread = Thread(target=run_loop, daemon=True)
        self.server_thread.start()
        self.is_running = True
        print(f"[BRIDGE] Background thread spawned for {self.host}:{self.port}")

    def shutdown_server(self):
        """Stop the background bridge server. Intended for tests and process shutdown."""
        if not self.is_running or not self.loop:
            return

        def stop_loop():
            if self._stop_event and not self._stop_event.is_set():
                self._stop_event.set()

        self.loop.call_soon_threadsafe(stop_loop)
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=2.0)

    async def _wait_for_connection(self, timeout: float = 5.0, poll_interval: float = 0.25) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.connection:
                return True
            await asyncio.sleep(poll_interval)
        return self.connection is not None

    async def _keepalive_loop(self, websocket):
        try:
            while websocket == self.connection:
                await asyncio.sleep(10.0)
                if websocket != self.connection:
                    break
                await websocket.send(
                    json.dumps(
                        {
                            "type": "ping",
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    def _heartbeat_age(self) -> Optional[float]:
        if self.last_heartbeat_at is None:
            return None
        return max(0.0, time.monotonic() - self.last_heartbeat_at)

    def is_healthy(self, stale_after: float = HEARTBEAT_STALE_SECONDS) -> bool:
        heartbeat_age = self._heartbeat_age()
        return bool(self.connection) and heartbeat_age is not None and heartbeat_age <= stale_after

    def get_status(self) -> Dict[str, Any]:
        heartbeat_age = self._heartbeat_age()
        return {
            "backend": "extension",
            "server_running": self.is_running,
            "connected": bool(self.connection),
            "healthy": self.is_healthy(),
            "heartbeat_age_seconds": round(heartbeat_age, 2) if heartbeat_age is not None else None,
            "pending_requests": len(self.pending_requests),
            "host": self.host,
            "port": self.port,
        }

    async def _send_command(self, action: str, params: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Dict[str, Any]:
        """Send a command to the extension and wait for a response."""
        if not self.connection:
            connected = await self._wait_for_connection(timeout=min(float(timeout), 5.0))
            if not connected:
                return {
                    "success": False,
                    "error": "Extension not connected. Ensure the 'EmploAI Bridge' extension is active in Chrome.",
                    "error_type": "connection",
                }

        heartbeat_age = self._heartbeat_age()
        if heartbeat_age is not None and heartbeat_age > HEARTBEAT_STALE_SECONDS:
            return {
                "success": False,
                "error": f"Extension heartbeat is stale ({heartbeat_age:.1f}s).",
                "error_type": "connection",
            }

        if not self.connection:
            return {
                "success": False,
                "error": "Extension not connected. Ensure the 'EmploAI Bridge' extension is active in Chrome.",
                "error_type": "connection",
            }

        request_id = str(uuid.uuid4())
        command = {
            "id": request_id,
            "action": action,
            "params": params or {},
        }

        future = asyncio.get_running_loop().create_future()
        self.pending_requests[request_id] = future

        try:
            await self.connection.send(json.dumps(command))
            result = await asyncio.wait_for(future, timeout)
            if "error_type" not in result and not result.get("success", False):
                result["error_type"] = "command"
            return result
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": f"Command {action} timed out",
                "error_type": "timeout",
            }
        except Exception as exc:
            return {
                "success": False,
                "error": f"Command error: {exc}",
                "error_type": "protocol",
            }
        finally:
            self.pending_requests.pop(request_id, None)

    def run_sync(self, coro):
        if not self.loop:
            self.start_server()
            time.sleep(0.5)
        if not self.loop:
            raise RuntimeError("Extension bridge loop failed to start")
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()

    def _command(self, action: str, params: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Dict[str, Any]:
        return self.run_sync(self._send_command(action, params=params, timeout=timeout))

    def _normalize_state(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "tab_id": data.get("tabId", data.get("tab_id")),
            "window_id": data.get("windowId", data.get("window_id")),
            "url": data.get("url"),
            "title": data.get("title", ""),
            "snapshot_hash": data.get("snapshotHash", data.get("snapshot_hash")),
            "interactive_count": data.get("interactiveCount", data.get("interactive_count")),
            "focused_ref": data.get("focusedRef", data.get("focused_ref")),
            "active": data.get("active"),
            "index": data.get("index"),
        }

    def _state_params(self, tab_id: Optional[Any] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if tab_id is not None:
            params["tabId"] = tab_id
        return params

    def _get_state(self, tab_id: Optional[Any] = None) -> Dict[str, Any]:
        result = self._command("get_state", self._state_params(tab_id), timeout=10)
        if not result.get("success"):
            return browser_error(
                "extension",
                result.get("error", "Unknown error"),
                error_type=result.get("error_type", "command"),
            )
        return self._normalize_state(result.get("result", {}))

    def _get_page_text(self, tab_id: Optional[Any] = None) -> Dict[str, Any]:
        result = self._command("get_text_content", self._state_params(tab_id), timeout=10)
        if not result.get("success"):
            return browser_error(
                "extension",
                result.get("error", "Unknown error"),
                error_type=result.get("error_type", "command"),
            )
        return result.get("result", {})

    def _list_tabs_raw(self) -> Dict[str, Any]:
        result = self._command("list_tabs", timeout=10)
        if not result.get("success"):
            return browser_error(
                "extension",
                result.get("error", "Unknown error"),
                error_type=result.get("error_type", "command"),
            )
        data = result.get("result", {})
        tabs = []
        for tab in data.get("tabs", []):
            tabs.append(
                {
                    "tab_id": tab.get("tabId", tab.get("tab_id")),
                    "index": tab.get("index"),
                    "title": tab.get("title", ""),
                    "url": tab.get("url"),
                    "active": tab.get("active", False),
                    "pinned": tab.get("pinned", False),
                    "window_id": tab.get("windowId", tab.get("window_id")),
                }
            )
        return {
            "backend": "extension",
            "tabs": tabs,
            "count": data.get("count", len(tabs)),
            "active_index": data.get("activeIndex", data.get("active_index")),
        }

    def _find_active_replacement(self, window_id: Optional[Any], excluded_tab_id: Any) -> Optional[Any]:
        if window_id is None:
            return None
        tabs_result = self._list_tabs_raw()
        if "error" in tabs_result:
            return None
        for tab in tabs_result.get("tabs", []):
            if tab.get("window_id") != window_id:
                continue
            if tab.get("active") and tab.get("tab_id") != excluded_tab_id:
                return tab.get("tab_id")
        return None

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

    def _wait_for_observed_change(self, before: Dict[str, Any], tab_id: Any, timeout_seconds: float = 10.0) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        last_state = before

        while time.monotonic() < deadline:
            state = self._get_state(tab_id)
            if "error" in state:
                replacement_tab_id = self._find_active_replacement(before.get("window_id"), before.get("tab_id"))
                if replacement_tab_id is not None:
                    replacement_state = self._get_state(replacement_tab_id)
                    if "error" not in replacement_state:
                        replacement_state["wait_reason"] = "tab_replaced"
                        return replacement_state
                return state

            last_state = state
            wait_reason = self._detect_state_change(before, state)
            if wait_reason:
                state["wait_reason"] = wait_reason
                return state

            replacement_tab_id = self._find_active_replacement(before.get("window_id"), before.get("tab_id"))
            if replacement_tab_id is not None and replacement_tab_id != state.get("tab_id"):
                replacement_state = self._get_state(replacement_tab_id)
                if "error" not in replacement_state:
                    replacement_state["wait_reason"] = "tab_replaced"
                    return replacement_state

            time.sleep(0.25)

        last_state = dict(last_state)
        last_state["wait_reason"] = "timeout_no_change"
        return last_state

    def navigate(self, url: str, tab_id: Optional[Any] = None) -> Dict[str, Any]:
        params = {"url": url}
        if tab_id is not None:
            params["tabId"] = tab_id

        result = self._command("navigate", params, timeout=30)
        if not result.get("success"):
            return browser_error(
                "extension",
                result.get("error", "Unknown error"),
                error_type=result.get("error_type", "command"),
            )

        raw = self._normalize_state(result.get("result", {}))
        state = self._get_state(raw.get("tab_id"))
        if "error" in state:
            state = raw
        return browser_success(
            "extension",
            tab_id=state.get("tab_id"),
            window_id=state.get("window_id"),
            url=state.get("url", url),
            title=state.get("title", ""),
            wait_reason="navigation_complete",
            snapshot_hash=state.get("snapshot_hash"),
            interactive_count=state.get("interactive_count"),
            focused_ref=state.get("focused_ref"),
            extras={"status": result.get("result", {}).get("status", "complete")},
        )

    def snapshot(self, tab_id: Optional[Any] = None) -> Dict[str, Any]:
        result = self._command("snapshot", self._state_params(tab_id), timeout=15)
        if not result.get("success"):
            return browser_error(
                "extension",
                result.get("error", "Unknown error"),
                error_type=result.get("error_type", "command"),
            )

        data = result.get("result", {})
        elements = data.get("elements", [])
        formatted = data.get("formatted", "")
        snapshot_hash = stable_snapshot_hash(formatted, elements)
        count = data.get("count", len(elements))
        return browser_success(
            "extension",
            tab_id=data.get("tabId", data.get("tab_id")),
            window_id=data.get("windowId", data.get("window_id")),
            url=data.get("url"),
            title=data.get("title", ""),
            wait_reason="snapshot_captured",
            snapshot_hash=snapshot_hash,
            interactive_count=count,
            focused_ref=data.get("focusedRef", data.get("focused_ref")),
            extras={
                "elements": elements,
                "formatted": formatted or "No interactive elements found",
                "count": count,
            },
        )

    def click_by_ref(self, ref: int, tab_id: Optional[Any] = None) -> Dict[str, Any]:
        before = self._get_state(tab_id)
        if "error" in before:
            return before

        params = {"ref": ref, "tabId": before.get("tab_id")}
        result = self._command("click_ref", params, timeout=15)
        if not result.get("success"):
            return browser_error(
                "extension",
                result.get("error", "Unknown error"),
                error_type=result.get("error_type", "command"),
                tab_id=before.get("tab_id"),
                window_id=before.get("window_id"),
                url=before.get("url"),
                title=before.get("title"),
            )

        after = self._wait_for_observed_change(before, before.get("tab_id"), timeout_seconds=10.0)
        if "error" in after:
            return after

        return browser_success(
            "extension",
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

    def type(self, text: str, clear_first: bool = False, ref: Optional[int] = None, tab_id: Optional[Any] = None) -> Dict[str, Any]:
        before = self._get_state(tab_id)
        if "error" in before:
            return before

        params = {
            "text": text,
            "clearFirst": clear_first,
            "tabId": before.get("tab_id"),
        }
        if ref is not None:
            params["ref"] = ref

        result = self._command("type", params, timeout=15)
        if not result.get("success"):
            return browser_error(
                "extension",
                result.get("error", "Unknown error"),
                error_type=result.get("error_type", "command"),
                tab_id=before.get("tab_id"),
                window_id=before.get("window_id"),
                url=before.get("url"),
                title=before.get("title"),
            )

        data = result.get("result", {})
        after = self._get_state(before.get("tab_id"))
        if "error" in after:
            after = before

        return browser_success(
            "extension",
            tab_id=after.get("tab_id"),
            window_id=after.get("window_id"),
            url=after.get("url"),
            title=after.get("title", ""),
            wait_reason="typed",
            snapshot_hash=after.get("snapshot_hash"),
            interactive_count=after.get("interactive_count"),
            focused_ref=after.get("focused_ref"),
            extras={
                "typed": text,
                "ref": ref,
                "clear_first": clear_first,
                "field_value": data.get("fieldValue", data.get("field_value")),
                "typed_verified": data.get("typedVerified", data.get("typed_verified", True)),
            },
        )

    def clear_ref(self, ref: int, tab_id: Optional[Any] = None) -> Dict[str, Any]:
        before = self._get_state(tab_id)
        if "error" in before:
            return before

        result = self._command("clear_ref", {"ref": ref, "tabId": before.get("tab_id")}, timeout=15)
        if not result.get("success"):
            return browser_error(
                "extension",
                result.get("error", "Unknown error"),
                error_type=result.get("error_type", "command"),
                tab_id=before.get("tab_id"),
                window_id=before.get("window_id"),
                url=before.get("url"),
                title=before.get("title"),
            )

        data = result.get("result", {})
        after = self._get_state(before.get("tab_id"))
        if "error" in after:
            after = before

        return browser_success(
            "extension",
            tab_id=after.get("tab_id"),
            window_id=after.get("window_id"),
            url=after.get("url"),
            title=after.get("title", ""),
            wait_reason="field_cleared",
            snapshot_hash=after.get("snapshot_hash"),
            interactive_count=after.get("interactive_count"),
            focused_ref=after.get("focused_ref"),
            extras={
                "ref": ref,
                "field_value": data.get("fieldValue", data.get("field_value")),
                "cleared": data.get("cleared", True),
            },
        )

    def select_option_by_ref(
        self,
        ref: int,
        *,
        text: Optional[str] = None,
        value: Optional[str] = None,
        index: Optional[int] = None,
        tab_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        before = self._get_state(tab_id)
        if "error" in before:
            return before

        selectors = [text is not None, value is not None, index is not None]
        if sum(1 for enabled in selectors if enabled) != 1:
            return browser_error(
                "extension",
                "select_option_by_ref requires exactly one of text, value, or index.",
                error_type="command",
                tab_id=before.get("tab_id"),
                window_id=before.get("window_id"),
                url=before.get("url"),
                title=before.get("title"),
            )

        params: Dict[str, Any] = {"ref": ref, "tabId": before.get("tab_id")}
        if text is not None:
            params["text"] = text
        if value is not None:
            params["value"] = value
        if index is not None:
            params["index"] = index

        result = self._command("select_option_ref", params, timeout=15)
        if not result.get("success"):
            return browser_error(
                "extension",
                result.get("error", "Unknown error"),
                error_type=result.get("error_type", "command"),
                tab_id=before.get("tab_id"),
                window_id=before.get("window_id"),
                url=before.get("url"),
                title=before.get("title"),
            )

        data = result.get("result", {})
        after = self._get_state(before.get("tab_id"))
        if "error" in after:
            after = before

        return browser_success(
            "extension",
            tab_id=after.get("tab_id"),
            window_id=after.get("window_id"),
            url=after.get("url"),
            title=after.get("title", ""),
            wait_reason="option_selected",
            snapshot_hash=after.get("snapshot_hash"),
            interactive_count=after.get("interactive_count"),
            focused_ref=after.get("focused_ref"),
            extras={
                "ref": ref,
                "selected_text": data.get("selectedText", data.get("selected_text")),
                "selected_value": data.get("selectedValue", data.get("selected_value")),
            },
        )

    def wait_for(
        self,
        *,
        url_contains: Optional[str] = None,
        title_contains: Optional[str] = None,
        text_contains: Optional[str] = None,
        timeout_seconds: float = 10.0,
        tab_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if not any([url_contains, title_contains, text_contains]):
            return browser_error(
                "extension",
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
                page_text = text_result.get("text") or ""
                if text_contains.lower() in page_text.lower():
                    matched_conditions.append("text_contains")

            if matched_conditions:
                extras = {"matched_conditions": matched_conditions}
                if page_text is not None:
                    extras["text_contains"] = text_contains
                return browser_success(
                    "extension",
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
            "extension",
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

    def screenshot(self, tab_id: Optional[Any] = None) -> Dict[str, Any]:
        result = self._command("screenshot", self._state_params(tab_id), timeout=20)
        if not result.get("success"):
            return browser_error(
                "extension",
                result.get("error", "Unknown error"),
                error_type=result.get("error_type", "command"),
            )

        data = result.get("result", {})
        return browser_success(
            "extension",
            tab_id=data.get("tabId", data.get("tab_id")),
            window_id=data.get("windowId", data.get("window_id")),
            url=data.get("url"),
            title=data.get("title", ""),
            wait_reason="screenshot_captured",
            extras={
                "image_captured": True,
                "image_base64": data.get("image"),
                "description": "Native extension screenshot captured.",
            },
        )

    def scroll(self, direction: str = "down", amount: int = 300, tab_id: Optional[Any] = None) -> Dict[str, Any]:
        before = self._get_state(tab_id)
        if "error" in before:
            return before

        result = self._command(
            "scroll",
            {"direction": direction, "amount": amount, "tabId": before.get("tab_id")},
            timeout=10,
        )
        if not result.get("success"):
            return browser_error(
                "extension",
                result.get("error", "Unknown error"),
                error_type=result.get("error_type", "command"),
                tab_id=before.get("tab_id"),
                window_id=before.get("window_id"),
                url=before.get("url"),
                title=before.get("title"),
            )

        after = self._get_state(before.get("tab_id"))
        if "error" in after:
            after = before

        return browser_success(
            "extension",
            tab_id=after.get("tab_id"),
            window_id=after.get("window_id"),
            url=after.get("url"),
            title=after.get("title", ""),
            wait_reason="scrolled",
            snapshot_hash=after.get("snapshot_hash"),
            interactive_count=after.get("interactive_count"),
            focused_ref=after.get("focused_ref"),
            extras={"direction": direction, "amount": amount},
        )

    def press_key(self, key: str, tab_id: Optional[Any] = None) -> Dict[str, Any]:
        before = self._get_state(tab_id)
        if "error" in before:
            return before

        result = self._command("press_key", {"key": key, "tabId": before.get("tab_id")}, timeout=10)
        if not result.get("success"):
            return browser_error(
                "extension",
                result.get("error", "Unknown error"),
                error_type=result.get("error_type", "command"),
                tab_id=before.get("tab_id"),
                window_id=before.get("window_id"),
                url=before.get("url"),
                title=before.get("title"),
            )

        after = self._wait_for_observed_change(before, before.get("tab_id"), timeout_seconds=2.0)
        if "error" in after:
            after = before

        return browser_success(
            "extension",
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

    def back(self, tab_id: Optional[Any] = None) -> Dict[str, Any]:
        before = self._get_state(tab_id)
        if "error" in before:
            return before

        result = self._command("back", {"tabId": before.get("tab_id")}, timeout=15)
        if not result.get("success"):
            return browser_error(
                "extension",
                result.get("error", "Unknown error"),
                error_type=result.get("error_type", "command"),
                tab_id=before.get("tab_id"),
                window_id=before.get("window_id"),
                url=before.get("url"),
                title=before.get("title"),
            )

        after = self._wait_for_observed_change(before, before.get("tab_id"), timeout_seconds=10.0)
        if "error" in after:
            return after

        return browser_success(
            "extension",
            tab_id=after.get("tab_id"),
            window_id=after.get("window_id"),
            url=after.get("url"),
            title=after.get("title", ""),
            wait_reason=after.get("wait_reason", "history_back"),
            snapshot_hash=after.get("snapshot_hash"),
            interactive_count=after.get("interactive_count"),
            focused_ref=after.get("focused_ref"),
        )

    def forward(self, tab_id: Optional[Any] = None) -> Dict[str, Any]:
        before = self._get_state(tab_id)
        if "error" in before:
            return before

        result = self._command("forward", {"tabId": before.get("tab_id")}, timeout=15)
        if not result.get("success"):
            return browser_error(
                "extension",
                result.get("error", "Unknown error"),
                error_type=result.get("error_type", "command"),
                tab_id=before.get("tab_id"),
                window_id=before.get("window_id"),
                url=before.get("url"),
                title=before.get("title"),
            )

        after = self._wait_for_observed_change(before, before.get("tab_id"), timeout_seconds=10.0)
        if "error" in after:
            return after

        return browser_success(
            "extension",
            tab_id=after.get("tab_id"),
            window_id=after.get("window_id"),
            url=after.get("url"),
            title=after.get("title", ""),
            wait_reason=after.get("wait_reason", "history_forward"),
            snapshot_hash=after.get("snapshot_hash"),
            interactive_count=after.get("interactive_count"),
            focused_ref=after.get("focused_ref"),
        )

    def switch_tab(self, index: int) -> Dict[str, Any]:
        return self.activate_tab(index=index)

    def close_tab(self, tab_id: Optional[Any] = None) -> Dict[str, Any]:
        params = self._state_params(tab_id)
        result = self._command("close_tab", params, timeout=10)
        if not result.get("success"):
            return browser_error(
                "extension",
                result.get("error", "Unknown error"),
                error_type=result.get("error_type", "command"),
            )

        data = result.get("result", {})
        return browser_success(
            "extension",
            tab_id=data.get("tabId", data.get("tab_id")),
            window_id=data.get("windowId", data.get("window_id")),
            url=data.get("url"),
            title=data.get("title", ""),
            wait_reason="tab_closed",
            extras={"closed_tab_id": data.get("closedTabId", data.get("closed_tab_id"))},
        )

    def get_page_info(self, tab_id: Optional[Any] = None) -> Dict[str, Any]:
        state = self._get_state(tab_id)
        if "error" in state:
            return state
        return {
            "backend": "extension",
            "tab_id": state.get("tab_id"),
            "window_id": state.get("window_id"),
            "url": state.get("url"),
            "title": state.get("title", ""),
            "snapshot_hash": state.get("snapshot_hash"),
            "interactive_count": state.get("interactive_count"),
            "focused_ref": state.get("focused_ref"),
        }

    def list_tabs(self) -> Dict[str, Any]:
        return self._list_tabs_raw()

    def activate_tab(
        self,
        index: Optional[int] = None,
        title_contains: Optional[str] = None,
        url_contains: Optional[str] = None,
        tab_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if index is not None:
            params["index"] = index
        if title_contains:
            params["title_contains"] = title_contains
        if url_contains:
            params["url_contains"] = url_contains
        if tab_id is not None:
            params["tab_id"] = tab_id

        result = self._command("activate_tab", params, timeout=15)
        if not result.get("success"):
            return browser_error(
                "extension",
                result.get("error", "Unknown error"),
                error_type=result.get("error_type", "command"),
            )

        raw = self._normalize_state(result.get("result", {}))
        state = self._get_state(raw.get("tab_id"))
        if "error" in state:
            state = raw

        return browser_success(
            "extension",
            tab_id=state.get("tab_id"),
            window_id=state.get("window_id"),
            url=state.get("url"),
            title=state.get("title", ""),
            wait_reason="tab_activated",
            snapshot_hash=state.get("snapshot_hash"),
            interactive_count=state.get("interactive_count"),
            focused_ref=state.get("focused_ref"),
            extras={"index": result.get("result", {}).get("index", raw.get("index")), "active": True},
        )

    def get_current_mode(self) -> str:
        return "extension"

    def stop(self) -> Dict[str, Any]:
        return {"status": "Extension bridge remains active", "backend": "extension"}


def create_extension_tool() -> ExtensionTool:
    return ExtensionTool()
