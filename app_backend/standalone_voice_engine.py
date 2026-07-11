from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from shared.atomic_io import atomic_write_json


DEFAULT_WAKE_PHRASE = "EmploAI"
DEFAULT_AWAKE_TIMEOUT_S = 12.0
DEFAULT_COMMAND_GAP_S = 1.6
DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.72
DEFAULT_PROJECT_TERM_LIMIT = 48
DEFAULT_PROMPT_TERM_LIMIT = 24
DEFAULT_REVIEW_ITEM_LIMIT = 80
DEFAULT_COMMAND_HISTORY_LIMIT = 50
DEFAULT_SESSION_COMMAND_LIMIT = 80

DEFAULT_SEED_TERMS = (
    "EmploAI",
    "OpenAI",
    "GitHub",
    "Telegram",
    "telegram_agent.py",
    ".env",
    "MEMORY.md",
    "whisper.cpp",
)

IGNORED_SCAN_DIRS = {
    ".git",
    ".idea",
    ".next",
    ".tools",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "test_outputs",
}

COMMON_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "but",
    "by",
    "for",
    "from",
    "hey",
    "i",
    "if",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "please",
    "so",
    "tell",
    "that",
    "the",
    "then",
    "this",
    "to",
    "use",
    "what",
    "you",
    "your",
}

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
NORMALIZE_RE = re.compile(r"[^a-z0-9]+")
CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def default_voice_engine_state_dir(base_output_dir: Path) -> Path:
    return Path(base_output_dir) / "voice_engine"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _normalize_phrase(text: str) -> str:
    return re.sub(r"\s+", " ", NORMALIZE_RE.sub(" ", (text or "").lower())).strip()


def _alias_variants(phrase: str, aliases: Optional[list[str]] = None) -> list[str]:
    values = []
    for item in [phrase, *(aliases or [])]:
        cleaned = _clean_spaces(item)
        if not cleaned:
            continue
        values.append(cleaned)
        camel_split = _clean_spaces(CAMEL_BOUNDARY_RE.sub(" ", cleaned).replace("_", " ").replace("-", " "))
        if camel_split and camel_split.lower() != cleaned.lower():
            values.append(camel_split)

    seen: set[str] = set()
    ordered: list[str] = []
    for item in values:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(item)
    return ordered


def _compile_phrase_patterns(phrases: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    compiled: list[tuple[str, re.Pattern[str]]] = []
    for phrase in phrases:
        tokens = re.findall(r"[A-Za-z0-9]+", phrase)
        if not tokens:
            continue
        pattern = r"\b" + r"[\W_]*".join(re.escape(token) for token in tokens) + r"\b"
        compiled.append((phrase, re.compile(pattern, re.IGNORECASE)))
    return compiled


def _tokenize_for_learning(text: str) -> list[str]:
    return [match.group(0) for match in TOKEN_RE.finditer(text or "")]


def _score_project_term(name: str, *, depth: int) -> int:
    score = 1
    suffix = Path(name).suffix.lower()
    if name.startswith("."):
        score += 4
    if suffix in {".py", ".md", ".json", ".yaml", ".yml", ".toml", ".env", ".txt"}:
        score += 3
    if any(char.isupper() for char in name):
        score += 1
    if "_" in name or "-" in name:
        score += 2
    if "." in Path(name).name:
        score += 1
    if depth <= 2:
        score += 2
    return score


def scan_project_terms(repo_root: Path, *, limit: int = DEFAULT_PROJECT_TERM_LIMIT) -> list[str]:
    repo_root = Path(repo_root).resolve()
    scored: dict[str, int] = {}

    for current_root, dirnames, filenames in os.walk(repo_root):
        relative_parts = Path(current_root).resolve().relative_to(repo_root).parts if Path(current_root).resolve() != repo_root else ()
        dirnames[:] = [name for name in dirnames if name not in IGNORED_SCAN_DIRS]
        depth = len(relative_parts)

        if depth <= 2:
            for dirname in dirnames:
                score = _score_project_term(dirname, depth=depth) - 1
                if score > 0 and len(dirname) <= 48:
                    scored[dirname] = max(scored.get(dirname, 0), score)

        for filename in filenames:
            if len(filename) > 80:
                continue
            score = _score_project_term(filename, depth=depth)
            scored[filename] = max(scored.get(filename, 0), score)

    ordered = sorted(scored.items(), key=lambda item: (-item[1], len(item[0]), item[0].lower()))
    return [term for term, _ in ordered[: max(0, limit)]]


class StandaloneVoiceEngine:
    """
    Standalone desktop voice-engine state.

    This intentionally stays separate from the main agent runtime. It handles:
    - wake phrase detection
    - awake/sleep command windows
    - project-term vocabulary seeding
    - low-confidence review memory
    - per-session command history
    """

    def __init__(
        self,
        *,
        repo_root: Path,
        state_dir: Path,
        wake_phrase: str = DEFAULT_WAKE_PHRASE,
        wake_aliases: Optional[list[str]] = None,
        known_terms: Optional[list[str]] = None,
        awake_timeout_s: float = DEFAULT_AWAKE_TIMEOUT_S,
        command_gap_s: float = DEFAULT_COMMAND_GAP_S,
        low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
        project_term_limit: int = DEFAULT_PROJECT_TERM_LIMIT,
        prompt_term_limit: int = DEFAULT_PROMPT_TERM_LIMIT,
    ):
        self.repo_root = Path(repo_root).resolve()
        self.state_dir = Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.profile_path = self.state_dir / "profile.json"
        self.session_path = self.state_dir / "latest_session.json"
        self._lock = threading.RLock()

        self.wake_phrase = _clean_spaces(wake_phrase) or DEFAULT_WAKE_PHRASE
        self.wake_aliases = _alias_variants(self.wake_phrase, wake_aliases)
        self._wake_patterns = _compile_phrase_patterns(self.wake_aliases)

        self.awake_timeout_s = max(1.0, float(awake_timeout_s))
        self.command_gap_s = max(0.2, float(command_gap_s))
        self.low_confidence_threshold = max(0.0, min(1.0, float(low_confidence_threshold)))
        self.project_term_limit = max(0, int(project_term_limit))
        self.prompt_term_limit = max(0, int(prompt_term_limit))

        self.profile = self._load_profile()
        self.project_terms = scan_project_terms(self.repo_root, limit=self.project_term_limit)
        self._merge_known_terms_locked([*DEFAULT_SEED_TERMS, self.wake_phrase, *(known_terms or []), *self.project_terms])
        self.profile["wake_phrase"] = self.wake_phrase
        self.profile["wake_aliases"] = list(self.wake_aliases)
        self.profile["project_terms"] = list(self.project_terms)
        self.profile["updated_at"] = _utc_now_iso()

        self.awake = False
        self.awake_until_monotonic: Optional[float] = None
        self.command_segments: list[dict[str, object]] = []
        self.last_command_activity_monotonic: Optional[float] = None
        self.session = {
            "session_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "started_at": _utc_now_iso(),
            "wake_phrase": self.wake_phrase,
            "commands": [],
            "events": [],
        }
        self._persist_locked()

    def _empty_profile(self) -> dict:
        return {
            "version": 1,
            "wake_phrase": self.wake_phrase,
            "wake_aliases": list(self.wake_aliases),
            "known_terms": [],
            "project_terms": [],
            "frequent_terms": {},
            "low_confidence_terms": {},
            "pending_reviews": [],
            "command_history": [],
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }

    def _load_profile(self) -> dict:
        if not self.profile_path.exists():
            return self._empty_profile()

        try:
            payload = json.loads(self.profile_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return self._empty_profile()

        profile = self._empty_profile()
        if isinstance(payload, dict):
            profile.update(payload)
        profile["known_terms"] = [str(item) for item in profile.get("known_terms", []) if str(item).strip()]
        profile["project_terms"] = [str(item) for item in profile.get("project_terms", []) if str(item).strip()]
        profile["frequent_terms"] = {
            str(key): int(value)
            for key, value in dict(profile.get("frequent_terms", {})).items()
            if str(key).strip()
        }
        profile["low_confidence_terms"] = {
            str(key): int(value)
            for key, value in dict(profile.get("low_confidence_terms", {})).items()
            if str(key).strip()
        }
        profile["pending_reviews"] = list(profile.get("pending_reviews", []))[-DEFAULT_REVIEW_ITEM_LIMIT:]
        profile["command_history"] = list(profile.get("command_history", []))[-DEFAULT_COMMAND_HISTORY_LIMIT:]
        return profile

    def _persist_locked(self) -> None:
        self.profile["updated_at"] = _utc_now_iso()
        atomic_write_json(self.profile_path, self.profile, sort_keys=True)
        atomic_write_json(self.session_path, self.session, sort_keys=True)

    def _append_session_event_locked(self, event_type: str, *, text: Optional[str] = None, confidence: Optional[float] = None) -> None:
        event = {
            "timestamp": _utc_now_iso(),
            "type": event_type,
        }
        if text:
            event["text"] = text
        if confidence is not None:
            event["confidence"] = round(float(confidence), 3)
        self.session["events"].append(event)
        self.session["events"] = self.session["events"][-120:]

    def _merge_known_terms_locked(self, values: list[str]) -> None:
        merged = {str(item).strip(): None for item in self.profile.get("known_terms", []) if str(item).strip()}
        for value in values:
            cleaned = _clean_spaces(str(value))
            if cleaned:
                merged.setdefault(cleaned, None)
        self.profile["known_terms"] = list(merged.keys())

    def _prompt_terms_locked(self) -> list[str]:
        preferred = []
        for item in [*DEFAULT_SEED_TERMS, *self.project_terms, *self.profile.get("known_terms", [])]:
            cleaned = _clean_spaces(str(item))
            if cleaned:
                preferred.append(cleaned)

        seen: set[str] = set()
        unique: list[str] = []
        for item in preferred:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique[: self.prompt_term_limit]

    def _record_term_usage_locked(self, text: str, confidence: Optional[float]) -> None:
        lowered_counts: Counter[str] = Counter()
        exact_terms: list[str] = []
        for token in _tokenize_for_learning(text):
            normalized = token.lower()
            if len(normalized) < 2 or normalized in COMMON_STOPWORDS:
                continue
            lowered_counts[normalized] += 1
            if any(marker in token for marker in ("_", "-", ".")) or any(char.isupper() for char in token):
                exact_terms.append(token)

        frequent_terms = dict(self.profile.get("frequent_terms", {}))
        for token, count in lowered_counts.items():
            frequent_terms[token] = int(frequent_terms.get(token, 0)) + int(count)
        self.profile["frequent_terms"] = frequent_terms

        if exact_terms:
            self._merge_known_terms_locked(exact_terms)

        if confidence is None or confidence >= self.low_confidence_threshold:
            return

        low_confidence_terms = dict(self.profile.get("low_confidence_terms", {}))
        review_terms: list[str] = []
        for token in lowered_counts:
            low_confidence_terms[token] = int(low_confidence_terms.get(token, 0)) + 1
            review_terms.append(token)
        self.profile["low_confidence_terms"] = low_confidence_terms

        if review_terms:
            pending_reviews = list(self.profile.get("pending_reviews", []))
            pending_reviews.append(
                {
                    "timestamp": _utc_now_iso(),
                    "text": text,
                    "confidence": round(float(confidence), 3),
                    "terms": review_terms[:8],
                }
            )
            self.profile["pending_reviews"] = pending_reviews[-DEFAULT_REVIEW_ITEM_LIMIT:]

    def _extract_wake_remainder_locked(self, text: str) -> Optional[str]:
        source = _clean_spaces(text)
        if not source:
            return None
        for _, pattern in self._wake_patterns:
            match = pattern.search(source)
            if not match:
                continue
            remainder = _clean_spaces(source[match.end() :].lstrip(" ,.:;!-"))
            return remainder
        return None

    def _wake_locked(self, *, source: str, now: float, transcript: str, confidence: Optional[float]) -> list[str]:
        just_woke = not self.awake
        self.awake = True
        self.awake_until_monotonic = now + self.awake_timeout_s
        self._append_session_event_locked(f"wake_{source}", text=transcript, confidence=confidence)
        if just_woke:
            return [f'[wake] detected "{self.wake_phrase}" via {source} transcript']
        return []

    def _append_command_segment_locked(self, text: str, *, confidence: Optional[float], now: float) -> list[str]:
        cleaned = _clean_spaces(text)
        if not cleaned:
            return []
        self.command_segments.append(
            {
                "text": cleaned,
                "confidence": None if confidence is None else round(float(confidence), 3),
                "timestamp": _utc_now_iso(),
            }
        )
        self.command_segments = self.command_segments[-24:]
        self.last_command_activity_monotonic = now
        self.awake_until_monotonic = now + self.awake_timeout_s
        return [f"[command segment] {cleaned}"]

    def _finalize_command_locked(self, *, reason: str) -> list[str]:
        if not self.command_segments:
            return []

        parts: list[str] = []
        confidences: list[float] = []
        for segment in self.command_segments:
            text = _clean_spaces(str(segment.get("text", "")))
            if not text:
                continue
            if not parts or parts[-1].lower() != text.lower():
                parts.append(text)
            confidence = segment.get("confidence")
            if confidence is not None:
                try:
                    confidences.append(float(confidence))
                except (TypeError, ValueError):
                    continue

        command_text = _clean_spaces(" ".join(parts))
        self.command_segments.clear()
        self.last_command_activity_monotonic = None
        if not command_text:
            return []

        average_confidence = (sum(confidences) / len(confidences)) if confidences else None
        command_entry = {
            "timestamp": _utc_now_iso(),
            "text": command_text,
            "reason": reason,
        }
        if average_confidence is not None:
            command_entry["confidence"] = round(average_confidence, 3)

        command_history = list(self.profile.get("command_history", []))
        command_history.append(command_entry)
        self.profile["command_history"] = command_history[-DEFAULT_COMMAND_HISTORY_LIMIT:]

        session_commands = list(self.session.get("commands", []))
        session_commands.append(command_entry)
        self.session["commands"] = session_commands[-DEFAULT_SESSION_COMMAND_LIMIT:]

        self._record_term_usage_locked(command_text, average_confidence)
        self._append_session_event_locked("command_ready", text=command_text, confidence=average_confidence)
        self._persist_locked()
        return [f"[command ready] {command_text}"]

    def build_prompt(self, *, base_prompt: Optional[str], recent_transcripts: list[str], context_chars: int) -> Optional[str]:
        with self._lock:
            parts: list[str] = []
            base = _clean_spaces(base_prompt or "")
            if base:
                parts.append(base)

            parts.append(f"Wake phrase: {self.wake_phrase}.")

            prompt_terms = self._prompt_terms_locked()
            if prompt_terms:
                parts.append("Prefer these literal project terms and filenames exactly if heard: " + ", ".join(prompt_terms) + ".")

            frequent_terms = [term for term, _ in sorted(self.profile.get("frequent_terms", {}).items(), key=lambda item: (-item[1], item[0]))[:6]]
            if frequent_terms:
                parts.append("The speaker often uses these words: " + ", ".join(frequent_terms) + ".")

            watch_terms = [term for term, _ in sorted(self.profile.get("low_confidence_terms", {}).items(), key=lambda item: (-item[1], item[0]))[:4]]
            if watch_terms:
                parts.append("Be careful with these low-confidence terms: " + ", ".join(watch_terms) + ".")

            cleaned_recent = [_clean_spaces(item) for item in recent_transcripts if _clean_spaces(item)]
            if context_chars > 0 and cleaned_recent:
                recent_text = " ".join(cleaned_recent)
                if len(recent_text) > context_chars:
                    recent_text = recent_text[-context_chars:].lstrip()
                parts.append(f"Recent confirmed transcript context: {recent_text}")

            prompt = "\n".join(parts).strip()
            return prompt or None

    def observe_preview(self, *, transcript: str, confidence: Optional[float], now: Optional[float] = None) -> list[str]:
        cleaned = _clean_spaces(transcript)
        if not cleaned:
            return []
        with self._lock:
            moment = time.monotonic() if now is None else float(now)
            remainder = self._extract_wake_remainder_locked(cleaned)
            if remainder is None:
                return []
            return self._wake_locked(source="preview", now=moment, transcript=cleaned, confidence=confidence)

    def observe_final(self, *, transcript: str, confidence: Optional[float], now: Optional[float] = None) -> list[str]:
        cleaned = _clean_spaces(transcript)
        if not cleaned:
            return []
        with self._lock:
            moment = time.monotonic() if now is None else float(now)
            events: list[str] = []
            remainder = self._extract_wake_remainder_locked(cleaned)

            if remainder is not None:
                if self.command_segments:
                    events.extend(self._finalize_command_locked(reason="new_wake_phrase"))
                events.extend(self._wake_locked(source="final", now=moment, transcript=cleaned, confidence=confidence))
                if remainder:
                    events.extend(self._append_command_segment_locked(remainder, confidence=confidence, now=moment))
                self._persist_locked()
                return events

            if not self.awake:
                return []

            events.extend(self._append_command_segment_locked(cleaned, confidence=confidence, now=moment))
            self._persist_locked()
            return events

    def poll(self, *, recording_active: bool, now: Optional[float] = None) -> list[str]:
        with self._lock:
            moment = time.monotonic() if now is None else float(now)
            events: list[str] = []

            if self.command_segments and self.last_command_activity_monotonic is not None and not recording_active:
                if (moment - self.last_command_activity_monotonic) >= self.command_gap_s:
                    events.extend(self._finalize_command_locked(reason="idle_gap"))

            if self.awake and self.awake_until_monotonic is not None and not recording_active:
                if moment >= self.awake_until_monotonic:
                    if self.command_segments:
                        events.extend(self._finalize_command_locked(reason="awake_timeout"))
                    self.awake = False
                    self.awake_until_monotonic = None
                    self._append_session_event_locked("sleep")
                    self._persist_locked()
                    events.append("[sleep] awake window expired")

            return events

    def flush(self) -> list[str]:
        with self._lock:
            events = self._finalize_command_locked(reason="shutdown")
            if self.awake:
                self.awake = False
                self.awake_until_monotonic = None
                self._append_session_event_locked("sleep")
                self._persist_locked()
            return events

    def profile_summary(self) -> dict:
        with self._lock:
            frequent_terms = sorted(self.profile.get("frequent_terms", {}).items(), key=lambda item: (-item[1], item[0]))[:8]
            low_confidence_terms = sorted(self.profile.get("low_confidence_terms", {}).items(), key=lambda item: (-item[1], item[0]))[:8]
            command_history = list(self.profile.get("command_history", []))[-5:]
            return {
                "wake_phrase": self.wake_phrase,
                "wake_aliases": list(self.wake_aliases),
                "state_dir": str(self.state_dir),
                "profile_path": str(self.profile_path),
                "known_terms_count": len(self.profile.get("known_terms", [])),
                "project_term_count": len(self.project_terms),
                "pending_review_count": len(self.profile.get("pending_reviews", [])),
                "recent_commands": command_history,
                "top_frequent_terms": [{"term": term, "count": count} for term, count in frequent_terms],
                "top_low_confidence_terms": [{"term": term, "count": count} for term, count in low_confidence_terms],
            }

    def export_profile(self) -> dict:
        with self._lock:
            return deepcopy(self.profile)

    def session_summary_lines(self) -> list[str]:
        with self._lock:
            lines = [
                f"Voice session commands: {len(self.session.get('commands', []))} | Pending review items: {len(self.profile.get('pending_reviews', []))}",
                f"Voice profile saved to: {self.profile_path}",
            ]
            recent_commands = [entry.get("text", "") for entry in self.session.get("commands", [])[-3:] if entry.get("text")]
            if recent_commands:
                lines.append("Recent commands: " + " | ".join(recent_commands))
            watch_terms = [term for term, _ in sorted(self.profile.get("low_confidence_terms", {}).items(), key=lambda item: (-item[1], item[0]))[:5]]
            if watch_terms:
                lines.append("Watch terms: " + ", ".join(watch_terms))
            return lines
