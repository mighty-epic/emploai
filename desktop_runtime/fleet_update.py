from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from shared.atomic_io import atomic_write_json
from shared.subprocess_utils import hidden_subprocess_kwargs


FLEET_UPDATE_STATE_FILENAME = "fleet-update-state.json"
FLEET_UPDATE_LOG_FILENAME = "fleet-update.log"
ACTIVE_UPDATE_STATES = frozenset({"queued", "checking", "preserving", "stopping", "pulling", "dependencies", "building", "validating", "restarting"})
UPDATE_STASH_PREFIX = "EmploAI remote update backup"
GIT_TIMEOUT_SECONDS = 3 * 60
SETUP_TIMEOUT_SECONDS = 15 * 60
HOST_RESTART_TIMEOUT_SECONDS = 30
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_path(home: Path) -> Path:
    return Path(home).resolve() / FLEET_UPDATE_STATE_FILENAME


def _log_path(home: Path) -> Path:
    path = Path(home).resolve() / "logs" / FLEET_UPDATE_LOG_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _read_state(home: Path) -> dict[str, Any]:
    try:
        payload = json.loads(_state_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _write_state(home: Path, payload: dict[str, Any]) -> dict[str, Any]:
    next_payload = {**dict(payload), "updated_at": _now()}
    atomic_write_json(_state_path(home), next_payload)
    return next_payload


def _update_job(home: Path, job_id: str, **changes: Any) -> dict[str, Any]:
    state = _read_state(home)
    job = dict(state.get("job") or {})
    if str(job.get("job_id") or "") != str(job_id or ""):
        raise RuntimeError("The remote update job is no longer current")
    job.update(changes)
    state["job"] = job
    return _write_state(home, state)


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    from desktop_runtime.fleet_host import _process_exists as process_exists

    return bool(process_exists(pid))


def _run_capture(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: int = GIT_TIMEOUT_SECONDS,
) -> str:
    result = subprocess.run(
        [str(item) for item in command],
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        **hidden_subprocess_kwargs(),
    )
    if result.returncode != 0:
        raise RuntimeError(f"{Path(str(command[0])).name} exited with code {result.returncode}")
    return str(result.stdout or "").strip()


def _run_logged(
    command: Sequence[str],
    *,
    cwd: Path,
    home: Path,
    timeout: int,
    label: str,
) -> None:
    log_path = _log_path(home)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n[{_now()}] {label}\n")
        log.flush()
        result = subprocess.run(
            [str(item) for item in command],
            cwd=str(cwd),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            **hidden_subprocess_kwargs(),
        )
    if result.returncode != 0:
        raise RuntimeError(f"{label} failed with exit code {result.returncode}")


def _git(root: Path, *args: str, timeout: int = GIT_TIMEOUT_SECONDS) -> str:
    return _run_capture(["git", *args], cwd=root, timeout=timeout)


def _git_ref_exists(root: Path, ref_name: str) -> bool:
    try:
        _git(root, "rev-parse", "--verify", f"{ref_name}^{{commit}}")
        return True
    except Exception:
        return False


def _remote_branch(ref_name: str) -> tuple[str, str] | None:
    clean = str(ref_name or "").strip()
    if "/" not in clean or clean.endswith("/HEAD"):
        return None
    remote, branch = clean.split("/", 1)
    if not remote or not branch:
        return None
    return remote, branch


def _target_version(root: Path, target_commit: str) -> str | None:
    try:
        payload = json.loads(_git(root, "show", f"{target_commit}:package.json"))
    except Exception:
        return None
    return str(payload.get("version") or "").strip() or None if isinstance(payload, dict) else None


def check_source_update(root: Path, *, fetch: bool = True) -> dict[str, Any]:
    root = Path(root).resolve()
    if not (root / ".git").exists():
        return {
            "supported": False,
            "checked": True,
            "state": "unsupported",
            "can_update": False,
            "message": "This EmploAI instance is not running from a Git checkout.",
        }
    if not shutil.which("git"):
        return {
            "supported": False,
            "checked": True,
            "state": "unsupported",
            "can_update": False,
            "message": "Git is not installed or available on PATH.",
        }

    try:
        if fetch:
            _git(root, "fetch", "--quiet", "--all", "--prune")
        branch = _git(root, "branch", "--show-current")
        if not branch:
            raise RuntimeError("The checkout is detached from a branch")
        try:
            upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        except Exception:
            upstream = f"origin/{branch}" if _git_ref_exists(root, f"origin/{branch}") else ""
        pull_target = _remote_branch(upstream)
        if not upstream or not pull_target:
            raise RuntimeError("The current branch has no pullable remote branch")

        current_commit = _git(root, "rev-parse", "HEAD").lower()
        target_commit = _git(root, "rev-parse", upstream).lower()
        counts = _git(root, "rev-list", "--left-right", "--count", f"HEAD...{upstream}").split()
        ahead = max(0, int(counts[0] if counts else 0))
        behind = max(0, int(counts[1] if len(counts) > 1 else 0))
        dirty_lines = [line for line in _git(root, "status", "--porcelain", "--untracked-files=all").splitlines() if line.strip()]
        diverged = ahead > 0 and behind > 0
        update_available = behind > 0
        can_update = bool(update_available and not diverged and pull_target)
        if diverged:
            state = "blocked"
            message = "The remote branch has new commits, but this checkout also has local commits and cannot fast-forward safely."
        elif update_available:
            state = "available"
            message = f"{behind} update commit{'s are' if behind != 1 else ' is'} ready."
        elif ahead:
            state = "ahead"
            message = f"This checkout is {ahead} commit{'s' if ahead != 1 else ''} ahead of its remote branch."
        else:
            state = "current"
            message = "This computer is already up to date."
        return {
            "supported": True,
            "checked": True,
            "state": state,
            "can_update": can_update,
            "update_available": update_available,
            "message": message,
            "branch": branch,
            "upstream": upstream,
            "remote": pull_target[0],
            "remote_branch": pull_target[1],
            "current_commit": current_commit,
            "target_commit": target_commit,
            "current_short_commit": current_commit[:8],
            "target_short_commit": target_commit[:8],
            "target_version": _target_version(root, target_commit),
            "ahead_count": ahead,
            "behind_count": behind,
            "dirty": bool(dirty_lines),
            "dirty_count": len(dirty_lines),
            "local_changes_will_be_preserved": bool(dirty_lines and can_update),
        }
    except Exception as exc:
        return {
            "supported": True,
            "checked": True,
            "state": "error",
            "can_update": False,
            "update_available": False,
            "message": _safe_error(exc, "The remote update check failed."),
        }


def _safe_error(exc: Exception, fallback: str) -> str:
    text = str(exc or "").strip() or fallback
    text = re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1***@", text)
    return text[:600]


def fleet_update_status(home: Path, root: Path) -> dict[str, Any]:
    state = _read_state(home)
    job = dict(state.get("job") or {})
    updater_pid = int(job.get("updater_pid") or 0)
    active = str(job.get("state") or "") in ACTIVE_UPDATE_STATES
    if active and updater_pid and not _process_exists(updater_pid):
        job.update(
            {
                "state": "failed",
                "phase": "failed",
                "message": "The remote updater stopped unexpectedly. The persistent host is still available; check the update log and retry.",
                "error_code": "updater_stopped",
                "completed_at": _now(),
            }
        )
        state["job"] = job
        _write_state(home, state)
        active = False
    return {
        "supported": bool((Path(root).resolve() / ".git").exists() and shutil.which("git")),
        "state": str(job.get("state") or "idle"),
        "active": active,
        "last_check": state.get("last_check") if isinstance(state.get("last_check"), dict) else None,
        "job": job or None,
        "log_path": str(_log_path(home)),
    }


def check_fleet_update(home: Path, root: Path) -> dict[str, Any]:
    status = fleet_update_status(home, root)
    if status["active"]:
        return status
    check = check_source_update(root, fetch=True)
    state = _read_state(home)
    previous_job = dict(state.get("job") or {})
    if previous_job and str(previous_job.get("state") or "") not in ACTIVE_UPDATE_STATES:
        state["last_job"] = previous_job
        state.pop("job", None)
    state["last_check"] = {**check, "checked_at": _now()}
    _write_state(home, state)
    return fleet_update_status(home, root)


def _record_current_check(home: Path, root: Path, job_id: str, current_commit: str) -> None:
    state = _read_state(home)
    job = dict(state.get("job") or {})
    if str(job.get("job_id") or "") != str(job_id or ""):
        raise RuntimeError("The completed update job is no longer current")
    upstream = str(job.get("upstream") or "").strip()
    pull_target = _remote_branch(upstream)
    current_version = _target_version(root, current_commit)
    state["last_check"] = {
        "supported": True,
        "checked": True,
        "state": "current",
        "can_update": False,
        "update_available": False,
        "message": "This computer is already up to date.",
        "branch": job.get("branch"),
        "upstream": upstream or None,
        "remote": pull_target[0] if pull_target else None,
        "remote_branch": pull_target[1] if pull_target else None,
        "current_commit": current_commit,
        "target_commit": current_commit,
        "current_short_commit": current_commit[:8],
        "target_short_commit": current_commit[:8],
        "target_version": current_version,
        "ahead_count": 0,
        "behind_count": 0,
        "dirty": False,
        "dirty_count": 0,
        "local_changes_will_be_preserved": False,
        "checked_at": _now(),
    }
    _write_state(home, state)


def _updater_command(home: Path, job_id: str, expected_commit: str) -> list[str]:
    return [
        str(Path(sys.executable).resolve()),
        "-m",
        "desktop_runtime.backend",
        "fleet-update-run",
        "--home",
        str(Path(home).resolve()),
        "--job-id",
        job_id,
        "--expected-commit",
        expected_commit,
    ]


def start_fleet_update(home: Path, root: Path, *, expected_commit: str, host_pid: int) -> dict[str, Any]:
    home = Path(home).resolve()
    root = Path(root).resolve()
    current_status = fleet_update_status(home, root)
    if current_status["active"]:
        return current_status
    clean_expected = str(expected_commit or "").strip().lower()
    if not _COMMIT_RE.fullmatch(clean_expected):
        raise ValueError("A full expected update commit is required")

    check = check_source_update(root, fetch=True)
    if not check.get("update_available"):
        state = _read_state(home)
        state["last_check"] = {**check, "checked_at": _now()}
        _write_state(home, state)
        return fleet_update_status(home, root)
    if not check.get("can_update"):
        raise RuntimeError(str(check.get("message") or "This checkout cannot be updated safely"))
    if str(check.get("target_commit") or "").lower() != clean_expected:
        raise RuntimeError("The remote branch changed after it was checked. Refresh the update status before confirming.")

    job_id = f"fup_{secrets.token_hex(8)}"
    created_at = _now()
    state = _read_state(home)
    state["last_check"] = {**check, "checked_at": created_at}
    state["job"] = {
        "job_id": job_id,
        "state": "queued",
        "phase": "queued",
        "message": "Remote update accepted and waiting for the updater process.",
        "created_at": created_at,
        "started_at": None,
        "completed_at": None,
        "previous_commit": check.get("current_commit"),
        "target_commit": clean_expected,
        "target_version": check.get("target_version"),
        "branch": check.get("branch"),
        "upstream": check.get("upstream"),
        "dirty_count": check.get("dirty_count", 0),
        "host_pid": int(host_pid or 0) or None,
        "updater_pid": None,
    }
    _write_state(home, state)

    env = os.environ.copy()
    env["EMPLOAI_HOME"] = str(home)
    source_root = str(root)
    existing_pythonpath = str(env.get("PYTHONPATH") or "").strip()
    env["PYTHONPATH"] = os.pathsep.join([source_root, existing_pythonpath]) if existing_pythonpath else source_root
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    try:
        with _log_path(home).open("a", encoding="utf-8") as log:
            process = subprocess.Popen(
                _updater_command(home, job_id, clean_expected),
                cwd=str(root),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                close_fds=True,
                creationflags=creationflags,
            )
    except Exception as exc:
        _update_job(
            home,
            job_id,
            state="failed",
            phase="failed",
            message=_safe_error(exc, "The remote updater could not start."),
            error_code="updater_start_failed",
            completed_at=_now(),
        )
        raise
    latest = _read_state(home)
    latest_job = dict(latest.get("job") or {})
    if str(latest_job.get("job_id") or "") == job_id and str(latest_job.get("state") or "") == "queued":
        latest_job["updater_pid"] = int(process.pid)
        latest["job"] = latest_job
        _write_state(home, latest)
    return fleet_update_status(home, root)


def _stash_changes(home: Path, root: Path, job_id: str, dirty_count: int) -> dict[str, Any] | None:
    if dirty_count <= 0:
        return None
    label = f"{UPDATE_STASH_PREFIX} {_now().replace(':', '-')} ({job_id})"
    _run_logged(
        ["git", "stash", "push", "--include-untracked", "--message", label],
        cwd=root,
        home=home,
        timeout=GIT_TIMEOUT_SECONDS,
        label="Backing up local project changes",
    )
    stash_commit = _git(root, "rev-parse", "--verify", "refs/stash")
    if not stash_commit:
        raise RuntimeError("Local project changes could not be backed up safely")
    return {"count": dirty_count, "label": label, "stash_commit": stash_commit}


def _restore_stash(home: Path, root: Path, backup: dict[str, Any] | None) -> bool:
    if not backup:
        return False
    if _git(root, "rev-parse", "--verify", "refs/stash") != str(backup.get("stash_commit") or ""):
        raise RuntimeError("The update backup is no longer the newest Git stash")
    _run_logged(
        ["git", "stash", "pop", "--index"],
        cwd=root,
        home=home,
        timeout=GIT_TIMEOUT_SECONDS,
        label="Restoring local project changes",
    )
    return True


def _desktop_pid(home: Path) -> int:
    try:
        payload = json.loads((Path(home) / "desktop_shell.pid.json").read_text(encoding="utf-8"))
        pid = int(payload.get("pid") or 0) if isinstance(payload, dict) else 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 0
    return pid if _process_exists(pid) else 0


def _terminate_process_tree(pid: int) -> None:
    if pid <= 0 or not _process_exists(pid):
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
            check=False,
            capture_output=True,
            timeout=30,
            **hidden_subprocess_kwargs(),
        )
    else:
        os.kill(pid, 15)


def _terminate_single_process(pid: int) -> None:
    if pid <= 0 or not _process_exists(pid):
        return
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x0001, False, pid)
        if handle:
            try:
                ctypes.windll.kernel32.TerminateProcess(handle, 1)
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
    else:
        os.kill(pid, 15)


def _stop_app_runtime(home: Path, root: Path) -> None:
    desktop_pid = _desktop_pid(home)
    if desktop_pid:
        _terminate_process_tree(desktop_pid)
    _run_logged(
        [str(Path(sys.executable).resolve()), "-m", "desktop_runtime.backend", "stop", "--preserve-fleet-host"],
        cwd=root,
        home=home,
        timeout=90,
        label="Stopping the desktop backend",
    )


def _changed_files(root: Path, before_commit: str, after_commit: str) -> list[str]:
    if before_commit == after_commit:
        return []
    return [item.strip().replace("\\", "/") for item in _git(root, "diff", "--name-only", f"{before_commit}..{after_commit}").splitlines() if item.strip()]


def _npm_executable() -> str:
    candidate = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not candidate:
        raise RuntimeError("npm is not installed or available on PATH")
    return candidate


def _install_dependencies(home: Path, root: Path, changed_files: Sequence[str]) -> None:
    changed = set(changed_files)
    npm = _npm_executable()
    if {"desktop_app/package.json", "desktop_app/package-lock.json"} & changed:
        _run_logged([npm, "ci"], cwd=root / "desktop_app", home=home, timeout=SETUP_TIMEOUT_SECONDS, label="Installing desktop shell dependencies")
    if {"desktop_app/renderer_client/package.json", "desktop_app/renderer_client/package-lock.json"} & changed:
        _run_logged([npm, "ci"], cwd=root / "desktop_app" / "renderer_client", home=home, timeout=SETUP_TIMEOUT_SECONDS, label="Installing renderer dependencies")
    if "requirements.txt" in changed:
        _run_logged(
            [str(Path(sys.executable).resolve()), "-m", "pip", "install", "-r", str(root / "requirements.txt")],
            cwd=root,
            home=home,
            timeout=SETUP_TIMEOUT_SECONDS,
            label="Installing Python dependencies",
        )


def _build_and_validate(home: Path, root: Path) -> None:
    _run_logged(
        [_npm_executable(), "run", "desktop:build-renderer"],
        cwd=root,
        home=home,
        timeout=SETUP_TIMEOUT_SECONDS,
        label="Building the desktop renderer",
    )
    _run_logged(
        [str(Path(sys.executable).resolve()), "-m", "compileall", "-q", "app_backend", "desktop_runtime", "shared"],
        cwd=root,
        home=home,
        timeout=5 * 60,
        label="Validating the updated Python runtime",
    )


def _start_updated_app(home: Path, root: Path) -> dict[str, Any]:
    os.environ["EMPLOAI_HOME"] = str(Path(home).resolve())
    from app_backend.fleet_host_control import start_desktop_from_fleet_host

    return start_desktop_from_fleet_host()


def _stop_managed_fleet_hosts(home: Path, old_host_pid: int) -> set[int]:
    """Stop every Fleet host generation for this runtime home."""

    from desktop_runtime import backend as desktop_backend

    pids = set(desktop_backend._managed_remote_control_worker_pids(home))
    if old_host_pid > 0 and _process_exists(old_host_pid):
        pids.add(old_host_pid)
    desktop_backend._stop_remote_control_worker(home, scan_processes=True)
    if old_host_pid > 0 and _process_exists(old_host_pid):
        _terminate_single_process(old_host_pid)
    deadline = time.monotonic() + 10
    while any(_process_exists(pid) for pid in pids) and time.monotonic() < deadline:
        time.sleep(0.2)
    return pids


def _restart_host(home: Path, root: Path, old_host_pid: int) -> tuple[bool, int | None]:
    from desktop_runtime.fleet_host import FLEET_HOST_TASK_NAME

    previous_record: dict[str, Any] = {}
    record_path = Path(home) / "desktop_remote_control.pid.json"
    try:
        payload = json.loads(record_path.read_text(encoding="utf-8"))
        previous_record = dict(payload) if isinstance(payload, dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    stopped_pids = _stop_managed_fleet_hosts(home, old_host_pid)
    if any(_process_exists(pid) for pid in stopped_pids):
        return False, None
    _run_logged(
        [str(Path(sys.executable).resolve()), "-m", "desktop_runtime.backend", "fleet-host-install"],
        cwd=root,
        home=home,
        timeout=60,
        label="Refreshing the persistent host registration",
    )
    if os.name == "nt":
        _run_logged(
            ["schtasks.exe", "/Run", "/TN", FLEET_HOST_TASK_NAME],
            cwd=root,
            home=home,
            timeout=30,
            label="Restarting the persistent Fleet host",
        )
    deadline = time.monotonic() + HOST_RESTART_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            payload = json.loads(record_path.read_text(encoding="utf-8"))
            new_pid = int(payload.get("pid") or 0) if isinstance(payload, dict) else 0
            new_started_at = str(payload.get("startedAt") or "") if isinstance(payload, dict) else ""
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            new_pid = 0
            new_started_at = ""
        is_new_generation = bool(
            new_started_at
            and new_started_at != str(previous_record.get("startedAt") or "")
        )
        if new_pid and _process_exists(new_pid) and (
            new_pid not in stopped_pids or is_new_generation
        ):
            return True, new_pid
        time.sleep(0.5)
    return False, None


def run_fleet_update(home: Path, root: Path, *, job_id: str, expected_commit: str) -> dict[str, Any]:
    home = Path(home).resolve()
    root = Path(root).resolve()
    state = _read_state(home)
    job = dict(state.get("job") or {})
    if str(job.get("job_id") or "") != str(job_id or ""):
        raise RuntimeError("Unknown remote update job")
    updater_pid = os.getpid()
    _update_job(home, job_id, state="checking", phase="checking", message="Confirming the remote commit before updating.", started_at=_now(), updater_pid=updater_pid)

    previous_commit = str(job.get("previous_commit") or "").lower()
    backup: dict[str, Any] | None = None
    changed_files: list[str] = []
    checkout_updated = False
    app_restarted = False
    host_restart_attempted = False
    host_restarted = False
    new_host_pid: int | None = None
    rollback_succeeded = False
    restored_local_changes = False
    try:
        check = check_source_update(root, fetch=True)
        if not check.get("can_update") or str(check.get("target_commit") or "").lower() != str(expected_commit or "").lower():
            raise RuntimeError("The checked remote commit is no longer available for a safe fast-forward update")
        if str(check.get("current_commit") or "").lower() != previous_commit:
            raise RuntimeError("The checkout changed after the update was accepted")

        _update_job(home, job_id, state="preserving", phase="preserving", message="Backing up local project changes before updating.")
        backup = _stash_changes(home, root, job_id, int(check.get("dirty_count") or 0))
        _update_job(home, job_id, backup=backup)

        _update_job(home, job_id, state="stopping", phase="stopping", message="Stopping the remote desktop app and backend while keeping Fleet connected.")
        _stop_app_runtime(home, root)

        _update_job(home, job_id, state="pulling", phase="pulling", message=f"Fast-forwarding to {str(expected_commit)[:8]}.")
        _run_logged(
            ["git", "merge", "--ff-only", str(expected_commit)],
            cwd=root,
            home=home,
            timeout=GIT_TIMEOUT_SECONDS,
            label="Fast-forwarding the EmploAI checkout",
        )
        current_commit = _git(root, "rev-parse", "HEAD").lower()
        if current_commit != str(expected_commit).lower():
            raise RuntimeError("The checkout did not reach the confirmed update commit")
        checkout_updated = True
        changed_files = _changed_files(root, previous_commit, current_commit)

        _update_job(home, job_id, state="dependencies", phase="dependencies", message="Installing dependency changes required by the update.", changed_files=changed_files)
        _install_dependencies(home, root, changed_files)
        _update_job(home, job_id, state="building", phase="building", message="Building the updated desktop interface.")
        _build_and_validate(home, root)
        _update_job(home, job_id, state="restarting", phase="restarting", message="Starting the updated backend and desktop app.")
        app_status = _start_updated_app(home, root)
        app_restarted = bool((app_status.get("runtime") or {}).get("ready") and (app_status.get("desktop") or {}).get("running"))
        if not app_restarted:
            raise RuntimeError("The updated backend or desktop app did not become ready")

        current_version = _target_version(root, current_commit)
        host_restart_attempted = True
        host_restarted, new_host_pid = _restart_host(
            home,
            root,
            int(job.get("host_pid") or 0),
        )
        if not host_restarted:
            raise RuntimeError(
                "The updated app started, but its persistent Fleet host did not reload cleanly"
            )
        _update_job(
            home,
            job_id,
            state="completed",
            phase="completed",
            message=f"Updated to {current_commit[:8]} and restarted EmploAI.",
            current_commit=current_commit,
            current_version=current_version,
            completed_at=_now(),
            app_restarted=True,
            host_restart_pending=False,
            host_restarted=True,
            new_host_pid=new_host_pid,
            updater_pid=updater_pid,
        )
        _record_current_check(home, root, job_id, current_commit)
        return fleet_update_status(home, root)
    except Exception as exc:
        recovery_errors: list[str] = []
        if checkout_updated and previous_commit and _COMMIT_RE.fullmatch(previous_commit):
            try:
                _update_job(home, job_id, state="restarting", phase="rollback", message="The update failed; restoring the previous checkout.")
                _run_logged(
                    ["git", "reset", "--hard", previous_commit],
                    cwd=root,
                    home=home,
                    timeout=GIT_TIMEOUT_SECONDS,
                    label="Rolling back the failed update",
                )
                _install_dependencies(home, root, changed_files)
                _build_and_validate(home, root)
                rollback_succeeded = _git(root, "rev-parse", "HEAD").lower() == previous_commit
            except Exception as rollback_error:
                recovery_errors.append(_safe_error(rollback_error, "Rollback failed"))
        if backup and (not checkout_updated or rollback_succeeded):
            try:
                restored_local_changes = _restore_stash(home, root, backup)
            except Exception as restore_error:
                recovery_errors.append(_safe_error(restore_error, "Local-change restore failed"))
        if host_restart_attempted:
            try:
                recovered_host, recovered_host_pid = _restart_host(
                    home,
                    root,
                    int(new_host_pid or job.get("host_pid") or 0),
                )
                host_restarted = bool(recovered_host)
                new_host_pid = recovered_host_pid
                if not recovered_host:
                    recovery_errors.append("Persistent Fleet host recovery did not become ready")
            except Exception as host_recovery_error:
                recovery_errors.append(
                    _safe_error(host_recovery_error, "Persistent Fleet host recovery failed")
                )
        try:
            app_status = _start_updated_app(home, root)
            app_restarted = bool((app_status.get("runtime") or {}).get("ready") and (app_status.get("desktop") or {}).get("running"))
        except Exception as restart_error:
            recovery_errors.append(_safe_error(restart_error, "Restart failed"))
        message = _safe_error(exc, "The remote update failed.")
        if rollback_succeeded:
            message += " The previous version was restored."
        if recovery_errors:
            message += " Recovery needs attention; inspect the local Fleet update log."
        _update_job(
            home,
            job_id,
            state="failed",
            phase="failed",
            message=message,
            error_code="remote_update_failed",
            completed_at=_now(),
            checkout_updated=checkout_updated,
            rollback_succeeded=rollback_succeeded,
            restored_local_changes=restored_local_changes,
            app_restarted=app_restarted,
            host_restart_pending=bool(host_restart_attempted and not host_restarted),
            host_restarted=host_restarted,
            new_host_pid=new_host_pid,
            recovery_errors=recovery_errors,
            updater_pid=updater_pid,
        )
        return fleet_update_status(home, root)
