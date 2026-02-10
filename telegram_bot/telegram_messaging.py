"""Telegram messaging helpers with Markdown-safe fallbacks."""

from __future__ import annotations

from telegram import Update
from telegram.constants import ParseMode


async def safe_reply(update: Update, text: str, reply_markup=None):
    """Send message with Markdown, fallback to plain text, and handle long messages."""
    message = update.effective_message
    if not message:
        return None

    if len(text) > 4000:
        text = text[:3900] + "... (truncated)"

    try:
        return await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    except Exception:
        try:
            clean_text = text.replace("*", "").replace("_", "").replace("`", "")
            return await message.reply_text(clean_text, reply_markup=reply_markup)
        except Exception as exc:
            print(f"[REPLY ERROR] {exc}")
    return None


async def safe_edit_message(message, text: str, reply_markup=None):
    """Edit a message with Markdown, fallback to plain text."""
    if not message:
        return

    if len(text) > 4000:
        text = text[:3900] + "... (truncated)"

    try:
        await message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    except Exception:
        try:
            clean_text = text.replace("*", "").replace("_", "").replace("`", "")
            await message.edit_text(clean_text, reply_markup=reply_markup)
        except Exception as exc:
            print(f"[EDIT ERROR] {exc}")


async def safe_edit(query, text: str, reply_markup=None):
    """Edit message with Markdown, fallback to plain text."""
    if len(text) > 4000:
        text = text[:3900] + "... (truncated)"

    try:
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    except Exception:
        try:
            clean_text = text.replace("*", "").replace("_", "").replace("`", "")
            await query.edit_message_text(clean_text, reply_markup=reply_markup)
        except Exception as exc:
            print(f"[EDIT ERROR] {exc}")


async def safe_send(bot, chat_id: int, text: str):
    """Send message with Markdown, fallback to plain text."""
    if len(text) > 4000:
        text = text[:3900] + "... (truncated)"

    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        try:
            clean_text = text.replace("*", "").replace("_", "").replace("`", "")
            await bot.send_message(chat_id=chat_id, text=clean_text)
        except Exception as exc:
            print(f"[SEND ERROR] {exc}")
