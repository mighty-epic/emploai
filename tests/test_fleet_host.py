from __future__ import annotations

from pathlib import Path

import os

from desktop_runtime.fleet_host import (
    _backend_command,
    _launcher_text,
    _process_exists,
    _scheduled_task_text,
    fleet_host_process_lock,
)


def test_fleet_host_launcher_is_hidden_and_runs_the_dedicated_host(tmp_path: Path):
    launcher = _launcher_text(_backend_command(tmp_path))

    assert "run-remote-control-worker" in launcher
    assert "--home" in launcher
    assert ", 0, False" in launcher
    assert "sessionToken" not in launcher


def test_fleet_host_scheduled_task_restarts_failures_without_a_time_limit(tmp_path: Path):
    task = _scheduled_task_text(tmp_path)

    assert "run-remote-control-worker" in task
    assert "<RestartOnFailure>" in task
    assert "<Count>999</Count>" in task
    assert "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>" in task
    assert "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>" in task
    assert "sessionToken" not in task


def test_fleet_host_process_lock_allows_only_one_owner(tmp_path: Path):
    with fleet_host_process_lock(tmp_path) as first:
        with fleet_host_process_lock(tmp_path) as second:
            assert first is True
            assert second is False

    with fleet_host_process_lock(tmp_path) as reacquired:
        assert reacquired is True


def test_fleet_host_process_check_handles_current_windows_process():
    assert _process_exists(os.getpid()) is True
    assert _process_exists(0) is False
