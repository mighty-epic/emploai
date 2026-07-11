from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from shared.atomic_io import atomic_write_json
from shared.runtime_paths import user_state_root
from shared.security_policy import redact_json, redact_text
from shared.tool_packs import default_enabled_tool_packs, normalize_enabled_tool_packs, pack_ids


ONBOARDING_STORE_VERSION = 1
MAX_FIELD_CHARS = 12000
MAX_LIST_ITEMS = 80

_TOOL_KEYWORDS: Dict[str, tuple[str, ...]] = {
    "workspace_read": (
        "read files",
        "inspect code",
        "search code",
        "analyze repo",
        "repository",
        "codebase",
        "logs",
    ),
    "workspace_write": (
        "edit",
        "write files",
        "change code",
        "implement",
        "fix bugs",
        "run command",
        "terminal",
        "tests",
    ),
    "browser_isolated": (
        "browser",
        "website",
        "web app",
        "selenium",
        "scrape",
        "login page",
    ),
    "interactive_desktop": (
        "desktop",
        "screen",
        "click",
        "type into",
        "native app",
        "windows app",
        "observe",
    ),
    "web_research": (
        "research",
        "web search",
        "internet",
        "latest",
        "docs",
        "documentation",
    ),
    "scheduler": (
        "automation",
        "automations",
        "schedule",
        "recurring",
        "cron",
        "every day",
        "reminder",
    ),
    "app_runtime": (
        "fleet",
        "worker",
        "workers",
        "session",
        "chat",
        "runtime",
    ),
}

_MISSING_REQUIREMENT_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("gmail", "Configure Gmail/login credentials before workflows can send or read Gmail."),
    ("email", "Configure the relevant email account before email workflows run."),
    ("telegram", "Configure Telegram settings before Telegram workflows run."),
    ("openai", "Add an OpenAI API key or ChatGPT subscription before OpenAI-specific workflows run."),
    ("anthropic", "Add an Anthropic API key before Claude-specific workflows run."),
    ("claude", "Add an Anthropic API key before Claude-specific workflows run."),
    ("gemini", "Add a Google Gemini API key before Gemini-specific workflows run."),
    ("google", "Configure the needed Google credentials before Google workflows run."),
    ("nvidia", "Add an NVIDIA API key before NVIDIA model workflows run."),
    ("browser extension", "Install or enable the browser extension before live Chrome workflows run."),
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_workspace_path(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(Path(text).expanduser().resolve())
    except Exception:
        return text.replace("/", "\\").rstrip("\\")


def workspace_key(value: Any) -> str:
    normalized = normalize_workspace_path(value)
    return normalized.casefold()


def _clean_text(value: Any, *, limit: int = MAX_FIELD_CHARS) -> str:
    text = redact_text(value).strip()
    if len(text) > limit:
        return text[:limit].rstrip()
    return text


def _clean_list(value: Any, *, limit: int = MAX_LIST_ITEMS) -> List[str]:
    if isinstance(value, str):
        raw_items = re.split(r"[\r\n]+|,", value)
    elif isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, Mapping)):
        raw_items = list(value)
    else:
        raw_items = []
    items: List[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = _clean_text(item, limit=1000)
        key = text.casefold()
        if not text or key in seen:
            continue
        items.append(text)
        seen.add(key)
        if len(items) >= limit:
            break
    return items


def onboarding_store_path(user_id: int) -> Path:
    return user_state_root(int(user_id)) / "project-onboarding.json"


def _empty_profile(workspace: str = "", *, workspace_id: Optional[str] = None) -> Dict[str, Any]:
    normalized_workspace = normalize_workspace_path(workspace)
    return {
        "workspace": normalized_workspace,
        "workspace_key": workspace_key(normalized_workspace),
        "workspace_id": str(workspace_id or "").strip() or None,
        "enabled": False,
        "role_identity": "",
        "job_mission": "",
        "required_tools": [],
        "workflows": [],
        "constraints": "",
        "communication_style": "",
        "raw_notes": "",
        "desired_tool_packs": [],
        "missing_requirements": [],
        "guided_transcript": [],
        "created_at": None,
        "updated_at": None,
        "prompt_preview": "",
    }


def summarize_onboarding_answers(payload: Mapping[str, Any]) -> Dict[str, Any]:
    answers = payload.get("answers") if isinstance(payload.get("answers"), Mapping) else {}
    transcript = payload.get("guided_transcript") or payload.get("transcript") or []
    profile = {
        "enabled": True,
        "role_identity": _clean_text(answers.get("role_identity") or answers.get("role") or payload.get("role_identity")),
        "job_mission": _clean_text(answers.get("job_mission") or answers.get("mission") or payload.get("job_mission")),
        "required_tools": _clean_list(answers.get("required_tools") or answers.get("tools") or payload.get("required_tools")),
        "workflows": _clean_list(answers.get("workflows") or payload.get("workflows")),
        "constraints": _clean_text(answers.get("constraints") or payload.get("constraints")),
        "communication_style": _clean_text(answers.get("communication_style") or answers.get("style") or payload.get("communication_style")),
        "raw_notes": _clean_text(answers.get("raw_notes") or answers.get("notes") or payload.get("raw_notes")),
        "guided_transcript": sanitize_guided_transcript(transcript),
    }
    profile["desired_tool_packs"] = infer_desired_tool_packs(profile)
    profile["missing_requirements"] = infer_missing_requirements(profile)
    profile["prompt_preview"] = render_project_onboarding_prompt(profile)
    return profile


def sanitize_guided_transcript(value: Any) -> List[Dict[str, str]]:
    if not isinstance(value, list):
        return []
    messages: List[Dict[str, str]] = []
    for item in value[:80]:
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role") or "user").strip().lower()
        if role not in {"assistant", "user", "system"}:
            role = "user"
        content = _clean_text(item.get("content"), limit=4000)
        if not content:
            continue
        messages.append(
            {
                "role": role,
                "content": content,
                "created_at": _clean_text(item.get("created_at") or utc_now_iso(), limit=80),
            }
        )
    return messages


def sanitize_profile_payload(
    payload: Mapping[str, Any],
    *,
    workspace: str,
    workspace_id: Optional[str] = None,
    previous: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    now = utc_now_iso()
    previous_profile = dict(previous or {})
    profile = _empty_profile(workspace, workspace_id=workspace_id or previous_profile.get("workspace_id"))
    profile["enabled"] = bool(payload.get("enabled", previous_profile.get("enabled", True)))
    for field in ("role_identity", "job_mission", "constraints", "communication_style", "raw_notes"):
        profile[field] = _clean_text(payload.get(field, previous_profile.get(field, "")))
    profile["required_tools"] = _clean_list(payload.get("required_tools", previous_profile.get("required_tools", [])))
    profile["workflows"] = _clean_list(payload.get("workflows", previous_profile.get("workflows", [])))
    profile["guided_transcript"] = sanitize_guided_transcript(
        payload.get("guided_transcript", previous_profile.get("guided_transcript", []))
    )
    desired = payload.get("desired_tool_packs")
    inferred = infer_desired_tool_packs(profile)
    profile["desired_tool_packs"] = normalize_enabled_tool_packs(list(desired or []) + inferred)
    profile["missing_requirements"] = _clean_list(
        payload.get("missing_requirements", previous_profile.get("missing_requirements", []))
    ) or infer_missing_requirements(profile)
    profile["created_at"] = previous_profile.get("created_at") or now
    profile["updated_at"] = now
    profile["prompt_preview"] = render_project_onboarding_prompt(profile)
    return redact_json(profile)


def _profile_search_text(profile: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for key in ("role_identity", "job_mission", "constraints", "communication_style", "raw_notes"):
        parts.append(str(profile.get(key) or ""))
    for key in ("required_tools", "workflows"):
        values = profile.get(key)
        if isinstance(values, list):
            parts.extend(str(item or "") for item in values)
    return "\n".join(parts).casefold()


def infer_desired_tool_packs(profile: Mapping[str, Any]) -> List[str]:
    text = _profile_search_text(profile)
    desired: List[str] = []
    known = set(pack_ids())
    for pack_id, keywords in _TOOL_KEYWORDS.items():
        if pack_id not in known:
            continue
        if any(keyword in text for keyword in keywords):
            desired.append(pack_id)
    if not desired:
        desired = ["workspace_read", "app_runtime"]
    return normalize_enabled_tool_packs(desired)


def infer_missing_requirements(profile: Mapping[str, Any]) -> List[str]:
    text = _profile_search_text(profile)
    missing: List[str] = []
    for keyword, message in _MISSING_REQUIREMENT_KEYWORDS:
        if keyword in text and message not in missing:
            missing.append(message)
    return missing


def merge_tool_packs(current: Iterable[str], desired: Iterable[str]) -> List[str]:
    base = normalize_enabled_tool_packs(list(current or []))
    if not base:
        base = default_enabled_tool_packs()
    return normalize_enabled_tool_packs(base + list(desired or []))


def render_project_onboarding_prompt(profile: Mapping[str, Any]) -> str:
    if not profile or not bool(profile.get("enabled", False)):
        return ""
    lines: List[str] = []
    role = str(profile.get("role_identity") or "").strip()
    mission = str(profile.get("job_mission") or "").strip()
    constraints = str(profile.get("constraints") or "").strip()
    style = str(profile.get("communication_style") or "").strip()
    raw_notes = str(profile.get("raw_notes") or "").strip()
    if role:
        lines.append(f"Role / identity: {role}")
    if mission:
        lines.append(f"Job / mission: {mission}")
    tools = [str(item).strip() for item in profile.get("required_tools", []) if str(item).strip()]
    if tools:
        lines.append("Tools the user expects you to use or account for:")
        lines.extend(f"- {item}" for item in tools[:MAX_LIST_ITEMS])
    workflows = [str(item).strip() for item in profile.get("workflows", []) if str(item).strip()]
    if workflows:
        lines.append("Workflows / SOPs:")
        lines.extend(f"- {item}" for item in workflows[:MAX_LIST_ITEMS])
    if constraints:
        lines.append(f"Constraints / boundaries: {constraints}")
    if style:
        lines.append(f"Communication style: {style}")
    if raw_notes:
        lines.append(f"Additional notes: {raw_notes}")
    if not lines:
        return ""
    return "\n".join(lines).strip()


def project_onboarding_prompt_for_session(session: Any) -> str:
    workspace = str(getattr(session, "workspace", "") or "").strip()
    if not workspace:
        return ""
    user_id = getattr(session, "user_id", None)
    if user_id is None:
        user_id = getattr(getattr(session, "session", None), "user_id", None)
    try:
        store = ProjectOnboardingStore(user_id=int(user_id or 1))
        profile = store.get_by_workspace(workspace)
    except Exception:
        return ""
    return render_project_onboarding_prompt(profile)


class ProjectOnboardingStore:
    def __init__(self, *, user_id: int) -> None:
        self.user_id = int(user_id)
        self.path = onboarding_store_path(self.user_id)

    def _read_payload(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"version": ONBOARDING_STORE_VERSION, "profiles": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"version": ONBOARDING_STORE_VERSION, "profiles": {}}
        if not isinstance(payload, dict):
            return {"version": ONBOARDING_STORE_VERSION, "profiles": {}}
        profiles = payload.get("profiles")
        if not isinstance(profiles, dict):
            profiles = {}
        return {"version": ONBOARDING_STORE_VERSION, "profiles": profiles}

    def _write_payload(self, payload: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.path, payload, ensure_ascii=True, default=str)

    def get_by_workspace(self, workspace: str) -> Dict[str, Any]:
        key = workspace_key(workspace)
        if not key:
            return _empty_profile(workspace)
        payload = self._read_payload()
        profile = payload.get("profiles", {}).get(key)
        if isinstance(profile, dict):
            return dict(profile)
        return _empty_profile(workspace)

    def upsert(self, *, workspace: str, profile: Mapping[str, Any], workspace_id: Optional[str] = None) -> Dict[str, Any]:
        key = workspace_key(workspace)
        if not key:
            raise ValueError("Workspace is required")
        payload = self._read_payload()
        profiles = dict(payload.get("profiles") or {})
        next_profile = sanitize_profile_payload(
            profile,
            workspace=workspace,
            workspace_id=workspace_id,
            previous=profiles.get(key) if isinstance(profiles.get(key), Mapping) else None,
        )
        profiles[key] = next_profile
        payload["profiles"] = profiles
        payload["version"] = ONBOARDING_STORE_VERSION
        self._write_payload(payload)
        return next_profile

    def list_profiles(self) -> List[Dict[str, Any]]:
        payload = self._read_payload()
        profiles = payload.get("profiles") if isinstance(payload.get("profiles"), dict) else {}
        return [dict(profile) for profile in profiles.values() if isinstance(profile, dict)]
