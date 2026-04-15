from __future__ import annotations

import json
import os
import shutil
import sys
import textwrap
from pathlib import Path
from typing import Callable, Dict, Mapping, MutableMapping

from dotenv import dotenv_values, load_dotenv


APP_NAME = "EmploAI"
ENV_FILENAME = ".env"
LOG_DIRNAME = "logs"
EXTENSION_DIRNAME = "browser_extension"
RELEASE_STATE_FILENAME = "release_state.json"

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
    "HEADLESS",
]


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


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


def env_path(home: Path) -> Path:
    return home / ENV_FILENAME


def default_workspace() -> Path:
    home = Path.home()
    documents = home / "Documents"
    if documents.exists():
        return documents.resolve()
    return home.resolve()


def default_release_config() -> Dict[str, object]:
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
        "channels": {
            "telegram": {
                "enabled": True,
            },
            "app": {
                "enabled": False,
                "host": "0.0.0.0",
                "port": 8787,
                "auth_mode": "token",
                "steering_beta": False,
                "push_notifications": False,
            },
        },
    }


def ensure_runtime_files(home: Path, source_root: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / LOG_DIRNAME).mkdir(parents=True, exist_ok=True)
    (home / "memory").mkdir(parents=True, exist_ok=True)

    config_file = home / "config.json"
    if not config_file.exists():
        config_file.write_text(
            json.dumps(default_release_config(), indent=2),
            encoding="utf-8",
        )

    example_src = source_root / ".env.example"
    example_dst = home / ".env.example"
    if example_src.exists() and not example_dst.exists():
        shutil.copyfile(example_src, example_dst)

    extension_src = source_root / EXTENSION_DIRNAME
    extension_dst = home / EXTENSION_DIRNAME
    if extension_src.exists():
        shutil.copytree(extension_src, extension_dst, dirs_exist_ok=True)


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
    _release_state_path(home).write_text(
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
    return not values.get("TELEGRAM_BOT_TOKEN") or not values.get("ALLOWED_USER_IDS")


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

            The bot runs in this console window and prints logs here directly.
            You can re-run setup later by launching the exe with `--setup`.
            EmploAI reopens setup once after each installed update so you can review keys and configuration.

            Telegram setup:
              1. Open Telegram and talk to @BotFather
              2. Run /newbot and copy the bot token
              3. Open @userinfobot and send any message
              4. Copy your numeric Telegram user ID

            Browser extension path for this beta build:
              {home / EXTENSION_DIRNAME}

            If you want the real Chrome extension bridge later:
              1. Open chrome://extensions
              2. Enable Developer mode
              3. Click Load unpacked
              4. Select the browser_extension folder above

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

    updates: Dict[str, str] = {}
    token_default = existing.get("TELEGRAM_BOT_TOKEN", "")
    if token_default:
        token = _prompt_with_default("Telegram bot token", token_default, input_fn)
    else:
        token = _prompt_nonempty("Telegram bot token: ", input_fn)
    updates["TELEGRAM_BOT_TOKEN"] = token

    ids_default = existing.get("ALLOWED_USER_IDS", "")
    if ids_default:
        allowed_ids = _prompt_with_default("Allowed Telegram user ID(s)", ids_default, input_fn)
    else:
        allowed_ids = _prompt_nonempty("Allowed Telegram user ID(s): ", input_fn)
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
        existing=existing.get("GOOGLE_API_KEY", ""),
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

    updates.setdefault("MAX_REQUESTS_PER_MINUTE", existing.get("MAX_REQUESTS_PER_MINUTE", "30"))
    updates.setdefault("MAX_REQUESTS_PER_HOUR", existing.get("MAX_REQUESTS_PER_HOUR", "200"))
    updates.setdefault("BETA_MODE", existing.get("BETA_MODE", "true"))
    updates.setdefault("HEADLESS", existing.get("HEADLESS", "false"))

    merged = merge_env(existing, updates)
    save_env(env_file, merged)
    state = load_release_state(home)
    state["last_onboarded_version"] = current_release_version(source_root)
    save_release_state(home, state)

    print()
    print(f"Saved setup to {env_file}")
    configured_keys = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "XAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "OPENROUTER_API_KEY",
    ]
    if not any(merged.get(key) for key in configured_keys):
        print("Warning: no model API key was configured. The bot will start, but model calls will fail until you add one.")
    print()
    return merged


def configure_process_environment(home: Path, env_file: Path) -> Dict[str, str]:
    os.chdir(home)
    load_dotenv(dotenv_path=env_file, override=True)

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
    print("Logs stream in this console window. Press Ctrl+C to stop the bot.")
    print()
