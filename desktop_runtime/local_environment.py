"""Local desktop environment preparation.

This module intentionally contains no account, mobile, or hosted-backend
bootstrap behavior. Dependencies are injected by ``desktop_runtime.backend`` in
the same way as the other split runtime modules.
"""

from __future__ import annotations


def _runtime_secret_overlay_values() -> dict[str, str]:
    raw_payload = os.getenv(RUNTIME_SECRET_OVERLAY_ENV, "").strip()
    if not raw_payload:
        return {}
    try:
        payload = json.loads(raw_payload)
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    values: dict[str, str] = {}
    for key, value in payload.items():
        clean_key = str(key).strip()
        clean_value = str(value).strip()
        if clean_key in RUNTIME_SECRET_OVERLAY_FIELDS and clean_value:
            values[clean_key] = clean_value
    if values.get("GOOGLE_API_KEY") and not values.get("GEMINI_API_KEY"):
        values["GEMINI_API_KEY"] = values["GOOGLE_API_KEY"]
    return values


def _apply_runtime_secret_overlay(existing: dict[str, str]) -> dict[str, str]:
    overlay = _runtime_secret_overlay_values()
    if not overlay:
        return existing
    effective_existing = dict(existing)
    for key, value in overlay.items():
        os.environ[key] = value
        effective_existing[key] = value
    return effective_existing


def _prepare_environment(*, apply_cloud_overlay: bool = False) -> tuple[Path, Path, Path, dict[str, str]]:
    root, home, env_file = _runtime_paths()
    existing = load_existing_env_values(env_file)
    existing = configure_process_environment(home, env_file)
    _configure_pack_source_environment(root)
    return root, home, env_file, _apply_runtime_secret_overlay(existing)


def _refresh_setup_model_catalog(setup_state: dict[str, Any], effective_values: dict[str, str]) -> None:
    labels = configured_provider_labels(effective_values)
    if labels:
        setup_state["configuredProviders"] = labels
        setup_state["modelGroups"] = configured_model_groups(effective_values)
        setup_state["plannerModels"] = configured_planner_models(effective_values)


def _refresh_setup_voice_status(setup_state: dict[str, Any], home: Path) -> None:
    voice_status = resolve_voice_runtime_status(include_pack_status=False)
    runtime_config = load_runtime_config(home)
    voice_config = runtime_config.get("voice") if isinstance(runtime_config.get("voice"), dict) else {}
    setup_state["voiceAvailable"] = bool(voice_status.get("input_ok", voice_status.get("ok")))
    setup_state["voiceStatus"] = voice_status
    setup_state["voicePacks"] = _voice_pack_setup_payload(voice_config, voice_status)


def _effective_release_env_values(
    root: Path,
    home: Path,
    existing: dict[str, str],
    *,
    mark_rebind_required: bool = False,
) -> tuple[dict[str, str], bool]:
    rebind_required = should_require_telegram_rebind(home, root, mark=mark_rebind_required)
    return apply_telegram_rebind_gate(existing, rebind_required=rebind_required), rebind_required
