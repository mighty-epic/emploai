from __future__ import annotations

import os
from pathlib import Path

from app_backend import local_runtime_server


def test_detached_runtime_can_import_app_backend_outside_source_workspace(monkeypatch, tmp_path: Path):
    workspace = tmp_path / "runtime-home"
    workspace.mkdir()
    log_path = tmp_path / "runtime.log"
    launches: list[dict] = []

    monkeypatch.setattr(local_runtime_server, "_desktop_log_path", lambda: log_path)
    monkeypatch.setattr(
        local_runtime_server.subprocess,
        "Popen",
        lambda command, **kwargs: launches.append({"command": command, **kwargs}),
    )

    local_runtime_server.launch_detached_runtime(
        local_runtime_server.DesktopRuntimeConfig(
            enabled=True,
            host="127.0.0.1",
            port=8787,
            auto_start=True,
            attach_timeout_seconds=5,
            restart_attach_timeout_seconds=5,
            workspace=str(workspace),
        )
    )

    launch = launches[0]
    source_root = Path(local_runtime_server.__file__).resolve().parents[1]
    assert launch["cwd"] == str(source_root)
    assert launch["env"]["PYTHONPATH"].split(os.pathsep)[0] == str(source_root)
    assert launch["command"][1:3] == ["-m", "app_backend.local_runtime_server"]
