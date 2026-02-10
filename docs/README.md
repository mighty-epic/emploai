# EmploAI

An AI-powered personal assistant that runs on your computer. Control it through **Telegram** or a **terminal CLI** — it can write code, browse the web, automate desktop apps, manage files, run terminal commands, and more.

---

## What Can It Do?

### 💻 Codebase & System
- Read, write, and edit files in your workspace
- Execute shell commands and manage terminal processes
- Search for files and text patterns across your project
- Run builds, tests, and scripts

### 🌐 Web Browsing (Selenium)
- Open Chrome and navigate to any URL
- Click, type, scroll, and interact with web elements
- Switch between tabs, go back/forward
- Extract page content and interactive elements

### 🖥️ Desktop Automation
- **Vision**: Capture screenshots, describe screen content, OCR text extraction
- **Input**: Simulate mouse clicks, keyboard typing, hotkeys, scroll, drag-and-drop
- **Window Management**: List, focus, minimize, maximize, close applications
- **App Control**: Open any application, interact with desktop UI

### 🧠 AI & Memory
- Multi-provider LLM support (OpenAI, Anthropic, Google Gemini, xAI, DeepSeek, OpenRouter)
- Persistent memory across sessions
- Skill system for specialized tasks
- Context-aware conversations with smart summarization

---

## Interfaces

### Telegram Bot (Primary)
The main way to use EmploAI. Chat with your bot in Telegram to get things done.

- **Entry point**: `telegram_bot/telegram_agent.py`
- **Setup guide**: [`telegram_bot/SETUP.md`](../telegram_bot/SETUP.md)
- 30+ slash commands for model selection, task automation, session management, and more
- Inline button UI for interactive controls
- File upload support (images, PDFs, documents)

### CLI / TUI (Terminal)
A Textual-based terminal UI for local use.

- **Entry point**: `cli/__main__.py`
- Rich terminal interface with command palette, session switcher, and message styling
- Same agent capabilities as the Telegram bot

---

## Supported Models

| Provider | Models |
|---|---|
| **OpenAI** | GPT-5, GPT-5.1, GPT-5.2, GPT-5.1-Codex-Max, GPT-5.2-Codex, GPT-4.1, GPT-4o, GPT-4o-mini |
| **Anthropic** | Claude Sonnet 4.5, Claude Opus 4.5, Claude Haiku 4.5, Claude Sonnet 4, Claude Opus 4, Claude Haiku 4 |
| **Google** | Gemini 3 Pro, Gemini 3 Flash, Gemini 2.5 Pro, Gemini 2.5 Flash, Gemini 2.0 Flash, Gemini 1.5 Pro |
| **xAI** | Grok 4.1 Fast, Grok Code Fast, Grok 4, Grok 3, Grok 2 |
| **DeepSeek** | DeepSeek Chat, DeepSeek Reasoner |
| **OpenRouter** | Any model routed through OpenRouter |

> **Note:** OpenAI and Anthropic models are fully production-tested across all agent modes. Other providers are available but may have limited mode support.

---

## Project Structure

```
emploai/
├── telegram_bot/          # Telegram bot interface (main entry point)
│   ├── telegram_agent.py  # Bot launcher
│   ├── telegram_app.py    # Handler registration & polling
│   ├── telegram_session_state.py  # Per-user state management
│   ├── telegram_unified_agent.py  # Tool executor bridge (30+ tools)
│   ├── telegram_chat_flow.py      # Chat message execution flow
│   ├── telegram_task_flow.py      # Task execution flow
│   ├── telegram_commands_*.py     # Slash command handlers
│   ├── telegram_callback_handlers.py  # Inline button handlers
│   ├── telegram_messaging.py     # Safe message send/edit helpers
│   └── SETUP.md                  # Beta tester setup guide
│
├── cli/                   # Terminal UI (Textual TUI)
│   ├── __main__.py        # CLI entry point
│   ├── tui_app.py         # Terminal UI application
│   └── tui_constants.py   # Model configs, prompts, constants
│
├── shared/                # Core shared infrastructure
│   ├── unified_agent.py   # UnifiedAgent — provider-agnostic LLM orchestrator
│   ├── memory.py          # Persistent memory with keyword search
│   ├── context_loader.py  # System prompt context builder
│   ├── skills_enhanced.py # Skill loading & matching
│   ├── session_types.py   # Session lifecycle management
│   ├── live_config.py     # Hot-reloadable configuration
│   ├── heartbeat.py       # Agent health/announcement system
│   └── agents/            # Provider-specific agent implementations
│       ├── base.py        # Abstract base agent class
│       ├── anthropic_agent.py
│       ├── openai_agent.py
│       └── google_agent.py
│
├── bot_core/              # Bot support modules
│   ├── security.py        # Auth, rate limiting, input validation
│   ├── ui_helpers.py      # Message formatting, inline keyboards
│   ├── file_processor.py  # Image/PDF/DOCX/XLSX processing
│   ├── hooks.py           # Extensible event system
│   └── analytics.py       # Usage tracking & statistics
│
├── single_agent/          # Full agent with browser, spawn, scheduling
│   ├── refined_agent.py   # RefinedAgent (browser + desktop + spawn)
│   ├── browser_tool.py    # Selenium browser wrapper
│   ├── cron_scheduler.py  # Recurring task scheduler
│   └── spawn_tool.py      # Sub-agent spawning
│
├── skills/                # Loadable skill modules
│   ├── web-search/        # Web search skill
│   ├── file-ops/          # File operations skill
│   ├── ai-doc-scraper.skill  # Documentation scraper
│   ├── skill-creator/     # Skill creation tool
│   └── mobile-developer/  # Mobile development skill
│
├── .env.example           # Environment variable template
└── requirements.txt       # Python dependencies
```

---

## Quick Start

### Telegram Bot

See the full setup guide: **[`telegram_bot/SETUP.md`](../telegram_bot/SETUP.md)**

Short version:
1. Install prerequisites (Python 3.10+, Chrome, Tesseract OCR)
2. `pip install -r requirements.txt`
3. Create a bot via `@BotFather` on Telegram
4. Copy `.env.example` → `.env` and fill in your tokens/keys
5. `cd telegram_bot && python telegram_agent.py`

### CLI
```bash
cd cli
python __main__.py
```

---

## Agent Modes

EmploAI supports three operating modes, configurable via `/mode` (Telegram) or `/mode` (CLI):

| Mode | Description |
|---|---|
| **Manual** | Chat agent and task agent are completely isolated — no context sharing |
| **Semi** | Partial sync via intelligent summaries between agents |
| **Auto** | Unified agent with all tools merged (CLI + browser + desktop) |

---

## Beta Mode

For beta testers, set `BETA_MODE=true` in your `.env` file. This restricts expensive Anthropic models (Sonnet, Opus) — only Claude Haiku is available. All other providers remain unrestricted. This keeps API costs manageable.

---

## Security

- **User authorization**: Only Telegram user IDs listed in `ALLOWED_USER_IDS` can interact with the bot
- **Rate limiting**: Configurable per-minute and per-hour limits per command
- **Input validation**: Sanitization of user input and path traversal protection
- **Audit logging**: Security events are logged for monitoring

---

## Development Status

🚧 **Active Development** — The Telegram bot and CLI are fully functional. New skills and model support are being added regularly.
