from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


SECRET_NAME_RE = re.compile(r"^[A-Za-z0-9_:\-\.]{2,128}$")
MAX_PROFILE_DICT_KEYS = 100
MAX_EMAIL_CHARS = 254
MAX_PASSWORD_CHARS = 256
MIN_STRONG_PASSWORD_CHARS = 12
MAX_DISPLAY_NAME_CHARS = 160
MAX_DEVICE_PLATFORM_CHARS = 80
MAX_DEVICE_KEY_CHARS = 256
MAX_SECRET_ITEMS_PER_REQUEST = 100
MAX_SECRET_VALUE_CHARS = 20_000
MAX_SECRET_REVEAL_NAMES = 100
COMMON_WEAK_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password12",
        "password123",
        "password123!",
        "qwerty123",
        "qwerty123!",
        "letmein123",
        "admin12345",
        "welcome123",
        "changeme123",
        "123456789",
        "1234567890",
    }
)
SETUP_SECRET_NAMES = frozenset(
    {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "XAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "NVIDIA_API_KEY",
        "OPENROUTER_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "GMAIL_LOGIN_EMAIL",
        "GMAIL_LOGIN_PASSWORD",
    }
)


def normalize_email(value: str) -> str:
    return value.strip().casefold()


def strong_password_errors(password: str, *, email: str = "", display_name: Optional[str] = None) -> List[str]:
    value = str(password or "")
    errors: List[str] = []
    if len(value) < MIN_STRONG_PASSWORD_CHARS:
        errors.append(f"Password must be at least {MIN_STRONG_PASSWORD_CHARS} characters.")
    if len(value) > MAX_PASSWORD_CHARS:
        errors.append("Password is too long.")

    if not re.search(r"[a-z]", value):
        errors.append("Password must include a lowercase letter.")
    if not re.search(r"[A-Z]", value):
        errors.append("Password must include an uppercase letter.")
    if not re.search(r"\d", value):
        errors.append("Password must include a number.")
    if not re.search(r"[^A-Za-z0-9]", value):
        errors.append("Password must include a symbol.")

    lowered = value.casefold()
    compact_lowered = re.sub(r"\s+", "", lowered)
    if compact_lowered in COMMON_WEAK_PASSWORDS:
        errors.append("Password is too common.")

    normalized_email = normalize_email(email)
    local_part = normalized_email.split("@", 1)[0] if "@" in normalized_email else ""
    if local_part and len(local_part) >= 4 and local_part.casefold() in lowered:
        errors.append("Password cannot include the email name.")

    clean_display = re.sub(r"[^A-Za-z0-9]+", "", str(display_name or "")).casefold()
    clean_password = re.sub(r"[^A-Za-z0-9]+", "", lowered)
    if clean_display and len(clean_display) >= 4 and clean_display in clean_password:
        errors.append("Password cannot include the display name.")

    if re.search(r"(.)\1{4,}", value):
        errors.append("Password cannot repeat the same character too many times.")
    if re.search(r"(0123|1234|2345|3456|4567|5678|6789|abcd|bcde|cdef|qwer|wert|asdf|sdfg|zxcv)", lowered):
        errors.append("Password cannot contain obvious keyboard or counting sequences.")
    return errors


def default_user_profile() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "preferences": {
            "verbose_mode": False,
            "cloud_chat_backup_enabled": True,
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
            "mobile": {},
        },
        "integrations": {
            "telegram": {
                "enabled": False,
                "allowed_user_ids": [],
                "default_bot_config_id": None,
                "bots": [],
            },
        },
        "credential_refs": {},
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


def safe_secret_metadata(value: Any) -> Dict[str, Any]:
    cleaned = safe_profile_value(value)
    return cleaned if isinstance(cleaned, dict) else {}


def redact_secret_value(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"


def validate_secret_namespace(namespace: str) -> str:
    normalized_namespace = str(namespace or "setup").strip().lower() or "setup"
    if len(normalized_namespace) > 64 or not re.match(r"^[a-z0-9_\-\.]+$", normalized_namespace):
        raise ValueError("Secret namespace is invalid")
    return normalized_namespace


def validate_secret_location(namespace: str, name: str) -> tuple[str, str]:
    normalized_namespace = validate_secret_namespace(namespace)
    normalized_name = str(name or "").strip()
    if not SECRET_NAME_RE.match(normalized_name):
        raise ValueError("Secret name is invalid")
    if normalized_namespace == "setup" and normalized_name not in SETUP_SECRET_NAMES:
        raise ValueError(f"Unsupported setup secret: {normalized_name}")
    return normalized_namespace, normalized_name


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
    for key in ("preferences", "setup", "integrations", "credential_refs", "metadata"):
        if isinstance(safe_payload.get(key), dict):
            profile[key] = deep_merge_dict(dict(profile.get(key) or {}), safe_payload[key])

    preferences = dict(profile.get("preferences") or {})
    preferences["verbose_mode"] = bool(preferences.get("verbose_mode", False))
    preferences["cloud_chat_backup_enabled"] = bool(preferences.get("cloud_chat_backup_enabled", True))
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
    for surface in ("desktop", "mobile"):
        surface_payload = setup.get(surface)
        setup[surface] = surface_payload if isinstance(surface_payload, dict) else {}
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
