import asyncio
import json
import socket
import threading
import time

import pytest
import websockets

from single_agent.extension_tool import ExtensionTool


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class FakeExtensionClient:
    def __init__(self, port: int, handlers):
        self.port = port
        self.handlers = handlers
        self.connected = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._loop = None

    async def _run(self):
        uri = f"ws://127.0.0.1:{self.port}"
        async with websockets.connect(uri) as websocket:
            self.connected.set()
            while not self._stop.is_set():
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue

                data = json.loads(message)
                if data.get("type") == "ping":
                    await websocket.send(json.dumps({"type": "pong", "timestamp": data.get("timestamp")}))
                    continue

                handler = self.handlers.get(data["action"])
                if handler is None:
                    await websocket.send(
                        json.dumps(
                            {
                                "id": data["id"],
                                "success": True,
                                "result": {"echo": data["action"]},
                            }
                        )
                    )
                    continue

                response = await handler(data) if asyncio.iscoroutinefunction(handler) else handler(data)
                if response is None:
                    continue
                payload = {"id": data["id"]}
                payload.update(response)
                await websocket.send(json.dumps(payload))

    def start(self):
        def runner():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._run())

        self._thread = threading.Thread(target=runner, daemon=True)
        self._thread.start()
        assert self.connected.wait(timeout=5), "fake extension did not connect"

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)


def test_extension_tool_correlates_request_responses():
    port = _free_port()
    tool = ExtensionTool(port=port)
    tool.start_server()

    async def delayed_info(_message):
        await asyncio.sleep(0.2)
        return {"success": True, "result": {"url": "https://one.example", "title": "One"}}

    async def delayed_state(_message):
        await asyncio.sleep(0.05)
        return {
            "success": True,
            "result": {
                "tabId": 11,
                "windowId": 21,
                "url": "https://two.example",
                "title": "Two",
                "snapshotHash": "abcd1234",
                "interactiveCount": 2,
                "focusedRef": 7,
            },
        }

    client = FakeExtensionClient(port, {"get_info": delayed_info, "get_state": delayed_state})
    client.start()

    async def issue_two():
        return await asyncio.gather(
            tool._send_command("get_info"),
            tool._send_command("get_state"),
        )

    info_result, state_result = tool.run_sync(issue_two())

    assert info_result["result"]["title"] == "One"
    assert state_result["result"]["title"] == "Two"
    assert state_result["result"]["tabId"] == 11

    client.stop()
    tool.shutdown_server()


def test_extension_tool_times_out_when_client_does_not_reply():
    port = _free_port()
    tool = ExtensionTool(port=port)
    tool.start_server()

    client = FakeExtensionClient(port, {"snapshot": lambda _message: None})
    client.start()

    result = tool.run_sync(tool._send_command("snapshot", timeout=0.1))

    assert result["error_type"] == "timeout"
    assert "timed out" in result["error"]

    client.stop()
    tool.shutdown_server()


def test_extension_tool_rejects_stale_heartbeat():
    port = _free_port()
    tool = ExtensionTool(port=port)
    tool.start_server()

    client = FakeExtensionClient(
        port,
        {
            "list_tabs": lambda _message: {
                "success": True,
                "result": {"tabs": [], "count": 0, "activeIndex": -1},
            }
        },
    )
    client.start()

    tool._heartbeat_age = lambda: 60.0
    result = tool.run_sync(tool._send_command("list_tabs", timeout=1))

    assert result["error_type"] == "connection"
    assert "heartbeat is stale" in result["error"]

    client.stop()
    tool.shutdown_server()
