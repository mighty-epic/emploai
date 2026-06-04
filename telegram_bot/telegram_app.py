"""Telegram bot application wiring."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, Optional

from telegram import BotCommand
from telegram.error import NetworkError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters


COMMAND_ORDER = [
    "start",
    "help",
    "mode",
    "variant",
    "model",
    "models",
    "planner",
    "settings",
    "workspace",
    "continue",
    "pause",
    "stop",
    "session",
    "reset",
    "context",
    "spawn",
    "subagents",
    "schedule",
    "jobs",
    "job_remove",
    "headless",
    "security",
    "skills",
    "skill",
    "skilltest",
    "monitor",
    "analytics",
    "history",
    "files",
    "setup",
    "forget",
    "memory",
    "memory_update",
    "config",
    "heartbeat",
    "restart",
    "verbose",
    "bridge",
]

POLLING_BOOTSTRAP_RETRIES = -1
NETWORK_ERROR_LOG_INTERVAL_SECONDS = 15.0
_last_network_error_log_at = 0.0


def build_bot_commands() -> list[BotCommand]:
    return [
        BotCommand("start", "Initialize the agent"),
        BotCommand("help", "Show available commands"),
        BotCommand("variant", "Set model variant"),
        BotCommand("model", "Switch AI model"),
        BotCommand("models", "List all models"),
        BotCommand("planner", "Choose planner model"),
        BotCommand("settings", "Configure max turns"),
        BotCommand("workspace", "Set workspace path"),
        BotCommand("headless", "Toggle browser mode"),
        BotCommand("security", "Security status"),
        BotCommand("pause", "Pause running task"),
        BotCommand("stop", "Stop running task"),
        BotCommand("spawn", "Spawn parallel sub-agent"),
        BotCommand("subagents", "List running sub-agents"),
        BotCommand("schedule", "Schedule recurring task"),
        BotCommand("jobs", "List scheduled jobs"),
        BotCommand("job_remove", "Remove scheduled job"),
        BotCommand("session", "Manage sessions"),
        BotCommand("reset", "Clear chat history"),
        BotCommand("context", "Show token usage"),
        BotCommand("skills", "List available skills"),
        BotCommand("skill", "Invoke a specific skill"),
        BotCommand("skilltest", "Validate a skill"),
        BotCommand("files", "Show pending files"),
        BotCommand("monitor", "Toggle auto-reply"),
        BotCommand("analytics", "Usage summary"),
        BotCommand("history", "Conversation history"),
        BotCommand("setup", "Guided setup wizard"),
        BotCommand("forget", "Remove last user message"),
        BotCommand("restart", "Restart the bot process"),
        BotCommand("verbose", "Toggle live tool logging"),
        BotCommand("bridge", "Toggle native browser bridge"),
    ]


async def post_init(application: Application):
    """Set bot commands menu after initialization."""
    await application.bot.set_my_commands(build_bot_commands())
    print("[OK] Bot commands menu registered")


def is_network_error(error: BaseException) -> bool:
    return isinstance(error, NetworkError)


def format_network_error_message(error: BaseException) -> str:
    message = str(error).strip() or error.__class__.__name__
    lowered = message.lower()
    if "getaddrinfo failed" in lowered:
        return "Telegram unreachable: DNS lookup failed. Check internet/DNS; retrying automatically."
    if "timed out" in lowered or "timeout" in lowered:
        return "Telegram unreachable: connection timed out. Retrying automatically."
    return f"Telegram unreachable: {message}. Retrying automatically."


async def application_error_handler(_update: object, context) -> None:
    global _last_network_error_log_at

    error = context.error
    if error is None:
        return

    if is_network_error(error):
        now = time.monotonic()
        if now - _last_network_error_log_at >= NETWORK_ERROR_LOG_INTERVAL_SECONDS:
            _last_network_error_log_at = now
            print(f"[WARN] {format_network_error_message(error)}")
        return

    logging.error(
        "Unhandled Telegram application error",
        exc_info=(type(error), error, error.__traceback__),
    )


def build_polling_kwargs() -> dict[str, object]:
    return {
        "drop_pending_updates": True,
        "bootstrap_retries": POLLING_BOOTSTRAP_RETRIES,
    }


def register_handlers(
    application: Application,
    *,
    command_handlers: Dict[str, Callable[..., Any]],
    callback_handler: Callable[..., Any],
    message_handlers: Dict[str, Callable[..., Any]],
):
    for command in COMMAND_ORDER:
        handler = command_handlers[command]
        application.add_handler(CommandHandler(command, handler))

    application.add_handler(CallbackQueryHandler(callback_handler))

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, message_handlers["handle_message"])
    )
    application.add_handler(
        MessageHandler(filters.Document.ALL, message_handlers["handle_document"])
    )
    application.add_handler(MessageHandler(filters.PHOTO, message_handlers["handle_photo"]))
    application.add_handler(
        MessageHandler(
            filters.UpdateType.EDITED_MESSAGE & filters.TEXT,
            message_handlers["handle_message_edit"],
        )
    )


def run_bot(
    *,
    bot_token: str,
    command_handlers: Dict[str, Callable[..., Any]],
    callback_handler: Callable[..., Any],
    message_handlers: Dict[str, Callable[..., Any]],
    on_application_ready: Optional[Callable[[Application], Any]] = None,
    extra_bot_tokens_provider: Optional[Callable[[], list[str]]] = None,
):
    print("Telegram CLI Agent Starting...")
    logging.info(f"Bot Token: {bot_token[:10]}...")

    async def _run_ready_callbacks(application: Application, callback: Optional[Callable[[Application], Any]]) -> None:
        await post_init(application)
        if not callback:
            return
        maybe = callback(application)
        if maybe is not None and hasattr(maybe, "__await__"):
            await maybe

    def _build_application(token: str, *, callback: Optional[Callable[[Application], Any]], use_post_init: bool) -> Application:
        builder = (
            Application.builder()
            .token(token)
            .concurrent_updates(True)
        )
        if use_post_init:
            async def _post_init(application: Application):
                await _run_ready_callbacks(application, callback)
            builder = builder.post_init(_post_init)
        application = builder.build()
        application.add_error_handler(application_error_handler)
        register_handlers(
            application,
            command_handlers=command_handlers,
            callback_handler=callback_handler,
            message_handlers=message_handlers,
        )
        return application

    if not extra_bot_tokens_provider:
        application = _build_application(bot_token, callback=on_application_ready, use_post_init=True)
        print("[INFO] Starting polling (dropping pending updates)...")
        application.run_polling(**build_polling_kwargs())
        return

    async def _start_application(application: Application, *, callback: Optional[Callable[[Application], Any]]) -> None:
        await application.initialize()
        await _run_ready_callbacks(application, callback)
        await application.start()
        if application.updater is not None:
            await application.updater.start_polling(**build_polling_kwargs())

    async def _stop_application(application: Application) -> None:
        if application.updater is not None:
            await application.updater.stop()
        await application.stop()
        await application.shutdown()

    async def _run_multi_bot_group() -> None:
        primary_app = _build_application(bot_token, callback=None, use_post_init=False)
        extra_apps: Dict[str, Application] = {}
        await _start_application(primary_app, callback=on_application_ready)
        try:
            while True:
                desired_tokens = {
                    str(token or "").strip()
                    for token in (extra_bot_tokens_provider() or [])
                    if str(token or "").strip() and str(token or "").strip() != bot_token
                }
                for token in sorted(desired_tokens):
                    if token in extra_apps:
                        continue
                    logging.info("Starting additional Telegram bot polling for %s...", f"{token[:10]}...")
                    extra_app = _build_application(token, callback=None, use_post_init=False)
                    await _start_application(extra_app, callback=None)
                    extra_apps[token] = extra_app

                for token, app in list(extra_apps.items()):
                    if token in desired_tokens:
                        continue
                    logging.info("Stopping removed Telegram bot polling for %s...", f"{token[:10]}...")
                    await _stop_application(app)
                    extra_apps.pop(token, None)

                await asyncio.sleep(5.0)
        finally:
            for token, app in list(extra_apps.items()):
                try:
                    await _stop_application(app)
                finally:
                    extra_apps.pop(token, None)
            await _stop_application(primary_app)

    print("[INFO] Starting polling (dropping pending updates)...")
    asyncio.run(_run_multi_bot_group())
