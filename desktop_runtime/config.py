from __future__ import annotations

import json
import os
import re
import shutil
import sys
import textwrap
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, MutableMapping

from dotenv import dotenv_values

from cli.tui_constants import AVAILABLE_MODELS, MODEL_CONFIGS
from shared.model_availability import (
    enabled_providers_from_env,
    filter_models_by_provider_access,
    group_models_by_provider,
    normalize_openai_provider_mode,
)
from shared.model_defaults import default_model_pair_for_enabled_providers
from shared.openai_codex_auth import codex_auth_status, is_codex_auth_configured
from shared.fleet_connection import fleet_connection_configured
from shared.atomic_io import atomic_write_json
from shared.tesseract_runtime import resolve_tesseract_runtime

try:
    import winreg
except ImportError:  # pragma: no cover
    winreg = None


APP_NAME = "EmploAI"
PACKAGED_RUNTIME_HOME_NAME = "EmploAI Beta"
ENV_FILENAME = ".env"
LOG_DIRNAME = "logs"
EXTENSION_DIRNAME = "browser_extension"
RELEASE_STATE_FILENAME = "release_state.json"
EXTENSION_GUIDE_FILENAME = "HOW_TO_LOAD_BROWSER_EXTENSION.txt"
TELEGRAM_REBIND_REQUIRED_STATE_KEY = "telegram_rebind_required"
RUNTIME_DATA_SCHEMA_STATE_KEY = "runtime_data_schema_version"
RUNTIME_DATA_SCHEMA_VERSION = 2
_ENV_ORDER = [
    "TELEGRAM_BOT_TOKEN",
    "ALLOWED_USER_IDS",
    "OPENAI_PROVIDER_MODE",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "NVIDIA_API_KEY",
    "OPENROUTER_API_KEY",
    "MAX_REQUESTS_PER_MINUTE",
    "MAX_REQUESTS_PER_HOUR",
    "BETA_MODE",
    "DEFAULT_WORKSPACE",
    "PLANNER_MODEL",
    "INTERRUPT_POLICY_DEFAULT",
    "HEADLESS",
]

_PROVIDER_KEY_FIELDS = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "NVIDIA_API_KEY",
    "OPENROUTER_API_KEY",
]
_LOCAL_SECRET_ENV_FIELDS = frozenset(
    {
        *_PROVIDER_KEY_FIELDS,
        "GEMINI_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "EMPLOAI_TELEGRAM_BOT_TOKENS_JSON",
        "GMAIL_LOGIN_EMAIL",
        "GMAIL_LOGIN_PASSWORD",
        "GMAIL_EMAIL",
        "GMAIL_PASSWORD",
        # Removed hosted-account fields are retained only so upgrades scrub
        # stale values from old .env files instead of preserving them.
        "EMPLOAI_REMOTE_CONTROL_BASE_URL",
        "EMPLOAI_REMOTE_CONTROL_EMAIL",
        "EMPLOAI_REMOTE_CONTROL_PASSWORD",
        "EMPLOAI_REMOTE_CONTROL_SESSION_TOKEN",
        "EMPLOAI_REMOTE_CONTROL_USER_ID",
        "EMPLOAI_REMOTE_CONTROL_DESKTOP_ID",
    }
)

VOICE_ENGINE_NONE = "none"
VOICE_ENGINE_ENGLISH = "english_local"
VOICE_ENGINE_HEBREW = "hebrew_local"
VOICE_ENGINE_KOKORO_TTS = "kokoro_tts"
VOICE_ENGINE_KYUTAI_TTS = "kyutai_clone_tts"
TTS_BACKEND_OPENAI = "openai"
TTS_BACKEND_KOKORO = "kokoro_onnx"
TTS_BACKEND_KYUTAI = "pocket"
STT_BACKEND_LOCAL_WHISPER = "local_whisper"
STT_BACKEND_OPENAI = "openai"
STT_BACKEND_OPENAI_REALTIME = "openai_realtime"
STT_BACKEND_GEMINI = "gemini"
VOICE_DEFAULT_ENGINE_FIELD = "VOICE_DEFAULT_ENGINE"
VOICE_ENGLISH_REQUESTED_FIELD = "VOICE_ENGLISH_REQUESTED"
VOICE_HEBREW_REQUESTED_FIELD = "VOICE_HEBREW_REQUESTED"
_VOICE_SETUP_FIELDS = [
    VOICE_DEFAULT_ENGINE_FIELD,
    VOICE_ENGLISH_REQUESTED_FIELD,
    VOICE_HEBREW_REQUESTED_FIELD,
]


def _voice_pack_status_functions():
    from app_backend.voice_pack_manager import (
        get_english_pack_status,
        get_hebrew_pack_status,
        get_kokoro_tts_pack_status,
        get_kyutai_tts_pack_status,
    )

    return (
        get_english_pack_status,
        get_hebrew_pack_status,
        get_kokoro_tts_pack_status,
        get_kyutai_tts_pack_status,
    )


def _deferred_voice_pack_status(pack_id: str, *, requested: bool) -> Dict[str, object]:
    return {
        "id": pack_id,
        "available": False,
        "requested": bool(requested),
        "state": "checking",
        "source": "deferred",
        "issues": [],
    }
VOICE_PACK_REGISTRY_KEY = r"Software\MightyEpic\EmploAI\VoicePacks"
VOICE_PACK_SELECTION_SCHEMA_VERSION = 1

_SETUP_EDITABLE_FIELDS = [
    "TELEGRAM_BOT_TOKEN",
    "ALLOWED_USER_IDS",
    "DEFAULT_WORKSPACE",
    "PLANNER_MODEL",
    "INTERRUPT_POLICY_DEFAULT",
    "OPENAI_PROVIDER_MODE",
    *_PROVIDER_KEY_FIELDS,
    *_VOICE_SETUP_FIELDS,
]

_PROVIDER_LABELS = {
    "OPENAI_API_KEY": "OpenAI",
    "ANTHROPIC_API_KEY": "Anthropic",
    "GOOGLE_API_KEY": "Google Gemini",
    "XAI_API_KEY": "xAI Grok",
    "DEEPSEEK_API_KEY": "DeepSeek",
    "NVIDIA_API_KEY": "NVIDIA NIM",
    "OPENROUTER_API_KEY": "OpenRouter",
}

def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def configure_ssl_certificate_environment() -> str | None:
    """Keep httpx/requests usable inside the frozen Windows backend."""

    certificate_env_keys = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")
    openssl_config_env_keys = ("OPENSSL_CONF", "OPENSSL_MODULES", "SSL_CERT_DIR")

    # Ignore host-level OpenSSL config in the packaged Windows backend.
    # Machine-specific OpenSSL settings can reference config/modules that do
    # not exist inside the frozen app, which breaks ssl.create_default_context().
    if is_frozen() and os.name == "nt":
        for key in openssl_config_env_keys:
            os.environ.pop(key, None)

    for key in certificate_env_keys:
        configured = os.getenv(key, "").strip()
        if not configured:
            continue
        try:
            configured_path = Path(configured).expanduser().resolve()
        except Exception:
            os.environ.pop(key, None)
            continue
        if configured_path.exists():
            for target_key in certificate_env_keys:
                os.environ[target_key] = str(configured_path)
            return str(configured_path)
        os.environ.pop(key, None)

    root = bundle_root()
    candidates = [
        root / "certifi" / "cacert.pem",
        root / "_internal" / "certifi" / "cacert.pem",
    ]
    try:
        import certifi

        candidates.append(Path(certifi.where()))
    except Exception:
        pass

    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except Exception:
            continue
        if not resolved.exists():
            continue
        for key in certificate_env_keys:
            os.environ[key] = str(resolved)
        return str(resolved)
    return None


def runtime_home() -> Path:
    configured = os.getenv("EMPLOAI_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    runtime_home_name = os.getenv("EMPLOAI_RUNTIME_HOME_NAME", "").strip()
    if not runtime_home_name and getattr(sys, "frozen", False):
        runtime_home_name = os.getenv("EMPLOAI_PACKAGED_RUNTIME_HOME_NAME", "").strip()
    if not runtime_home_name:
        runtime_home_name = PACKAGED_RUNTIME_HOME_NAME if getattr(sys, "frozen", False) else APP_NAME

    base = (
        os.getenv("LOCALAPPDATA")
        or os.getenv("APPDATA")
        or str(Path.home())
    )
    return (Path(base) / runtime_home_name).resolve()


def _parse_numeric_version(value: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", str(value or ""))
    return tuple(int(part) for part in parts) if parts else (0,)


def bundled_internal_root(root: Path | None = None) -> Path:
    bundle = root or bundle_root()
    internal_root = bundle / "_internal"
    return internal_root if internal_root.exists() else bundle


def _prune_duplicate_bundled_dist_info(package_name: str, *, root: Path | None = None) -> list[str]:
    internal_root = bundled_internal_root(root)
    if not internal_root.exists():
        return []

    prefix = f"{package_name}-"
    candidates = [
        path
        for path in internal_root.glob(f"{package_name}-*.dist-info")
        if path.is_dir() and path.name.startswith(prefix) and path.name.endswith(".dist-info")
    ]
    if len(candidates) <= 1:
        return []

    def _version_key(path: Path) -> tuple[int, ...]:
        version_text = path.name[len(prefix) : -len(".dist-info")]
        return _parse_numeric_version(version_text)

    keep = max(candidates, key=_version_key)
    removed: list[str] = []
    for candidate in candidates:
        if candidate == keep:
            continue
        shutil.rmtree(candidate, ignore_errors=True)
        if not candidate.exists():
            removed.append(str(candidate))
    return removed


def _prune_all_duplicate_bundled_dist_info(*, root: Path | None = None) -> list[str]:
    internal_root = bundled_internal_root(root)
    if not internal_root.exists():
        return []

    duplicate_names: set[str] = set()
    for path in internal_root.glob("*.dist-info"):
        if not path.is_dir():
            continue
        match = re.match(r"^(?P<name>.+)-(?P<version>\d[^\\/]*)\.dist-info$", path.name)
        if not match:
            continue
        duplicate_names.add(match.group("name"))

    removed: list[str] = []
    for package_name in sorted(duplicate_names):
        removed.extend(_prune_duplicate_bundled_dist_info(package_name, root=internal_root))
    return removed


def extension_path(home: Path) -> Path:
    return home / EXTENSION_DIRNAME


def _sync_extension_tree(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for source_path in source.rglob("*"):
        relative_path = source_path.relative_to(source)
        target_path = target / relative_path
        if source_path.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue
        if target_path.exists():
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(source_path, target_path)
        except PermissionError:
            continue


def env_path(home: Path) -> Path:
    return home / ENV_FILENAME


def default_workspace() -> Path:
    home = Path.home()
    documents = home / "Documents"
    if documents.exists():
        return documents.resolve()
    return home.resolve()


def _default_memory_file_content() -> str:
    return textwrap.dedent(
        """\
        # MEMORY.md - Long-Term Memory

        ## User Preferences

        *(Add user preferences here)*

        ## Key Events

        *(Important events and decisions)*

        ## Lessons Learned

        *(Things to remember for future interactions)*

        ## Context

        *(General context about the user, projects, etc.)*
        """
    )


def _merge_missing_defaults(target: dict, defaults: dict) -> None:
    for key, default_value in defaults.items():
        if key not in target:
            target[key] = deepcopy(default_value)
            continue
        if isinstance(target.get(key), dict) and isinstance(default_value, dict):
            _merge_missing_defaults(target[key], default_value)


def _config_path(home: Path) -> Path:
    return home / "config.json"


def _bundled_context_dir(source_root: Path) -> Path | None:
    for candidate in (
        source_root / "runtime_context",
        source_root / "telegram_bot" / "agent_data",
    ):
        if candidate.is_dir():
            return candidate
    return None


def _coerce_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value or "").strip().lower()
    if not normalized:
        return default
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _setting_bool(value: object, default: bool = False) -> str:
    return "1" if _coerce_bool(value, default) else "0"


def _read_installer_voice_pack_preferences() -> Dict[str, object]:
    # Voice pack selection is now app-driven only. The Windows installer no longer
    # exposes voice-pack feature choices, so legacy registry state must not leak
    # into a fresh packaged runtime home and silently re-enable voice.
    return {
        "schema_version": 0,
        "english_requested": None,
        "hebrew_requested": None,
    }


def _default_voice_config(*, installer_preferences: Mapping[str, object] | None = None) -> Dict[str, object]:
    return {
        "selection_source": "default",
        "default_engine": VOICE_ENGINE_NONE,
        "tts_backend": TTS_BACKEND_OPENAI,
        "packs": {
            VOICE_ENGINE_ENGLISH: {
                "requested": False,
                "display_name": "English voice pack",
                "placeholder": False,
            },
            VOICE_ENGINE_HEBREW: {
                "requested": False,
                "display_name": "Hebrew voice pack",
                "placeholder": False,
            },
        },
        "tts_packs": {
            VOICE_ENGINE_KOKORO_TTS: {
                "requested": False,
                "display_name": "Kokoro voice pack",
                "placeholder": False,
            },
            VOICE_ENGINE_KYUTAI_TTS: {
                "requested": False,
                "display_name": "Kyutai clone voice pack",
                "placeholder": False,
            },
        },
    }


def _normalize_voice_config(
    config: MutableMapping[str, object],
    *,
    installer_preferences: Mapping[str, object] | None = None,
) -> None:
    existing_voice = config.get("voice")
    if not isinstance(existing_voice, dict):
        config["voice"] = deepcopy(_default_voice_config(installer_preferences=installer_preferences))
        return

    _merge_missing_defaults(existing_voice, _default_voice_config())
    packs = existing_voice.setdefault("packs", {})
    english_pack = packs.setdefault(VOICE_ENGINE_ENGLISH, {})
    hebrew_pack = packs.setdefault(VOICE_ENGINE_HEBREW, {})
    english_requested = _coerce_bool(english_pack.get("requested"), False)
    hebrew_requested = _coerce_bool(hebrew_pack.get("requested"), False)
    english_pack["requested"] = english_requested
    hebrew_pack["requested"] = hebrew_requested
    english_pack.setdefault("display_name", "English voice pack")
    english_pack["placeholder"] = False
    hebrew_pack.setdefault("display_name", "Hebrew voice pack")
    hebrew_pack["placeholder"] = False

    tts_packs = existing_voice.setdefault("tts_packs", {})
    kokoro_tts_pack = tts_packs.setdefault(VOICE_ENGINE_KOKORO_TTS, {})
    kyutai_tts_pack = tts_packs.setdefault(VOICE_ENGINE_KYUTAI_TTS, {})
    kokoro_requested = _coerce_bool(kokoro_tts_pack.get("requested"), False)
    kyutai_requested = _coerce_bool(kyutai_tts_pack.get("requested"), False)
    kokoro_tts_pack["requested"] = kokoro_requested
    kyutai_tts_pack["requested"] = kyutai_requested
    kokoro_tts_pack.setdefault("display_name", "Kokoro voice pack")
    kokoro_tts_pack["placeholder"] = False
    kyutai_tts_pack.setdefault("display_name", "Kyutai clone voice pack")
    kyutai_tts_pack["placeholder"] = False

    default_engine = str(existing_voice.get("default_engine") or "").strip().lower()
    if default_engine not in {VOICE_ENGINE_NONE, VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW}:
        default_engine = VOICE_ENGINE_ENGLISH if english_requested else VOICE_ENGINE_HEBREW if hebrew_requested else VOICE_ENGINE_NONE
    if default_engine == VOICE_ENGINE_ENGLISH and not english_requested:
        default_engine = VOICE_ENGINE_HEBREW if hebrew_requested else VOICE_ENGINE_NONE
    if default_engine == VOICE_ENGINE_HEBREW and not hebrew_requested:
        default_engine = VOICE_ENGINE_ENGLISH if english_requested else VOICE_ENGINE_NONE
    existing_voice["default_engine"] = default_engine

    tts_backend = str(existing_voice.get("tts_backend") or TTS_BACKEND_OPENAI).strip().lower().replace("-", "_")
    if tts_backend not in {TTS_BACKEND_OPENAI, TTS_BACKEND_KOKORO, TTS_BACKEND_KYUTAI}:
        tts_backend = TTS_BACKEND_OPENAI
    if tts_backend == TTS_BACKEND_KOKORO and not kokoro_requested:
        tts_backend = TTS_BACKEND_KYUTAI if kyutai_requested else TTS_BACKEND_OPENAI
    if tts_backend == TTS_BACKEND_KYUTAI and not kyutai_requested:
        tts_backend = TTS_BACKEND_KOKORO if kokoro_requested else TTS_BACKEND_OPENAI
    existing_voice["tts_backend"] = tts_backend

    selection_source = str(existing_voice.get("selection_source") or "").strip().lower()
    if selection_source not in {"default", "installer", "settings"}:
        selection_source = "settings"
    existing_voice["selection_source"] = selection_source


def load_runtime_config(home: Path) -> Dict[str, object]:
    config_file = _config_path(home)
    if not config_file.exists():
        return default_release_config()
    try:
        payload = json.loads(config_file.read_text(encoding="utf-8"))
    except Exception:
        return default_release_config()
    if not isinstance(payload, dict):
        return default_release_config()
    return payload


def save_runtime_config(home: Path, payload: Mapping[str, object]) -> None:
    config_file = _config_path(home)
    atomic_write_json(config_file, dict(payload))


def apply_installer_voice_pack_preferences(home: Path) -> Dict[str, object]:
    runtime_config = load_runtime_config(home)
    original_config = deepcopy(runtime_config)
    _normalize_voice_config(runtime_config, installer_preferences=_read_installer_voice_pack_preferences())
    if runtime_config != original_config:
        save_runtime_config(home, runtime_config)
    return runtime_config


def _voice_pack_setup_payload(voice_config: Mapping[str, object], voice_status: Mapping[str, object]) -> Dict[str, object]:
    packs = voice_config.get("packs") if isinstance(voice_config.get("packs"), dict) else {}
    tts_packs = voice_config.get("tts_packs") if isinstance(voice_config.get("tts_packs"), dict) else {}
    english_requested = _coerce_bool((packs.get(VOICE_ENGINE_ENGLISH) or {}).get("requested"), False)
    hebrew_requested = _coerce_bool((packs.get(VOICE_ENGINE_HEBREW) or {}).get("requested"), False)
    kokoro_tts_requested = _coerce_bool((tts_packs.get(VOICE_ENGINE_KOKORO_TTS) or {}).get("requested"), False)
    kyutai_tts_requested = _coerce_bool((tts_packs.get(VOICE_ENGINE_KYUTAI_TTS) or {}).get("requested"), False)
    default_engine = str(voice_config.get("default_engine") or VOICE_ENGINE_NONE).strip().lower()
    if default_engine not in {VOICE_ENGINE_NONE, VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW}:
        default_engine = VOICE_ENGINE_ENGLISH if english_requested else VOICE_ENGINE_HEBREW if hebrew_requested else VOICE_ENGINE_NONE
    tts_backend = str(voice_config.get("tts_backend") or TTS_BACKEND_OPENAI).strip().lower().replace("-", "_")
    if tts_backend not in {TTS_BACKEND_OPENAI, TTS_BACKEND_KOKORO, TTS_BACKEND_KYUTAI}:
        tts_backend = TTS_BACKEND_OPENAI

    english_pack_status = voice_status.get("english_pack_status") if isinstance(voice_status.get("english_pack_status"), dict) else {}
    hebrew_pack_status = voice_status.get("hebrew_pack_status") if isinstance(voice_status.get("hebrew_pack_status"), dict) else {}
    kokoro_tts_pack_status = voice_status.get("kokoro_tts_pack_status") if isinstance(voice_status.get("kokoro_tts_pack_status"), dict) else {}
    kyutai_tts_pack_status = voice_status.get("kyutai_tts_pack_status") if isinstance(voice_status.get("kyutai_tts_pack_status"), dict) else {}
    english_pack_ready = _coerce_bool(english_pack_status.get("available"), _coerce_bool(voice_status.get("english_pack_ready"), False))
    hebrew_pack_ready = _coerce_bool(hebrew_pack_status.get("available"), _coerce_bool(voice_status.get("hebrew_pack_ready"), False))

    def build_pack_summary(
        *,
        pack_id: str,
        kind: str,
        title: str,
        description: str,
        requested: bool,
        enabled: bool,
        pack_status: Mapping[str, object],
        supports_always_on: bool,
        backend: str | None = None,
    ) -> dict[str, object]:
        installed = _coerce_bool(pack_status.get("installed"), False)
        available = _coerce_bool(pack_status.get("available"), installed)
        removable = _coerce_bool(pack_status.get("removable"), False)
        source = str(pack_status.get("source") or "")
        status = (
            "active"
            if enabled and available
            else "installed"
            if installed
            else "requested"
            if requested
            else "missing"
        )
        return {
            "id": pack_id,
            "kind": kind,
            "backend": backend,
            "title": title,
            "description": description,
            "requested": requested,
            "installed": installed,
            "available": available,
            "enabled": enabled,
            "placeholder": False,
            "supportsAlwaysOn": supports_always_on,
            "status": status,
            "removable": removable,
            "source": source,
            "path": str(pack_status.get("path") or pack_status.get("model_dir") or pack_status.get("binary_path") or ""),
            "issues": list(pack_status.get("issues") or []),
        }

    return {
        "defaultEngine": default_engine,
        "selectionSource": str(voice_config.get("selection_source") or "settings"),
        "packs": [
            build_pack_summary(
                pack_id=VOICE_ENGINE_ENGLISH,
                kind="stt",
                title="English voice pack",
                description="Optional local English speech-to-text with push-to-talk and always-on support.",
                requested=english_requested,
                enabled=default_engine == VOICE_ENGINE_ENGLISH,
                pack_status=english_pack_status,
                supports_always_on=True,
            ),
            build_pack_summary(
                pack_id=VOICE_ENGINE_HEBREW,
                kind="stt",
                title="Hebrew voice pack",
                description="Optional local Hebrew speech-to-text using the same push-to-talk and always-on capture flow as English.",
                requested=hebrew_requested,
                enabled=default_engine == VOICE_ENGINE_HEBREW,
                pack_status=hebrew_pack_status,
                supports_always_on=True,
            ),
            build_pack_summary(
                pack_id=VOICE_ENGINE_KOKORO_TTS,
                kind="tts",
                title="Kokoro speech pack",
                description="Local Jarvis speech output with Kokoro ONNX and the EmploAI voice bundle.",
                requested=kokoro_tts_requested,
                enabled=tts_backend == TTS_BACKEND_KOKORO,
                pack_status=kokoro_tts_pack_status,
                supports_always_on=False,
                backend=TTS_BACKEND_KOKORO,
            ),
            build_pack_summary(
                pack_id=VOICE_ENGINE_KYUTAI_TTS,
                kind="tts",
                title="Kyutai clone speech pack",
                description="Local Jarvis speech output using Pocket TTS and the bundled cloned voice state.",
                requested=kyutai_tts_requested,
                enabled=tts_backend == TTS_BACKEND_KYUTAI,
                pack_status=kyutai_tts_pack_status,
                supports_always_on=False,
                backend=TTS_BACKEND_KYUTAI,
            ),
        ],
    }


def default_release_config(*, installer_preferences: Mapping[str, object] | None = None) -> Dict[str, object]:
    return {
        "telegram": {
            "reply_mode": "full",
            "show_thinking": False,
            "inline_buttons": True,
            "rate_limit_per_min": 30,
            "rate_limit_per_hour": 200,
        },
        "heartbeat": {
            "enabled": False,
            "interval_seconds": 1800,
            "quiet_hours_start": 23,
            "quiet_hours_end": 8,
        },
        "memory": {
            "auto_save_daily_logs": True,
            "max_daily_log_days": 30,
            "enable_semantic_search": False,
        },
        "agent": {
            "default_model": "auto",
            "default_planner_model": "auto",
            "default_mode": "auto",
            "max_turns": 100,
            "context_compression_threshold": 0.5,
            "final_quality_guard": "planner",
            "final_quality_max_auto_continues": 2,
        },
        "skills": {
            "auto_trigger": True,
            "show_notifications": True,
        },
        "security": {
            "allowed_user_ids": [],
            "max_file_size_mb": 10,
            "allowed_file_types": ["txt", "md", "py", "js", "json", "yaml", "yml"],
        },
        "browser": {
            "use_extension": False,
        },
        "voice": _default_voice_config(installer_preferences=installer_preferences),
        "channels": {
            "telegram": {
                "enabled": False,
            },
            "app": {
                "enabled": True,
                "host": "127.0.0.1",
                "port": 8787,
                "auth_mode": "token",
                "steering_beta": False,
                "push_notifications": False,
            },
            "desktop": {
                "enabled": True,
                "host": "127.0.0.1",
                "port": 8787,
                "auto_start": False,
                "keep_runtime_on_app_close": False,
                "attach_timeout_seconds": 90,
            },
        },
    }


def _clear_runtime_home_contents(home: Path) -> list[str]:
    removed: list[str] = []
    if not home.exists():
        return removed
    for child in list(home.iterdir()):
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        except Exception:
            continue
        if not child.exists():
            removed.append(str(child))
    return removed


def _clear_runtime_schema_sensitive_files(home: Path) -> list[str]:
    removed: list[str] = []
    targets = [
        home / "desktop-sidebar-state.json",
    ]
    for target in targets:
        try:
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            else:
                target.unlink(missing_ok=True)
        except Exception:
            continue
        if not target.exists():
            removed.append(str(target))
    return removed


def _runtime_data_schema_version(state: Mapping[str, object] | None) -> int:
    if not state:
        return 0
    try:
        return int(state.get(RUNTIME_DATA_SCHEMA_STATE_KEY) or 0)
    except Exception:
        return 0


def _ensure_runtime_data_schema(home: Path) -> bool:
    state = load_release_state(home)
    if _runtime_data_schema_version(state) == RUNTIME_DATA_SCHEMA_VERSION:
        return False

    _clear_runtime_schema_sensitive_files(home)
    save_release_state(
        home,
        {
            RUNTIME_DATA_SCHEMA_STATE_KEY: RUNTIME_DATA_SCHEMA_VERSION,
        },
    )
    return True


def ensure_runtime_files(home: Path, source_root: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    _ensure_runtime_data_schema(home)
    (home / LOG_DIRNAME).mkdir(parents=True, exist_ok=True)
    (home / "memory").mkdir(parents=True, exist_ok=True)
    memory_file = home / "MEMORY.md"
    if not memory_file.exists():
        memory_file.write_text(_default_memory_file_content(), encoding="utf-8")

    context_dir = home / "agent_data"
    context_dir.mkdir(parents=True, exist_ok=True)
    bundled_context_dir = _bundled_context_dir(source_root)
    if bundled_context_dir is not None:
        for source_path in bundled_context_dir.iterdir():
            if not source_path.is_file():
                continue
            target_path = context_dir / source_path.name
            if target_path.exists():
                continue
            shutil.copyfile(source_path, target_path)
    from shared.context_loader import ContextLoader

    ContextLoader(home).initialize_workspace()

    config_file = _config_path(home)
    installer_voice_preferences = _read_installer_voice_pack_preferences()
    default_config = default_release_config(installer_preferences=installer_voice_preferences)
    if not config_file.exists():
        atomic_write_json(config_file, default_config)
    else:
        try:
            existing_config = json.loads(config_file.read_text(encoding="utf-8"))
            if not isinstance(existing_config, dict):
                existing_config = {}
        except Exception:
            existing_config = {}

        original_config = deepcopy(existing_config)

        _merge_missing_defaults(existing_config, default_config)
        _normalize_voice_config(existing_config, installer_preferences=installer_voice_preferences)

        channels_before = original_config.get("channels") if isinstance(original_config.get("channels"), dict) else {}
        legacy_runtime_config = "desktop" not in channels_before
        if legacy_runtime_config:
            channels = existing_config.setdefault("channels", {})
            app_channel = channels.setdefault("app", {})
            app_channel["enabled"] = True

        if existing_config != original_config:
            atomic_write_json(config_file, existing_config)

    example_src = source_root / ".env.example"
    example_dst = home / ".env.example"
    if example_src.exists() and not example_dst.exists():
        shutil.copyfile(example_src, example_dst)

    extension_src = source_root / EXTENSION_DIRNAME
    extension_dst = extension_path(home)
    if extension_src.exists():
        if not extension_dst.exists():
            shutil.copytree(extension_src, extension_dst)
        else:
            _sync_extension_tree(extension_src, extension_dst)

    guide_path = home / EXTENSION_GUIDE_FILENAME
    if not guide_path.exists():
        try:
            guide_path.write_text(
                "\n".join(
                    [
                        "EmploAI Chrome Extension Setup",
                        "",
                        "1. Open chrome://extensions",
                        "2. Enable Developer mode",
                        "3. Click Load unpacked",
                        f"4. Select this folder: {extension_dst}",
                        "",
                        "After loading it in Chrome, start EmploAI and use /bridge on.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
        except PermissionError:
            pass


def load_existing_env_values(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    values = dotenv_values(path)
    return {
        key: str(value).strip()
        for key, value in values.items()
        if value is not None
    }


def strip_local_secret_env_values(values: Mapping[str, str]) -> Dict[str, str]:
    return {
        str(key): str(value)
        for key, value in dict(values or {}).items()
        if str(key) not in _LOCAL_SECRET_ENV_FIELDS
    }


def _release_info_path(source_root: Path) -> Path:
    return source_root / "deploy" / "windows" / "release_info.json"


def current_release_version(source_root: Path) -> str:
    info_path = _release_info_path(source_root)
    if not info_path.exists():
        return "0.0.0-beta.0"
    try:
        payload = json.loads(info_path.read_text(encoding="utf-8"))
    except Exception:
        return "0.0.0-beta.0"
    return str(payload.get("version") or "0.0.0-beta.0")


def current_source_revision(source_root: Path) -> str:
    """Read the checked-out Git revision without launching a helper process."""

    marker = Path(source_root).resolve() / ".git"
    if marker.is_dir():
        git_dir = marker
    elif marker.is_file():
        try:
            pointer = marker.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
        if not pointer.lower().startswith("gitdir:"):
            return ""
        git_dir = Path(pointer.split(":", 1)[1].strip())
        if not git_dir.is_absolute():
            git_dir = (marker.parent / git_dir).resolve()
    else:
        return ""

    common_dir = git_dir
    common_marker = git_dir / "commondir"
    if common_marker.is_file():
        try:
            common_dir = (git_dir / common_marker.read_text(encoding="utf-8").strip()).resolve()
        except OSError:
            common_dir = git_dir
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if re.fullmatch(r"[0-9a-f]{40}", head, re.IGNORECASE):
        return head.lower()
    if not head.startswith("ref:"):
        return ""
    ref_name = head.split(":", 1)[1].strip()
    for base in (git_dir, common_dir):
        try:
            revision = (base / ref_name).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if re.fullmatch(r"[0-9a-f]{40}", revision, re.IGNORECASE):
            return revision.lower()
    for base in dict.fromkeys((git_dir, common_dir)):
        try:
            packed_refs = (base / "packed-refs").read_text(encoding="utf-8")
        except OSError:
            continue
        for line in packed_refs.splitlines():
            if not line or line.startswith(("#", "^")):
                continue
            revision, _, packed_ref = line.partition(" ")
            if packed_ref.strip() == ref_name and re.fullmatch(
                r"[0-9a-f]{40}",
                revision,
                re.IGNORECASE,
            ):
                return revision.lower()
    return ""


def _release_state_path(home: Path) -> Path:
    return home / RELEASE_STATE_FILENAME


def load_release_state(home: Path) -> Dict[str, object]:
    path = _release_state_path(home)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_release_state(home: Path, state: Mapping[str, object]) -> None:
    path = _release_state_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(state), indent=2),
        encoding="utf-8",
    )


def merge_env(existing: Mapping[str, str], updates: Mapping[str, str]) -> Dict[str, str]:
    merged = dict(existing)
    for key, value in updates.items():
        if value is None:
            continue
        merged[key] = str(value).strip()
    return merged


def render_env(values: Mapping[str, str]) -> str:
    ordered: list[str] = []
    seen: set[str] = set()

    for key in _ENV_ORDER:
        if key in values:
            ordered.append(f"{key}={values[key]}")
            seen.add(key)

    for key in sorted(values):
        if key in seen:
            continue
        ordered.append(f"{key}={values[key]}")

    return "\n".join(ordered) + "\n"


def save_env(path: Path, values: Mapping[str, str]) -> None:
    path.write_text(render_env(strip_local_secret_env_values(values)), encoding="utf-8")


def needs_first_run_setup(values: Mapping[str, str]) -> bool:
    return bool(validate_setup_values(values))


def _release_version_requires_setup(state: Mapping[str, object], *, source_root: Path) -> bool:
    release_version = current_release_version(source_root)
    last_onboarded_version = str(state.get("last_onboarded_version") or "")
    return last_onboarded_version != release_version


def should_require_telegram_rebind(
    home: Path,
    source_root: Path,
    *,
    state: Mapping[str, object] | None = None,
    mark: bool = False,
) -> bool:
    loaded_state = dict(state or load_release_state(home))
    rebind_required = bool(loaded_state.get(TELEGRAM_REBIND_REQUIRED_STATE_KEY))
    if not rebind_required and _release_version_requires_setup(loaded_state, source_root=source_root):
        rebind_required = True
        if mark:
            loaded_state[TELEGRAM_REBIND_REQUIRED_STATE_KEY] = True
            save_release_state(home, loaded_state)
    return rebind_required


def apply_telegram_rebind_gate(values: Mapping[str, str], *, rebind_required: bool) -> Dict[str, str]:
    gated = dict(values)
    if rebind_required:
        gated["TELEGRAM_BOT_TOKEN"] = ""
        gated["ALLOWED_USER_IDS"] = ""
    return gated


def needs_versioned_setup(values: Mapping[str, str], *, home: Path, source_root: Path) -> bool:
    if needs_first_run_setup(values):
        return True

    state = load_release_state(home)
    if bool(state.get(TELEGRAM_REBIND_REQUIRED_STATE_KEY)):
        return True
    return _release_version_requires_setup(state, source_root=source_root)


def _prompt_nonempty(prompt: str, input_fn: Callable[[str], str]) -> str:
    while True:
        value = input_fn(prompt).strip()
        if value:
            return value
        print("A value is required.")


def _prompt_with_default(prompt: str, default: str, input_fn: Callable[[str], str]) -> str:
    value = input_fn(f"{prompt} [{default}]: ").strip()
    return value or default


def _prompt_secret(
    label: str,
    *,
    existing: str,
    input_fn: Callable[[str], str],
) -> str:
    if existing:
        prompt = f"{label} [configured; Enter=keep, -=clear]: "
    else:
        prompt = f"{label} [optional; Enter=skip]: "
    value = input_fn(prompt).strip()
    if not value:
        return existing
    if value == "-":
        return ""
    return value


def _print_setup_intro(home: Path, env_file: Path, *, source_root: Path) -> None:
    release_version = current_release_version(source_root)
    print("=" * 72)
    print(f"{APP_NAME} Beta Setup")
    print("=" * 72)
    print(
        textwrap.dedent(
            f"""
            This beta build stores its runtime files here:
              {home}

            Release version:
              {release_version}

            EmploAI now ships as a desktop-first Windows app.
            Telegram is optional and can be added later from the same setup flow.

            The runtime can still run in this console window when launched directly.
            You can re-run setup later by launching the exe with `--setup`.
            EmploAI reopens setup once after each installed update so you can review keys and configuration.

            Desktop setup requires:
              1. A workspace root for file operations
              2. At least one model API key

            Optional Telegram setup:
              1. Open Telegram and talk to @BotFather
              2. Run /newbot and copy the bot token
              3. Open @userinfobot and send any message
              4. Copy your numeric Telegram user ID

            Browser extension path for this beta build:
              {extension_path(home)}

            Bundled OCR engine:
              Tesseract OCR is included with this Windows build.

            If you want the real Chrome extension bridge later:
              1. Open chrome://extensions
              2. Enable Developer mode
              3. Click Load unpacked
              4. Select the browser_extension folder above

            A guide file is also written here:
              {home / EXTENSION_GUIDE_FILENAME}

            Your editable environment file will be stored at:
              {env_file}
            """
        ).strip()
    )
    print()


def run_first_run_setup(
    *,
    home: Path,
    env_file: Path,
    source_root: Path,
    existing: Mapping[str, str],
    input_fn: Callable[[str], str] = input,
) -> Dict[str, str]:
    _print_setup_intro(home, env_file, source_root=source_root)
    telegram_rebind_required = should_require_telegram_rebind(home, source_root, mark=True)

    while True:
        updates: Dict[str, str] = {}

        token_default = "" if telegram_rebind_required else existing.get("TELEGRAM_BOT_TOKEN", "")
        updates["TELEGRAM_BOT_TOKEN"] = _prompt_secret(
            "Telegram bot token",
            existing=token_default,
            input_fn=input_fn,
        )

        ids_default = "" if telegram_rebind_required else existing.get("ALLOWED_USER_IDS", "")
        ids_prompt = "Allowed Telegram user ID(s)"
        if ids_default:
            allowed_ids = _prompt_with_default(ids_prompt, ids_default, input_fn)
        else:
            allowed_ids = input_fn(f"{ids_prompt} [optional; Enter=skip]: ").strip()
        updates["ALLOWED_USER_IDS"] = allowed_ids

        workspace_default = existing.get("DEFAULT_WORKSPACE") or str(default_workspace())
        workspace = _prompt_with_default("Workspace root for file operations", workspace_default, input_fn)
        updates["DEFAULT_WORKSPACE"] = workspace

        updates["OPENAI_API_KEY"] = _prompt_secret(
            "OpenAI API key",
            existing=existing.get("OPENAI_API_KEY", ""),
            input_fn=input_fn,
        )
        updates["ANTHROPIC_API_KEY"] = _prompt_secret(
            "Anthropic API key",
            existing=existing.get("ANTHROPIC_API_KEY", ""),
            input_fn=input_fn,
        )
        updates["GOOGLE_API_KEY"] = _prompt_secret(
            "Google API key (Gemini)",
            existing=existing.get("GOOGLE_API_KEY", existing.get("GEMINI_API_KEY", "")),
            input_fn=input_fn,
        )
        updates["XAI_API_KEY"] = _prompt_secret(
            "xAI API key (Grok)",
            existing=existing.get("XAI_API_KEY", ""),
            input_fn=input_fn,
        )
        updates["DEEPSEEK_API_KEY"] = _prompt_secret(
            "DeepSeek API key",
            existing=existing.get("DEEPSEEK_API_KEY", ""),
            input_fn=input_fn,
        )
        updates["NVIDIA_API_KEY"] = _prompt_secret(
            "NVIDIA API key",
            existing=existing.get("NVIDIA_API_KEY", ""),
            input_fn=input_fn,
        )
        updates["OPENROUTER_API_KEY"] = _prompt_secret(
            "OpenRouter API key",
            existing=existing.get("OPENROUTER_API_KEY", ""),
            input_fn=input_fn,
        )
        updates["PLANNER_MODEL"] = input_fn(
            "Planner model override [optional; Enter=automatic cheapest supported planner]: "
        ).strip()
        updates["INTERRUPT_POLICY_DEFAULT"] = input_fn(
            "Active-run send behavior [queue/steer_now/after_tool; Enter=queue]: "
        ).strip()

        updates.setdefault("MAX_REQUESTS_PER_MINUTE", existing.get("MAX_REQUESTS_PER_MINUTE", "30"))
        updates.setdefault("MAX_REQUESTS_PER_HOUR", existing.get("MAX_REQUESTS_PER_HOUR", "200"))
        updates.setdefault("BETA_MODE", existing.get("BETA_MODE", "true"))
        updates.setdefault("HEADLESS", existing.get("HEADLESS", "false"))

        try:
            merged = save_setup_values(
                home=home,
                env_file=env_file,
                source_root=source_root,
                existing=existing,
                updates=updates,
            )
        except ValueError as exc:
            print()
            print(str(exc))
            print("Please review the setup values and try again.")
            print()
            existing = merge_env(existing, updates)
            continue

        print()
        print(f"Saved setup to {env_file}")
        print()
        return merged


def configure_process_environment(home: Path, env_file: Path) -> Dict[str, str]:
    _prune_all_duplicate_bundled_dist_info()
    os.chdir(home)

    values = load_existing_env_values(env_file)
    persisted_values = strip_local_secret_env_values(values)
    if values != persisted_values:
        save_env(env_file, persisted_values)

    for key in _LOCAL_SECRET_ENV_FIELDS:
        os.environ.pop(key, None)

    for key, value in persisted_values.items():
        os.environ[key] = value

    os.environ.setdefault("DEFAULT_WORKSPACE", persisted_values.get("DEFAULT_WORKSPACE", str(default_workspace())))
    os.environ.setdefault("BETA_MODE", persisted_values.get("BETA_MODE", "true"))
    os.environ.setdefault("HEADLESS", persisted_values.get("HEADLESS", "false"))
    os.environ.setdefault("EMPLOAI_HOME", str(home))
    configure_ssl_certificate_environment()
    return persisted_values


def print_runtime_banner(home: Path) -> None:
    print("=" * 72)
    print(f"{APP_NAME} Beta Runtime")
    print("=" * 72)
    print(f"Runtime home: {home}")
    print("Bundled OCR engine: Tesseract OCR")
    print(f"Chrome extension folder: {extension_path(home)}")
    print(f"Extension setup guide: {home / EXTENSION_GUIDE_FILENAME}")
    print("If you want the real Chrome bridge, load that folder via chrome://extensions.")
    print("Logs stream in this console window. Press Ctrl+C to stop the bot.")
    print()


def open_extension_directory(home: Path) -> Path:
    target = extension_path(home)
    if os.name == "nt":
        os.startfile(str(target))
    else:
        raise RuntimeError("Extension directory opening is only implemented for Windows builds.")
    return target


def _normalized_existing_values(existing: Mapping[str, str]) -> Dict[str, str]:
    values = {key: str(value).strip() for key, value in dict(existing).items()}
    if not values.get("DEFAULT_WORKSPACE"):
        values["DEFAULT_WORKSPACE"] = str(default_workspace())
    if values.get("INTERRUPT_POLICY_DEFAULT", "").strip().lower() not in {"none", "steer_now", "after_tool"}:
        values["INTERRUPT_POLICY_DEFAULT"] = "none"
    values["OPENAI_PROVIDER_MODE"] = normalize_openai_provider_mode(values.get("OPENAI_PROVIDER_MODE"))
    if not values.get("GOOGLE_API_KEY") and values.get("GEMINI_API_KEY"):
        values["GOOGLE_API_KEY"] = values["GEMINI_API_KEY"]
    if not values.get("EMPLOAI_REMOTE_DESKTOP_NAME"):
        values["EMPLOAI_REMOTE_DESKTOP_NAME"] = "EmploAI Desktop"
    if not values.get("EMPLOAI_REMOTE_DESKTOP_KEY"):
        values["EMPLOAI_REMOTE_DESKTOP_KEY"] = "desktop-default"
    return values


def configured_provider_labels(values: Mapping[str, str]) -> list[str]:
    normalized = _normalized_existing_values(values)
    labels: list[str] = []
    for key in _PROVIDER_KEY_FIELDS:
        if normalized.get(key):
            labels.append(_PROVIDER_LABELS.get(key, key))
    if is_codex_auth_configured():
        labels.append("OpenAI Codex (ChatGPT)")
    return labels


def configured_model_groups(values: Mapping[str, str]) -> list[dict[str, object]]:
    normalized = _normalized_existing_values(values)
    enabled_providers = enabled_providers_from_env(normalized, include_local_codex_auth=True)
    available_models = filter_models_by_provider_access(
        AVAILABLE_MODELS,
        MODEL_CONFIGS,
        enabled_providers,
    )
    return group_models_by_provider(available_models, MODEL_CONFIGS)


def configured_planner_models(values: Mapping[str, str]) -> list[str]:
    normalized = _normalized_existing_values(values)
    enabled_providers = enabled_providers_from_env(normalized, include_local_codex_auth=True)
    default_planner = default_model_pair_for_enabled_providers(enabled_providers).planner_model
    available_models = filter_models_by_provider_access(
        AVAILABLE_MODELS,
        MODEL_CONFIGS,
        enabled_providers,
    )
    supported: list[str] = []
    for model in available_models:
        config = MODEL_CONFIGS.get(model, {})
        provider = str(config.get("provider", "unknown"))
        if provider == "google":
            supported.append(model)
            continue
        if provider in {"openai", "openai-codex", "anthropic", "xai", "deepseek", "openrouter", "nvidia"}:
            supported.append(model)
    if default_planner in supported:
        supported = [default_planner, *[model for model in supported if model != default_planner]]
    return supported


def validate_setup_values(values: Mapping[str, str]) -> list[str]:
    normalized = _normalized_existing_values(values)
    issues: list[str] = []

    workspace = normalized.get("DEFAULT_WORKSPACE", "").strip()
    if not workspace:
        issues.append("Workspace root is required.")

    if not any(normalized.get(key, "").strip() for key in _PROVIDER_KEY_FIELDS) and not is_codex_auth_configured():
        issues.append("At least one model provider is required. Add an API key or sign in with ChatGPT for Codex.")

    token = normalized.get("TELEGRAM_BOT_TOKEN", "").strip()
    allowed_ids = normalized.get("ALLOWED_USER_IDS", "").strip()
    if token and not allowed_ids:
        issues.append("Allowed Telegram user ID(s) are required when a Telegram bot token is configured.")
    if allowed_ids and not token:
        issues.append("Telegram bot token is required when allowed Telegram user ID(s) are configured.")

    return issues


def resolve_voice_runtime_status(*, include_pack_status: bool = True) -> Dict[str, object]:
    runtime_config = load_runtime_config(runtime_home())
    _normalize_voice_config(runtime_config, installer_preferences=_read_installer_voice_pack_preferences())
    voice_config = runtime_config.get("voice") if isinstance(runtime_config.get("voice"), dict) else {}
    packs = voice_config.get("packs") if isinstance(voice_config.get("packs"), dict) else {}
    english_requested = _coerce_bool((packs.get(VOICE_ENGINE_ENGLISH) or {}).get("requested"), False)
    hebrew_requested = _coerce_bool((packs.get(VOICE_ENGINE_HEBREW) or {}).get("requested"), False)

    default_engine = str(voice_config.get("default_engine") or VOICE_ENGINE_NONE).strip().lower()
    if default_engine not in {VOICE_ENGINE_NONE, VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW}:
        default_engine = VOICE_ENGINE_ENGLISH if english_requested else VOICE_ENGINE_HEBREW if hebrew_requested else VOICE_ENGINE_NONE
    if default_engine == VOICE_ENGINE_ENGLISH and not english_requested:
        default_engine = VOICE_ENGINE_HEBREW if hebrew_requested else VOICE_ENGINE_NONE
    if default_engine == VOICE_ENGINE_HEBREW and not hebrew_requested:
        default_engine = VOICE_ENGINE_ENGLISH if english_requested else VOICE_ENGINE_NONE

    stt_backend = (
        os.getenv("EMPLO_APP_STT_BACKEND", STT_BACKEND_LOCAL_WHISPER).strip().lower().replace("-", "_")
        or STT_BACKEND_LOCAL_WHISPER
    )
    if stt_backend in {"google", "google_gemini", "gemini_api"}:
        stt_backend = STT_BACKEND_GEMINI
    api_stt_backend = stt_backend in {STT_BACKEND_OPENAI, STT_BACKEND_OPENAI_REALTIME, STT_BACKEND_GEMINI}
    stt_model = os.getenv("EMPLO_APP_STT_MODEL", "base.en-q5_1").strip() or "base.en-q5_1"
    draft_model = os.getenv("EMPLO_APP_STT_DRAFT_MODEL", "tiny.en").strip() or "tiny.en"
    realtime_stt_model = (
        os.getenv("EMPLO_APP_STT_REALTIME_TRANSCRIPTION_MODEL", "").strip()
        or os.getenv("EMPLO_APP_STT_REALTIME_MODEL", "gpt-realtime-whisper").strip()
        or "gpt-realtime-whisper"
    )
    gemini_stt_model = (
        os.getenv("EMPLO_APP_STT_GEMINI_MODEL", "").strip()
        or "gemini-3.5-flash"
    )
    binary_flavor = os.getenv("EMPLO_APP_STT_BINARY_FLAVOR", "blas").strip() or "blas"
    tts_enabled = os.getenv("EMPLO_APP_TTS_ENABLED", "1").strip().lower() not in {"0", "false", "off", "no"}
    tts_backend = os.getenv("EMPLO_APP_TTS_BACKEND", str(voice_config.get("tts_backend") or TTS_BACKEND_OPENAI)).strip().lower().replace("-", "_") or TTS_BACKEND_OPENAI

    tts_packs = voice_config.get("tts_packs") if isinstance(voice_config.get("tts_packs"), dict) else {}
    kokoro_tts_requested = _coerce_bool((tts_packs.get(VOICE_ENGINE_KOKORO_TTS) or {}).get("requested"), False)
    kyutai_tts_requested = _coerce_bool((tts_packs.get(VOICE_ENGINE_KYUTAI_TTS) or {}).get("requested"), False)
    if include_pack_status:
        (
            get_english_pack_status,
            get_hebrew_pack_status,
            get_kokoro_tts_pack_status,
            get_kyutai_tts_pack_status,
        ) = _voice_pack_status_functions()
        english_pack_status = get_english_pack_status()
        hebrew_pack_status = get_hebrew_pack_status()
        kokoro_tts_pack_status = get_kokoro_tts_pack_status()
        kyutai_tts_pack_status = get_kyutai_tts_pack_status()
    else:
        english_pack_status = _deferred_voice_pack_status(VOICE_ENGINE_ENGLISH, requested=english_requested)
        hebrew_pack_status = _deferred_voice_pack_status(VOICE_ENGINE_HEBREW, requested=hebrew_requested)
        kokoro_tts_pack_status = _deferred_voice_pack_status(VOICE_ENGINE_KOKORO_TTS, requested=kokoro_tts_requested)
        kyutai_tts_pack_status = _deferred_voice_pack_status(VOICE_ENGINE_KYUTAI_TTS, requested=kyutai_tts_requested)
    english_pack_issues = list(english_pack_status.get("issues") or [])
    hebrew_pack_issues = list(hebrew_pack_status.get("issues") or [])
    english_pack_ready = bool(english_pack_status.get("available"))
    hebrew_pack_ready = bool(hebrew_pack_status.get("available"))

    input_issues: list[str] = []
    if default_engine == VOICE_ENGINE_NONE and not api_stt_backend:
        if not english_pack_ready and not hebrew_pack_ready:
            input_issues.append("No local voice packs are installed. Open setup or choose an API voice input engine.")
        else:
            input_issues.append("Voice input is disabled in setup and settings.")
    elif stt_backend == STT_BACKEND_GEMINI:
        if not (os.getenv("GOOGLE_API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip()):
            input_issues.append("GOOGLE_API_KEY or GEMINI_API_KEY is not configured, so Gemini voice transcription is unavailable.")
    elif api_stt_backend:
        if not os.getenv("OPENAI_API_KEY", "").strip():
            input_issues.append("OPENAI_API_KEY is not configured, so app voice transcription is unavailable.")
    elif default_engine == VOICE_ENGINE_HEBREW:
        input_issues.extend(hebrew_pack_issues)
    else:
        input_issues.extend(english_pack_issues)

    if default_engine == VOICE_ENGINE_NONE and not api_stt_backend:
        selected_engine_state = "disabled"
    elif input_issues:
        selected_engine_state = "error"
    elif api_stt_backend:
        selected_engine_state = "ready"
    elif default_engine == VOICE_ENGINE_HEBREW:
        try:
            from app_backend.voice_runtime import hebrew_model_bundle_loaded

            selected_engine_state = "ready" if hebrew_model_bundle_loaded() else "warming"
        except Exception:
            selected_engine_state = "warming"
    else:
        selected_engine_state = "ready"

    return {
        "ok": not input_issues,
        "input_ok": not input_issues,
        "issues": input_issues,
        "stt_backend": stt_backend,
        "stt_model": (
            f"{realtime_stt_model} realtime transcription"
            if stt_backend == STT_BACKEND_OPENAI_REALTIME
            else os.getenv("EMPLO_APP_STT_MODEL", "gpt-4o-mini-transcribe")
            if stt_backend == STT_BACKEND_OPENAI
            else gemini_stt_model
            if stt_backend == STT_BACKEND_GEMINI
            else str(hebrew_pack_status.get("model_dir") or "")
            if default_engine == VOICE_ENGINE_HEBREW
            else stt_model
        ),
        "draft_model": (
            None
            if api_stt_backend
            else str(hebrew_pack_status.get("model_dir") or "")
            if default_engine == VOICE_ENGINE_HEBREW
            else draft_model
        ),
        "binary_flavor": None if default_engine == VOICE_ENGINE_HEBREW or api_stt_backend else binary_flavor,
        "tts_enabled": tts_enabled,
        "tts_backend": tts_backend,
        "tts_ready": (
            (tts_backend == TTS_BACKEND_OPENAI and bool(os.getenv("OPENAI_API_KEY", "").strip()))
            or (tts_backend == TTS_BACKEND_KOKORO and bool(kokoro_tts_pack_status.get("available")))
            or (tts_backend == TTS_BACKEND_KYUTAI and bool(kyutai_tts_pack_status.get("available")))
        ),
        "pack_status_deferred": not include_pack_status,
        "selected_engine": default_engine,
        "english_requested": english_requested,
        "hebrew_requested": hebrew_requested,
        "english_pack_ready": english_pack_ready,
        "hebrew_pack_ready": hebrew_pack_ready,
        "english_pack_status": english_pack_status,
        "hebrew_pack_status": hebrew_pack_status,
        "kokoro_tts_pack_status": kokoro_tts_pack_status,
        "kyutai_tts_pack_status": kyutai_tts_pack_status,
        "english_pack_manifest": english_pack_status.get("manifest"),
        "english_pack_manifest_verified": bool(english_pack_status.get("manifest_verified")),
        "selected_engine_state": selected_engine_state,
        "selected_engine_ready": selected_engine_state == "ready",
        "hebrew_model_root": str(hebrew_pack_status.get("model_dir") or ""),
        "hebrew_draft_model_root": str(hebrew_pack_status.get("model_dir") or ""),
    }


def build_setup_state(
    *,
    home: Path,
    env_file: Path,
    source_root: Path,
    existing: Mapping[str, str],
    include_voice_runtime_status: bool = True,
) -> Dict[str, object]:
    os.environ["EMPLOAI_HOME"] = str(home)
    state = load_release_state(home)
    release_version = current_release_version(source_root)
    versioned = _release_version_requires_setup(state, source_root=source_root)
    telegram_rebind_required = should_require_telegram_rebind(
        home,
        source_root,
        state=state,
        mark=versioned,
    )
    gated_existing = apply_telegram_rebind_gate(existing, rebind_required=telegram_rebind_required)
    normalized = _normalized_existing_values(gated_existing)
    validation_issues = validate_setup_values(normalized)
    blocking_validation_issues = list(validation_issues)
    if telegram_rebind_required:
        validation_issues = [
            "Review Telegram bot access for this installed version, or leave Telegram blank to keep it off.",
            *validation_issues,
        ]
    runtime = resolve_tesseract_runtime()
    voice_status = resolve_voice_runtime_status(include_pack_status=include_voice_runtime_status)
    runtime_config = load_runtime_config(home)
    _normalize_voice_config(runtime_config, installer_preferences=_read_installer_voice_pack_preferences())
    voice_config = runtime_config.get("voice") if isinstance(runtime_config.get("voice"), dict) else {}
    values = {field: normalized.get(field, "").strip() for field in _SETUP_EDITABLE_FIELDS}
    for field in _LOCAL_SECRET_ENV_FIELDS:
        if field in values:
            values[field] = ""
    english_requested = _coerce_bool(
        (((voice_config.get("packs") or {}).get(VOICE_ENGINE_ENGLISH) or {}).get("requested")),
        False,
    )
    hebrew_requested = _coerce_bool(
        (((voice_config.get("packs") or {}).get(VOICE_ENGINE_HEBREW) or {}).get("requested")),
        False,
    )
    values[VOICE_DEFAULT_ENGINE_FIELD] = str(voice_config.get("default_engine") or VOICE_ENGINE_NONE)
    values[VOICE_ENGLISH_REQUESTED_FIELD] = _setting_bool(english_requested, False)
    values[VOICE_HEBREW_REQUESTED_FIELD] = _setting_bool(hebrew_requested, False)
    fleet_transport_configured = fleet_connection_configured(home)

    return {
        "required": bool(blocking_validation_issues),
        "versioned": versioned,
        "releaseVersion": release_version,
        "runtimeHome": str(home),
        "envFilePath": str(env_file),
        "extensionPath": str(extension_path(home)),
        "extensionGuidePath": str(home / EXTENSION_GUIDE_FILENAME),
        "values": values,
        "validationIssues": validation_issues,
        "configuredProviders": configured_provider_labels(normalized),
        "codexAuth": codex_auth_status(),
        "modelGroups": configured_model_groups(normalized),
        "plannerModels": configured_planner_models(normalized),
        "telegramConfigured": False if telegram_rebind_required else bool(normalized.get("TELEGRAM_BOT_TOKEN") and normalized.get("ALLOWED_USER_IDS")),
        "telegramPartiallyConfigured": False if telegram_rebind_required else bool(
            bool(normalized.get("TELEGRAM_BOT_TOKEN")) ^ bool(normalized.get("ALLOWED_USER_IDS"))
        ),
        "remoteControlConfigured": bool(fleet_transport_configured),
        "remoteControlPartiallyConfigured": False,
        "telegramRebindRequired": telegram_rebind_required,
        "ocrAvailable": runtime.executable is not None,
        "ocrSource": runtime.source,
        "voiceAvailable": bool(voice_status.get("input_ok", voice_status.get("ok"))),
        "voiceStatus": voice_status,
        "voicePacks": _voice_pack_setup_payload(voice_config, voice_status),
    }


def save_setup_values(
    *,
    home: Path,
    env_file: Path,
    source_root: Path,
    existing: Mapping[str, str],
    updates: Mapping[str, str],
) -> Dict[str, str]:
    os.environ["EMPLOAI_HOME"] = str(home)
    env_updates = {key: value for key, value in updates.items() if key not in _VOICE_SETUP_FIELDS}
    merged = merge_env(_normalized_existing_values(existing), env_updates)
    merged["DEFAULT_WORKSPACE"] = (merged.get("DEFAULT_WORKSPACE") or str(default_workspace())).strip()
    if "GOOGLE_API_KEY" in updates or merged.get("GOOGLE_API_KEY"):
        merged["GEMINI_API_KEY"] = merged.get("GOOGLE_API_KEY", "")
    merged.setdefault("MAX_REQUESTS_PER_MINUTE", existing.get("MAX_REQUESTS_PER_MINUTE", "30"))
    merged.setdefault("MAX_REQUESTS_PER_HOUR", existing.get("MAX_REQUESTS_PER_HOUR", "200"))
    merged.setdefault("BETA_MODE", existing.get("BETA_MODE", "true"))
    merged.setdefault("HEADLESS", existing.get("HEADLESS", "false"))
    interrupt_policy_default = str(merged.get("INTERRUPT_POLICY_DEFAULT") or "none").strip().lower()
    if interrupt_policy_default not in {"none", "steer_now", "after_tool"}:
        interrupt_policy_default = "none"
    merged["INTERRUPT_POLICY_DEFAULT"] = interrupt_policy_default
    merged["OPENAI_PROVIDER_MODE"] = normalize_openai_provider_mode(merged.get("OPENAI_PROVIDER_MODE"))

    issues = validate_setup_values(merged)
    if issues:
        raise ValueError("\n".join(issues))

    runtime_config = load_runtime_config(home)
    _normalize_voice_config(runtime_config, installer_preferences=_read_installer_voice_pack_preferences())
    voice_config = runtime_config.setdefault("voice", {})
    packs = voice_config.setdefault("packs", {})
    english_pack = packs.setdefault(VOICE_ENGINE_ENGLISH, {})
    hebrew_pack = packs.setdefault(VOICE_ENGINE_HEBREW, {})

    english_requested = _coerce_bool(
        updates.get(VOICE_ENGLISH_REQUESTED_FIELD),
        _coerce_bool(english_pack.get("requested"), False),
    )
    hebrew_requested = _coerce_bool(
        updates.get(VOICE_HEBREW_REQUESTED_FIELD),
        _coerce_bool(hebrew_pack.get("requested"), False),
    )
    english_pack["requested"] = english_requested
    hebrew_pack["requested"] = hebrew_requested
    english_pack["placeholder"] = False
    hebrew_pack["placeholder"] = False
    english_pack.setdefault("display_name", "English voice pack")
    hebrew_pack.setdefault("display_name", "Hebrew voice pack")

    default_engine = str(
        updates.get(VOICE_DEFAULT_ENGINE_FIELD)
        or voice_config.get("default_engine")
        or VOICE_ENGINE_NONE
    ).strip().lower()
    if default_engine not in {VOICE_ENGINE_NONE, VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW}:
        default_engine = VOICE_ENGINE_ENGLISH if english_requested else VOICE_ENGINE_HEBREW if hebrew_requested else VOICE_ENGINE_NONE
    if default_engine == VOICE_ENGINE_ENGLISH and not english_requested:
        default_engine = VOICE_ENGINE_HEBREW if hebrew_requested else VOICE_ENGINE_NONE
    if default_engine == VOICE_ENGINE_HEBREW and not hebrew_requested:
        default_engine = VOICE_ENGINE_ENGLISH if english_requested else VOICE_ENGINE_NONE
    voice_config["default_engine"] = default_engine
    voice_config["selection_source"] = "settings"
    save_runtime_config(home, runtime_config)

    save_env(env_file, merged)
    provider_by_key = {
        "OPENAI_API_KEY": "openai",
        "ANTHROPIC_API_KEY": "anthropic",
        "GOOGLE_API_KEY": "google",
        "XAI_API_KEY": "xai",
        "DEEPSEEK_API_KEY": "deepseek",
        "NVIDIA_API_KEY": "nvidia",
        "OPENROUTER_API_KEY": "openrouter",
    }
    changed_providers = {
        provider
        for key, provider in provider_by_key.items()
        if key in updates and str(updates.get(key) or "").strip() != str(existing.get(key) or "").strip()
    }
    if changed_providers:
        from shared.provider_availability import clear_provider_availability

        for provider in changed_providers:
            clear_provider_availability(provider)
    state = load_release_state(home)
    state["last_onboarded_version"] = current_release_version(source_root)
    state[TELEGRAM_REBIND_REQUIRED_STATE_KEY] = False
    save_release_state(home, state)
    return merged


def update_voice_pack_preferences(
    *,
    home: Path,
    pack_id: str | None = None,
    requested: bool | None = None,
    default_engine: str | None = None,
) -> Dict[str, object]:
    runtime_config = load_runtime_config(home)
    _normalize_voice_config(runtime_config, installer_preferences=_read_installer_voice_pack_preferences())
    voice_config = runtime_config.setdefault("voice", {})
    packs = voice_config.setdefault("packs", {})
    english_pack = packs.setdefault(VOICE_ENGINE_ENGLISH, {})
    hebrew_pack = packs.setdefault(VOICE_ENGINE_HEBREW, {})
    tts_packs = voice_config.setdefault("tts_packs", {})
    kokoro_tts_pack = tts_packs.setdefault(VOICE_ENGINE_KOKORO_TTS, {})
    kyutai_tts_pack = tts_packs.setdefault(VOICE_ENGINE_KYUTAI_TTS, {})

    if pack_id is not None and requested is not None:
        if pack_id == VOICE_ENGINE_ENGLISH:
            english_pack["requested"] = bool(requested)
        elif pack_id == VOICE_ENGINE_HEBREW:
            hebrew_pack["requested"] = bool(requested)
        elif pack_id == VOICE_ENGINE_KOKORO_TTS:
            kokoro_tts_pack["requested"] = bool(requested)
        elif pack_id == VOICE_ENGINE_KYUTAI_TTS:
            kyutai_tts_pack["requested"] = bool(requested)
        else:
            raise ValueError(f"Unsupported voice pack: {pack_id}")

    english_requested = _coerce_bool(english_pack.get("requested"), False)
    hebrew_requested = _coerce_bool(hebrew_pack.get("requested"), False)
    kokoro_tts_requested = _coerce_bool(kokoro_tts_pack.get("requested"), False)
    kyutai_tts_requested = _coerce_bool(kyutai_tts_pack.get("requested"), False)
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

    next_default_engine = str(default_engine or voice_config.get("default_engine") or VOICE_ENGINE_NONE).strip().lower()
    if next_default_engine not in {VOICE_ENGINE_NONE, VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW}:
        next_default_engine = VOICE_ENGINE_ENGLISH if english_requested else VOICE_ENGINE_HEBREW if hebrew_requested else VOICE_ENGINE_NONE
    if next_default_engine == VOICE_ENGINE_ENGLISH and not english_requested:
        next_default_engine = VOICE_ENGINE_HEBREW if hebrew_requested else VOICE_ENGINE_NONE
    if next_default_engine == VOICE_ENGINE_HEBREW and not hebrew_requested:
        next_default_engine = VOICE_ENGINE_ENGLISH if english_requested else VOICE_ENGINE_NONE

    voice_config["default_engine"] = next_default_engine
    next_tts_backend = str(voice_config.get("tts_backend") or TTS_BACKEND_OPENAI).strip().lower().replace("-", "_")
    if pack_id == VOICE_ENGINE_KOKORO_TTS and requested:
        next_tts_backend = TTS_BACKEND_KOKORO
    elif pack_id == VOICE_ENGINE_KYUTAI_TTS and requested:
        next_tts_backend = TTS_BACKEND_KYUTAI
    elif pack_id == VOICE_ENGINE_KOKORO_TTS and requested is False and next_tts_backend == TTS_BACKEND_KOKORO:
        next_tts_backend = TTS_BACKEND_KYUTAI if kyutai_tts_requested else TTS_BACKEND_OPENAI
    elif pack_id == VOICE_ENGINE_KYUTAI_TTS and requested is False and next_tts_backend == TTS_BACKEND_KYUTAI:
        next_tts_backend = TTS_BACKEND_KOKORO if kokoro_tts_requested else TTS_BACKEND_OPENAI
    if next_tts_backend not in {TTS_BACKEND_OPENAI, TTS_BACKEND_KOKORO, TTS_BACKEND_KYUTAI}:
        next_tts_backend = TTS_BACKEND_OPENAI
    voice_config["tts_backend"] = next_tts_backend
    voice_config["selection_source"] = "settings"
    save_runtime_config(home, runtime_config)
    return runtime_config
