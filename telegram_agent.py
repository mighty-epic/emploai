import logging
import os
import asyncio
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from telegram import Update
from telegram.constants import ParseMode, ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# DIRECT CONNECTION TO THE BRAIN 🧠
from single_agent.agent import SingleAgent

# ======================================================================================
# 🔒 CONFIGURATION
# ======================================================================================
BOT_TOKEN = "<TELEGRAM_BOT_TOKEN>"
ALLOWED_USER_ID = 8562474049
# ======================================================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global Agent Instance
# We will initialize it lazily or here.
# Note: SingleAgent expects GEMINI_API_KEY env var
agent_instance = None
current_chat_id = None

async def send_log_to_telegram(app: Application, message: str):
    """
    Callback used by SingleAgent to stream logs/thoughts to Telegram.
    We use a 'raw' send because we might be in a different thread context.
    """
    if not current_chat_id:
        return

    # Filter out boring logs if needed, or format them nice
    if "Turn" in message:
        valid_msg = f"🔄 **{message.strip()}**"
    elif "[TOOL]" in message:
        valid_msg = f"🛠️ `{message.strip()}`"
    elif "[RESULT]" in message:
        # truncate long results
        clean = message.replace("[RESULT]", "").strip()
        if len(clean) > 200: clean = clean[:200] + "..."
        valid_msg = f"✅ `{clean}`"
    elif "[ERROR]" in message:
        valid_msg = f"❌ {message}"
    elif "[COMPLETE]" in message:
        valid_msg = f"🏁 **{message.replace('[COMPLETE]', '').strip()}**"
    else:
        # Generic thought or log
        valid_msg = message

    try:
        # We need to schedule this coroutine in the main loop
        await app.bot.send_message(chat_id=current_chat_id, text=valid_msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        # Fallback for parse errors
        try:
             await app.bot.send_message(chat_id=current_chat_id, text=valid_msg)
        except:
             pass

def agent_logger_bridge(app_loop, app):
    """Factory to create a logger function that pushes to Telegram via the event loop."""
    def logger_func(text: str):
        # This function runs in the Agent's thread. 
        # We must fire-and-forget a task to the main asyncio loop.
        print(f"[AGENT] {text}")
        if current_chat_id:
            asyncio.run_coroutine_threadsafe(send_log_to_telegram(app, text), app_loop)
    return logger_func

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_chat_id, agent_instance
    user = update.effective_user
    if user.id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return
    
    current_chat_id = user.id
    
    # Initialize Agent with the Telegram Logger Bridge
    loop = asyncio.get_running_loop()
    bridge = agent_logger_bridge(loop, context.application)
    
    agent_instance = SingleAgent(logger=bridge)
    
    await update.message.reply_text(
        "🧠 **SingleAgent Connected**\n"
        "I am directly connected to the SingleAgent core.\n"
        "Model: Gemini 3 (Default)\n"
        "Tools: Full Browser & Desktop Automation.\n\n"
        "Give me a task!", 
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_chat_id, agent_instance
    user = update.effective_user
    if user.id != ALLOWED_USER_ID:
        return

    current_chat_id = user.id
    task_text = update.message.text
    
    # Helper to send messages safely (fallback to plain text if Markdown fails)
    async def safe_reply(text):
        try:
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            # Fallback: Send as plain text if Markdown parsing fails
            await update.message.reply_text(text)

    if not agent_instance:
         # Lazy Init
        loop = asyncio.get_running_loop()
        bridge = agent_logger_bridge(loop, context.application)
        agent_instance = SingleAgent(logger=bridge)

    await safe_reply(f"🚀 **Starting Task:** {task_text}")
    await context.bot.send_chat_action(chat_id=user.id, action=ChatAction.TYPING)

    # Run the blocking agent.run() in a separate thread to not freeze the bot
    loop = asyncio.get_running_loop()
    
    # Check if we should continue or start new
    # Simple logic: If user says "continue", we call continue_task
    result = ""
    try:
        if task_text.lower().strip() == "continue":
            result = await loop.run_in_executor(None, lambda: agent_instance.continue_task(max_turns=100))
        else:
            result = await loop.run_in_executor(None, lambda: agent_instance.run(task_text, max_turns=100))
    except Exception as e:
        result = f"🔥 CRITICAL ERROR: {str(e)}"
    
    await safe_reply(f"🏁 **Finished**\n{result}")

def main():
    print("🤖 Telegram SingleAgent Starting...")
    logging.info(f"Bot Token: {BOT_TOKEN[:10]}...")
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.run_polling()

if __name__ == "__main__":
    main()
