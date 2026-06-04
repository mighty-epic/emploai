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
