from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from desktop_runtime import fleet_update
from desktop_runtime.config import current_source_revision


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _update_fixture(tmp_path: Path) -> tuple[Path, str, str]:
    remote = tmp_path / "remote.git"
    author = tmp_path / "author"
    child = tmp_path / "child"
    remote.mkdir()
    _git(remote, "init", "--bare")
    author.mkdir()
    _git(author, "init", "-b", "emplo-changes")
    _git(author, "config", "user.email", "tests@example.com")
    _git(author, "config", "user.name", "EmploAI Tests")
    _write(author / "package.json", json.dumps({"name": "emploai", "version": "1.0.0"}))
    _write(author / "README.md", "initial\n")
    _git(author, "add", ".")
    _git(author, "commit", "-m", "initial")
    previous = _git(author, "rev-parse", "HEAD")
    _git(author, "remote", "add", "origin", str(remote))
    _git(author, "push", "-u", "origin", "emplo-changes")
    _git(tmp_path, "clone", "--branch", "emplo-changes", str(remote), str(child))
    _write(author / "package.json", json.dumps({"name": "emploai", "version": "1.1.0"}))
    _write(author / "README.md", "updated\n")
    _git(author, "add", ".")
    _git(author, "commit", "-m", "update")
    target = _git(author, "rev-parse", "HEAD")
    _git(author, "push")
    return child, previous, target


def _seed_job(home: Path, check: dict, *, job_id: str = "fup_test", host_pid: int = 1234) -> str:
    fleet_update._write_state(
        home,
        {
            "last_check": check,
            "job": {
                "job_id": job_id,
                "state": "queued",
                "phase": "queued",
                "previous_commit": check["current_commit"],
                "target_commit": check["target_commit"],
                "dirty_count": check["dirty_count"],
                "host_pid": host_pid,
            },
        },
    )
    return job_id


def test_source_update_check_reports_exact_fast_forward_and_dirty_backup(tmp_path: Path):
    child, previous, target = _update_fixture(tmp_path)
    _write(child / "local-note.txt", "keep me\n")

    status = fleet_update.check_source_update(child)

    assert status["state"] == "available"
    assert status["can_update"] is True
    assert status["current_commit"] == previous
    assert status["target_commit"] == target
    assert status["target_version"] == "1.1.0"
    assert status["dirty"] is True
    assert status["local_changes_will_be_preserved"] is True
    assert current_source_revision(child) == previous


def test_start_fleet_update_requires_the_checked_exact_commit(monkeypatch, tmp_path: Path):
    child, _previous, target = _update_fixture(tmp_path)
    home = tmp_path / "runtime"
    home.mkdir()
    check = fleet_update.check_source_update(child)

    class Process:
        pid = os.getpid()

    monkeypatch.setattr(fleet_update.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    monkeypatch.setattr(fleet_update, "check_source_update", lambda *_args, **_kwargs: dict(check))

    with pytest.raises(RuntimeError, match="changed after it was checked"):
        fleet_update.start_fleet_update(home, child, expected_commit="0" * 40, host_pid=55)

    accepted = fleet_update.start_fleet_update(home, child, expected_commit=target, host_pid=55)

    assert accepted["active"] is True
    assert accepted["job"]["target_commit"] == target
    assert accepted["job"]["host_pid"] == 55


def test_remote_update_preserves_changes_updates_restarts_and_reloads_host(monkeypatch, tmp_path: Path):
    child, previous, target = _update_fixture(tmp_path)
    home = tmp_path / "runtime"
    home.mkdir()
    _write(child / "local-note.txt", "keep me\n")
    check = fleet_update.check_source_update(child)
    job_id = _seed_job(home, check)
    calls: list[str] = []

    monkeypatch.setattr(fleet_update, "_stop_app_runtime", lambda *_args: calls.append("stop"))
    monkeypatch.setattr(fleet_update, "_install_dependencies", lambda *_args: calls.append("dependencies"))
    monkeypatch.setattr(fleet_update, "_build_and_validate", lambda *_args: calls.append("build"))
    monkeypatch.setattr(
        fleet_update,
        "_start_updated_app",
        lambda *_args: {"runtime": {"ready": True}, "desktop": {"running": True}},
    )
    monkeypatch.setattr(
        fleet_update,
        "_restart_host",
        lambda *_args, **_kwargs: (True, 9876),
    )

    result = fleet_update.run_fleet_update(home, child, job_id=job_id, expected_commit=target)

    assert result["state"] == "completed"
    assert result["job"]["host_restarted"] is True
    assert result["job"]["new_host_pid"] == 9876
    assert result["last_check"]["state"] == "current"
    assert result["last_check"]["update_available"] is False
    assert result["last_check"]["current_commit"] == target
    assert result["last_check"]["target_commit"] == target
    assert _git(child, "rev-parse", "HEAD") == target
    assert not (child / "local-note.txt").exists()
    assert fleet_update.UPDATE_STASH_PREFIX in _git(child, "stash", "list")
    assert calls == ["stop", "dependencies", "build"]
    assert previous != target


def test_remote_update_never_reports_completed_when_host_generation_did_not_reload(
    monkeypatch,
    tmp_path: Path,
):
    child, previous, target = _update_fixture(tmp_path)
    home = tmp_path / "runtime"
    home.mkdir()
    check = fleet_update.check_source_update(child)
    job_id = _seed_job(home, check)
    restart_results = iter(((False, None), (True, 9877)))

    monkeypatch.setattr(fleet_update, "_stop_app_runtime", lambda *_args: None)
    monkeypatch.setattr(fleet_update, "_install_dependencies", lambda *_args: None)
    monkeypatch.setattr(fleet_update, "_build_and_validate", lambda *_args: None)
    monkeypatch.setattr(
        fleet_update,
        "_start_updated_app",
        lambda *_args: {"runtime": {"ready": True}, "desktop": {"running": True}},
    )
    monkeypatch.setattr(
        fleet_update,
        "_restart_host",
        lambda *_args, **_kwargs: next(restart_results),
    )

    result = fleet_update.run_fleet_update(
        home,
        child,
        job_id=job_id,
        expected_commit=target,
    )

    assert result["state"] == "failed"
    assert result["job"]["rollback_succeeded"] is True
    assert result["job"]["host_restarted"] is True
    assert _git(child, "rev-parse", "HEAD") == previous


def test_restart_host_stops_every_previous_generation_before_starting_one(
    monkeypatch,
    tmp_path: Path,
):
    home = tmp_path / "runtime"
    root = tmp_path / "checkout"
    home.mkdir()
    root.mkdir()
    calls: list[object] = []
    live_pids = {111, 222}
    record_path = home / "desktop_remote_control.pid.json"
    record_path.write_text(
        json.dumps({"pid": 111, "startedAt": "2026-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )

    def stop_hosts(_home, old_host_pid):
        calls.append(("stop", old_host_pid))
        live_pids.clear()
        record_path.unlink()
        return {111, 222}

    def run_logged(command, **_kwargs):
        calls.append(tuple(command))
        if "schtasks.exe" in command:
            record_path.write_text(
                json.dumps({"pid": 333, "startedAt": "2026-01-01T00:01:00+00:00"}),
                encoding="utf-8",
            )
            live_pids.add(333)

    monkeypatch.setattr(fleet_update, "_stop_managed_fleet_hosts", stop_hosts)
    monkeypatch.setattr(fleet_update, "_run_logged", run_logged)
    monkeypatch.setattr(fleet_update, "_process_exists", lambda pid: pid in live_pids)
    monkeypatch.setattr(fleet_update.time, "sleep", lambda _seconds: None)

    restarted, new_pid = fleet_update._restart_host(home, root, 111)

    assert restarted is True
    assert new_pid == 333
    assert calls[0] == ("stop", 111)
    assert any("fleet-host-install" in call for call in calls if isinstance(call, tuple))


def test_restart_host_requires_the_expected_source_generation(monkeypatch, tmp_path: Path):
    home = tmp_path / "runtime"
    root = tmp_path / "checkout"
    home.mkdir()
    root.mkdir()
    live_pids = {333}
    record_path = home / "desktop_remote_control.pid.json"

    monkeypatch.setattr(fleet_update, "_stop_managed_fleet_hosts", lambda *_args: set())
    monkeypatch.setattr(fleet_update, "_process_exists", lambda pid: pid in live_pids)
    monkeypatch.setattr(fleet_update.time, "sleep", lambda _seconds: None)

    def run_logged(command, **_kwargs):
        if "schtasks.exe" in command:
            record_path.write_text(
                json.dumps(
                    {
                        "pid": 333,
                        "startedAt": "2026-01-01T00:01:00+00:00",
                        "sourceRevision": "old-revision",
                    }
                ),
                encoding="utf-8",
            )

    monkeypatch.setattr(fleet_update, "_run_logged", run_logged)

    restarted, new_pid = fleet_update._restart_host(
        home,
        root,
        111,
        expected_revision="new-revision",
    )

    assert restarted is False
    assert new_pid is None


def test_failed_remote_update_rolls_back_and_restores_local_changes(monkeypatch, tmp_path: Path):
    child, previous, target = _update_fixture(tmp_path)
    home = tmp_path / "runtime"
    home.mkdir()
    _write(child / "local-note.txt", "keep me\n")
    check = fleet_update.check_source_update(child)
    job_id = _seed_job(home, check)
    build_calls = 0

    monkeypatch.setattr(fleet_update, "_stop_app_runtime", lambda *_args: None)
    monkeypatch.setattr(fleet_update, "_install_dependencies", lambda *_args: None)

    def build_then_recover(*_args):
        nonlocal build_calls
        build_calls += 1
        if build_calls == 1:
            raise RuntimeError("simulated build failure")

    monkeypatch.setattr(fleet_update, "_build_and_validate", build_then_recover)
    monkeypatch.setattr(
        fleet_update,
        "_start_updated_app",
        lambda *_args: {"runtime": {"ready": True}, "desktop": {"running": True}},
    )

    result = fleet_update.run_fleet_update(home, child, job_id=job_id, expected_commit=target)

    assert result["state"] == "failed"
    assert result["job"]["rollback_succeeded"] is True
    assert result["job"]["restored_local_changes"] is True
    assert result["job"]["app_restarted"] is True
    assert _git(child, "rev-parse", "HEAD") == previous
    assert (child / "local-note.txt").read_text(encoding="utf-8") == "keep me\n"
