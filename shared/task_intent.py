from __future__ import annotations

import re


_CASUAL_EXACT = {
    "hi",
    "hello",
    "hey",
    "yo",
    "sup",
    "thanks",
    "thank you",
    "ok",
    "okay",
    "cool",
    "great",
    "nice",
    "good morning",
    "good afternoon",
    "good evening",
    "how are you",
    "are you there",
    "ping",
    "test",
}

_TASK_HINTS = (
    "open",
    "create",
    "run",
    "check",
    "look at",
    "look for",
    "look again",
    "find",
    "install",
    "fix",
    "debug",
    "describe",
    "show me",
    "check the screen",
    "tell me what you see",
    "what do you see",
    "what do you see now",
    "what do you see visually",
    "what's on the screen",
    "whats on the screen",
    "what changed",
    "how about now",
    "what about now",
    "take a screenshot",
    "read",
    "edit",
    "write",
    "delete",
    "switch",
    "send",
    "click",
    "type",
    "focus",
    "navigate",
)

_SCREEN_OBSERVATION_HINTS = (
    "what do you see",
    "what do you see now",
    "what do you see visually",
    "what do you notice",
    "what's on the screen",
    "whats on the screen",
    "what changed",
    "look again",
    "check the screen",
    "check the desktop",
    "look at the screen",
    "look at the desktop",
    "visually",
    "see meaning vision",
    "how about now",
    "what about now",
)

_SCREEN_CONTEXT_HINTS = (
    "screen",
    "desktop",
    "window",
    "windows",
    "visually",
    "vision",
    "screenshot",
)

_FILESYSTEM_HINTS = (
    "directory",
    "directories",
    "folder",
    "folders",
    "file",
    "files",
    "path",
    "workspace",
    "repo",
    "repository",
    "contents",
    "absolute path",
    "windows path",
)

_TOOL_SURFACE_HINTS = (
    "screen",
    "desktop",
    "window",
    "windows",
    "browser",
    "chrome",
    "edge",
    "firefox",
    "website",
    "webpage",
    "page",
    "url",
    "link",
    "tab",
    "file",
    "files",
    "folder",
    "folders",
    "directory",
    "directories",
    "path",
    "workspace",
    "repo",
    "repository",
    "app",
    "application",
    "program",
    "spotify",
    "whatsapp",
    "telegram",
    "gmail",
    "email",
    "message",
    "calendar",
    "computer",
    "machine",
    "terminal",
    "command",
)

_CODING_TOOL_HINTS = (
    "code",
    "coding",
    "script",
    "electron",
    "website",
    "web app",
    "server",
    "api",
    "backend",
    "frontend",
    "build",
    "compile",
    "npm",
    "node",
    "package",
    "pytest",
    "test",
    "tests",
    "eval",
    "evaluation",
)

_LIVE_INFO_HINTS = (
    "latest",
    "today",
    "tonight",
    "tomorrow",
    "yesterday",
    "current",
    "right now",
    "real time",
    "real-time",
    "news",
    "weather",
    "stock",
    "stocks",
    "price",
    "prices",
    "exchange rate",
)

_DISCUSSION_INTENT_RE = re.compile(
    r"^\s*("
    r"explain|tell me about|what is|what are|why|how does|how do i|how do we|"
    r"how would|what would|can we|could we|should we|is it possible|are there|"
    r"can you explain|could you explain|would you explain"
    r")\b"
)
_DIRECT_TOOL_ACTION_RE = re.compile(
    r"\b("
    r"open|launch|install|send|message|email|reply|click|type|focus|navigate|"
    r"delete|edit|save|download|upload|move|copy|rename|close|press|scroll|"
    r"log\s*in|login"
    r")\b"
)
_AMBIGUOUS_TOOL_ACTION_RE = re.compile(
    r"\b("
    r"check|look at|look for|find|search|read|describe|show me|inspect|verify|"
    r"summarize|gather|research|look up|create|write|make|run|start|build|"
    r"compile|test|debug|implement|fix"
    r")\b"
)


def normalize_user_text(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def is_filesystem_observation_message(text: str) -> bool:
    normalized = normalize_user_text(text)
    if not normalized:
        return False
    return any(hint in normalized for hint in _FILESYSTEM_HINTS)


def is_screen_observation_message(text: str) -> bool:
    normalized = normalize_user_text(text)
    if not normalized:
        return False

    has_screen_hint = any(hint in normalized for hint in _SCREEN_OBSERVATION_HINTS)
    if not has_screen_hint:
        has_screen_hint = bool(re.search(r"\b(see|look|looking|visually|vision)\b", normalized))
    if not has_screen_hint:
        return False

    filesystem_only = is_filesystem_observation_message(normalized) and not any(
        hint in normalized for hint in _SCREEN_CONTEXT_HINTS
    )
    if filesystem_only:
        return False

    if normalized.startswith("look") or normalized.startswith("see"):
        return True
    if any(hint in normalized for hint in _SCREEN_OBSERVATION_HINTS):
        return True
    return any(hint in normalized for hint in _SCREEN_CONTEXT_HINTS)


def is_task_like_message(text: str) -> bool:
    normalized = normalize_user_text(text)
    if not normalized:
        return False

    if normalized in _CASUAL_EXACT:
        return False

    if re.fullmatch(r"(hi|hello|hey|yo)[!. ]*", normalized):
        return False

    if re.fullmatch(r"(thanks|thank you|thx)[!. ]*", normalized):
        return False

    if is_screen_observation_message(normalized):
        return True

    if any(hint in normalized for hint in _TASK_HINTS):
        return True

    if normalized.endswith("?") and any(token in normalized for token in ("can you", "could you", "would you", "please", "should we")):
        return True

    return len(normalized.split()) >= 8


def request_requires_tool_evidence(text: str) -> bool:
    """Return whether the request needs observable/tool evidence before final answer.

    This is intentionally narrower than ``is_task_like_message``. Long questions and
    explanation requests can be task-like without requiring desktop/browser/file
    tools, and the final-quality planner should not force retries for those turns.
    """
    normalized = normalize_user_text(text)
    if not normalized:
        return False

    if normalized in _CASUAL_EXACT:
        return False

    if is_screen_observation_message(normalized):
        return True

    if is_filesystem_observation_message(normalized) and re.search(
        r"\b(what|what's|whats|list|contents|current|show|read|find|search|where)\b",
        normalized,
    ):
        return True

    has_surface = any(hint in normalized for hint in _TOOL_SURFACE_HINTS)
    has_coding_surface = any(hint in normalized for hint in _CODING_TOOL_HINTS)
    has_live_info = any(hint in normalized for hint in _LIVE_INFO_HINTS)
    has_ambiguous_action = bool(_AMBIGUOUS_TOOL_ACTION_RE.search(normalized))

    if _DISCUSSION_INTENT_RE.search(normalized) and not has_live_info:
        return False

    if _DIRECT_TOOL_ACTION_RE.search(normalized):
        return True

    if has_ambiguous_action and (has_surface or has_coding_surface or has_live_info):
        return True

    if has_coding_surface and re.search(r"\b(create|write|make|run|start|build|compile|test|debug|implement|fix)\b", normalized):
        return True

    if has_live_info and (normalized.endswith("?") or has_ambiguous_action):
        return True

    return False
