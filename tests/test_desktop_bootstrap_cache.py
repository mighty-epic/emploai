from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _merge_with_node(previous: dict, payload: dict, options: dict | None = None) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for desktop bootstrap-cache tests")
    script = """
const { mergeBootstrapCache } = require('./desktop_app/bootstrap_cache');
const [previous, payload, options] = JSON.parse(process.argv[1]);
process.stdout.write(JSON.stringify(mergeBootstrapCache(previous, payload, options)));
"""
    result = subprocess.run(
        [node, "-e", script, json.dumps([previous, payload, options or {}])],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_busy_runtime_bootstrap_keeps_last_usable_local_session() -> None:
    previous = {
        "apiBaseUrl": "http://127.0.0.1:8787",
        "accessToken": "usable-token",
        "currentSessionId": "session-1",
        "deviceId": "device-1",
    }
    transient = {
        "apiBaseUrl": "http://127.0.0.1:8787",
        "accessToken": "",
        "currentSessionId": None,
        "deviceId": None,
        "runtimeProcessDetected": True,
        "runtimeStatus": {"ok": False, "state": "offline"},
    }

    merged = _merge_with_node(previous, transient)

    assert merged["accessToken"] == "usable-token"
    assert merged["currentSessionId"] == "session-1"
    assert merged["deviceId"] == "device-1"
    assert merged["runtimeStatus"]["ok"] is False


def test_stopped_runtime_bootstrap_clears_local_session() -> None:
    previous = {
        "apiBaseUrl": "http://127.0.0.1:8787",
        "accessToken": "usable-token",
    }
    stopped = {
        "apiBaseUrl": "http://127.0.0.1:8787",
        "accessToken": "",
        "runtimeProcessDetected": False,
        "runtimeStatus": {"ok": False, "state": "offline"},
    }

    assert _merge_with_node(previous, stopped)["accessToken"] == ""
    assert _merge_with_node(
        previous,
        {**stopped, "runtimeProcessDetected": True},
        {"preserveConnectedSession": False},
    )["accessToken"] == ""
