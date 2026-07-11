from __future__ import annotations

import os
import re
import secrets
from typing import Any, Dict, Optional


JARVIS_BARGE_IN_MIN_WORDS = 2
JARVIS_BARGE_IN_MIN_CHARS = 6
DEFAULT_JARVIS_WAKE_PHRASE = "jarvis"
JARVIS_WAKE_PHRASE_ENV = "EMPLOAI_JARVIS_WAKE_PHRASE"
JARVIS_TOOL_UPDATE_EVERY_ENV = "EMPLOAI_JARVIS_TOOL_UPDATE_EVERY"


def jarvis_wake_phrase() -> str:
    phrase = str(os.getenv(JARVIS_WAKE_PHRASE_ENV, "") or "").strip()
    return phrase or DEFAULT_JARVIS_WAKE_PHRASE


def jarvis_extract_wake_request(text: str, wake_phrase: Optional[str] = None) -> tuple[bool, str]:
    raw = re.sub(r"\s+", " ", str(text or "").strip())
    phrase = re.sub(r"\s+", " ", str(wake_phrase or jarvis_wake_phrase()).strip())
    if not raw or not phrase:
        return False, raw

    phrase_pattern = r"\s+".join(re.escape(part) for part in phrase.split())
    prefix_pattern = rf"^\s*(?:(?:hey|hi|hello|ok|okay)\s+)?{phrase_pattern}\b[\s,.:;!\-]*"
    if not re.match(prefix_pattern, raw, flags=re.IGNORECASE):
        return False, raw
    request = re.sub(prefix_pattern, "", raw, count=1, flags=re.IGNORECASE).strip()
    return True, request


def jarvis_tool_update_every() -> int:
    raw_value = str(os.getenv(JARVIS_TOOL_UPDATE_EVERY_ENV, "3") or "").strip()
    try:
        return max(0, int(raw_value))
    except ValueError:
        return 3


def jarvis_tool_update_message(tool_count: int, tool_name: str) -> str:
    count = max(1, int(tool_count or 1))
    label = re.sub(r"[_\-]+", " ", str(tool_name or "").strip())
    label = re.sub(r"\s+", " ", label).strip()
    if label:
        return f"Still working. I have completed {count} tool steps, most recently {label}."
    return f"Still working. I have completed {count} tool steps."


def jarvis_voice_turn_is_task_like(text: str) -> bool:
    try:
        from shared.task_intent import request_requires_tool_evidence
    except Exception:
        return len(str(text or "").split()) >= 8
    return bool(request_requires_tool_evidence(text))


def jarvis_start_task_message(text: str) -> str:
    try:
        from shared.task_intent import is_screen_observation_message
    except Exception:
        is_screen_turn = False
    else:
        is_screen_turn = bool(is_screen_observation_message(text))

    normalized = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if is_screen_turn:
        return "I am checking what is on screen now."
    if re.search(r"\b(open|launch|start|show|bring up)\b", normalized):
        return "Opening that now."
    if re.search(r"\b(search|find|look up|research|check|read|summarize|gather)\b", normalized):
        return "I am checking that now."
    if re.search(r"\b(send|message|email|reply|whatsapp|telegram|gmail)\b", normalized):
        return "I will prepare that now."
    if re.search(r"\b(create|write|make|save|edit|update|fix|change)\b", normalized):
        return "I am working on that now."
    return "I am on it. I will start working on that now."


def jarvis_barge_in_text_is_meaningful(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "").strip())
    if len(normalized) < JARVIS_BARGE_IN_MIN_CHARS:
        return False
    words = [word for word in re.split(r"\s+", normalized) if re.search(r"[A-Za-z0-9]", word)]
    return len(words) >= JARVIS_BARGE_IN_MIN_WORDS


def jarvis_barge_in_words(text: str) -> list[str]:
    return [
        word.lower()
        for word in re.findall(r"[A-Za-z0-9]+", str(text or ""))
        if len(word) > 1
    ]


def jarvis_barge_in_is_self_echo(text: str, reference_text: str) -> bool:
    candidate_words = jarvis_barge_in_words(text)
    reference_words = set(jarvis_barge_in_words(reference_text))
    if len(candidate_words) < JARVIS_BARGE_IN_MIN_WORDS or not reference_words:
        return False

    overlap = sum(1 for word in candidate_words if word in reference_words) / max(1, len(candidate_words))
    if overlap >= 0.8:
        return True

    normalized_candidate = re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()
    normalized_reference = re.sub(r"[^a-z0-9]+", " ", str(reference_text or "").lower()).strip()
    return bool(normalized_candidate and normalized_candidate in normalized_reference)


def jarvis_confirmation_intent(text: str) -> Optional[bool]:
    cleaned = re.sub(r"[^a-zA-Z\s]", " ", str(text or "").lower()).strip()
    words = [word for word in cleaned.split() if word]
    if not words or len(words) > 8:
        return None
    yes_words = {"yes", "yeah", "yep", "confirm", "confirmed", "approve", "approved", "proceed", "continue", "do", "ok", "okay"}
    no_words = {"no", "nope", "cancel", "stop", "deny", "decline", "abort"}
    has_yes = any(word in yes_words for word in words)
    has_no = any(word in no_words for word in words)
    if has_yes and not has_no:
        return True
    if has_no and not has_yes:
        return False
    return None


def jarvis_confirmation_prompt(tool_name: str, tool_result: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(tool_result, dict):
        return None
    confirmation_required = bool(tool_result.get("confirmation_required"))
    security_required = str(tool_result.get("error_type") or "") == "security_confirmation_required"
    if not confirmation_required and not security_required:
        return None
    action = str(tool_result.get("action") or tool_result.get("tool_name") or tool_name or "this action").strip()
    summary = str(tool_result.get("summary") or tool_result.get("error") or "").strip()
    risk = str(tool_result.get("risk") or "").strip()
    confirmation_id = str(tool_result.get("confirmation_id") or f"voice_confirm_{secrets.token_hex(6)}").strip()
    spoken = f"Please confirm whether I should proceed with {action}."
    if summary:
        spoken = f"{spoken} {summary[:180]}"
    if risk:
        spoken = f"{spoken} Risk level: {risk}."
    return {
        "confirmation_id": confirmation_id,
        "tool_name": tool_name,
        "action": action,
        "summary": summary,
        "risk": risk,
        "spoken_prompt": spoken,
        "tool_result": tool_result,
    }
