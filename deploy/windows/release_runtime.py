from __future__ import annotations

import json
import os
import shutil
import sys
import textwrap
from copy import deepcopy
from pathlib import Path
from typing import Callable, Dict, Mapping, MutableMapping

from dotenv import dotenv_values, load_dotenv

from shared.tesseract_runtime import resolve_tesseract_runtime

try:
    import winreg
except ImportError:  # pragma: no cover
    winreg = None


APP_NAME = "EmploAI"
ENV_FILENAME = ".env"
LOG_DIRNAME = "logs"
EXTENSION_DIRNAME = "browser_extension"
RELEASE_STATE_FILENAME = "release_state.json"
EXTENSION_GUIDE_FILENAME = "HOW_TO_LOAD_BROWSER_EXTENSION.txt"

_ENV_ORDER = [
    "TELEGRAM_BOT_TOKEN",
    "ALLOWED_USER_IDS",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
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
    "OPENROUTER_API_KEY",
]

VOICE_ENGINE_NONE = "none"
VOICE_ENGINE_ENGLISH = "english_local"
VOICE_ENGINE_HEBREW = "hebrew_local"
VOICE_DEFAULT_ENGINE_FIELD = "VOICE_DEFAULT_ENGINE"
VOICE_ENGLISH_REQUESTED_FIELD = "VOICE_ENGLISH_REQUESTED"
VOICE_HEBREW_REQUESTED_FIELD = "VOICE_HEBREW_REQUESTED"
_VOICE_SETUP_FIELDS = [
    VOICE_DEFAULT_ENGINE_FIELD,
    VOICE_ENGLISH_REQUESTED_FIELD,
    VOICE_HEBREW_REQUESTED_FIELD,
]
VOICE_PACK_REGISTRY_KEY = r"Software\MightyEpic\EmploAI\VoicePacks"
VOICE_PACK_SELECTION_SCHEMA_VERSION = 1

_SETUP_EDITABLE_FIELDS = [
    "TELEGRAM_BOT_TOKEN",
    "ALLOWED_USER_IDS",
    "DEFAULT_WORKSPACE",
    "PLANNER_MODEL",
    "INTERRUPT_POLICY_DEFAULT",
    *_PROVIDER_KEY_FIELDS,
    *_VOICE_SETUP_FIELDS,
]

_PROVIDER_LABELS = {
    "OPENAI_API_KEY": "OpenAI",
    "ANTHROPIC_API_KEY": "Anthropic",
    "GOOGLE_API_KEY": "Google Gemini",
    "XAI_API_KEY": "xAI Grok",
    "DEEPSEEK_API_KEY": "DeepSeek",
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
    return Path(__file__).resolve().parents[2]


def configure_ssl_certificate_environment() -> str | None:
    """Keep httpx/requests usable inside the frozen Windows backend."""

    certificate_env_keys = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")
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

    base = (
        os.getenv("LOCALAPPDATA")
        or os.getenv("APPDATA")
        or str(Path.home())
    )
    return (Path(base) / APP_NAME).resolve()


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
    preferences: Dict[str, object] = {
        "schema_version": 0,
        "english_requested": None,
        "hebrew_requested": None,
    }
    if winreg is None:
        return preferences

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, VOICE_PACK_REGISTRY_KEY) as key:
            try:
                preferences["schema_version"] = int(winreg.QueryValueEx(key, "SelectionSchemaVersion")[0] or 0)
            except OSError:
                preferences["schema_version"] = 0

            for registry_name, field_name in (
                ("EnglishRequested", "english_requested"),
                ("HebrewRequested", "hebrew_requested"),
            ):
                try:
                    raw_value = winreg.QueryValueEx(key, registry_name)[0]
                    preferences[field_name] = _coerce_bool(raw_value)
                except OSError:
                    if int(preferences.get("schema_version") or 0) >= VOICE_PACK_SELECTION_SCHEMA_VERSION:
                        preferences[field_name] = False
    except OSError:
        return preferences

    return preferences


def _default_voice_config(*, installer_preferences: Mapping[str, object] | None = None) -> Dict[str, object]:
    schema_present = bool(
        installer_preferences
        and int(installer_preferences.get("schema_version") or 0) >= VOICE_PACK_SELECTION_SCHEMA_VERSION
    )
    english_requested = True
    hebrew_requested = False
    selection_source = "default"
    if schema_present:
        english_requested = _coerce_bool(installer_preferences.get("english_requested"), False)
        hebrew_requested = _coerce_bool(installer_preferences.get("hebrew_requested"), False)
        selection_source = "installer"

    return {
        "selection_source": selection_source,
        "default_engine": (
            VOICE_ENGINE_ENGLISH
            if english_requested
            else VOICE_ENGINE_HEBREW
            if hebrew_requested
            else VOICE_ENGINE_NONE
        ),
        "packs": {
            VOICE_ENGINE_ENGLISH: {
                "requested": english_requested,
                "display_name": "English voice pack",
                "placeholder": False,
            },
            VOICE_ENGINE_HEBREW: {
                "requested": hebrew_requested,
                "display_name": "Hebrew voice pack",
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
    english_requested = _coerce_bool(english_pack.get("requested"), True)
    hebrew_requested = _coerce_bool(hebrew_pack.get("requested"), False)
    english_pack["requested"] = english_requested
    hebrew_pack["requested"] = hebrew_requested
    english_pack.setdefault("display_name", "English voice pack")
    english_pack["placeholder"] = False
    hebrew_pack.setdefault("display_name", "Hebrew voice pack")
    hebrew_pack["placeholder"] = False

    default_engine = str(existing_voice.get("default_engine") or "").strip().lower()
    if default_engine not in {VOICE_ENGINE_NONE, VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW}:
        default_engine = VOICE_ENGINE_ENGLISH if english_requested else VOICE_ENGINE_HEBREW if hebrew_requested else VOICE_ENGINE_NONE
    if default_engine == VOICE_ENGINE_ENGLISH and not english_requested:
        default_engine = VOICE_ENGINE_HEBREW if hebrew_requested else VOICE_ENGINE_NONE
    if default_engine == VOICE_ENGINE_HEBREW and not hebrew_requested:
        default_engine = VOICE_ENGINE_ENGLISH if english_requested else VOICE_ENGINE_NONE
    existing_voice["default_engine"] = default_engine

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
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(dict(payload), indent=2), encoding="utf-8")


def apply_installer_voice_pack_preferences(home: Path) -> Dict[str, object]:
    runtime_config = load_runtime_config(home)
    _normalize_voice_config(runtime_config, installer_preferences=_read_installer_voice_pack_preferences())
    save_runtime_config(home, runtime_config)
    return runtime_config


def _voice_pack_setup_payload(voice_config: Mapping[str, object], voice_status: Mapping[str, object]) -> Dict[str, object]:
    packs = voice_config.get("packs") if isinstance(voice_config.get("packs"), dict) else {}
    english_requested = _coerce_bool((packs.get(VOICE_ENGINE_ENGLISH) or {}).get("requested"), True)
    hebrew_requested = _coerce_bool((packs.get(VOICE_ENGINE_HEBREW) or {}).get("requested"), False)
    default_engine = str(voice_config.get("default_engine") or VOICE_ENGINE_NONE).strip().lower()
    if default_engine not in {VOICE_ENGINE_NONE, VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW}:
        default_engine = VOICE_ENGINE_ENGLISH if english_requested else VOICE_ENGINE_HEBREW if hebrew_requested else VOICE_ENGINE_NONE

    english_pack_status = voice_status.get("english_pack_status") if isinstance(voice_status.get("english_pack_status"), dict) else {}
    hebrew_pack_status = voice_status.get("hebrew_pack_status") if isinstance(voice_status.get("hebrew_pack_status"), dict) else {}
    english_pack_ready = _coerce_bool(english_pack_status.get("available"), _coerce_bool(voice_status.get("english_pack_ready"), False))
    hebrew_pack_ready = _coerce_bool(hebrew_pack_status.get("available"), _coerce_bool(voice_status.get("hebrew_pack_ready"), False))

    def build_pack_summary(
        *,
        pack_id: str,
        title: str,
        description: str,
        requested: bool,
        enabled: bool,
        pack_status: Mapping[str, object],
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
            "title": title,
            "description": description,
            "requested": requested,
            "installed": installed,
            "available": available,
            "enabled": enabled,
            "placeholder": False,
            "supportsAlwaysOn": True,
            "status": status,
            "removable": removable,
            "source": source,
            "path": str(pack_status.get("model_dir") or pack_status.get("binary_path") or ""),
            "issues": list(pack_status.get("issues") or []),
        }

    return {
        "defaultEngine": default_engine,
        "selectionSource": str(voice_config.get("selection_source") or "settings"),
        "packs": [
            build_pack_summary(
                pack_id=VOICE_ENGINE_ENGLISH,
                title="English voice pack",
                description="Optional local English speech-to-text with push-to-talk and always-on support.",
                requested=english_requested,
                enabled=default_engine == VOICE_ENGINE_ENGLISH,
                pack_status=english_pack_status,
            ),
            build_pack_summary(
                pack_id=VOICE_ENGINE_HEBREW,
                title="Hebrew voice pack",
                description="Optional local Hebrew speech-to-text using the same push-to-talk and always-on capture flow as English.",
                requested=hebrew_requested,
                enabled=default_engine == VOICE_ENGINE_HEBREW,
                pack_status=hebrew_pack_status,
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
            "default_model": "gpt-4o-mini",
            "default_mode": "auto",
            "max_turns": 100,
            "context_compression_threshold": 0.5,
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
                "enabled": True,
            },
            "app": {
                "enabled": True,
                "host": "0.0.0.0",
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


def ensure_runtime_files(home: Path, source_root: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / LOG_DIRNAME).mkdir(parents=True, exist_ok=True)
    (home / "memory").mkdir(parents=True, exist_ok=True)
    memory_file = home / "MEMORY.md"
    if not memory_file.exists():
        memory_file.write_text(_default_memory_file_content(), encoding="utf-8")

    context_dir = home / "agent_data"
    context_dir.mkdir(parents=True, exist_ok=True)
    bundled_context_dir = source_root / "telegram_bot" / "agent_data"
    if bundled_context_dir.is_dir():
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
        config_file.write_text(
            json.dumps(default_config, indent=2),
            encoding="utf-8",
        )
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
            config_file.write_text(
                json.dumps(existing_config, indent=2),
                encoding="utf-8",
            )

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
    path.write_text(render_env(values), encoding="utf-8")


def needs_first_run_setup(values: Mapping[str, str]) -> bool:
    return bool(validate_setup_values(values))


def needs_versioned_setup(values: Mapping[str, str], *, home: Path, source_root: Path) -> bool:
    if needs_first_run_setup(values):
        return True

    release_version = current_release_version(source_root)
    state = load_release_state(home)
    last_onboarded_version = str(state.get("last_onboarded_version") or "")
    return last_onboarded_version != release_version


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

    while True:
        updates: Dict[str, str] = {}

        token_default = existing.get("TELEGRAM_BOT_TOKEN", "")
        updates["TELEGRAM_BOT_TOKEN"] = _prompt_secret(
            "Telegram bot token",
            existing=token_default,
            input_fn=input_fn,
        )

        ids_default = existing.get("ALLOWED_USER_IDS", "")
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
    os.chdir(home)
    load_dotenv(dotenv_path=env_file, override=True)
    configure_ssl_certificate_environment()

    values = load_existing_env_values(env_file)
    for key, value in values.items():
        os.environ[key] = value

    os.environ.setdefault("DEFAULT_WORKSPACE", values.get("DEFAULT_WORKSPACE", str(default_workspace())))
    os.environ.setdefault("BETA_MODE", values.get("BETA_MODE", "true"))
    os.environ.setdefault("HEADLESS", values.get("HEADLESS", "false"))
    os.environ.setdefault("EMPLOAI_HOME", str(home))
    return values


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
    if not values.get("GOOGLE_API_KEY") and values.get("GEMINI_API_KEY"):
        values["GOOGLE_API_KEY"] = values["GEMINI_API_KEY"]
    return values


def configured_provider_labels(values: Mapping[str, str]) -> list[str]:
    normalized = _normalized_existing_values(values)
    labels: list[str] = []
    for key in _PROVIDER_KEY_FIELDS:
        if normalized.get(key):
            labels.append(_PROVIDER_LABELS.get(key, key))
    return labels


def validate_setup_values(values: Mapping[str, str]) -> list[str]:
    normalized = _normalized_existing_values(values)
    issues: list[str] = []

    workspace = normalized.get("DEFAULT_WORKSPACE", "").strip()
    if not workspace:
        issues.append("Workspace root is required.")

    if not any(normalized.get(key, "").strip() for key in _PROVIDER_KEY_FIELDS):
        issues.append("At least one model API key is required.")

    token = normalized.get("TELEGRAM_BOT_TOKEN", "").strip()
    allowed_ids = normalized.get("ALLOWED_USER_IDS", "").strip()
    if token and not allowed_ids:
        issues.append("Allowed Telegram user ID(s) are required when a Telegram bot token is configured.")
    if allowed_ids and not token:
        issues.append("Telegram bot token is required when allowed Telegram user ID(s) are configured.")

    return issues


def resolve_voice_runtime_status() -> Dict[str, object]:
    try:
        from mobile_app.backend.voice_runtime import get_voice_runtime_status

        return get_voice_runtime_status()
    except Exception as exc:
        return {
            "ok": False,
            "issues": [f"Voice runtime check failed: {exc}"],
            "stt_backend": "local_whisper",
            "stt_model": None,
            "draft_model": None,
            "binary_flavor": None,
            "tts_enabled": False,
        }


def build_setup_state(
    *,
    home: Path,
    env_file: Path,
    source_root: Path,
    existing: Mapping[str, str],
) -> Dict[str, object]:
    normalized = _normalized_existing_values(existing)
    state = load_release_state(home)
    release_version = current_release_version(source_root)
    runtime = resolve_tesseract_runtime()
    voice_status = resolve_voice_runtime_status()
    runtime_config = load_runtime_config(home)
    _normalize_voice_config(runtime_config, installer_preferences=_read_installer_voice_pack_preferences())
    voice_config = runtime_config.get("voice") if isinstance(runtime_config.get("voice"), dict) else {}
    values = {field: normalized.get(field, "").strip() for field in _SETUP_EDITABLE_FIELDS}
    english_requested = _coerce_bool(
        (((voice_config.get("packs") or {}).get(VOICE_ENGINE_ENGLISH) or {}).get("requested")),
        True,
    )
    hebrew_requested = _coerce_bool(
        (((voice_config.get("packs") or {}).get(VOICE_ENGINE_HEBREW) or {}).get("requested")),
        False,
    )
    values[VOICE_DEFAULT_ENGINE_FIELD] = str(voice_config.get("default_engine") or VOICE_ENGINE_NONE)
    values[VOICE_ENGLISH_REQUESTED_FIELD] = _setting_bool(english_requested, True)
    values[VOICE_HEBREW_REQUESTED_FIELD] = _setting_bool(hebrew_requested, False)

    return {
        "required": bool(validate_setup_values(normalized)),
        "versioned": str(state.get("last_onboarded_version") or "") != release_version,
        "releaseVersion": release_version,
        "runtimeHome": str(home),
        "envFilePath": str(env_file),
        "extensionPath": str(extension_path(home)),
        "extensionGuidePath": str(home / EXTENSION_GUIDE_FILENAME),
        "values": values,
        "validationIssues": validate_setup_values(normalized),
        "configuredProviders": configured_provider_labels(normalized),
        "telegramConfigured": bool(normalized.get("TELEGRAM_BOT_TOKEN") and normalized.get("ALLOWED_USER_IDS")),
        "telegramPartiallyConfigured": bool(
            bool(normalized.get("TELEGRAM_BOT_TOKEN")) ^ bool(normalized.get("ALLOWED_USER_IDS"))
        ),
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
        _coerce_bool(english_pack.get("requested"), True),
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
        or VOICE_ENGINE_ENGLISH
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
    state = load_release_state(home)
    state["last_onboarded_version"] = current_release_version(source_root)
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

    if pack_id is not None and requested is not None:
        if pack_id == VOICE_ENGINE_ENGLISH:
            english_pack["requested"] = bool(requested)
        elif pack_id == VOICE_ENGINE_HEBREW:
            hebrew_pack["requested"] = bool(requested)
        else:
            raise ValueError(f"Unsupported voice pack: {pack_id}")

    english_requested = _coerce_bool(english_pack.get("requested"), True)
    hebrew_requested = _coerce_bool(hebrew_pack.get("requested"), False)
    english_pack["requested"] = english_requested
    hebrew_pack["requested"] = hebrew_requested
    english_pack["placeholder"] = False
    hebrew_pack["placeholder"] = False
    english_pack.setdefault("display_name", "English voice pack")
    hebrew_pack.setdefault("display_name", "Hebrew voice pack")

    next_default_engine = str(default_engine or voice_config.get("default_engine") or VOICE_ENGINE_NONE).strip().lower()
    if next_default_engine not in {VOICE_ENGINE_NONE, VOICE_ENGINE_ENGLISH, VOICE_ENGINE_HEBREW}:
        next_default_engine = VOICE_ENGINE_ENGLISH if english_requested else VOICE_ENGINE_HEBREW if hebrew_requested else VOICE_ENGINE_NONE
    if next_default_engine == VOICE_ENGINE_ENGLISH and not english_requested:
        next_default_engine = VOICE_ENGINE_HEBREW if hebrew_requested else VOICE_ENGINE_NONE
    if next_default_engine == VOICE_ENGINE_HEBREW and not hebrew_requested:
        next_default_engine = VOICE_ENGINE_ENGLISH if english_requested else VOICE_ENGINE_NONE

    voice_config["default_engine"] = next_default_engine
    voice_config["selection_source"] = "settings"
    save_runtime_config(home, runtime_config)
    return runtime_config
