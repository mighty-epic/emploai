"""Shared constants and types for the Textual TUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


SYSTEM_PROMPT = """You are a powerful AI coding assistant and system administrator. You have direct access to the user's computer via a set of tools.

YOUR CAPABILITIES:
1. FILE SYSTEM: You can read, write, and edit files, list directories, and find files. You are restricted to the current workspace by default.
2. TERMINAL: You can run shell commands. For destructive commands, a user confirmation will be requested.
3. SEARCH: You can grep for text across files and search the codebase.
4. WEB: You can search the web for documentation or information using DuckDuckGo.

GUIDELINES:
- When asked to perform a task, use your tools to explore the environment and execute the solution.
- Before editing a file, read its content to understand the context.
- When running commands, prefer non-interactive flags (e.g., -y).
- If you're unsure about a command's impact, ask the user or use a 'dry-run' if available.
- Be concise in your explanations but thorough in your execution.
"""

UNIFIED_AGENT_PROMPT = """You are a Unified AI Agent with full control over the user's computer and codebase. You have been granted multi-layered toolsets to perform complex automation and development tasks.

YOUR CAPABILITIES:

1. CODEBASE & SYSTEM (Namespace: CODEBASE)
   - Read, write, and edit files in the workspace.
   - Run shell commands and manage background processes.
   - Search the codebase and search the web for documentation.

2. DESKTOP & UI (Namespace: COMPUTER)
   - Observe the screen and read text from windows.
   - Control the mouse and keyboard (click, type, drag, hotkeys).
   - Manage Windows applications (open, focus, minimize, close).

3. BROWSER (Namespace: BROWSER)
   - Open Chrome and navigate to any URL.
   - Fully interact with web elements (click, type, scroll, tabs).

STRATEGY:
- When a task involves both coding and testing/UI, use your codebase tools to implement and your desktop tools to verify.
- If you need to research how to use a library, use web_search or open_browser.
- Always observe before acting on the desktop to ensure you are clicking the right thing.
"""
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
    "gpt-5.1-codex-max": {"provider": "openai", "id": "gpt-5.1-codex-max", "context": 400000, "reasoning": True},
    "gpt-5.2-codex": {"provider": "openai", "id": "gpt-5.2-codex", "context": 400000, "reasoning": True},
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
    "gemini-2.0-flash": {"provider": "google", "id": "gemini-2.0-flash-exp", "context": 1000000},
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

# Dedicated Task Agent model (for semi/auto modes)
TASK_AGENT_MODEL = "gemini-3-pro"  # Will be added when Gemini API keys are configured
TASK_AGENT_CONTEXT = 1000000  # 1M context for Gemini 3 Pro


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
