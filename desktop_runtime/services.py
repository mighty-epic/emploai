from __future__ import annotations

def _telegram_service_status(
    home: Path,
    *,
    enabled: bool,
    configured: bool,
    scan_processes: bool = True,
) -> TelegramServiceStatus:
    log_path = _telegram_runtime_log_path(home)
    record = _read_telegram_pid_record(home)
    status_record = _read_telegram_status_record(home) or {}
    status_state = str(status_record.get("state") or "").strip().lower()
    status_detail = str(status_record.get("detail") or "").strip() or None
    ready_at = str(status_record.get("readyAt") or "").strip() or None

    if not enabled:
        return TelegramServiceStatus(
            enabled=False,
            configured=configured,
            state="disabled",
            detail="Telegram channel is disabled in config.json.",
            log_path=str(log_path),
            ready_at=ready_at,
        )

    if not configured:
        return TelegramServiceStatus(
            enabled=True,
            configured=False,
            state="not_configured",
            detail="Telegram is enabled but TELEGRAM_BOT_TOKEN or ALLOWED_USER_IDS is missing.",
            log_path=str(log_path),
            ready_at=ready_at,
        )

    worker_pids: list[int] = []
    pid = 0
    if scan_processes:
        worker_pids = _managed_telegram_worker_pids(home)
        pid = worker_pids[0] if len(worker_pids) == 1 else 0
    if not pid and record:
        recorded_pid = int(record.get("pid") or 0)
        if recorded_pid and _process_exists(recorded_pid):
            pid = recorded_pid
            worker_pids = [pid]

    tail = _tail_text(log_path)
    if len(worker_pids) > 1:
        return TelegramServiceStatus(
            enabled=True,
            configured=True,
            state="degraded",
            detail=f"Multiple local Telegram workers are running ({len(worker_pids)}). Restarting the managed worker will clean them up.",
            log_path=str(log_path),
            ready_at=ready_at,
        )

    if pid:
        if "telegram.error.Conflict" in tail or "terminated by other getUpdates request" in tail:
            return TelegramServiceStatus(
                enabled=True,
                configured=True,
                state="degraded",
                detail="Telegram worker is running but another bot poller is conflicting with getUpdates.",
                process_id=pid,
                log_path=str(log_path),
                ready_at=ready_at,
            )
        if status_state == "running":
            return TelegramServiceStatus(
                enabled=True,
                configured=True,
                state="running",
                detail=status_detail,
                process_id=pid,
                log_path=str(log_path),
                ready_at=ready_at,
            )
        if status_state == "degraded":
            return TelegramServiceStatus(
                enabled=True,
                configured=True,
                state="degraded",
                detail=status_detail or "Telegram worker started but reported a degraded state.",
                process_id=pid,
                log_path=str(log_path),
                ready_at=ready_at,
            )
        return TelegramServiceStatus(
            enabled=True,
            configured=True,
            state="starting",
            detail=status_detail or "Telegram worker is starting in the background.",
            process_id=pid,
            log_path=str(log_path),
            ready_at=ready_at,
        )

    if "telegram.error.Conflict" in tail or "terminated by other getUpdates request" in tail:
        return TelegramServiceStatus(
            enabled=True,
            configured=True,
            state="degraded",
            detail="Telegram worker could not stabilize because another bot poller is active.",
            log_path=str(log_path),
            ready_at=ready_at,
        )

    if status_state == "degraded":
        return TelegramServiceStatus(
            enabled=True,
            configured=True,
            state="degraded",
            detail=status_detail or "Telegram worker failed during startup.",
            log_path=str(log_path),
            ready_at=ready_at,
        )

    return TelegramServiceStatus(
        enabled=True,
        configured=True,
        state="offline",
        detail=status_detail or "Telegram worker is not running.",
        log_path=str(log_path),
        ready_at=ready_at,
    )


def _ensure_telegram_worker(
    home: Path,
    *,
    enabled: bool,
    configured: bool,
    config_fingerprint: str = "",
) -> TelegramServiceStatus:
    if not enabled or not configured:
        _stop_telegram_worker(home, scan_processes=False)
        return _telegram_service_status(home, enabled=enabled, configured=configured, scan_processes=False)

    record = _read_telegram_pid_record(home) or {}
    status_record = _read_telegram_status_record(home) or {}
    record_fingerprint = str(
        record.get("configFingerprint")
        or status_record.get("configFingerprint")
        or ""
    ).strip()
    if config_fingerprint and record_fingerprint != config_fingerprint:
        _stop_telegram_worker(home)

    worker_pids = _managed_telegram_worker_pids(home)
    if len(worker_pids) > 1:
        _stop_telegram_worker(home)

    status = _telegram_service_status(home, enabled=enabled, configured=configured)
    if status.process_id:
        return status
    if status.state == "degraded":
        status_record = _read_telegram_status_record(home) or {}
        updated_at = str(status_record.get("updatedAt") or "").strip()
        if updated_at:
            try:
                updated_at_epoch = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).timestamp()
            except Exception:
                updated_at_epoch = 0.0
            if updated_at_epoch and (time.time() - updated_at_epoch) < 15:
                return status

    _write_telegram_status_record(
        home,
        state="starting",
        detail="Telegram worker is starting in the background.",
        config_fingerprint=config_fingerprint or None,
    )
    _launch_detached_telegram_worker(home)
    time.sleep(0.2)
    return _telegram_service_status(home, enabled=enabled, configured=configured)


from shared.standalone_policy import cloud_backend_enabled


def _yggdrasil_remote_session_configured(home: Path) -> bool:
    try:
        payload = remote_account_session_payload(home)
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        return False
    transport = payload.get("transport") if isinstance(payload.get("transport"), dict) else {}
    return bool(
        str((transport or {}).get("kind") or "").strip().lower() == "yggdrasil"
        and str(payload.get("apiBaseUrl") or payload.get("api_base_url") or "").strip()
        and str(payload.get("sessionToken") or payload.get("session_token") or "").strip()
    )


def _remote_control_configured_from_values(values: dict[str, str]) -> bool:
    if not cloud_backend_enabled():
        return _yggdrasil_remote_session_configured(runtime_home())
    if remote_account_session_configured(runtime_home()):
        return True
    return bool(
        str(values.get("EMPLOAI_REMOTE_CONTROL_BASE_URL", "") or "").strip()
        and str(values.get("EMPLOAI_REMOTE_CONTROL_EMAIL", "") or "").strip()
        and str(values.get("EMPLOAI_REMOTE_CONTROL_PASSWORD", "") or "").strip()
    )


def _remote_control_service_status(
    home: Path,
    *,
    configured: bool,
    validate_pid: bool = True,
) -> RemoteControlServiceStatus:
    log_path = _remote_control_runtime_log_path(home)
    record = _read_remote_control_pid_record(home)
    status_record = _read_remote_control_status_record(home) or {}
    pid = int(record.get("pid") or 0) if record else 0
    if validate_pid and pid and not _process_exists(pid):
        pid = 0
    status_state = str(status_record.get("state") or "").strip().lower()
    status_detail = str(status_record.get("detail") or "").strip() or None
    ready_at = str(status_record.get("readyAt") or "").strip() or None
    desktop_id = str(status_record.get("desktopId") or "").strip() or None
    desktop_name = str(status_record.get("desktopName") or "").strip() or None

    if not configured:
        return RemoteControlServiceStatus(
            configured=False,
            state="not_configured",
            detail="Remote control is not configured yet.",
            log_path=str(log_path),
            desktop_id=desktop_id,
            desktop_name=desktop_name,
            ready_at=ready_at,
        )

    if pid:
        if status_state == "running":
            running_detail = (
                "Desktop is connected to the Yggdrasil Fleet manager."
                if _yggdrasil_remote_session_configured(home)
                else "Desktop is connected to the EmploAI cloud control plane."
            )
            return RemoteControlServiceStatus(
                configured=True,
                state="running",
                detail=status_detail or running_detail,
                process_id=pid,
                log_path=str(log_path),
                desktop_id=desktop_id,
                desktop_name=desktop_name,
                ready_at=ready_at,
            )
        if status_state == "degraded":
            return RemoteControlServiceStatus(
                configured=True,
                state="degraded",
                detail=status_detail or "Remote control worker started but reported an error.",
                process_id=pid,
                log_path=str(log_path),
                desktop_id=desktop_id,
                desktop_name=desktop_name,
                ready_at=ready_at,
            )
        return RemoteControlServiceStatus(
            configured=True,
            state="starting",
            detail=status_detail or "Remote control worker is starting in the background.",
            process_id=pid,
            log_path=str(log_path),
            desktop_id=desktop_id,
            desktop_name=desktop_name,
            ready_at=ready_at,
        )

    if status_state == "degraded":
        return RemoteControlServiceStatus(
            configured=True,
            state="degraded",
            detail=status_detail or "Remote control worker failed during startup.",
            log_path=str(log_path),
            desktop_id=desktop_id,
            desktop_name=desktop_name,
            ready_at=ready_at,
        )

    return RemoteControlServiceStatus(
        configured=True,
        state="offline",
        detail=status_detail or "Remote control worker is not running.",
        log_path=str(log_path),
        desktop_id=desktop_id,
        desktop_name=desktop_name,
        ready_at=ready_at,
    )


def _ensure_remote_control_worker(
    home: Path,
    *,
    configured: bool,
    config_fingerprint: str = "",
) -> RemoteControlServiceStatus:
    if not configured:
        _stop_remote_control_worker(home)
        return _remote_control_service_status(home, configured=False)

    record = _read_remote_control_pid_record(home) or {}
    status_record = _read_remote_control_status_record(home) or {}
    record_fingerprint = str(
        record.get("configFingerprint")
        or status_record.get("configFingerprint")
        or ""
    ).strip()
    if config_fingerprint and record_fingerprint != config_fingerprint:
        _stop_remote_control_worker(home)

    record = _read_remote_control_pid_record(home) or {}
    recorded_pid = int(record.get("pid") or 0)
    worker_pids = _managed_remote_control_worker_pids(home)
    if len(worker_pids) > 1 or (worker_pids and recorded_pid not in worker_pids):
        _stop_remote_control_worker(home)

    status = _remote_control_service_status(home, configured=True)
    if status.process_id:
        return status
    if status.state == "degraded":
        status_record = _read_remote_control_status_record(home) or {}
        updated_at = str(status_record.get("updatedAt") or "").strip()
        if updated_at:
            try:
                updated_at_epoch = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).timestamp()
            except Exception:
                updated_at_epoch = 0.0
            if updated_at_epoch and (time.time() - updated_at_epoch) < 15:
                return status

    _write_remote_control_status_record(
        home,
        state="starting",
        detail="Remote control worker is starting in the background.",
        config_fingerprint=config_fingerprint or None,
    )
    _launch_detached_remote_control_worker(home)
    time.sleep(0.2)
    return _remote_control_service_status(home, configured=True)


def _wait_for_runtime(config: "DesktopRuntimeConfig", home: Path, *, timeout_seconds: int) -> DesktopRuntimeStatus:
    deadline = time.monotonic() + max(2, timeout_seconds)
    last_status = _get_runtime_status()
    failure_detail = _runtime_log_failure_detail(home)
    if failure_detail:
        last_status.detail = failure_detail
        last_status.state = "failed"
        last_status.degraded = True
        return last_status
    while time.monotonic() < deadline:
        time.sleep(READINESS_POLL_INTERVAL_SECONDS)
        last_status = _get_runtime_status()
        if last_status.ok:
            return last_status
        failure_detail = _runtime_log_failure_detail(home)
        if failure_detail:
            last_status.detail = failure_detail
            last_status.state = "failed"
            last_status.degraded = True
            return last_status
    return last_status


def _port_conflict_pids(config: "DesktopRuntimeConfig", home: Path, *, status: Any | None = None) -> list[int]:
    managed_pids = set(_managed_runtime_pids(home, config, status=status))
    return sorted(
        pid
        for pid in _process_ids_for_port(int(config.port or 0))
        if pid not in managed_pids and _process_exists(pid)
    )


def _ensure_runtime(
    config: "DesktopRuntimeConfig",
    home: Path,
    *,
    require_auto_start: bool = True,
    attach_timeout_override: int | None = None,
    restart_attach_timeout_override: int | None = None,
) -> tuple[Any, str]:
    status = _get_runtime_status()
    if status.ok:
        if not _attached_runtime_requires_restart_checked(status, home=home):
            return status, "attached"

        incompatible_pids = _managed_runtime_pids(home, config, status=status)
        health_pid = _runtime_health_process_id(status)
        if health_pid and health_pid not in incompatible_pids and _is_runtime_process(health_pid):
            incompatible_pids.append(health_pid)
        for pid in sorted(set(incompatible_pids)):
            _terminate_pid(pid)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if not any(_process_exists(pid) for pid in incompatible_pids):
                break
            time.sleep(0.2)
        status = _get_runtime_status()
        if status.ok and not _attached_runtime_requires_restart_checked(status, home=home):
            return status, "reattached"

    if not config.enabled:
        raise RuntimeError(status.detail or "Desktop runtime is disabled in config.json")
    if require_auto_start and not config.auto_start:
        raise RuntimeError("Desktop runtime is offline and auto-start is disabled")

    port_conflicts = _port_conflict_pids(config, home, status=status)
    if port_conflicts:
        conflict_text = ", ".join(str(pid) for pid in port_conflicts)
        raise RuntimeError(
            f"Configured desktop port {config.port} is already in use by another process ({conflict_text})."
        )

    stale_pids = _managed_runtime_pids(home, config, status=status)
    if stale_pids:
        _stop_runtime(home, config)
        time.sleep(0.4)

    attach_timeout_seconds = max(2, int(attach_timeout_override or config.attach_timeout_seconds or DEFAULT_ATTACH_TIMEOUT_SECONDS))
    restart_attach_timeout_seconds = max(
        2,
        int(
            restart_attach_timeout_override
            or min(DEFAULT_RESTART_ATTACH_TIMEOUT_SECONDS, attach_timeout_seconds)
        ),
    )

    _launch_detached_daemon(config, home)
    status = _wait_for_runtime(config, home, timeout_seconds=attach_timeout_seconds)
    if status.ok:
        return status, "launched"

    recovered_pids = _managed_runtime_pids(home, config, status=status)
    if recovered_pids:
        _stop_runtime(home, config)
        time.sleep(0.4)
        _launch_detached_daemon(config, home)
        status = _wait_for_runtime(config, home, timeout_seconds=restart_attach_timeout_seconds)
        if status.ok:
            return status, "recovered"

    failure_detail = str(status.detail or "").strip()
    if failure_detail:
        raise RuntimeError(failure_detail)

    raise RuntimeError(
        f"Desktop runtime did not become ready within {attach_timeout_seconds} seconds. "
        f"See {_runtime_log_path(home)} for startup logs."
    )


def _runtime_health_process_id(status: Any) -> int:
    try:
        return int(getattr(status, "process_id", 0) or 0)
    except Exception:
        return 0


def _process_command_line(pid: int) -> str:
    if pid <= 0:
        return ""

    try:
        if os.name == "nt":
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        f'$process = Get-CimInstance Win32_Process -Filter "ProcessId = {pid}" '
                        '-ErrorAction SilentlyContinue; '
                        'if ($null -ne $process) { [string]$process.CommandLine }'
                    ),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.stdout.strip()

        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _process_ids_for_command_markers(*markers: str) -> set[int]:
    normalized_markers = [str(marker or "").strip().lower() for marker in markers if str(marker or "").strip()]
    if not normalized_markers:
        return set()

    try:
        if os.name == "nt":
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        "Get-CimInstance Win32_Process | ForEach-Object { "
                        "if ($_.CommandLine) { \"{0}`t{1}\" -f $_.ProcessId, $_.CommandLine } "
                        "}"
                    ),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            result = subprocess.run(
                ["ps", "-eo", "pid=,command="],
                capture_output=True,
                text=True,
                check=False,
            )

        pids: set[int] = set()
        for line in result.stdout.splitlines():
            if os.name == "nt":
                pid_text, separator, command_line = line.partition("\t")
            else:
                stripped = line.strip()
                pid_text, separator, command_line = stripped.partition(" ")
            if not separator:
                continue
            normalized_command_line = command_line.lower()
            if not all(marker in normalized_command_line for marker in normalized_markers):
                continue
            try:
                pids.add(int(pid_text.strip()))
            except ValueError:
                continue
        return pids
    except Exception:
        return set()


def _process_executable_path(pid: int) -> str:
    if pid <= 0:
        return ""

    try:
        if os.name == "nt":
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    (
                        f'$process = Get-CimInstance Win32_Process -Filter "ProcessId = {pid}" '
                        '-ErrorAction SilentlyContinue; '
                        'if ($null -ne $process) { [string]$process.ExecutablePath }'
                    ),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.stdout.strip()

        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "comm="],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _is_runtime_process(pid: int) -> bool:
    command_line = _process_command_line(pid).lower()
    if not command_line:
        return False

    marker_groups = (
        ("desktop_runtime.backend", "run-daemon"),
        ("deploy.windows.release_backend", "run-daemon"),
        ("app_backend.local_runtime_server", " run"),
        ("app_backend.desktop_runtime", " run"),
        ("emploaibackend.exe", "run-daemon"),
    )
    return any(all(marker in command_line for marker in markers) for markers in marker_groups)


def _is_desktop_runtime_worker_process(pid: int, worker_command: str) -> bool:
    command_line = _process_command_line(pid).lower()
    if not command_line or worker_command not in command_line:
        return False

    executable_path = _process_executable_path(pid).lower()
    if "emploaibackend" in executable_path or "emploaibackend.exe" in command_line:
        return True

    normalized = f" {command_line}"
    return (
        " -m desktop_runtime.backend" in normalized
        or " -m deploy.windows.release_backend" in normalized
    )


def _runtime_process_matches_current_build(pid: int) -> bool:
    if pid <= 0 or not _process_exists(pid):
        return False
    if not _is_runtime_process(pid):
        return False

    current_executable = str(Path(sys.executable).resolve()).strip().lower()
    process_executable = _process_executable_path(pid).strip().lower()
    if current_executable and process_executable:
        return process_executable == current_executable

    command_line = _process_command_line(pid).strip().lower()
    if not command_line:
        return False
    if getattr(sys, "frozen", False):
        return current_executable in command_line if current_executable else False
    return (
        "desktop_runtime.backend" in command_line
        or "deploy.windows.release_backend" in command_line
        or "app_backend.local_runtime_server" in command_line
        or "app_backend.desktop_runtime" in command_line
    ) and (current_executable in command_line if current_executable else True)


def _attached_runtime_requires_restart_checked(
    status: Any,
    *,
    home: Path | None = None,
    root: Path | None = None,
) -> bool:
    try:
        return _attached_runtime_requires_restart(status, home=home, root=root)
    except TypeError as exc:
        if "unexpected keyword" not in str(exc):
            raise
        return _attached_runtime_requires_restart(status)


def _is_telegram_capable_runtime_command_line(command_line: str) -> bool:
    normalized = str(command_line or "").lower()
    if not normalized:
        return False

    marker_groups = (
        ("telegram_bot.telegram_agent",),
        ("telegram_agent.py",),
        ("desktop_runtime.backend", "run-daemon"),
        ("deploy.windows.release_backend", "run-daemon"),
        ("emploaibackend.exe", "run-daemon"),
    )
    return any(all(marker in normalized for marker in markers) for markers in marker_groups)


def _process_ids_for_port(port: int) -> set[int]:
    if port <= 0:
        return set()

    try:
        if os.name == "nt":
            result = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True,
                text=True,
                check=False,
            )
            pids: set[int] = set()
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) < 5 or parts[0].upper() != "TCP":
                    continue
                local_address = parts[1]
                state = parts[3].upper()
                pid_text = parts[4]
                if state != "LISTENING":
                    continue
                if local_address.rsplit(":", 1)[-1] != str(port):
                    continue
                try:
                    pids.add(int(pid_text))
                except ValueError:
                    continue
            return pids

        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            int(line.strip())
            for line in result.stdout.splitlines()
            if line.strip().isdigit()
        }
    except Exception:
        return set()


def _managed_runtime_pids(home: Path, config: "DesktopRuntimeConfig", *, status: Any | None = None) -> list[int]:
    record = _read_pid_record(home)
    status = status or _get_runtime_status()
    pids: set[int] = set()

    recorded_pid = int(record.get("pid") or 0) if record else 0
    if recorded_pid and _process_exists(recorded_pid):
        pids.add(recorded_pid)

    health_pid = _runtime_health_process_id(status)
    if health_pid and _process_exists(health_pid):
        pids.add(health_pid)

    if (
        getattr(status, "ok", False)
        and health_pid
        and recorded_pid
        and recorded_pid == health_pid
    ):
        return sorted(pids)

    for port_pid in _process_ids_for_port(int(config.port or 0)):
        if not _process_exists(port_pid):
            continue
        if port_pid in pids or _is_runtime_process(port_pid):
            pids.add(port_pid)

    return sorted(pids)


def _managed_telegram_worker_pids(home: Path) -> list[int]:
    pids: set[int] = set()
    record = _read_telegram_pid_record(home)
    recorded_pid = int(record.get("pid") or 0) if record else 0
    if recorded_pid and _process_exists(recorded_pid):
        pids.add(recorded_pid)

    for pid in _process_ids_for_command_markers("run-telegram-worker"):
        if pid == os.getpid() or not _process_exists(pid):
            continue
        if not _is_desktop_runtime_worker_process(pid, "run-telegram-worker"):
            continue
        pids.add(pid)

    return sorted(pids)


def _managed_remote_control_worker_pids(home: Path) -> list[int]:
    pids: set[int] = set()
    record = _read_remote_control_pid_record(home)
    recorded_pid = int(record.get("pid") or 0) if record else 0
    if recorded_pid and _process_exists(recorded_pid):
        pids.add(recorded_pid)

    for pid in _process_ids_for_command_markers("run-remote-control-worker"):
        if pid == os.getpid() or not _process_exists(pid):
            continue
        if not _is_desktop_runtime_worker_process(pid, "run-remote-control-worker"):
            continue
        pids.add(pid)

    return sorted(pids)


def _managed_service_pids(home: Path, config: "DesktopRuntimeConfig", *, status: Any | None = None) -> list[int]:
    pids = set(_managed_runtime_pids(home, config, status=status))
    pids.update(_managed_telegram_worker_pids(home))
    pids.update(_managed_remote_control_worker_pids(home))
    return sorted(pids)


def _runtime_compatibility_issue(
    home: Path,
    config: "DesktopRuntimeConfig",
    status: Any,
    *,
    telegram_enabled: bool,
    telegram_configured: bool,
) -> str | None:
    if not getattr(status, "ok", False):
        return None
    if not (telegram_enabled and telegram_configured):
        return None

    record = _read_pid_record(home)
    if record:
        mode = str(record.get("mode") or "").strip()
        if mode == "telegram+app":
            return None
        if mode == "desktop-app-only":
            return (
                "Local runtime is running in desktop-app-only mode. Stop it and start the managed "
                "local runtime so Telegram and desktop share one live session."
            )

    active_pids = _managed_runtime_pids(home, config, status=status)
    for pid in active_pids:
        if _is_telegram_capable_runtime_command_line(_process_command_line(pid)):
            return None

    return (
        "Local runtime is attached to an app-only server. Stop it and start the managed local "
        "runtime so Telegram and desktop share one live session."
    )


def _attached_runtime_requires_restart(status: Any, *, home: Path | None = None, root: Path | None = None) -> bool:
    if not getattr(status, "ok", False):
        return False
    health_pid = _runtime_health_process_id(status)
    if health_pid <= 0:
        return False
    if home is not None:
        record = _read_pid_record(home)
        if record and int(record.get("pid") or 0) == health_pid:
            expected_release = current_release_version(root or bundle_root())
            record_release = str(record.get("releaseVersion") or "").strip()
            if record_release and record_release != expected_release:
                return True
            record_executable = str(record.get("executable") or "").strip()
            current_executable = str(Path(sys.executable).resolve())
            if record_executable and os.path.normcase(record_executable) != os.path.normcase(current_executable):
                return True
            return False
    return not _runtime_process_matches_current_build(health_pid)
