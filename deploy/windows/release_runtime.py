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


def load_existing_env_values(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    values = dotenv_values(path)
    return {
        key: str(value).strip()
        for key, value in values.items()
        if value is not None
    }


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


def _prompt_nonempty(prompt: str, input_fn: Callable[[str], str]) -> str:
    while True:
        value = input_fn(prompt).strip()
        if value:
            return value
        print("A value is required.")


def _prompt_with_default(prompt: str, default: str, input_fn: Callable[[str], str]) -> str:
    value = input_fn(f"{prompt} [{default}]: ").strip()
    return value or default


def _print_setup_intro(home: Path, env_file: Path) -> None:
    print("=" * 72)
    print(f"{APP_NAME} Beta Setup")
    print("=" * 72)
    print(
        textwrap.dedent(
            f"""
            This beta build stores its runtime files here:
              {home}

            The bot runs in this console window and prints logs here directly.
            You can re-run setup later by launching the exe with `--setup`.

            Telegram setup:
              1. Open Telegram and talk to @BotFather
              2. Run /newbot and copy the bot token
              3. Open @userinfobot and send any message
              4. Copy your numeric Telegram user ID

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
    existing: Mapping[str, str],
    input_fn: Callable[[str], str] = input,
) -> Dict[str, str]:
    _print_setup_intro(home, env_file)

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

    openai_default = existing.get("OPENAI_API_KEY", "")
    openai_prompt = (
        "OpenAI API key (recommended for first run, press Enter to skip)"
        if not openai_default
        else "OpenAI API key"
    )
    openai_value = input_fn(f"{openai_prompt}{f' [{openai_default}]' if openai_default else ''}: ").strip()
    updates["OPENAI_API_KEY"] = openai_value or openai_default

    anthropic_default = existing.get("ANTHROPIC_API_KEY", "")
    anthropic_prompt = (
        "Anthropic API key (optional, press Enter to skip)"
        if not anthropic_default
        else "Anthropic API key"
    )
    anthropic_value = input_fn(f"{anthropic_prompt}{f' [{anthropic_default}]' if anthropic_default else ''}: ").strip()
    updates["ANTHROPIC_API_KEY"] = anthropic_value or anthropic_default

    updates.setdefault("MAX_REQUESTS_PER_MINUTE", existing.get("MAX_REQUESTS_PER_MINUTE", "30"))
    updates.setdefault("MAX_REQUESTS_PER_HOUR", existing.get("MAX_REQUESTS_PER_HOUR", "200"))
    updates.setdefault("BETA_MODE", existing.get("BETA_MODE", "true"))
    updates.setdefault("HEADLESS", existing.get("HEADLESS", "false"))

    merged = merge_env(existing, updates)
    save_env(env_file, merged)

    print()
    print(f"Saved setup to {env_file}")
    if not merged.get("OPENAI_API_KEY") and not merged.get("ANTHROPIC_API_KEY"):
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

