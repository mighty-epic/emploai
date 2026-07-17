from __future__ import annotations

from shared.subprocess_utils import hidden_subprocess_kwargs


def _bootstrap_payload(
    *,
    launch_if_needed: bool = False,
    force_launch: bool = False,
    resolve_current_session: bool = True,
    attach_timeout_override: int | None = None,
    restart_attach_timeout_override: int | None = None,
    defer_services: bool = False,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    root, home, env_file, existing = _prepare_environment(apply_cloud_overlay=False)
    prepare_ms = round((time.perf_counter() - started_at) * 1000, 1)

    phase_started_at = time.perf_counter()
    apply_installer_voice_pack_preferences(home)
    setup_state = build_setup_state(
        home=home,
        env_file=env_file,
        source_root=root,
        existing=existing,
        include_voice_runtime_status=False,
    )
    local_existing = _apply_runtime_secret_overlay(existing)
    effective_existing, _ = _effective_release_env_values(root, home, local_existing, mark_rebind_required=False)
    _refresh_setup_model_catalog(setup_state, effective_existing)
    _refresh_setup_voice_status(setup_state, home)
    setup_state_ms = round((time.perf_counter() - phase_started_at) * 1000, 1)

    config = _load_desktop_runtime_config()
    if bool(setup_state.get("telegramRebindRequired")):
        _stop_telegram_worker(home)

    phase_started_at = time.perf_counter()
    status = _get_runtime_status()
    if _attached_runtime_requires_restart_checked(status, home=home, root=root):
        try:
            status.detail = (
                "Restarting the packaged local runtime so the desktop app uses the current installed build."
            )
            status.state = "offline"
            status.ok = False
        except Exception:
            pass
    status_ms = round((time.perf_counter() - phase_started_at) * 1000, 1)
    runtime_mode = status.mode
    telegram_enabled = bool(configure_channels_enabled("telegram"))
    telegram_configured = bool(setup_state.get("telegramConfigured"))
    telegram_config_fingerprint = _telegram_config_fingerprint_from_values(effective_existing)
    remote_control_configured = _remote_control_configured_from_values(effective_existing)
    remote_control_config_fingerprint = _remote_control_config_fingerprint_from_values(effective_existing)

    should_try_launch = not setup_state["required"] and config.enabled and not status.ok and (force_launch or launch_if_needed)
    launch_ms = 0.0
    if should_try_launch:
        phase_started_at = time.perf_counter()
        try:
            status, runtime_mode = _ensure_runtime(
                config,
                home,
                require_auto_start=not force_launch,
                attach_timeout_override=attach_timeout_override,
                restart_attach_timeout_override=restart_attach_timeout_override,
            )
        except RuntimeError as exc:
            status = _get_runtime_status()
            status.detail = str(exc)
            try:
                status.state = "failed"
            except Exception:
                pass
            try:
                status.degraded = True
            except Exception:
                pass
            runtime_mode = "detached"
        launch_ms = round((time.perf_counter() - phase_started_at) * 1000, 1)

    phase_started_at = time.perf_counter()
    if status.ok and not defer_services:
        telegram_status = _ensure_telegram_worker(
            home,
            enabled=telegram_enabled,
            configured=telegram_configured,
            config_fingerprint=telegram_config_fingerprint,
        )
    else:
        telegram_status = _telegram_service_status(
            home,
            enabled=telegram_enabled,
            configured=telegram_configured,
            scan_processes=not defer_services,
        )
    telegram_ms = round((time.perf_counter() - phase_started_at) * 1000, 1)

    phase_started_at = time.perf_counter()
    if status.ok and not defer_services:
        remote_control_status = _ensure_remote_control_worker(
            home,
            configured=remote_control_configured,
            config_fingerprint=remote_control_config_fingerprint,
        )
    else:
        remote_control_status = _remote_control_service_status(
            home,
            configured=remote_control_configured,
            validate_pid=False,
        )
    remote_control_ms = round((time.perf_counter() - phase_started_at) * 1000, 1)

    setup_state["remoteControlStatus"] = asdict(remote_control_status)

    managed_runtime_pids = _managed_runtime_pids(home, config, status=status)

    access_token = ""
    current_session_id: str | None = None
    device_id: str | None = None
    session_ms = 0.0
    if status.ok:
        phase_started_at = time.perf_counter()
        token_payload = _ensure_desktop_token()
        access_token = str(token_payload["access_token"])
        device_id = str(token_payload["device_id"])
        if resolve_current_session:
            workspace = Path(config.workspace)
            try:
                current_session_id = _current_session_id(workspace)
            except Exception as exc:
                issues = list(status.issues or [])
                issues.append(f"Shared session warm-up failed: {exc}")
                try:
                    status.issues = issues
                    status.degraded = True
                except Exception:
                    pass
        session_ms = round((time.perf_counter() - phase_started_at) * 1000, 1)

    timings = {
        "prepare_environment_ms": prepare_ms,
        "setup_state_ms": setup_state_ms,
        "runtime_status_ms": status_ms,
        "runtime_launch_ms": launch_ms,
        "telegram_ms": telegram_ms,
        "remote_control_ms": remote_control_ms,
        "session_ms": session_ms,
        "total_ms": round((time.perf_counter() - started_at) * 1000, 1),
    }

    return {
        "ok": True,
        "apiBaseUrl": config.api_base_url,
        "accessToken": access_token,
        "currentSessionId": current_session_id,
        "runtimeMode": runtime_mode,
        "runtimeStatus": asdict(status),
        "deviceId": device_id,
        "userId": _default_user_id(),
        "runtimeAvailable": bool(status.ok),
        "canLaunchLocalRuntime": bool(config.enabled and not setup_state["required"]),
        "runtimeProcessDetected": bool(managed_runtime_pids),
        "workspaceRoot": config.workspace,
        "runtimeHome": str(home),
        "envFilePath": str(env_file),
        "desktopLogPath": str(_runtime_log_path(home)),
        "telegramLogPath": str(_telegram_runtime_log_path(home)),
        "releaseVersion": current_release_version(root),
        "setupState": setup_state,
        "telegramStatus": asdict(telegram_status),
        "startupTimings": timings,
    }


def _bootstrap_installer_voice_packs() -> dict[str, Any]:
    root, home, _, _ = _prepare_environment()
    runtime_config = apply_installer_voice_pack_preferences(home)
    voice_config = runtime_config.get("voice") if isinstance(runtime_config.get("voice"), dict) else {}
    packs = voice_config.get("packs") if isinstance(voice_config.get("packs"), dict) else {}
    requested_packs = [
        pack_id
        for pack_id, pack_state in packs.items()
        if isinstance(pack_state, dict) and bool(pack_state.get("requested"))
    ]
    voice_pack_manager = _voice_pack_manager()
    statuses = {pack_id: voice_pack_manager.get_voice_pack_status(pack_id) for pack_id in requested_packs}
    payload: dict[str, Any] = {
        "ok": True,
        "releaseVersion": current_release_version(root),
        "runtimeHome": str(home),
        "voiceConfig": voice_config,
        "requestedPacks": requested_packs,
        "installed": [],
        "errors": {},
        "statuses": statuses,
        "completedAt": datetime.now(timezone.utc).isoformat(),
    }
    _voice_pack_bootstrap_report_path(home).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _set_voice_engine(engine: str) -> dict[str, Any]:
    if engine not in {VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW, "none"}:
        raise RuntimeError(f"Unsupported voice engine: {engine}")

    _, home, _, _ = _prepare_environment()
    if engine in {VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW}:
        update_voice_pack_preferences(
            home=home,
            pack_id=engine,
            requested=True,
            default_engine=engine,
        )
    else:
        update_voice_pack_preferences(home=home, default_engine=engine)
    return _bootstrap_payload(launch_if_needed=False, resolve_current_session=False)


def _process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                text=True,
                check=False,
                **hidden_subprocess_kwargs(),
            )
            return str(pid) in result.stdout
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _terminate_pid(pid: int) -> None:
    if pid <= 0:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
            **hidden_subprocess_kwargs(),
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return


def _request_runtime_agent_stop(config: "DesktopRuntimeConfig") -> dict[str, Any] | None:
    status = _get_runtime_status()
    if not status.ok:
        return None
    try:
        token = str(_ensure_desktop_token().get("access_token") or "").strip()
    except Exception:
        token = ""
    if not token:
        return None

    request = urllib.request.Request(
        url=f"{config.api_base_url.rstrip('/')}/api/app/agent/control/stop",
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=2.5) as response:
            payload = response.read().decode("utf-8", errors="replace")
        return json.loads(payload) if payload.strip() else {"ok": True}
    except Exception:
        return None


def _stop_runtime(
    home: Path,
    config: "DesktopRuntimeConfig" | None = None,
    *,
    preserve_fleet_host: bool = False,
) -> dict[str, Any]:
    config = config or _load_desktop_runtime_config()
    graceful_stop = _request_runtime_agent_stop(config)
    managed_pids = set(_managed_runtime_pids(home, config))
    managed_pids.update(_managed_telegram_worker_pids(home))
    if not preserve_fleet_host:
        managed_pids.update(_managed_remote_control_worker_pids(home))
    managed_pids = sorted(managed_pids)
    remaining = set(managed_pids)

    for pid in managed_pids:
        _terminate_pid(pid)

    deadline = time.monotonic() + 10
    while remaining and time.monotonic() < deadline:
        remaining = {pid for pid in remaining if _process_exists(pid)}
        if not remaining:
            break
        time.sleep(0.25)

    _runtime_pid_path(home).unlink(missing_ok=True)
    _telegram_runtime_pid_path(home).unlink(missing_ok=True)
    if not preserve_fleet_host:
        _remote_control_runtime_pid_path(home).unlink(missing_ok=True)
    _clear_telegram_status_record(home)
    if not preserve_fleet_host:
        _clear_remote_control_status_record(home)
    return {
        "ok": True,
        "stopped": not remaining,
        "pid": managed_pids[0] if len(managed_pids) == 1 else None,
        "pids": managed_pids,
        "remainingPids": sorted(remaining),
        "gracefulAgentStop": graceful_stop,
        "fleetHostPreserved": bool(preserve_fleet_host),
    }


def _runtime_is_managed(home: Path, config: "DesktopRuntimeConfig" | None = None) -> bool:
    config = config or _load_desktop_runtime_config()
    return bool(_managed_service_pids(home, config))


def _daemon_mode_for_desktop_runtime(*, telegram_enabled: bool, telegram_configured: bool) -> str:
    return "telegram+app" if telegram_enabled and telegram_configured else "desktop-app-only"


def _snapshot_voice_preferences(home: Path) -> dict[str, Any]:
    runtime_config = load_runtime_config(home)
    voice_config = runtime_config.get("voice") if isinstance(runtime_config.get("voice"), dict) else {}
    packs = voice_config.get("packs") if isinstance(voice_config.get("packs"), dict) else {}
    tts_packs = voice_config.get("tts_packs") if isinstance(voice_config.get("tts_packs"), dict) else {}
    return {
        "default_engine": str(voice_config.get("default_engine") or VOICE_ENGINE_NONE).strip().lower() or VOICE_ENGINE_NONE,
        "tts_backend": str(voice_config.get("tts_backend") or TTS_BACKEND_OPENAI).strip().lower().replace("-", "_") or TTS_BACKEND_OPENAI,
        "requested": {
            VOICE_ENGINE_ENGLISH: bool((packs.get(VOICE_ENGINE_ENGLISH) or {}).get("requested", False)),
            VOICE_ENGINE_HEBREW: bool((packs.get(VOICE_ENGINE_HEBREW) or {}).get("requested", False)),
            VOICE_ENGINE_KOKORO_TTS: bool((tts_packs.get(VOICE_ENGINE_KOKORO_TTS) or {}).get("requested", False)),
            VOICE_ENGINE_KYUTAI_TTS: bool((tts_packs.get(VOICE_ENGINE_KYUTAI_TTS) or {}).get("requested", False)),
        },
    }


def _restore_voice_preferences(home: Path, snapshot: dict[str, Any]) -> None:
    runtime_config = load_runtime_config(home)
    voice_config = runtime_config.setdefault("voice", {})
    packs = voice_config.setdefault("packs", {})
    english_pack = packs.setdefault(VOICE_ENGINE_ENGLISH, {})
    hebrew_pack = packs.setdefault(VOICE_ENGINE_HEBREW, {})
    tts_packs = voice_config.setdefault("tts_packs", {})
    kokoro_tts_pack = tts_packs.setdefault(VOICE_ENGINE_KOKORO_TTS, {})
    kyutai_tts_pack = tts_packs.setdefault(VOICE_ENGINE_KYUTAI_TTS, {})

    english_requested = bool((snapshot.get("requested") or {}).get(VOICE_ENGINE_ENGLISH, False))
    hebrew_requested = bool((snapshot.get("requested") or {}).get(VOICE_ENGINE_HEBREW, False))
    kokoro_tts_requested = bool((snapshot.get("requested") or {}).get(VOICE_ENGINE_KOKORO_TTS, False))
    kyutai_tts_requested = bool((snapshot.get("requested") or {}).get(VOICE_ENGINE_KYUTAI_TTS, False))
    english_pack["requested"] = english_requested
    hebrew_pack["requested"] = hebrew_requested
    english_pack["placeholder"] = False
    hebrew_pack["placeholder"] = False
    english_pack.setdefault("display_name", "English voice pack")
    hebrew_pack.setdefault("display_name", "Hebrew voice pack")
    kokoro_tts_pack["requested"] = kokoro_tts_requested
    kyutai_tts_pack["requested"] = kyutai_tts_requested
    kokoro_tts_pack["placeholder"] = False
    kyutai_tts_pack["placeholder"] = False
    kokoro_tts_pack.setdefault("display_name", "Kokoro voice pack")
    kyutai_tts_pack.setdefault("display_name", "Kyutai clone voice pack")

    default_engine = str(snapshot.get("default_engine") or VOICE_ENGINE_NONE).strip().lower()
    if default_engine not in {VOICE_ENGINE_NONE, VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW}:
        default_engine = VOICE_ENGINE_NONE
    if default_engine == VOICE_ENGINE_ENGLISH and not english_requested:
        default_engine = VOICE_ENGINE_HEBREW if hebrew_requested else VOICE_ENGINE_NONE
    if default_engine == VOICE_ENGINE_HEBREW and not hebrew_requested:
        default_engine = VOICE_ENGINE_ENGLISH if english_requested else VOICE_ENGINE_NONE

    voice_config["default_engine"] = default_engine
    tts_backend = str(snapshot.get("tts_backend") or TTS_BACKEND_OPENAI).strip().lower().replace("-", "_")
    if tts_backend not in {TTS_BACKEND_OPENAI, TTS_BACKEND_KOKORO, TTS_BACKEND_KYUTAI}:
        tts_backend = TTS_BACKEND_OPENAI
    voice_config["tts_backend"] = tts_backend
    voice_config["selection_source"] = "settings"
    save_runtime_config(home, runtime_config)


def _voice_pack_label(pack_id: str) -> str:
    if pack_id == VOICE_ENGINE_HEBREW:
        return "Hebrew"
    if pack_id == VOICE_ENGINE_KOKORO_TTS:
        return "Kokoro"
    if pack_id == VOICE_ENGINE_KYUTAI_TTS:
        return "Kyutai clone"
    return "English"


def _tts_backend_for_pack(pack_id: str) -> str:
    if pack_id == VOICE_ENGINE_KOKORO_TTS:
        return TTS_BACKEND_KOKORO
    if pack_id == VOICE_ENGINE_KYUTAI_TTS:
        return TTS_BACKEND_KYUTAI
    return TTS_BACKEND_OPENAI


def _set_release_tts_backend(home: Path, backend: str, *, previous_env: Mapping[str, str] | None = None) -> None:
    root = bundle_root()
    env_file = env_path(home)
    existing = dict(previous_env or load_existing_env_values(env_file))
    next_values = dict(existing)
    normalized = str(backend or TTS_BACKEND_OPENAI).strip().lower().replace("-", "_") or TTS_BACKEND_OPENAI
    if normalized not in {TTS_BACKEND_OPENAI, TTS_BACKEND_KOKORO, TTS_BACKEND_KYUTAI}:
        normalized = TTS_BACKEND_OPENAI
    next_values["EMPLO_APP_TTS_BACKEND"] = normalized
    next_values.setdefault("EMPLO_APP_TTS_ENABLED", "1")
    save_env(env_file, next_values)
    os.environ["EMPLO_APP_TTS_BACKEND"] = normalized
    os.environ.setdefault("EMPLO_APP_TTS_ENABLED", "1")
    _configure_pack_source_environment(root)


def _save_setup(launch_if_needed: bool) -> dict[str, Any]:
    root, home, env_file, existing = _prepare_environment(apply_cloud_overlay=False)
    config = _load_desktop_runtime_config()
    payload = json.loads(sys.stdin.read() or "{}")
    values = payload.get("values") if isinstance(payload, dict) else None
    if not isinstance(values, dict):
        values = payload if isinstance(payload, dict) else {}
    restart_policy = "auto"
    if isinstance(payload, dict):
        restart_policy = str(payload.get("restart_policy") or payload.get("restartPolicy") or "auto").strip().lower()
    allow_restart = restart_policy not in {"never", "no_restart", "no-restart", "preserve", "false", "0"}

    status_before_save = _get_runtime_status()
    was_running = allow_restart and (_runtime_is_managed(home, config) or bool(status_before_save.ok))
    save_setup_values(
        home=home,
        env_file=env_file,
        source_root=root,
        existing=existing,
        updates={key: str(value or "") for key, value in values.items()},
    )
    if was_running:
        _stop_runtime(home, config)
        time.sleep(0.2)
    return _bootstrap_payload(
        launch_if_needed=launch_if_needed,
        force_launch=was_running,
    )


def _warm_installed_voice_pack(pack_id: str, *, progress_callback=None) -> None:
    label = _voice_pack_label(pack_id)
    _emit_voice_pack_progress(
        progress_callback,
        pack_id=pack_id,
        state="warming",
        phase="warmup",
        message=f"Warming {label} voice engine...",
        percent=96,
    )
    if pack_id == VOICE_ENGINE_HEBREW:
        from app_backend.voice_runtime import preload_hebrew_models

        timings = preload_hebrew_models()
        _emit_voice_pack_progress(
            progress_callback,
            pack_id=pack_id,
            state="warming",
            phase="warmup",
            message=f"Hebrew voice engine warmed ({timings.get('final_seconds', 0.0)}s).",
            percent=98,
        )
    elif pack_id in TTS_VOICE_PACK_IDS:
        from app_backend.voice_runtime import preload_tts_engine, reset_tts_runtime_cache

        reset_tts_runtime_cache()
        timings = preload_tts_engine()
        _emit_voice_pack_progress(
            progress_callback,
            pack_id=pack_id,
            state="warming",
            phase="warmup",
            message=f"{label} speech engine warmed.",
            percent=98,
        )


def _voice_pack_action(pack_id: str, *, install: bool, progress_callback=None) -> dict[str, Any]:
    if pack_id not in VOICE_PACK_IDS:
        raise RuntimeError(f"Unsupported voice pack: {pack_id}")

    _, home, _, _ = _prepare_environment()
    config = _load_desktop_runtime_config()
    status_before_action = _get_runtime_status()
    voice_preferences_before = _snapshot_voice_preferences(home)
    env_file = env_path(home)
    env_values_before = load_existing_env_values(env_file)
    was_running = _runtime_is_managed(home, config) or bool(status_before_action.ok)
    if was_running:
        _emit_voice_pack_progress(
            progress_callback,
            pack_id=pack_id,
            state="starting",
            phase="runtime",
            message="Stopping local runtime before updating voice packs...",
            percent=2,
        )
        _stop_runtime(home, config)
        time.sleep(0.6)

    try:
        if install:
            install_voice_pack(pack_id, progress_callback=progress_callback)
            if pack_id in TTS_VOICE_PACK_IDS:
                _set_release_tts_backend(home, _tts_backend_for_pack(pack_id))
            _warm_installed_voice_pack(pack_id, progress_callback=progress_callback)
            _emit_voice_pack_progress(
                progress_callback,
                pack_id=pack_id,
                state="warming",
                phase="activate",
                message=f"Activating {_voice_pack_label(pack_id)} voice pack...",
                percent=99,
            )
            update_voice_pack_preferences(
                home=home,
                pack_id=pack_id,
                requested=True,
                default_engine=pack_id if pack_id not in TTS_VOICE_PACK_IDS else None,
            )
        else:
            runtime_config = load_runtime_config(home)
            voice_config = runtime_config.get("voice") if isinstance(runtime_config.get("voice"), dict) else {}
            current_default = str(voice_config.get("default_engine") or "").strip().lower()
            next_default = current_default
            if pack_id not in TTS_VOICE_PACK_IDS and current_default == pack_id:
                next_default = VOICE_ENGINE_HEBREW if pack_id == VOICE_ENGINE_ENGLISH else VOICE_ENGINE_ENGLISH
            update_voice_pack_preferences(home=home, pack_id=pack_id, requested=False, default_engine=next_default)
            remove_voice_pack(pack_id)
            if pack_id in TTS_VOICE_PACK_IDS:
                current_backend = str(load_existing_env_values(env_file).get("EMPLO_APP_TTS_BACKEND") or "").strip().lower().replace("-", "_")
                if current_backend == _tts_backend_for_pack(pack_id):
                    _set_release_tts_backend(home, TTS_BACKEND_OPENAI)
    except Exception:
        _restore_voice_preferences(home, voice_preferences_before)
        save_env(env_file, env_values_before)
        previous_backend = str(env_values_before.get("EMPLO_APP_TTS_BACKEND") or "").strip()
        if previous_backend:
            os.environ["EMPLO_APP_TTS_BACKEND"] = previous_backend
        else:
            os.environ.pop("EMPLO_APP_TTS_BACKEND", None)
        if install:
            try:
                remove_voice_pack(pack_id)
            except Exception:
                pass
        if was_running:
            try:
                _bootstrap_payload(
                    launch_if_needed=True,
                    force_launch=True,
                    resolve_current_session=False,
                )
            except Exception:
                pass
        raise

    payload = _bootstrap_payload(
        launch_if_needed=True,
        force_launch=was_running,
        resolve_current_session=False,
    )
    if install:
        _emit_voice_pack_progress(
            progress_callback,
            pack_id=pack_id,
            state="ready",
            phase="complete",
            message=f"{_voice_pack_label(pack_id)} voice pack is ready.",
            percent=100,
        )
    return payload


def _forward_voice_bridge(args: list[str]) -> int:
    home = runtime_home()
    env_file = env_path(home)
    configure_process_environment(home, env_file)
    whisper_live = importlib.import_module("app_backend.whisper_cpp_live")
    previous_argv = list(sys.argv)
    try:
        sys.argv = [previous_argv[0], *args]
        return int(whisper_live.main())
    finally:
        sys.argv = previous_argv


def _validate_hebrew_runtime_dependencies() -> dict[str, Any]:
    _prepare_environment()
    from app_backend.hebrew_transformers_runtime import validate_transformers_runtime_stack

    versions = validate_transformers_runtime_stack()
    return {
        "ok": True,
        "transformersVersion": versions.get("transformers"),
        "regexVersion": versions.get("regex"),
    }


def _cleanup_runtime_home(*, voice_packs_only: bool = False) -> dict[str, Any]:
    _, home, _, _ = _prepare_environment()
    config = _load_desktop_runtime_config()
    stop_result = _stop_runtime(home, config)

    removed_paths: list[str] = []
    if voice_packs_only:
        managed_voice_root = _voice_pack_manager().managed_voice_packs_root()
        if managed_voice_root.exists():
            shutil.rmtree(managed_voice_root, ignore_errors=True)
            if not managed_voice_root.exists():
                removed_paths.append(str(managed_voice_root))

        for path in (
            _voice_pack_bootstrap_report_path(home),
            _runtime_pid_path(home),
            _telegram_runtime_pid_path(home),
            _telegram_runtime_status_path(home),
            _remote_control_runtime_pid_path(home),
            _remote_control_runtime_status_path(home),
        ):
            if path.exists():
                path.unlink(missing_ok=True)
                if not path.exists():
                    removed_paths.append(str(path))

        try:
            if home.exists() and not any(home.iterdir()):
                home.rmdir()
        except Exception:
            pass
    else:
        for child in list(home.iterdir()) if home.exists() else []:
            try:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
            except Exception:
                continue
            if not child.exists():
                removed_paths.append(str(child))
        try:
            if home.exists() and not any(home.iterdir()):
                home.rmdir()
                removed_paths.append(str(home))
        except Exception:
            pass

    return {
        "ok": True,
        "runtimeHome": str(home),
        "voicePacksOnly": voice_packs_only,
        "removedPaths": removed_paths,
        "stopResult": stop_result,
    }
