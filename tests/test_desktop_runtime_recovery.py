from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _run_recovery_scenario(script_body: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for desktop runtime-recovery tests")
    script = f"""
const {{ createRuntimeRecoverySupervisor }} = require('./desktop_app/runtime_recovery');
(async () => {{
  {script_body}
}})().catch((error) => {{
  process.stderr.write(String(error?.stack || error));
  process.exit(1);
}});
"""
    result = subprocess.run(
        [node, "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_runtime_recovery_confirms_failure_before_restarting_once() -> None:
    result = _run_recovery_scenario(
        """
let starts = 0;
const supervisor = createRuntimeRecoverySupervisor({
  getRuntimeStatus: async () => ({ ok: false }),
  startRuntime: async () => {
    starts += 1;
    return { runtimeStatus: { ok: true, process_id: 42 } };
  },
  checkIntervalMs: 60_000,
});
supervisor.start();
const first = await supervisor.checkNow();
const second = await supervisor.checkNow();
supervisor.stop();
process.stdout.write(JSON.stringify({ starts, first: first.state, second: second.state }));
"""
    )

    assert result == {"starts": 1, "first": "confirming", "second": "recovered"}


def test_runtime_recovery_respects_manual_stop_until_resumed() -> None:
    result = _run_recovery_scenario(
        """
let starts = 0;
const supervisor = createRuntimeRecoverySupervisor({
  getRuntimeStatus: async () => ({ ok: false }),
  startRuntime: async () => {
    starts += 1;
    return { runtimeStatus: { ok: true } };
  },
  failureThreshold: 1,
  checkIntervalMs: 60_000,
});
supervisor.start();
supervisor.suspend();
const suspended = await supervisor.checkNow();
supervisor.resume();
const resumed = await supervisor.checkNow();
supervisor.stop();
process.stdout.write(JSON.stringify({ starts, suspended: suspended.state, resumed: resumed.state }));
"""
    )

    assert result == {"starts": 1, "suspended": "suspended", "resumed": "recovered"}
