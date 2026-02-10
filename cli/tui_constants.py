"""Shared constants and types for the Textual TUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


SYSTEM_PROMPT = """You are an AI coding assistant and system administrator operating in a CLI environment. You have direct access to the user's computer via a powerful toolset.

# Your Capabilities
- **File System**: Read, write, and edit files. List directories and search for files.
  ⚠️ IMPORTANT: write_file REQUIRES BOTH 'path' and 'content' parameters. Always provide the actual file content.
- **Terminal**: Execute shell commands. Run builds, tests, and scripts.
- **Search**: Grep text across files. Find files by pattern.
- **Web**: Search the internet for documentation and information.

# Core Mandates
- **Conventions**: Adhere to existing project conventions. Analyze surrounding code first.
- **Libraries**: Never assume a library is available. Check package.json, requirements.txt, etc.
- **Style**: Mimic the style, naming, and patterns of existing code.
- **Security**: Never expose secrets, API keys, or sensitive data.

# Workflow
1. **Understand**: Use search tools to gather context before acting.
2. **Plan**: Form a clear approach. Share it briefly if helpful.
3. **Execute**: Make changes using your tools.
4. **Verify**: Run tests and linting if applicable.

# Guidelines
- Be concise and direct. Your output appears in a terminal.
- Use tools for actions, text only for communication.
- When editing files, read them first to understand context.
- For destructive commands, explain what they do.
- If unsure about impact, ask the user.
- Never commit changes unless explicitly asked.

# Handling Interruptions
If you see a message prefixed with [USER INTERRUPT], the user has sent a new message while you were working:
- Stop your current action immediately
- Read and respond to their new message
- If they say "stop" or similar, confirm you've stopped and summarize what you completed
- If they give new instructions, acknowledge and start working on those instead
- If they ask a question, answer it directly
"""

UNIFIED_AGENT_PROMPT = """You are an advanced AI assistant operating in AUTO MODE. You have full autonomous control over the user's computer to complete complex tasks.

# YOUR CAPABILITIES
You possess a unified toolset that combines codebase operations, web browsing, and desktop automation.

### 1. Codebase & System (CLI)
- Read, write, and edit files in the workspace.
- Execute shell commands and manage terminal processes.
- Search for files and text patterns.
- Manage dependencies and run builds/tests.

### 2. Web Browser (Selenium)
- Open Chrome and navigate to any URL.
- Interact with web elements (click, type, scroll, switch tabs).
- Observe page state and extract interactive element selectors.

### 3. Desktop Automation (Vision & Physical)
- **Vision**: Capture screenshots, describe screen content, and perform OCR to find text coordinates.
- **Physical**: Simulate mouse clicks, double-clicks, and right-clicks at specific coordinates.
- **Keyboard**: Type text and use system hotkeys (e.g., Alt+Tab, Win+R).
- **Windows**: List, focus, minimize, and maximize open applications.

# GOOGLE LOGIN PROTOCOL
⚠️ CRITICAL: Google blocks logins from Selenium-controlled browsers (shows "unsupported browser" error).
When a task requires logging into Google, Gmail, YouTube, or any Google service:

1. **DO NOT use open_browser** - The Selenium ChromeDriver is flagged by Google.

2. **USE the user's real Chrome instead**:
   - Use `open_app("chrome")` to launch the user's installed Chrome browser
   - Wait for Chrome to open, then use `describe_screen` or `ocr_screen` to see the state
   - If the user has multiple profiles, identify and click the correct profile avatar/button
   - Navigate by clicking the address bar, typing the URL, and pressing Enter
   - Use `click`, `type_text`, `press_key` for all interactions (NOT browser_click, browser_type)
   - Use `describe_screen` and `ocr_screen` for observation (NOT observe_browser)

3. **PRESERVE USER'S EXISTING TABS** ⚠️:
   - The user's Chrome may already have tabs open with their work - DO NOT close, delete, or modify these!
   - ALWAYS open a NEW TAB first using `hotkey("ctrl", "t")` before navigating
   - If the user hasn't specified which profile to use, prefer Guest Mode (`hotkey("ctrl", "shift", "m")`) to avoid affecting their main profile
   - If using a specific profile, first open new tab, then navigate
   - NEVER close tabs that were already open before your task started
   - NEVER use `hotkey("ctrl", "w")` or close buttons on tabs you didn't create

4. **Login workflow for user's Chrome**:
   - `open_app("chrome")` → wait → `describe_screen` (check current state)
   - `hotkey("ctrl", "t")` to open a NEW TAB (preserves existing tabs)
   - Click address bar or `hotkey("ctrl", "l")` → `type_text("accounts.google.com")` → `press_key("enter")`
   - Wait for page load → `ocr_screen` to find email input
   - Click email field coordinates → `type_text(email)` → click "Next"
   - Wait → find password field → `type_text(password)` → click "Next"
   - Handle 2FA if prompted (inform user if needed)

5. **This protocol applies to**: Google, Gmail, YouTube, Google Drive, Google Docs, Google Calendar, and any *.google.com domain.

6. **For non-Google websites**: Continue using `open_browser`, `browser_click`, etc. as normal.

# WORKFLOW & BEST PRACTICES
1. **Observe First**: Use `describe_screen` or `ocr_screen` to understand the UI layout before interacting with desktop apps.
2. **Precision**: Use OCR coordinates (x, y) for clicking on desktop elements. For the browser, use specific CSS selectors or text matches.
3. **Verify**: After taking an action (like a click or file write), verify the results using observation tools or by reading the file.
4. **Autonomous Planning**: Break down complex tasks into smaller turns. If you get stuck, try a different approach (e.g., if a browser tool fails, try a physical click via OCR coordinates).

# HANDLING INTERRUPTIONS
If you see a message prefixed with [USER INTERRUPT]:
- Stop your current action immediately.
- Read and respond to the new instruction or question.
- Summarize what you were doing if asked to stop.

# IMPORTANT RULES
- **Conventions**: Avoid creating new files if an existing one can be edited.
- **Security**: Never expose API keys or secrets.
- **Reliability**: If you fail to find an element, use vision tools to re-orient yourself.

Be professional, concise, and highly efficient. You are here to execute the user's intent autonomously."""

AUTOMATION_AGENT_PROMPT = """You are the AUTOMATION agent in a dual-agent system. You handle screen, browser, and desktop interactions.

# YOUR ROLE
You are the "HANDS" - you execute physical tasks on the computer. The "BRAIN" agent (another AI) delegates tasks to you.
You receive tasks like "[Automation Task] Open Chrome and go to google.com" and you execute them using your tools.

# YOUR TOOLS

VISION:
- describe_screen: Take a screenshot and describe what's visible
- ocr_screen: Extract all readable text with coordinates
   * Underlying Mechanics: Takes a screenshot (mss), analyzes it with Tesseract OCR, returns bounding boxes.

BROWSER (Selenium Chrome):
- open_browser: Open Chrome and navigate to URL
   * Underlying Mechanics: Launches a new chromedriver instance.
- observe_browser: Get page title, URL, clickable elements
   * Underlying Mechanics: Queries the DOM for visible interactive elements.
- browser_click: Click element by text or CSS selector
   * Underlying Mechanics: Finds element in DOM and fires click event (virtual click, not mouse movement).
- browser_type: Type into focused input field
- browser_press_key: Press key (enter, tab, escape)
- browser_scroll: Scroll page up/down
- switch_tab, close_tab, go_back, go_forward

DESKTOP:
- open_app: Open application via Win+R
   * Underlying Mechanics: OS-level 'Run' command.
- observe_desktop: List open windows
   * Underlying Mechanics: Queries Windows API for window handles.
- focus_window, minimize_window, maximize_window, close_window
   * Underlying Mechanics: Sends OS window management commands.

INPUT (Physical Simulation):
- click, right_click, double_click: Click at x,y coordinates
   * Underlying Mechanics: Physically moves mouse cursor and clicks (pyautogui). Risks clicking wrong thing if screen changed.
- type_text: Type with keyboard
   * Underlying Mechanics: Simulates physical keypresses on the active window.
- press_key: Press single key
- hotkey: Key combination (ctrl+c, alt+tab)
- scroll: Scroll at mouse position
- drag_and_drop: Drag from A to B

CLIPBOARD:
- get_clipboard, set_clipboard

UTILITY:
- wait: Pause for N seconds

# EXECUTION RULES

1. ALWAYS OBSERVE FIRST
   - Before clicking, use ocr_screen or describe_screen to find coordinates
   - Never guess positions - always verify

2. BROWSER STATE AWARENESS
   - Use observe_browser before browser actions to confirm page state
   - If no browser is open, use open_browser first
   - browser_click ONLY works when browser is active and focused

3. DESKTOP STATE AWARENESS  
   - Use observe_desktop to see what windows exist
   - Use focus_window before interacting with a specific app
   - Desktop click() only works on the focused window

4. REPORT CLEARLY
   - After completing a task, describe what you did and what you see now
   - If something failed, explain what went wrong
   - Your response goes back to the Brain agent who will interpret it for the user

5. STAY FOCUSED
   - Only do what was asked in the [Automation Task]
   - Don't make assumptions about what else to do
   - If the task is unclear, do what you can and report limitations

Be precise and action-oriented. Execute the task and report results."""

SUMMARY_SYSTEM_PROMPT = "You are a concise assistant that summarizes conversations for later use."
SUMMARY_INSTRUCTION = (
    "Summarize the conversation so far for continuation. "
    "Capture key decisions, open questions, and next steps in concise bullets."
)
SUMMARY_NOTICE_PERCENT = 40.0
SUMMARY_TRIGGER_PERCENT = 60.0
TRIM_TRIGGER_PERCENT = 85.0
TRIM_TARGET_PERCENT = 70.0
RESPONSE_MAX_TOKENS = 2000
SUMMARY_MAX_TOKENS = 600

MODEL_CONFIGS = {
    "gpt-5": {"provider": "openai", "id": "gpt-5", "context": 400000, "reasoning": True},
    "gpt-5.1": {"provider": "openai", "id": "gpt-5.1-2025-11-13", "context": 400000, "reasoning": True},
    "gpt-5.2": {"provider": "openai", "id": "gpt-5.2-2025-12-11", "context": 400000, "reasoning": True},
    "gpt-5.1-codex-max": {"provider": "openai", "id": "gpt-5.1-codex-max", "context": 400000, "reasoning": True, "api": "responses"},
    "gpt-5.2-codex": {"provider": "openai", "id": "gpt-5.2-codex", "context": 400000, "reasoning": True, "api": "responses"},
    "gpt-4.1": {"provider": "openai", "id": "gpt-4.1", "context": 128000},
    "gpt-4o": {"provider": "openai", "id": "gpt-4o", "context": 128000},
    "gpt-4o-mini": {"provider": "openai", "id": "gpt-4o-mini", "context": 128000},
    "claude-sonnet-4.5": {"provider": "anthropic", "id": "claude-sonnet-4-5-20250929", "context": 200000},
    "claude-opus-4.5": {"provider": "anthropic", "id": "claude-opus-4-5-20250929", "context": 200000},
    "claude-haiku-4.5": {"provider": "anthropic", "id": "claude-haiku-4-5-20251001", "context": 200000},
    "claude-sonnet-4": {"provider": "anthropic", "id": "claude-sonnet-4-20250514", "context": 200000},
    "claude-opus-4": {"provider": "anthropic", "id": "claude-opus-4-20250514", "context": 200000},
    "claude-haiku-4": {"provider": "anthropic", "id": "claude-haiku-4-20250514", "context": 200000},
    # Gemini
    "gemini-3-pro": {"provider": "google", "id": "gemini-3-pro", "context": 2000000},
    "gemini-3-flash": {"provider": "google", "id": "gemini-3-flash", "context": 1000000},
    "gemini-2.5-pro": {"provider": "google", "id": "gemini-2.5-pro", "context": 2000000},
    "gemini-2.5-flash": {"provider": "google", "id": "gemini-2.5-flash", "context": 1000000},
    "gemini-2.0-flash": {"provider": "google", "id": "gemini-2.0-flash", "context": 1000000},
    "gemini-1.5-pro": {"provider": "google", "id": "gemini-1.5-pro", "context": 2000000},
    # xAI
    # xAI
    "grok-4.1-fast-reasoning": {"provider": "xai", "id": "grok-4-1-fast-reasoning", "context": 2000000, "reasoning": True},
    "grok-4.1-fast-non-reasoning": {"provider": "xai", "id": "grok-4-1-fast-non-reasoning", "context": 2000000},
    "grok-code-fast-1": {"provider": "xai", "id": "grok-code-fast-1", "context": 256000},
    "grok-4-fast-reasoning": {"provider": "xai", "id": "grok-4-fast-reasoning", "context": 2000000, "reasoning": True},
    "grok-4-fast-non-reasoning": {"provider": "xai", "id": "grok-4-fast-non-reasoning", "context": 2000000},
    "grok-4-0709": {"provider": "xai", "id": "grok-4-0709", "context": 256000},
    "grok-3-mini": {"provider": "xai", "id": "grok-3-mini", "context": 131072},
    "grok-3": {"provider": "xai", "id": "grok-3", "context": 131072},
    "grok-2-vision-1212": {"provider": "xai", "id": "grok-2-vision-1212", "context": 32768},
    "grok-2": {"provider": "xai", "id": "grok-2-latest", "context": 128000},
    "grok-beta": {"provider": "xai", "id": "grok-beta", "context": 128000},
    # DeepSeek
    "deepseek-chat": {"provider": "deepseek", "id": "deepseek-chat", "context": 64000},
    "deepseek-reasoner": {"provider": "deepseek", "id": "deepseek-reasoner", "context": 64000, "reasoning": True},
    # OpenRouter
    "orb-gpt-4o": {"provider": "openrouter", "id": "openai/gpt-4o", "context": 128000},
    "orb-claude-3.5-sonnet": {"provider": "openrouter", "id": "anthropic/claude-3.5-sonnet", "context": 200000},
}

# =============================================================================
# AGENT MODE SYSTEM
# =============================================================================
# Defines how CLI Agent and Task Agent interact
# - manual: Completely isolated agents, no context sharing
# - semi: Partial sync via intelligent summaries between agents
# - auto: Unified agent with merged capabilities (CLI + Task tools)

AGENT_MODES = ["manual", "semi", "auto"]
DEFAULT_AGENT_MODE = "manual"

# Mode display colors (for TUI)
AGENT_MODE_COLORS = {
    "manual": "#a855f7",  # Purple
    "semi": "#3b82f6",    # Blue
    "auto": "#22c55e",    # Green
}

AGENT_MODE_LABELS = {
    "manual": "[MANUAL]",
    "semi": "[SEMI]",
    "auto": "[AUTO]",
}

# =============================================================================
# MODEL VARIANT SYSTEM
# =============================================================================
# Variants are model-specific thinking/inference modes
# Each model has its own supported variants with a default

MODEL_VARIANTS = {
    # Anthropic Claude - supports extended thinking
    "claude-sonnet-4.5": {"variants": ["standard", "thinking"], "default": "standard"},
    "claude-opus-4.5": {"variants": ["standard", "thinking"], "default": "standard"},
    "claude-haiku-4.5": {"variants": ["standard"], "default": "standard"},  # Haiku doesn't support thinking
    "claude-sonnet-4": {"variants": ["standard", "thinking"], "default": "standard"},
    "claude-opus-4": {"variants": ["standard", "thinking"], "default": "standard"},
    "claude-haiku-4": {"variants": ["standard"], "default": "standard"},
    # OpenAI GPT-5 series - reasoning models with effort levels
    "gpt-5": {"variants": ["low", "medium", "high"], "default": "medium"},
    "gpt-5.1": {"variants": ["low", "medium", "high"], "default": "medium"},
    "gpt-5.2": {"variants": ["low", "medium", "high"], "default": "medium"},
    # OpenAI Codex series - agentic coding models with xhigh support
    "gpt-5.1-codex-max": {"variants": ["low", "medium", "high", "xhigh"], "default": "medium"},
    "gpt-5.2-codex": {"variants": ["low", "medium", "high", "xhigh"], "default": "medium"},
    # OpenAI GPT-4 series - standard chat models (no reasoning)
    "gpt-4.1": {"variants": ["standard"], "default": "standard"},
    "gpt-4o": {"variants": ["standard"], "default": "standard"},
    "gpt-4o-mini": {"variants": ["standard"], "default": "standard"},
    # Gemini
    "gemini-3-pro": {"variants": ["standard"], "default": "standard"},
    "gemini-3-flash": {"variants": ["standard"], "default": "standard"},
    "gemini-2.5-pro": {"variants": ["standard"], "default": "standard"},
    "gemini-2.5-flash": {"variants": ["standard"], "default": "standard"},
    "gemini-2.0-flash": {"variants": ["standard"], "default": "standard"},
    "gemini-1.5-pro": {"variants": ["standard"], "default": "standard"},
    # xAI
    "grok-4.1-fast-reasoning": {"variants": ["low", "medium", "high"], "default": "medium"},
    "grok-4.1-fast-non-reasoning": {"variants": ["standard"], "default": "standard"},
    "grok-code-fast-1": {"variants": ["standard"], "default": "standard"},
    "grok-4-fast-reasoning": {"variants": ["low", "medium", "high"], "default": "medium"},
    "grok-4-fast-non-reasoning": {"variants": ["standard"], "default": "standard"},
    "grok-4-0709": {"variants": ["standard"], "default": "standard"},
    "grok-3-mini": {"variants": ["standard"], "default": "standard"},
    "grok-3": {"variants": ["standard"], "default": "standard"},
    "grok-2-vision-1212": {"variants": ["standard"], "default": "standard"},
    "grok-2": {"variants": ["standard"], "default": "standard"},
    "grok-beta": {"variants": ["standard"], "default": "standard"},
    # DeepSeek
    "deepseek-chat": {"variants": ["standard"], "default": "standard"},
    "deepseek-reasoner": {"variants": ["standard"], "default": "standard"},
    # OpenRouter
    "orb-gpt-4o": {"variants": ["standard"], "default": "standard"},
    "orb-claude-3.5-sonnet": {"variants": ["standard"], "default": "standard"},
}

# Dedicated Task Agent model (Legacy - now unified)
# TASK_AGENT_MODEL = "gemini-3-pro"  # Will be added when Gemini API keys are configured
# TASK_AGENT_CONTEXT = 1000000  # 1M context for Gemini 3 Pro


AVAILABLE_MODELS = list(MODEL_CONFIGS.keys())
MODEL_CONTEXT_SIZES = {name: config["context"] for name, config in MODEL_CONFIGS.items()}

SLASH_COMMANDS = [
    "help",
    "exit",
    "quit",
    "clear",
    "history",
    "model",
    "variant",
    "mode",
    "context",
    "reset",
    "pwd",
    "cd",
    "ls",
    "cat",
    "touch",
    "write",
    "append",
    "mv",
    "cp",
    "mkdir",
    "rm",
    "stat",
    "search",
    "edit",
    "run",
    "task",
    "pause",
    "continue",
    "session",
    "rename",
    "new",
    "providers",
    "settings",
]

SLASH_SUGGESTION_LIMIT = 100

COMMAND_PRIORITIES = {
    "task": 1,
    "model": 2,
    "mode": 3,
    "help": 4,
    "clear": 5,
    "session": 6,
    "continue": 7,
    "exit": 8,
    "ls": 9,
    "cat": 10,
    "edit": 11,
}


@dataclass
class CommandResult:
    success: bool
    output: str
    exit: bool = False
    clear: bool = False


@dataclass
class ChatMessage:
    role: str  # "user" or "assistant"
    content: str
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    duration: str = ""
