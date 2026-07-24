from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _probe_with_node(*, cached: dict, bootstrap: dict, health: dict | None) -> dict | None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for desktop runtime-status probe tests")
    script = r"""
const { createRuntimeStatusProbe } = require('./desktop_app/runtime_status_probe');
const input = JSON.parse(process.argv[1]);
const net = {
  fetch: async () => {
    if (input.health === null) throw new Error('offline');
    return { ok: true, status: 200, json: async () => input.health };
  },
};
const probe = createRuntimeStatusProbe({
  net,
  getRuntimeStatusCache: () => input.cached,
  getBootstrapCache: () => input.bootstrap,
  timeoutMs: 250,
});
probe().then((value) => process.stdout.write(JSON.stringify(value)));
"""
    result = subprocess.run(
        [
            node,
            "-e",
            script,
            json.dumps({"cached": cached, "bootstrap": bootstrap, "health": health}),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_cached_runtime_status_uses_direct_loopback_health_probe() -> None:
    status = _probe_with_node(
        cached={"ok": True, "state": "ready", "api_base_url": "http://localhost:8787"},
        bootstrap={},
        health={"ok": True, "startup_state": "idle", "readiness_scope": "app_api"},
    )

    assert status is not None
    assert status["ok"] is True
    assert status["runtimeProcessDetected"] is True
    assert status["api_base_url"] == "http://localhost:8787"


def test_failed_direct_probe_reports_offline_without_a_python_helper() -> None:
    status = _probe_with_node(
        cached={"ok": True, "state": "ready"},
        bootstrap={"apiBaseUrl": "http://127.0.0.1:8787"},
        health=None,
    )

    assert status is not None
    assert status["ok"] is False
    assert status["runtimeProcessDetected"] is False
    assert status["detail"] == "The local EmploAI backend is not responding."


def test_probe_refuses_non_loopback_runtime_urls() -> None:
    status = _probe_with_node(
        cached={"ok": True, "api_base_url": "https://example.com"},
        bootstrap={},
        health={"ok": True},
    )

    assert status is None
