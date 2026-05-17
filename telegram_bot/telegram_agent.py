"""
Telegram CLI Agent - Unified auto agent via Telegram with interactive menus.
Supports: variants, models, sessions, automation, and settings.

Default chat uses the unified auto agent for file ops, terminal, search,
browser, and desktop automation.
"""

import asyncio
import logging
import os
import sys

# Add parent directory to path to allow imports from root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from telegram_bot.linux import headed_linux_runtime_error
except ImportError:
    try:
        from linux import headed_linux_runtime_error
    except ImportError:
        def headed_linux_runtime_error() -> str | None:
            return None

from dotenv import load_dotenv
load_dotenv()

from bot_core.hooks import HookEvent, HookType
from bot_core.security import SecurityManager, rate_limited, authorized_only
from bot_core.ui_helpers import InlineKeyboardHelper, MessageFormatter
from cli.tui_constants import AVAILABLE_MODELS as _ALL_MODELS, MODEL_CONFIGS as _ALL_MODEL_CONFIGS
try:
    from telegram_bot.telegram_app import run_bot
except ImportError:
    from telegram_app import run_bot

# ======================================================================================
# BETA MODE — restrict expensive models
# ======================================================================================
# When BETA_MODE=true, only cheap Anthropic models (Haiku) are available.
# All other providers (OpenAI, Google, xAI, DeepSeek, OpenRouter) are unrestricted.
BETA_MODE = os.getenv("BETA_MODE", "false").lower() in ("true", "1", "yes")

# Anthropic models allowed in beta mode (cheap ones only)
_BETA_ALLOWED_ANTHROPIC = {"claude-haiku-4.5", "claude-haiku-4"}

if BETA_MODE:
    MODEL_CONFIGS = {
        name: config for name, config in _ALL_MODEL_CONFIGS.items()
        if config.get("provider") != "anthropic" or name in _BETA_ALLOWED_ANTHROPIC
    }
    AVAILABLE_MODELS = list(MODEL_CONFIGS.keys())
    logging.info(f"[BETA MODE] Active — Anthropic restricted to: {_BETA_ALLOWED_ANTHROPIC}")
else:
    MODEL_CONFIGS = _ALL_MODEL_CONFIGS
    AVAILABLE_MODELS = _ALL_MODELS
try:
    from telegram_bot.telegram_callback_handlers import build_callback_handlers
    from telegram_bot.telegram_chat_flow import run_chat_flow
    from telegram_bot.telegram_commands_core import build_core_command_handlers
    from telegram_bot.telegram_commands_session import build_session_command_handlers
    from telegram_bot.telegram_commands_skills import build_skill_command_handlers
    from telegram_bot.telegram_commands_tasks import build_task_command_handlers
    from telegram_bot.telegram_commands_utility import build_utility_command_handlers
    from telegram_bot.telegram_message_handlers import build_message_handlers
    from telegram_bot.telegram_messaging import safe_edit, safe_reply
    from telegram_bot.restart_runtime import exec_current_process
    from telegram_bot.telegram_session_state import get_session, set_telegram_application, track_command_usage
except ImportError:
    from telegram_callback_handlers import build_callback_handlers
    from telegram_chat_flow import run_chat_flow
    from telegram_commands_core import build_core_command_handlers
    from telegram_commands_session import build_session_command_handlers
    from telegram_commands_skills import build_skill_command_handlers
    from telegram_commands_tasks import build_task_command_handlers
    from telegram_commands_utility import build_utility_command_handlers
    from telegram_message_handlers import build_message_handlers
    from telegram_messaging import safe_edit, safe_reply
    from restart_runtime import exec_current_process
    from telegram_session_state import get_session, set_telegram_application, track_command_usage

# ======================================================================================
# 🔒 CONFIGURATION
# ======================================================================================
# Initialize security manager (loads from environment variables)
# Required env vars: TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS (comma-separated)
# Optional: MAX_REQUESTS_PER_MINUTE (default: 30), MAX_REQUESTS_PER_HOUR (default: 200)
try:
    security_manager = SecurityManager(
        max_requests_per_minute=int(os.getenv("MAX_REQUESTS_PER_MINUTE", "30")),
        max_requests_per_hour=int(os.getenv("MAX_REQUESTS_PER_HOUR", "200")),
    )
    BOT_TOKEN = security_manager.bot_token
    ALLOWED_USER_ID = list(security_manager.allowed_user_ids)[0] if security_manager.allowed_user_ids else None
except ValueError as e:
    logging.error(f"Security configuration error: {e}")
    raise

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def restart_process() -> None:
    """Re-exec the current Python process so the bot restarts in-place."""
    exec_current_process(script_path_fallback=os.path.abspath(__file__))


def _safe_start_embedded_app_server() -> None:
    try:
        from mobile_app.backend import start_embedded_app_server_if_enabled

        force_enabled = os.getenv("EMPLOAI_DESKTOP_FORCE_APP_SERVER", "").strip().lower() in {"1", "true", "yes", "on"}
        start_embedded_app_server_if_enabled(force=force_enabled)
    except Exception:
        logger.exception("Embedded app server startup failed; continuing without mobile app backend")


async def _safe_start_cron_scheduler() -> None:
    try:
        from mobile_app.backend.cron_runtime import ensure_global_cron_scheduler_started

        await ensure_global_cron_scheduler_started()
    except Exception:
        logger.exception("Cron scheduler startup failed; continuing without background cron runtime")


# ======================================================================================
# COMMAND HANDLERS
# ======================================================================================

_core_command_handlers = build_core_command_handlers(
    security_manager=security_manager,
    rate_limited=rate_limited,
    authorized_only=authorized_only,
    get_session=get_session,
    track_command_usage=track_command_usage,
    safe_reply=safe_reply,
    logger=logger,
)

start = _core_command_handlers["start"]
help_command = _core_command_handlers["help_command"]
mode_command = _core_command_handlers["mode_command"]
variant_command = _core_command_handlers["variant_command"]
model_command = _core_command_handlers["model_command"]
models_command = _core_command_handlers["models_command"]
planner_command = _core_command_handlers["planner_command"]
settings_command = _core_command_handlers["settings_command"]
workspace_command = _core_command_handlers["workspace_command"]


_task_command_handlers = build_task_command_handlers(
    security_manager=security_manager,
    rate_limited=rate_limited,
    get_session=get_session,
    track_command_usage=track_command_usage,
    safe_reply=safe_reply,
)

continue_command = _task_command_handlers["continue_command"]
pause_command = _task_command_handlers["pause_command"]
stop_command = _task_command_handlers["stop_command"]
task_command = _task_command_handlers["task_command"]
reassess_command = _task_command_handlers["reassess_command"]
spawn_command = _task_command_handlers["spawn_command"]
subagents_command = _task_command_handlers["subagents_command"]
schedule_command = _task_command_handlers["schedule_command"]
jobs_command = _task_command_handlers["jobs_command"]
job_remove_command = _task_command_handlers["job_remove_command"]
headless_command = _task_command_handlers["headless_command"]

_session_command_handlers = build_session_command_handlers(
    security_manager=security_manager,
    rate_limited=rate_limited,
    authorized_only=authorized_only,
    get_session=get_session,
    track_command_usage=track_command_usage,
    safe_reply=safe_reply,
    InlineKeyboardHelper=InlineKeyboardHelper,
)

session_command = _session_command_handlers["session_command"]
new_command = _session_command_handlers["new_command"]
reset_command = _session_command_handlers["reset_command"]
compact_command = _session_command_handlers["compact_command"]
context_command = _session_command_handlers["context_command"]
security_command = _session_command_handlers["security_command"]

_skill_command_handlers = build_skill_command_handlers(
    security_manager=security_manager,
    rate_limited=rate_limited,
    get_session=get_session,
    track_command_usage=track_command_usage,
    safe_reply=safe_reply,
)

skills_command = _skill_command_handlers["skills_command"]
skill_command = _skill_command_handlers["skill_command"]
skilltest_command = _skill_command_handlers["skilltest_command"]

_utility_command_handlers = build_utility_command_handlers(
    security_manager=security_manager,
    rate_limited=rate_limited,
    get_session=get_session,
    track_command_usage=track_command_usage,
    safe_reply=safe_reply,
    InlineKeyboardHelper=InlineKeyboardHelper,
    restart_process=restart_process,
)

monitor_command = _utility_command_handlers["monitor_command"]
analytics_command = _utility_command_handlers["analytics_command"]
history_command = _utility_command_handlers["history_command"]
files_command = _utility_command_handlers["files_command"]
forget_command = _utility_command_handlers["forget_command"]
setup_command = _utility_command_handlers["setup_command"]
memory_command = _utility_command_handlers["memory_command"]
memory_update_command = _utility_command_handlers["memory_update_command"]
config_command = _utility_command_handlers["config_command"]
heartbeat_command = _utility_command_handlers["heartbeat_command"]
verbose_command = _utility_command_handlers["verbose_command"]
bridge_command = _utility_command_handlers["bridge_command"]
restart_command = _utility_command_handlers["restart_command"]

# ======================================================================================
# CALLBACK QUERY HANDLER (for inline buttons)
# ======================================================================================

_callback_handlers = build_callback_handlers(
    allowed_user_id=ALLOWED_USER_ID,
    get_session=get_session,
    safe_edit=safe_edit,
    run_chat_flow=run_chat_flow,
    stop_command=stop_command,
    pause_command=pause_command,
    continue_command=continue_command,
    InlineKeyboardHelper=InlineKeyboardHelper,
    AVAILABLE_MODELS=AVAILABLE_MODELS,
    MODEL_CONFIGS=MODEL_CONFIGS,
)

button_callback = _callback_handlers["button_callback"]


_message_handlers = build_message_handlers(
    security_manager=security_manager,
    safe_reply=safe_reply,
    get_session=get_session,
    run_chat_flow=run_chat_flow,
    logger=logger,
    HookType=HookType,
    HookEvent=HookEvent,
    MessageFormatter=MessageFormatter,
)

handle_message = _message_handlers["handle_message"]
handle_message_edit = _message_handlers["handle_message_edit"]
handle_file_upload = _message_handlers["handle_file_upload"]
handle_document = _message_handlers["handle_document"]
handle_photo = _message_handlers["handle_photo"]


# ======================================================================================
# BOT APP
# ======================================================================================

command_handlers = {
    "start": start,
    "help": help_command,
    "mode": mode_command,
    "variant": variant_command,
    "model": model_command,
    "models": models_command,
    "planner": planner_command,
    "settings": settings_command,
    "workspace": workspace_command,
    "continue": continue_command,
    "pause": pause_command,
    "stop": stop_command,
    "task": task_command,
    "reassess": reassess_command,
    "session": session_command,
    "new": new_command,
    "reset": reset_command,
    "compact": compact_command,
    "context": context_command,
    "spawn": spawn_command,
    "subagents": subagents_command,
    "schedule": schedule_command,
    "jobs": jobs_command,
    "job_remove": job_remove_command,
    "headless": headless_command,
    "security": security_command,
    "skills": skills_command,
    "skill": skill_command,
    "skilltest": skilltest_command,
    "monitor": monitor_command,
    "analytics": analytics_command,
    "history": history_command,
    "files": files_command,
    "setup": setup_command,
    "forget": forget_command,
    "memory": memory_command,
    "memory_update": memory_update_command,
    "config": config_command,
    "heartbeat": heartbeat_command,
    "restart": restart_command,
    "verbose": verbose_command,
    "bridge": bridge_command,
}

message_handlers = {
    "handle_message": handle_message,
    "handle_document": handle_document,
    "handle_photo": handle_photo,
    "handle_message_edit": handle_message_edit,
}


def main():
    runtime_error = headed_linux_runtime_error()
    if runtime_error:
        logger.error(runtime_error)
        raise RuntimeError(runtime_error)

    _safe_start_embedded_app_server()
    asyncio.run(_safe_start_cron_scheduler())

    run_bot(
        bot_token=BOT_TOKEN,
        command_handlers=command_handlers,
        callback_handler=button_callback,
        message_handlers=message_handlers,
        on_application_ready=set_telegram_application,
    )


if __name__ == "__main__":
    import signal
    import sys
    
    def signal_handler(sig, frame):
        print("\n[SHUTDOWN] Ctrl+C received. Forcing exit...")
        # Force kill all child processes and exit immediately
        os._exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Exiting...")
        os._exit(0)
