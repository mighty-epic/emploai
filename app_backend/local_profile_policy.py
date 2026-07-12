from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


MAX_DISPLAY_NAME_CHARS = 160
MAX_DEVICE_PLATFORM_CHARS = 80
MAX_DEVICE_KEY_CHARS = 256
MAX_PROFILE_DICT_KEYS = 100


def default_user_profile() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "preferences": {
            "verbose_mode": False,
            "interrupt_policy_default": "none",
            "custom_system_prompt_append": None,
            "max_turns": None,
            "sleep_mode_enabled": False,
            "memory_controls": {
                "prompt_context_enabled": True,
                "search_enabled": True,
                "write_enabled": True,
            },
            "default_workspace": None,
            "planner_model": None,
            "default_model": None,
        },
        "setup": {
            "completed_versions": {},
            "desktop": {},
        },
        "integrations": {
            "telegram": {
                "enabled": False,
                "allowed_user_ids": [],
                "default_bot_config_id": None,
                "bots": [],
            },
        },
        "metadata": {},
    }


def deep_merge_dict(base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dict(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def safe_string(value: Any, *, max_length: int = 512) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_length]


def safe_profile_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return None
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for index, (raw_key, raw_value) in enumerate(value.items()):
            if index >= MAX_PROFILE_DICT_KEYS:
                break
            key = str(raw_key or "").strip()
            if not key:
                continue
            key = key[:128]
            key_marker = key.casefold().replace("-", "_")
            if (
                key_marker in {"token", "password", "secret", "api_key", "apikey", "private_key"}
                or "password" in key_marker
                or "private_key" in key_marker
                or "secret_value" in key_marker
                or "access_token" in key_marker
                or "refresh_token" in key_marker
                or "session_token" in key_marker
                or "bot_token" in key_marker
                or key_marker.endswith("_api_key")
            ):
                continue
            cleaned = safe_profile_value(raw_value, depth=depth + 1)
            if cleaned is not None:
                sanitized[key] = cleaned
        return sanitized
    if isinstance(value, list):
        sanitized_items = []
        for item in value[:50]:
            cleaned = safe_profile_value(item, depth=depth + 1)
            if cleaned is not None:
                sanitized_items.append(cleaned)
        return sanitized_items
    if isinstance(value, (str, int, float, bool)):
        if isinstance(value, str):
            return value[:2000]
        return value
    return None


def normalize_allowed_user_ids(value: Any) -> List[str]:
    if isinstance(value, str):
        candidates = [part.strip() for part in value.split(",")]
    elif isinstance(value, list):
        candidates = value
    else:
        candidates = []
    normalized: List[str] = []
    for candidate in candidates[:50]:
        text = str(candidate or "").strip()
        if not text:
            continue
        if text.startswith("+"):
            text = text[1:]
        if text.lstrip("-").isdigit() and text not in normalized:
            normalized.append(text[:64])
    return normalized


def sanitize_user_profile(payload: Any) -> Dict[str, Any]:
    defaults = default_user_profile()
    safe_payload = safe_profile_value(payload)
    if not isinstance(safe_payload, dict):
        return defaults

    profile = dict(defaults)
    for key in ("preferences", "setup", "integrations", "metadata"):
        if isinstance(safe_payload.get(key), dict):
            profile[key] = deep_merge_dict(dict(profile.get(key) or {}), safe_payload[key])

    preferences = dict(profile.get("preferences") or {})
    preferences["verbose_mode"] = bool(preferences.get("verbose_mode", False))
    preferences["custom_system_prompt_append"] = safe_string(
        preferences.get("custom_system_prompt_append"),
        max_length=8000,
    )
    raw_max_turns = preferences.get("max_turns")
    try:
        max_turns = int(raw_max_turns) if raw_max_turns is not None and str(raw_max_turns).strip() != "" else None
    except (TypeError, ValueError):
        max_turns = None
    preferences["max_turns"] = max_turns if max_turns is not None and 10 <= max_turns <= 1000 else None
    preferences["sleep_mode_enabled"] = bool(preferences.get("sleep_mode_enabled", False))
    memory_controls = preferences.get("memory_controls")
    memory_controls = memory_controls if isinstance(memory_controls, dict) else {}
    preferences["memory_controls"] = {
        "prompt_context_enabled": bool(memory_controls.get("prompt_context_enabled", True)),
        "search_enabled": bool(memory_controls.get("search_enabled", True)),
        "write_enabled": bool(memory_controls.get("write_enabled", True)),
    }
    interrupt_policy = str(preferences.get("interrupt_policy_default") or "none").strip()
    if interrupt_policy not in {"none", "steer_now", "after_tool"}:
        interrupt_policy = "none"
    preferences["interrupt_policy_default"] = interrupt_policy
    for key in ("default_workspace", "planner_model", "default_model"):
        preferences[key] = safe_string(preferences.get(key), max_length=512)
    profile["preferences"] = preferences

    setup = dict(profile.get("setup") or {})
    completed_versions = setup.get("completed_versions")
    setup["completed_versions"] = completed_versions if isinstance(completed_versions, dict) else {}
    desktop_setup = setup.get("desktop")
    setup["desktop"] = desktop_setup if isinstance(desktop_setup, dict) else {}
    profile["setup"] = setup

    integrations = dict(profile.get("integrations") or {})
    telegram = dict(integrations.get("telegram") or {})
    telegram["enabled"] = bool(telegram.get("enabled", False))
    telegram["default_bot_config_id"] = safe_string(telegram.get("default_bot_config_id"), max_length=128)
    raw_allowed_user_ids = telegram.get("allowed_user_ids")
    if not raw_allowed_user_ids and "allowedUserIds" in telegram:
        raw_allowed_user_ids = telegram.get("allowedUserIds")
    telegram["allowed_user_ids"] = normalize_allowed_user_ids(raw_allowed_user_ids)
    bots = []
    for raw_bot in list(telegram.get("bots") or [])[:20]:
        if not isinstance(raw_bot, dict):
            continue
        bot = {
            "bot_config_id": safe_string(raw_bot.get("bot_config_id", raw_bot.get("id")), max_length=128),
            "label": safe_string(raw_bot.get("label"), max_length=128),
            "is_default": bool(raw_bot.get("is_default", raw_bot.get("default", False))),
            "last_verified_at": safe_string(raw_bot.get("last_verified_at"), max_length=64),
            "credential_ref": safe_string(raw_bot.get("credential_ref"), max_length=256),
        }
        bots.append({key: value for key, value in bot.items() if value is not None})
    telegram["bots"] = bots
    integrations["telegram"] = telegram
    profile["integrations"] = integrations
    profile["schema_version"] = 1
    return json.loads(json.dumps(profile))
