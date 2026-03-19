"""Telegram bot application wiring."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from telegram import BotCommand
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters


COMMAND_ORDER = [
    "start",
    "help",
    "mode",
    "variant",
    "model",
    "models",
    "settings",
    "workspace",
    "task",
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


def build_bot_commands() -> list[BotCommand]:
    return [
        BotCommand("start", "Initialize the agent"),
        BotCommand("help", "Show available commands"),
        BotCommand("variant", "Set model variant"),
        BotCommand("model", "Switch AI model"),
        BotCommand("models", "List all models"),
        BotCommand("settings", "Configure max turns"),
        BotCommand("workspace", "Set workspace path"),
        BotCommand("headless", "Toggle browser mode"),
        BotCommand("security", "Security status"),
        BotCommand("continue", "Resume paused task"),
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
):
    print("Telegram CLI Agent Starting...")
    logging.info(f"Bot Token: {bot_token[:10]}...")

    application = (
        Application.builder()
        .token(bot_token)
        .post_init(post_init)
        .concurrent_updates(True)
        .build()
    )

    register_handlers(
        application,
        command_handlers=command_handlers,
        callback_handler=callback_handler,
        message_handlers=message_handlers,
    )

    print("[INFO] Starting polling (dropping pending updates)...")
    application.run_polling(drop_pending_updates=True)
