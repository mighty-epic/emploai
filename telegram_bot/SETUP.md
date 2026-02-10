# EmploAI Telegram Agent — Setup Guide

> **For beta testers.** Follow every step below to get the Telegram agent running on your machine.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Clone the Repository](#2-clone-the-repository)
3. [Install Python Dependencies](#3-install-python-dependencies)
4. [Install System Dependencies](#4-install-system-dependencies)
5. [Create Your Telegram Bot](#5-create-your-telegram-bot)
6. [Get Your Telegram User ID](#6-get-your-telegram-user-id)
7. [Configure Environment Variables](#7-configure-environment-variables)
8. [Run the Bot](#8-run-the-bot)
9. [Available Commands](#9-available-commands)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Prerequisites

You need the following installed on your machine **before** starting:

| Requirement | Version | Check Command |
|---|---|---|
| **Python** | 3.10 or higher | `python --version` |
| **pip** | Latest | `pip --version` |
| **Git** | Any recent | `git --version` |
| **Google Chrome** | Latest stable | Needed for browser automation |
| **Tesseract OCR** | 5.x+ | `tesseract --version` |

### Installing Tesseract OCR

Tesseract is required for the OCR/vision tools (screen reading, text extraction).

**Windows:**
1. Download the installer from: https://github.com/UB-Mannheim/tesseract/wiki
2. Run the installer — **use the default install path** (`C:\Program Files\Tesseract-OCR`)
3. During installation, check the box for "Add to PATH" if available
4. If Tesseract is NOT on your PATH after installation, add it manually:
   - Open **System Properties** → **Environment Variables**
   - Under **System variables**, find `Path` and click **Edit**
   - Add: `C:\Program Files\Tesseract-OCR`
   - Click OK and restart your terminal
5. Verify: `tesseract --version`

**macOS:**
```bash
brew install tesseract
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt install tesseract-ocr
```

### Installing Google Chrome

Chrome is needed for Selenium-based browser automation (`/task` command, web browsing tools).

- Download from: https://www.google.com/chrome/
- Install normally. The bot uses ChromeDriver (auto-managed by `webdriver-manager`).

---

## 2. Clone the Repository

```bash
git clone https://github.com/<OWNER>/<REPO>.git
cd <REPO>/emploai
```

> Replace `<OWNER>/<REPO>` with the actual repository path you were given access to.

---

## 3. Install Python Dependencies

From the `emploai/` directory:

```bash
pip install -r requirements.txt
```

This installs everything: LLM clients (OpenAI, Anthropic, Google), Selenium, PyAutoGUI, Tesseract bindings, Telegram bot library, and more.

If you get errors on specific packages:

| Package | Issue | Fix |
|---|---|---|
| `pywinauto` | Windows-only | Safe to ignore on macOS/Linux |
| `pyautogui` | Needs display | Won't work on headless servers |
| `pytesseract` | Can't find Tesseract | Make sure Tesseract is installed and on PATH |
| `mss` | Screenshot fails | Needs a display (won't work on headless) |

You also need the `python-telegram-bot` package. If it's not in requirements.txt:
```bash
pip install python-telegram-bot[all]
```

---

## 4. Install System Dependencies

### ChromeDriver (Automatic)

ChromeDriver is managed automatically by `webdriver-manager`. No manual install needed — it downloads the correct version for your Chrome on first use.

### pyperclip (Clipboard)

For clipboard operations, `pyperclip` needs a clipboard mechanism:

**Windows:** Works out of the box.

**macOS:** Works out of the box.

**Linux:**
```bash
sudo apt install xclip
# or
sudo apt install xsel
```

---

## 5. Create Your Telegram Bot

You need your **own** Telegram bot. This takes ~2 minutes:

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Follow the prompts:
   - Give your bot a **name** (e.g., "My EmploAI Agent")
   - Give your bot a **username** (must end in `bot`, e.g., `my_emploai_bot`)
4. BotFather will give you a **Bot Token** — copy it. It looks like:
   ```
   <TELEGRAM_BOT_TOKEN>
   ```
5. **Save this token** — you'll need it for the `.env` file.

---

## 6. Get Your Telegram User ID

The bot only responds to authorized user IDs. To find yours:

1. Open Telegram and search for **@userinfobot**
2. Send it any message
3. It will reply with your **User ID** — a number like `8562474049`
4. **Save this ID** — you'll need it for the `.env` file.

---

## 7. Configure Environment Variables

1. In the `emploai/` directory, copy the example file:

   ```bash
   cp .env.example .env
   ```

   On Windows:
   ```cmd
   copy .env.example .env
   ```

2. Open `.env` in any text editor and fill in the values:

   ```env
   # === REQUIRED ===
   
   # Your bot token from @BotFather (Step 5)
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   
   # Your Telegram user ID from @userinfobot (Step 6)
   ALLOWED_USER_IDS=your_user_id_here
   
   # === API KEYS (provided to you separately) ===
   
   OPENAI_API_KEY=sk-proj-...
   ANTHROPIC_API_KEY=sk-ant-...
   XAI_API_KEY=xai-...
   GEMINI_API_KEY=AIza...
   DEEPSEEK_API_KEY=sk-...
   OPENROUTER_API_KEY=sk-or-...
   
   # === BETA MODE (leave as true) ===
   BETA_MODE=true
   
   # === OPTIONAL ===
   
   # Your workspace directory (where the bot can read/write files)
   # DEFAULT_WORKSPACE=C:\Users\YourName\Projects
   ```

3. **API keys will be provided to you separately** — paste them into the `.env` file.

> ⚠️ **Never share your `.env` file or commit it to Git.** It contains sensitive API keys.

---

## 8. Run the Bot

Navigate to the `telegram_bot/` directory and run:

```bash
cd telegram_bot
python telegram_agent.py
```

You should see output like:
```
Telegram CLI Agent Starting...
[OK] Bot commands menu registered
[INFO] Starting polling (dropping pending updates)...
```

Now open your bot in Telegram and send `/start`!

### Keeping it Running

The bot runs as long as the terminal is open. To run it in the background:

**Windows (PowerShell):**
```powershell
Start-Process python -ArgumentList "telegram_agent.py" -WindowStyle Hidden
```

**Linux/macOS:**
```bash
nohup python telegram_agent.py &
```

Or use `tmux`/`screen` for a persistent session.

---

## 9. Available Commands

Once the bot is running, these commands are available in Telegram:

### Core
| Command | Description |
|---|---|
| `/start` | Initialize the agent |
| `/help` | Show all commands |
| `/mode` | Set agent mode (manual/semi/auto) |
| `/variant` | Set model variant |
| `/model` | Switch AI model |
| `/models` | List all available models |
| `/settings` | Configure max turns |
| `/workspace` | Set workspace path |

### Tasks & Automation
| Command | Description |
|---|---|
| `/task <instruction>` | Run a multi-turn automation task |
| `/continue` | Resume a paused task |
| `/pause` | Pause a running task |
| `/stop` | Stop a running task |
| `/spawn <instruction>` | Spawn a parallel sub-agent |
| `/subagents` | List running sub-agents |
| `/schedule` | Schedule a recurring task |
| `/jobs` | List scheduled jobs |
| `/headless` | Toggle headless/headed browser |

### Sessions & Memory
| Command | Description |
|---|---|
| `/session` | Manage sessions |
| `/reset` | Clear chat history |
| `/context` | Show token usage |
| `/memory [query]` | Search/view memory |
| `/memory_update <note>` | Append to memory |
| `/forget` | Remove last user message |

### Utility
| Command | Description |
|---|---|
| `/monitor on\|off` | Toggle auto-reply |
| `/analytics` | Usage summary |
| `/history` | Conversation history |
| `/files` | Show pending files |
| `/skills` | List available skills |
| `/security` | Security status |
| `/config` | View/edit configuration |
| `/heartbeat` | Control heartbeat |

### How It Works

- **Default chat** (just type a message): Uses the CLI Agent with codebase tools — file operations, terminal commands, search, web browsing.
- **`/task` command**: Uses the unified agent for multi-turn browser/desktop automation.
- **`/mode`**: Controls how agents interact:
  - `manual` — Isolated agents, no context sharing
  - `semi` — Partial sync via summaries
  - `auto` — Unified agent with all tools merged

---

## 10. Troubleshooting

### Bot doesn't respond
- Make sure the bot is running in your terminal (check for errors)
- Make sure your `ALLOWED_USER_IDS` in `.env` matches your Telegram user ID
- Make sure your `TELEGRAM_BOT_TOKEN` is correct
- Try sending `/start` again

### "Unauthorized access" message
- Your Telegram user ID is not in `ALLOWED_USER_IDS`
- The bot shows your ID in the error message — add it to `.env` and restart

### Import errors / ModuleNotFoundError
- Make sure you ran `pip install -r requirements.txt` from the `emploai/` directory
- Make sure you're using Python 3.10+
- If `python-telegram-bot` is missing: `pip install python-telegram-bot[all]`

### Tesseract not found
- Install Tesseract OCR (see [Prerequisites](#1-prerequisites))
- Make sure it's on your PATH: `tesseract --version`
- On Windows: Default path is `C:\Program Files\Tesseract-OCR`

### Chrome/Browser errors
- Make sure Google Chrome is installed
- ChromeDriver is auto-managed — if issues persist, try: `pip install --upgrade webdriver-manager`
- For headless mode (no Chrome window): `/headless on` in the bot

### pyautogui errors on macOS
- Grant Terminal/IDE accessibility permissions:
  - **System Preferences** → **Security & Privacy** → **Privacy** → **Accessibility**
  - Add your terminal app (Terminal, iTerm2, VS Code, etc.)

### Rate limit exceeded
- Default: 30 requests/minute, 200/hour
- Adjust in `.env`: `MAX_REQUESTS_PER_MINUTE=60`

### Model not available
- If running in BETA_MODE, only cheap Anthropic models (Claude Haiku) are available
- All OpenAI, Gemini, xAI, DeepSeek, and OpenRouter models are unrestricted
- Check available models with `/models`

---

## Notes for Beta Testers

- **Please report bugs** — describe what you did, what you expected, and what happened. Include any error messages from the terminal.
- **The `/task` command** is the most powerful feature — it can browse the web, interact with desktop apps, read files, run terminal commands, and more.
- **BETA_MODE is enabled for you** — this means expensive Claude models (Sonnet, Opus) are not available to keep costs manageable. Claude Haiku and all OpenAI/other models work normally.
- **Your workspace** defaults to the current directory. Set it with `/workspace <path>` to point to your project folder for file operations.
