from __future__ import annotations

def _read_remote_account_session_payload(home: Path) -> dict[str, Any]:
    return remote_account_session_payload(home, _runtime_secret_overlay_values())


def _remote_account_user_id(home: Path) -> int | None:
    session = _read_remote_account_session_payload(home)
    user = session.get("user") if isinstance(session.get("user"), dict) else {}
    raw_user_id = user.get("user_id") or session.get("user_id")
    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        return None
    return user_id if user_id > 0 else None


def _remote_account_request_json(
    session: dict[str, Any],
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout_seconds: float = 12.0,
) -> dict[str, Any]:
    base_url = str(session.get("apiBaseUrl") or session.get("api_base_url") or "").strip().rstrip("/")
    session_token = str(session.get("sessionToken") or session.get("session_token") or "").strip()
    if not base_url or not session_token:
        raise RuntimeError("Remote account session is not configured")
    data: bytes | None = None
    headers = {
        "Authorization": f"Bearer {session_token}",
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url=f"{base_url}/{path.lstrip('/')}",
        data=data,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read().decode("utf-8")
    if not raw:
        return {}
    payload = json.loads(raw)
    return payload if isinstance(payload, dict) else {}


def _remote_account_reveal_secrets(session: dict[str, Any], namespace: str) -> dict[str, str]:
    payload = _remote_account_request_json(
        session,
        "/api/remote/account/secrets/reveal",
        method="POST",
        body={"namespace": namespace, "names": []},
    )
    secrets_payload = payload.get("secrets") if isinstance(payload.get("secrets"), dict) else {}
    return {
        str(key): str(value)
        for key, value in dict(secrets_payload or {}).items()
        if str(key).strip() and str(value).strip()
    }


def _remote_account_list_secrets(session: dict[str, Any], namespace: str) -> list[dict[str, Any]]:
    payload = _remote_account_request_json(
        session,
        f"/api/remote/account/secrets?namespace={quote(namespace)}",
    )
    items = payload.get("items")
    return list(items) if isinstance(items, list) else []


def _cloud_setup_values_from_profile(profile: dict[str, Any]) -> dict[str, str]:
    preferences = profile.get("preferences") if isinstance(profile.get("preferences"), dict) else {}
    integrations = profile.get("integrations") if isinstance(profile.get("integrations"), dict) else {}
    telegram = integrations.get("telegram") if isinstance(integrations.get("telegram"), dict) else {}
    values: dict[str, str] = {}

    default_workspace = str(preferences.get("default_workspace") or "").strip()
    if default_workspace:
        values["DEFAULT_WORKSPACE"] = default_workspace
    planner_model = str(preferences.get("planner_model") or "").strip()
    if planner_model:
        values["PLANNER_MODEL"] = planner_model
    interrupt_policy = str(preferences.get("interrupt_policy_default") or "").strip().lower()
    if interrupt_policy in {"none", "steer_now", "after_tool"}:
        values["INTERRUPT_POLICY_DEFAULT"] = interrupt_policy

    raw_allowed_ids = telegram.get("allowed_user_ids", telegram.get("allowedUserIds", []))
    if isinstance(raw_allowed_ids, str):
        candidates = [part.strip() for part in raw_allowed_ids.split(",")]
    elif isinstance(raw_allowed_ids, list):
        candidates = [str(item or "").strip() for item in raw_allowed_ids]
    else:
        candidates = []
    allowed_ids: list[str] = []
    for candidate in candidates:
        normalized = candidate[1:] if candidate.startswith("+") else candidate
        if normalized.lstrip("-").isdigit() and normalized not in allowed_ids:
            allowed_ids.append(normalized)
    if allowed_ids:
        values["ALLOWED_USER_IDS"] = ",".join(allowed_ids)
    return values


def _cloud_bot_assignment_map(shared_state: dict[str, Any], valid_bot_ids: set[str]) -> dict[str, str]:
    assignments: dict[str, str] = {}

    def record(session_id: Any, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        clean_session_id = str(session_id or payload.get("id") or payload.get("session_id") or "").strip()
        bot_config_id = str(payload.get("telegram_bot_config_id") or "").strip()
        if clean_session_id and bot_config_id in valid_bot_ids:
            assignments[clean_session_id] = bot_config_id

    details = shared_state.get("session_details") if isinstance(shared_state.get("session_details"), dict) else {}
    for session_id, detail in dict(details or {}).items():
        record(session_id, detail)

    sessions = shared_state.get("sessions") if isinstance(shared_state.get("sessions"), list) else []
    for summary in list(sessions or []):
        record(None, summary)

    return assignments


def _restore_cloud_telegram_bots(
    *,
    home: Path,
    workspace: Path,
    telegram_bot_secrets: dict[str, str],
    telegram_secret_items: list[dict[str, Any]],
    shared_state: dict[str, Any],
) -> dict[str, Any]:
    from mobile_app.backend.session_bridge import AppSessionBridge
    from shared.telegram_bot_config_store import TelegramBotConfigStore

    metadata_by_name: dict[str, dict[str, Any]] = {}
    ordered_names: list[str] = []
    for item in telegram_secret_items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        ordered_names.append(name)
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        metadata_by_name[name] = dict(metadata or {})

    for name in telegram_bot_secrets:
        if name not in ordered_names:
            ordered_names.append(name)

    configs: list[dict[str, Any]] = []
    default_bot_config_id = ""
    for index, name in enumerate(ordered_names):
        token = str(telegram_bot_secrets.get(name) or "").strip()
        if not token:
            continue
        metadata = metadata_by_name.get(name, {})
        bot_config_id = str(metadata.get("bot_config_id") or metadata.get("botConfigId") or name).strip()
        if not bot_config_id:
            continue
        label = str(metadata.get("label") or "").strip() or ("Telegram bot 1" if index == 0 else f"Telegram bot {len(configs) + 1}")
        is_default = bool(metadata.get("is_default") or metadata.get("isDefault"))
        if is_default and not default_bot_config_id:
            default_bot_config_id = bot_config_id
        configs.append(
            {
                "id": bot_config_id,
                "label": label,
                "bot_token": token,
                "is_default": is_default,
            }
        )

    store = TelegramBotConfigStore(user_id=_default_user_id())
    public_configs = store.replace_configs(configs, default_bot_config_id=default_bot_config_id or None)
    valid_bot_ids = {str(item.get("id") or "").strip() for item in public_configs if str(item.get("id") or "").strip()}
    assignments = _cloud_bot_assignment_map(shared_state, valid_bot_ids)
    parenting = (
        AppSessionBridge(user_id=_default_user_id(), workspace=workspace).restore_telegram_bot_parenting(assignments)
        if assignments
        else {"updated": 0, "skipped": 0}
    )
    return {
        "telegram_bot_count": len(public_configs),
        "restored_parenting": parenting,
    }


def _apply_cloud_account_runtime_overlay(root: Path, home: Path, existing: dict[str, str]) -> dict[str, str]:
    effective_existing = strip_local_secret_env_values(existing)
    session = _read_remote_account_session_payload(home)
    if not session:
        return effective_existing
    try:
        account = _remote_account_request_json(session, "/api/remote/account/me")
        profile = account.get("profile") if isinstance(account.get("profile"), dict) else {}
        shared_state = account.get("shared_state") if isinstance(account.get("shared_state"), dict) else {}
        setup_secrets = _remote_account_reveal_secrets(session, "setup")
        telegram_bot_secrets = _remote_account_reveal_secrets(session, "telegram_bots")
        telegram_secret_items = _remote_account_list_secrets(session, "telegram_bots")
    except Exception:
        return effective_existing

    cloud_values = {
        **setup_secrets,
        **_cloud_setup_values_from_profile(profile),
    }
    if not str(cloud_values.get("TELEGRAM_BOT_TOKEN") or "").strip():
        first_bot_token = next((str(value).strip() for value in telegram_bot_secrets.values() if str(value).strip()), "")
        if first_bot_token:
            cloud_values["TELEGRAM_BOT_TOKEN"] = first_bot_token
    if not telegram_bot_secrets and str(cloud_values.get("TELEGRAM_BOT_TOKEN") or "").strip():
        fallback_bot_id = "telegram_bot_1"
        telegram = {}
        if isinstance(profile.get("integrations"), dict):
            telegram = profile.get("integrations", {}).get("telegram") if isinstance(profile.get("integrations", {}).get("telegram"), dict) else {}
        fallback_bot_id = str(telegram.get("default_bot_config_id") or fallback_bot_id).strip() or "telegram_bot_1"
        telegram_bot_secrets = {fallback_bot_id: str(cloud_values["TELEGRAM_BOT_TOKEN"]).strip()}
        telegram_secret_items = [
            {
                "name": fallback_bot_id,
                "metadata": {
                    "label": "Telegram bot 1",
                    "bot_config_id": fallback_bot_id,
                    "is_default": True,
                },
            }
        ]
    if cloud_values.get("GOOGLE_API_KEY"):
        cloud_values["GEMINI_API_KEY"] = cloud_values["GOOGLE_API_KEY"]

    workspace = Path(cloud_values.get("DEFAULT_WORKSPACE") or effective_existing.get("DEFAULT_WORKSPACE") or home)
    try:
        restore_result = _restore_cloud_telegram_bots(
            home=home,
            workspace=workspace,
            telegram_bot_secrets=telegram_bot_secrets,
            telegram_secret_items=telegram_secret_items,
            shared_state=shared_state,
        )
        if restore_result.get("telegram_bot_count"):
            os.environ["EMPLOAI_CLOUD_TELEGRAM_BOT_COUNT"] = str(restore_result.get("telegram_bot_count") or "")
    except Exception:
        pass

    for key, value in cloud_values.items():
        clean = str(value or "").strip()
        if clean:
            os.environ[str(key)] = clean
            effective_existing[str(key)] = clean
    return effective_existing


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


def _prepare_environment(*, apply_cloud_overlay: bool = True) -> tuple[Path, Path, Path, dict[str, str]]:
    root, home, env_file = _runtime_paths()
    existing = load_existing_env_values(env_file)
    existing = configure_process_environment(home, env_file)
    _configure_pack_source_environment(root)
    effective_existing = (
        _apply_cloud_account_runtime_overlay(root, home, existing)
        if apply_cloud_overlay
        else existing
    )
    effective_existing = _apply_runtime_secret_overlay(effective_existing)
    return root, home, env_file, effective_existing


def _allow_cloud_account_setup_bootstrap(setup_state: dict[str, Any], home: Path) -> None:
    if not bool(setup_state.get("required")):
        return
    if not remote_account_session_configured(home):
        return
    issues = [str(issue) for issue in setup_state.get("validationIssues") or []]
    model_key_issue = "At least one model API key is required."
    if any(issue != model_key_issue for issue in issues):
        return
    setup_state["required"] = False
    setup_state["cloudAccountConfigured"] = True
    setup_state["cloudSetupDeferred"] = True
    setup_state["validationIssues"] = []
    if not setup_state.get("configuredProviders"):
        setup_state["configuredProviders"] = ["Cloud account"]


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
    rebind_required = should_require_telegram_rebind(
        home,
        root,
        mark=mark_rebind_required,
    )
    return apply_telegram_rebind_gate(existing, rebind_required=rebind_required), rebind_required
