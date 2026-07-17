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
    assert "<TimeTrigger>" in task
    assert "<Interval>PT1M</Interval>" in task
    assert "<StopAtDurationEnd>false</StopAtDurationEnd>" in task
    assert "sessionToken" not in task


def test_fleet_host_task_file_is_written_as_utf16_for_windows_scheduler(monkeypatch, tmp_path: Path):
    import desktop_runtime.fleet_host as fleet_host

    monkeypatch.setattr(fleet_host, "_run_schtasks", lambda *_args: type("Result", (), {"returncode": 0})())

    assert fleet_host._register_scheduled_task(tmp_path) is None
    payload = fleet_host.fleet_host_task_path(tmp_path).read_bytes()
    assert payload.startswith((b"\xff\xfe", b"\xfe\xff"))
    assert "RestartOnFailure" in payload.decode("utf-16")


def test_fleet_host_task_uses_windows_resolved_account(monkeypatch, tmp_path: Path):
    import desktop_runtime.fleet_host as fleet_host

    monkeypatch.setattr(fleet_host, "_windows_current_user_id", lambda: r"VPS\Administrator")

    task = fleet_host._scheduled_task_text(tmp_path)

    assert "<UserId>VPS\\Administrator</UserId>" in task
    assert "WORKGROUP\\Administrator" not in task


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
