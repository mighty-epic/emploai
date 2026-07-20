import asyncio
import logging
import os
from collections import deque
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from shared.subprocess_utils import hidden_subprocess_kwargs

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def _allowed_user_id() -> int | None:
    raw = os.getenv("ALLOWED_USER_ID", "").strip() or os.getenv("ALLOWED_USER_IDS", "").strip()
    first = raw.split(",", 1)[0].strip()
    if not first:
        return None
    try:
        return int(first)
    except ValueError:
        return None


ALLOWED_USER_ID = _allowed_user_id()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

class ShellSession:
    """
    Manages a persistent subprocess (PowerShell/CMD).
    """
    def __init__(self):
        self.process = None
        self.output_queue = asyncio.Queue()

    async def start(self):
        """Starts the persistent PowerShell process."""
        # Detect functionality for 'powershell' (Windows standard)
        shell_cmd = "powershell"
        
        try:
            self.process = await asyncio.create_subprocess_exec(
                shell_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **hidden_subprocess_kwargs(),
            )
            logger.info(f"Shell process ({shell_cmd}) started with PID {self.process.pid}.")
            
            # Start background tasks to read stdout/stderr simultaneously
            asyncio.create_task(self._read_stream(self.process.stdout))
            asyncio.create_task(self._read_stream(self.process.stderr))
            
            return True
        except Exception as e:
            logger.error(f"Failed to start shell: {e}")
            return False

    async def _read_stream(self, stream):
        """Continually reads from a stream and puts lines into the queue."""
        while True:
            line = await stream.readline()
            if line:
                # Decode bytes to string
                try:
                    decoded = line.decode('utf-8', errors='replace') # cp1252 might be needed for older windows, but utf-8 is safer default
                except Exception:
                    decoded = str(line)
                
                # Print to local console so user sees what is happening
                print(decoded, end="")

                await self.output_queue.put(decoded)
            else:
                break

    async def write(self, text: str):
        """Writes text to the shell's stdin."""
        if self.process and self.process.stdin:
            try:
                # Append newline to simulate pressing Enter
                input_data = text + "\n"
                self.process.stdin.write(input_data.encode('utf-8'))
                await self.process.stdin.drain()
            except Exception as e:
                logger.error(f"Failed to write to shell: {e}")

# Global shell instance
shell = ShellSession()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the command /start is issued."""
    user = update.effective_user
    
    # SECURITY CHECK
    if ALLOWED_USER_ID is None or user.id != ALLOWED_USER_ID:
        logger.warning(f"Unauthorized access attempt by User ID: {user.id}")
        await update.message.reply_text(f"⛔ Unauthorized access. Your ID: {user.id}")
        return

    # Start the shell if not already started
    if shell.process is None:
        success = await shell.start()
        if success:
            # Start the output flusher job for this specific chat
            # We run it every 1.0 seconds to batch output
            context.job_queue.run_repeating(flush_output, interval=1.0, data=update.effective_chat.id, name=str(update.effective_chat.id))
            await update.message.reply_html(
                f"👋 <b>Connected to Terminal.</b>\n"
                f"Session started. Type commands to execute them."
            )
        else:
            await update.message.reply_text("❌ Failed to start PowerShell process.")
    else:
        await update.message.reply_text("✅ Shell is already active.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Passes the user message to the shell input."""
    user = update.effective_user
    if ALLOWED_USER_ID is None or user.id != ALLOWED_USER_ID:
        return

    text = update.message.text
    
    if shell.process is None:
        await update.message.reply_text("⚠ Shell not active. Send /start to begin.")
        return

    # Send command to shell
    await shell.write(text)

async def flush_output(context: ContextTypes.DEFAULT_TYPE):
    """
    Periodically checks the output queue and sends batched messages to Telegram.
    This prevents flooding the chat with one message per line.
    """
    chat_id = context.job.data
    lines = []
    
    # Collect available lines (up to 20 at a time to keep it snappy)
    try:
        while not shell.output_queue.empty():
            lines.append(shell.output_queue.get_nowait())
            if len(lines) >= 15: 
                break
    except asyncio.QueueEmpty:
        pass

    if lines:
        text_block = "".join(lines)
        
        # Telegram limit is 4096 chars.
        if len(text_block) > 4000:
             text_block = text_block[:4000] + "\n... (truncated)"
        
        # Send as code block for formatting
        try:
            # We wrap in ``` to preserve monospaced terminal look
            await context.bot.send_message(
                chat_id=chat_id, 
                text=f"```\n{text_block}\n```", 
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            # Sometimes markdown parsing fails on special chars, fallback to plain text if needed
            logger.error(f"Markdown send failed: {e}. Retrying plain.")
            try:
                await context.bot.send_message(chat_id=chat_id, text=text_block)
            except Exception as e2:
                 logger.error(f"Plain text send failed: {e2}")

def main() -> None:
    """Start the bot."""
    # Simple check for configuration
    if not BOT_TOKEN or ALLOWED_USER_ID is None:
        print("\n" + "="*60)
        print("CONFIGURATION REQUIRED")
        print("Set TELEGRAM_BOT_TOKEN and ALLOWED_USER_ID or ALLOWED_USER_IDS.")
        print("="*60 + "\n")
        return

    print("Bot starting...")
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is polling. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
