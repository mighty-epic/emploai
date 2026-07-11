from __future__ import annotations

from shared.fleet_connection import load_fleet_connection

def _runtime_pid_path(home: Path) -> Path:
    return home / RUNTIME_PID_FILENAME


def _runtime_log_path(home: Path) -> Path:
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / RUNTIME_LOG_FILENAME


def _telegram_runtime_pid_path(home: Path) -> Path:
    return home / TELEGRAM_RUNTIME_PID_FILENAME


def _telegram_runtime_log_path(home: Path) -> Path:
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / TELEGRAM_RUNTIME_LOG_FILENAME


def _telegram_runtime_status_path(home: Path) -> Path:
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / TELEGRAM_RUNTIME_STATUS_FILENAME


def _remote_control_runtime_pid_path(home: Path) -> Path:
    return home / REMOTE_CONTROL_RUNTIME_PID_FILENAME


def _remote_control_runtime_log_path(home: Path) -> Path:
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / REMOTE_CONTROL_RUNTIME_LOG_FILENAME


def _remote_control_runtime_status_path(home: Path) -> Path:
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / REMOTE_CONTROL_RUNTIME_STATUS_FILENAME


def _voice_pack_bootstrap_report_path(home: Path) -> Path:
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / VOICE_PACK_BOOTSTRAP_REPORT_FILENAME


def _default_user_id() -> int:
    return DEFAULT_APP_USER_ID


def _normalize_allowed_user_ids(raw_value: str) -> str:
    values = sorted({item.strip() for item in str(raw_value or "").split(",") if item.strip()})
    return ",".join(values)


def _telegram_config_fingerprint(token: str, allowed_user_ids: str) -> str:
    normalized_token = str(token or "").strip()
    normalized_allowed = _normalize_allowed_user_ids(allowed_user_ids)
    if not (normalized_token and normalized_allowed):
        return ""
    payload = f"{normalized_token}\n{normalized_allowed}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _telegram_config_fingerprint_from_values(values: dict[str, str]) -> str:
    return _telegram_config_fingerprint(
        values.get("TELEGRAM_BOT_TOKEN", ""),
        values.get("ALLOWED_USER_IDS", ""),
    )


def _remote_control_config_fingerprint_from_values(values: dict[str, str]) -> str:
    return _fleet_connection_config_fingerprint(runtime_home())


def _fleet_connection_config_fingerprint(home: Path) -> str:
    payload = load_fleet_connection(home)
    base_url = str(payload.get("apiBaseUrl") or payload.get("api_base_url") or "").strip().rstrip("/")
    session_token = str(payload.get("sessionToken") or payload.get("session_token") or "").strip()
    desktop_id = str((payload.get("desktop") or {}).get("desktop_id") or "").strip()
    if not (base_url and session_token):
        return ""
    token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
    return hashlib.sha256("\n".join([base_url, token_hash, desktop_id]).encode("utf-8")).hexdigest()


def _current_session_id(workspace: Path) -> str | None:
    from app_backend.session_bridge import AppSessionBridge

    bridge = AppSessionBridge(user_id=_default_user_id(), workspace=workspace)
    current = bridge.get_current_session()
    if current:
        return current.id
    return None


def _ensure_desktop_token() -> dict[str, Any]:
    store = AppAuthStore()
    return store.ensure_device_token(
        user_id=_default_user_id(),
        device_name=DEFAULT_DEVICE_NAME,
        device_platform=DEFAULT_DEVICE_PLATFORM,
        token_ttl_seconds=TOKEN_TTL_SECONDS,
        device_key=DEFAULT_DEVICE_KEY,
    )


def _self_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).resolve())]
    return [sys.executable, "-m", "desktop_runtime.backend"]


def _read_pid_record(home: Path) -> dict[str, Any] | None:
    path = _runtime_pid_path(home)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_telegram_pid_record(home: Path) -> dict[str, Any] | None:
    path = _telegram_runtime_pid_path(home)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_remote_control_pid_record(home: Path) -> dict[str, Any] | None:
    path = _remote_control_runtime_pid_path(home)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_pid_record(home: Path, *, mode: str, host: str, port: int) -> None:
    root = bundle_root()
    _runtime_pid_path(home).write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "mode": mode,
                "host": host,
                "port": port,
                "startedAt": datetime.now(timezone.utc).isoformat(),
                "releaseVersion": current_release_version(root),
                "executable": str(Path(sys.executable).resolve()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_telegram_pid_record(home: Path, *, config_fingerprint: str | None = None) -> None:
    payload: dict[str, Any] = {
        "pid": os.getpid(),
        "startedAt": datetime.now(timezone.utc).isoformat(),
    }
    if config_fingerprint:
        payload["configFingerprint"] = config_fingerprint
    _telegram_runtime_pid_path(home).write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def _write_remote_control_pid_record(home: Path, *, config_fingerprint: str | None = None) -> None:
    payload: dict[str, Any] = {
        "pid": os.getpid(),
        "startedAt": datetime.now(timezone.utc).isoformat(),
    }
    if config_fingerprint:
        payload["configFingerprint"] = config_fingerprint
    _remote_control_runtime_pid_path(home).write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def _read_telegram_status_record(home: Path) -> dict[str, Any] | None:
    path = _telegram_runtime_status_path(home)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _read_remote_control_status_record(home: Path) -> dict[str, Any] | None:
    path = _remote_control_runtime_status_path(home)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _write_telegram_status_record(
    home: Path,
    *,
    state: str,
    detail: str | None = None,
    ready_at: str | None = None,
    config_fingerprint: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "state": state,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    if detail:
        payload["detail"] = detail
    if ready_at:
        payload["readyAt"] = ready_at
    if config_fingerprint:
        payload["configFingerprint"] = config_fingerprint
    _telegram_runtime_status_path(home).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_remote_control_status_record(
    home: Path,
    *,
    state: str,
    detail: str | None = None,
    ready_at: str | None = None,
    config_fingerprint: str | None = None,
    desktop_id: str | None = None,
    desktop_name: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "state": state,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    if detail:
        payload["detail"] = detail
    if ready_at:
        payload["readyAt"] = ready_at
    if config_fingerprint:
        payload["configFingerprint"] = config_fingerprint
    if desktop_id:
        payload["desktopId"] = desktop_id
    if desktop_name:
        payload["desktopName"] = desktop_name
    _remote_control_runtime_status_path(home).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _clear_pid_record(home: Path) -> None:
    path = _runtime_pid_path(home)
    record = _read_pid_record(home)
    if not record:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        return
    if int(record.get("pid") or 0) != os.getpid():
        return
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _clear_telegram_pid_record(home: Path) -> None:
    path = _telegram_runtime_pid_path(home)
    record = _read_telegram_pid_record(home)
    if not record:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        return
    if int(record.get("pid") or 0) != os.getpid():
        return
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _clear_remote_control_pid_record(home: Path) -> None:
    path = _remote_control_runtime_pid_path(home)
    record = _read_remote_control_pid_record(home)
    if not record:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        return
    if int(record.get("pid") or 0) != os.getpid():
        return
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _clear_telegram_status_record(home: Path) -> None:
    try:
        _telegram_runtime_status_path(home).unlink(missing_ok=True)
    except Exception:
        pass


def _clear_remote_control_status_record(home: Path) -> None:
    try:
        _remote_control_runtime_status_path(home).unlink(missing_ok=True)
    except Exception:
        pass


def _stop_telegram_worker(home: Path, *, scan_processes: bool = True) -> None:
    pids: set[int] = set()
    record = _read_telegram_pid_record(home)
    recorded_pid = int(record.get("pid") or 0) if record else 0
    if recorded_pid and _process_exists(recorded_pid):
        pids.add(recorded_pid)
    if scan_processes:
        pids.update(_managed_telegram_worker_pids(home))
    for pid in sorted(pids):
        _terminate_pid(pid)
        time.sleep(0.2)
    _telegram_runtime_pid_path(home).unlink(missing_ok=True)
    _clear_telegram_status_record(home)


def _stop_remote_control_worker(home: Path, *, scan_processes: bool = True) -> None:
    pids: set[int] = set()
    record = _read_remote_control_pid_record(home)
    recorded_pid = int(record.get("pid") or 0) if record else 0
    if recorded_pid and _process_exists(recorded_pid):
        pids.add(recorded_pid)
    if scan_processes:
        pids.update(_managed_remote_control_worker_pids(home))
    for pid in sorted(pids):
        _terminate_pid(pid)
        time.sleep(0.2)
    _remote_control_runtime_pid_path(home).unlink(missing_ok=True)
    _clear_remote_control_status_record(home)


def _launch_detached_daemon(config: "DesktopRuntimeConfig", home: Path) -> None:
    command = [
        *_self_command(),
        "run-daemon",
        "--host",
        config.host,
        "--port",
        str(config.port),
    ]
    env = os.environ.copy()
    env.setdefault("EMPLOAI_DESKTOP_RUNTIME", "1")
    env["EMPLOAI_HOME"] = str(home)

    launch_cwd = str(home)
    if not getattr(sys, "frozen", False):
        source_root = bundle_root()
        launch_cwd = str(source_root)
        existing_pythonpath = env.get("PYTHONPATH", "").strip()
        source_root_text = str(source_root)
        if existing_pythonpath:
            env["PYTHONPATH"] = os.pathsep.join([source_root_text, existing_pythonpath])
        else:
            env["PYTHONPATH"] = source_root_text

    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )

    log_path = _runtime_log_path(home)
    log_path.write_text("", encoding="utf-8")
    with log_path.open("a", encoding="utf-8") as handle:
        subprocess.Popen(
            command,
            cwd=launch_cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            close_fds=True,
            creationflags=creationflags,
        )


def _launch_detached_telegram_worker(home: Path) -> None:
    command = [*_self_command(), "run-telegram-worker", "--home", str(home)]
    env = os.environ.copy()
    env["EMPLOAI_HOME"] = str(home)
    env["EMPLOAI_SKIP_EMBEDDED_APP_SERVER"] = "1"
    env["EMPLOAI_SKIP_CRON_SCHEDULER"] = "1"
    env["EMPLOAI_DESKTOP_TELEGRAM_WORKER"] = "1"
    env[TELEGRAM_STATE_USER_ID_ENV] = str(_default_user_id())
    env[TELEGRAM_STATUS_PATH_ENV] = str(_telegram_runtime_status_path(home))
    env[TELEGRAM_NOTIFY_ON_READY_ENV] = "1"

    launch_cwd = str(home)
    if not getattr(sys, "frozen", False):
        source_root = bundle_root()
        launch_cwd = str(source_root)
        existing_pythonpath = env.get("PYTHONPATH", "").strip()
        source_root_text = str(source_root)
        env["PYTHONPATH"] = os.pathsep.join([source_root_text, existing_pythonpath]) if existing_pythonpath else source_root_text

    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )

    log_path = _telegram_runtime_log_path(home)
    log_path.write_text("", encoding="utf-8")
    with log_path.open("a", encoding="utf-8") as handle:
        subprocess.Popen(
            command,
            cwd=launch_cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            close_fds=True,
            creationflags=creationflags,
        )


def _launch_detached_remote_control_worker(home: Path) -> None:
    command = [*_self_command(), "run-remote-control-worker"]
    env = os.environ.copy()
    env["EMPLOAI_HOME"] = str(home)
    env["EMPLOAI_DESKTOP_REMOTE_CONTROL_WORKER"] = "1"
    env[REMOTE_CONTROL_STATUS_PATH_ENV] = str(_remote_control_runtime_status_path(home))

    launch_cwd = str(home)
    if not getattr(sys, "frozen", False):
        source_root = bundle_root()
        launch_cwd = str(source_root)
        existing_pythonpath = env.get("PYTHONPATH", "").strip()
        source_root_text = str(source_root)
        env["PYTHONPATH"] = os.pathsep.join([source_root_text, existing_pythonpath]) if existing_pythonpath else source_root_text

    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )

    log_path = _remote_control_runtime_log_path(home)
    log_path.write_text("", encoding="utf-8")
    with log_path.open("a", encoding="utf-8") as handle:
        subprocess.Popen(
            command,
            cwd=launch_cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            close_fds=True,
            creationflags=creationflags,
        )


def _tail_text(path: Path, *, max_bytes: int = 8192) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes))
            return handle.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _runtime_log_failure_detail(home: Path) -> str | None:
    tail = _tail_text(_runtime_log_path(home), max_bytes=RUNTIME_LOG_TAIL_BYTES)
    if not tail:
        return None

    text = tail.replace("\r\n", "\n")
    if "Traceback (most recent call last):" in text:
        traceback_lines = text[text.rfind("Traceback (most recent call last):") :].splitlines()
        summary_line = ""
        for line in reversed(traceback_lines):
            candidate = line.strip()
            if not candidate or candidate.startswith("File "):
                continue
            summary_line = candidate
            break
        if summary_line:
            return f"Local runtime crashed during startup: {summary_line}"

    if "Exception in callback" in text:
        exception_lines = text[text.rfind("Exception in callback") :].splitlines()
        for line in reversed(exception_lines):
            candidate = line.strip()
            if not candidate or candidate.startswith("File "):
                continue
            if ":" in candidate or candidate.startswith("Exception"):
                return f"Local runtime crashed during startup: {candidate}"
        return "Local runtime crashed during startup. Check the desktop runtime log for details."

    error_lines = [line.strip() for line in text.splitlines() if line.strip().startswith("ERROR:")]
    if error_lines:
        return f"Local runtime reported a startup error: {error_lines[-1]}"

    return None
