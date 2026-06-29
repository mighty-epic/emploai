from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional
from urllib.parse import urlparse


PermissionMode = str

ACTION_ALLOW = "allow"
ACTION_DENY = "deny"
ACTION_CONFIRM = "confirmation_required"

LOW_PERMISSION = "low"
STANDARD_PERMISSION = "standard"
FULL_PERMISSION = "full_permissions"

_BASE64_KEYS = frozenset({"image_base64", "base64", "image_data", "data", "screenshot"})
_SECRET_KEY_HINTS = (
    "api_key",
    "apikey",
    "authorization",
    "auth_token",
    "bearer",
    "client_secret",
    "cookie",
    "credential",
    "jwt",
    "pass",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "token",
)

_ACTIVE_BROWSER_TOOLS = {
    "browser_navigate",
    "browser_click_ref",
    "browser_type",
    "browser_press",
    "browser_select",
    "browser_upload_file",
    "browser_extension_toggle",
}
_ACTIVE_DESKTOP_TOOLS = {
    "click",
    "right_click",
    "double_click",
    "drag",
    "hotkey",
    "key_press",
    "move_mouse",
    "open_app",
    "scroll",
    "type_text",
}
_APP_OPEN_TOOLS = {"open_app", "open_file"}
_COMMAND_TOOLS = {"run_command", "run_background_command"}
_NETWORK_TOOLS = {"fetch_url"}
_WRITE_TOOLS = {"write_file", "append_file", "edit_file", "delete_file", "move_file", "copy_file"}
_OBSERVATION_TOOLS = {
    "describe_screen",
    "ocr_screen",
    "observe_desktop",
    "browser_snapshot",
    "browser_read_text",
    "browser_screenshot",
    "observe_browser",
}
_EXTERNAL_SEND_TOOLS = {
    "send_email",
    "gmail_send",
    "telegram_send",
    "whatsapp_send",
    "post_message",
    "fleet_send_worker_message",
    "fleet_send_group_message",
}

_PROTECTED_PATH_MARKERS = (
    ".aws",
    ".azure",
    ".config/gcloud",
    ".docker/config.json",
    ".env",
    ".git-credentials",
    ".gnupg",
    ".kube",
    ".npmrc",
    ".pypirc",
    ".ssh",
    "appdata/local/google/chrome/user data",
    "cookies",
    "id_dsa",
    "id_ed25519",
    "id_ecdsa",
    "id_rsa",
    "keychain",
    "login data",
    "remote-control.db",
    "remote_control.db",
    "remote_secrets.key",
    "secrets.json",
)

_EXPLICIT_DOMAIN_MARKERS = (
    "porn",
    "xvideos",
    "xnxx",
    "xhamster",
    "redtube",
    "youporn",
    "onlyfans",
    "chaturbate",
    "stripchat",
    "camgirl",
    "adultfriendfinder",
)

_ILLEGAL_DESTINATION_MARKERS = (
    "csam",
    "childporn",
    "child-porn",
    "exploitkit",
    "malware",
    "ransomware",
    "botnet",
)

_DESTRUCTIVE_COMMAND_PATTERNS = (
    r"\brm\s+(-[a-z]*r[a-z]*f|-rf|-fr)\b",
    r"\bremove-item\b.*(?:^|\s)-recurse\b.*(?:^|\s)-force\b",
    r"\brmdir\b.*\s/[sq]\b",
    r"\bdel\b.*\s/[fsq]\b",
    r"\bformat(?:\.com|\.exe)?\b",
    r"\bdiskpart\b",
    r"\bmkfs(?:\.\w+)?\b",
    r"\bdd\s+if=",
    r"\bshutdown(?:\.exe)?\b",
    r"\brestart-computer\b",
    r"\bstop-computer\b",
    r"\bbcdedit\b",
    r"\breg(?:\.exe)?\s+(?:add|delete)\b",
    r"\bset-mppreference\b.*\bdisable",
    r"\bnetsh\b.*\bfirewall\b.*\b(?:off|disable|allow)\b",
    r"\bufw\s+disable\b",
    r"\biptables\b",
)

_CREDENTIAL_COMMAND_PATTERNS = (
    r"\bmimikatz\b",
    r"\bsekurlsa\b",
    r"\blsass\b",
    r"\bprocdump\b.*\blsass\b",
    r"\bcredential(?:s)?\s+dump",
    r"\bdump(?:ing)?\s+(?:cookies|tokens|passwords|credentials)",
    r"\b(?:chrome|edge|firefox).*(?:cookies|login data|local state)",
    r"\bremote_secrets\.key\b",
    r"\b(?:id_rsa|id_ed25519|\.ssh)\b",
)

_SERVER_TAMPER_PATTERNS = (
    r"\bDROP\s+TABLE\b",
    r"\bDELETE\s+FROM\b.*\b(remote_|fleet_|users?|sessions?)",
    r"\b/var/lib/emploai",
    r"\bemploai-remote\b.*\b(?:delete|rm|truncate|drop|reset)\b",
    r"/api/remote/account/secrets/reveal",
)

_TOKEN_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
)


@dataclass(frozen=True)
class SecurityContext:
    permission_mode: PermissionMode = STANDARD_PERMISSION
    workspace_path: Optional[str] = None
    workspace_binding_status: Optional[str] = None
    workspace_write_enabled: Optional[bool] = None
    actor_kind: Optional[str] = None
    surface: Optional[str] = None
    session_id: Optional[str] = None
    identity_id: Optional[str] = None


@dataclass(frozen=True)
class SecurityDecision:
    action: str = ACTION_ALLOW
    reason: str = ""
    risk: str = "safe"
    requires_full_permissions: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.action == ACTION_ALLOW

    @property
    def needs_confirmation(self) -> bool:
        return self.action == ACTION_CONFIRM

    def to_tool_result(self, *, tool_name: str) -> Dict[str, Any]:
        return redact_json(
            {
                "error": self.reason or "Tool call blocked by security policy.",
                "error_type": "security_policy",
                "tool_name": tool_name,
                "security_decision": self.action,
                "risk": self.risk,
                "requires_full_permissions": self.requires_full_permissions,
                "metadata": self.metadata,
                "retry": False,
            }
        )


def normalize_permission_mode(value: Any) -> PermissionMode:
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in {"low", "ask", "ask_always", "restricted"}:
        return LOW_PERMISSION
    if normalized in {"full", "full_permission", "full_permissions"}:
        return FULL_PERMISSION
    return STANDARD_PERMISSION


def default_security_context(*, workspace_path: Optional[str] = None) -> SecurityContext:
    return SecurityContext(
        permission_mode=normalize_permission_mode(os.getenv("EMPLOAI_PERMISSION_MODE") or STANDARD_PERMISSION),
        workspace_path=workspace_path,
    )


def redact_text(value: Any) -> str:
    text = str(value or "")
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub("[REDACTED_SECRET]", text)
    text = re.sub(
        r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|authorization|cookie)\s*[:=]\s*([^\s,;\"']+)",
        r"\1=[REDACTED_SECRET]",
        text,
    )
    return text


def redact_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        cleaned: Dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            lower = key_str.lower()
            if lower in _BASE64_KEYS and isinstance(item, str) and len(item) > 128:
                cleaned[key_str] = f"[BINARY_DATA_REDACTED {len(item)} chars]"
            elif any(hint in lower for hint in _SECRET_KEY_HINTS):
                if item in (None, "", False):
                    cleaned[key_str] = item
                else:
                    cleaned[key_str] = "[REDACTED_SECRET]"
            else:
                cleaned[key_str] = redact_json(item)
        return cleaned
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_json(item) for item in value)
    if isinstance(value, str):
        if len(value) > 512 and re.fullmatch(r"[A-Za-z0-9+/=\r\n]+", value[: min(len(value), 800)]):
            return f"[BINARY_DATA_REDACTED {len(value)} chars]"
        return redact_text(value)
    return value


def _iter_arg_strings(args: Mapping[str, Any]) -> Iterable[str]:
    for value in (args or {}).values():
        if isinstance(value, str):
            yield value
        elif isinstance(value, Mapping):
            yield from _iter_arg_strings(value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, str):
                    yield item


def _path_is_protected(path_value: Any) -> Optional[str]:
    if not path_value:
        return None
    expanded = os.path.expandvars(str(path_value)).replace("\\", "/").lower()
    for marker in _PROTECTED_PATH_MARKERS:
        if marker in expanded:
            return marker
    return None


def _url_or_target_is_blocked(value: Any) -> Optional[str]:
    target = str(value or "").strip().lower()
    if not target:
        return None
    parsed = urlparse(target if re.match(r"^[a-z][a-z0-9+\-.]*://", target) else f"https://{target}")
    host = (parsed.netloc or parsed.path.split("/")[0]).lower()
    combined = f"{host} {parsed.path}".lower()
    if "/api/remote/account/secrets/reveal" in combined:
        return "raw secret reveal endpoints are manual UI-only"
    if parsed.scheme == "file":
        return "file URL navigation is blocked for browser tools"
    for marker in _EXPLICIT_DOMAIN_MARKERS:
        if marker in combined:
            return "explicit adult destination is blocked"
    for marker in _ILLEGAL_DESTINATION_MARKERS:
        if marker in combined:
            return "illegal or abusive destination is blocked"
    return None


def _command_block_reason(command: str) -> tuple[Optional[str], str]:
    lower = str(command or "").lower()
    for pattern in _CREDENTIAL_COMMAND_PATTERNS:
        if re.search(pattern, lower, re.I | re.S):
            return "credential extraction or secret access is blocked", "secret_access"
    for marker in _PROTECTED_PATH_MARKERS:
        if marker in lower.replace("\\", "/"):
            return f"protected credential/app data path is blocked: {marker}", "secret_access"
    for pattern in _DESTRUCTIVE_COMMAND_PATTERNS:
        if re.search(pattern, lower, re.I | re.S):
            return "destructive system command requires Full Permissions and confirmation", "destructive_command"
    for pattern in _SERVER_TAMPER_PATTERNS:
        if re.search(pattern, lower, re.I | re.S):
            return "server/database tampering requires Full Permissions and confirmation", "server_admin"
    return None, "shell"


def _tool_risk(tool_name: str, args: Mapping[str, Any]) -> str:
    if tool_name in _COMMAND_TOOLS:
        return "shell"
    if tool_name in _WRITE_TOOLS:
        return "file_write"
    if tool_name in _ACTIVE_BROWSER_TOOLS:
        return "browser_control"
    if tool_name in _ACTIVE_DESKTOP_TOOLS:
        return "desktop_control"
    if tool_name in _APP_OPEN_TOOLS:
        return "app_launch"
    if tool_name in _EXTERNAL_SEND_TOOLS:
        return "external_send"
    if tool_name in _OBSERVATION_TOOLS:
        return "observe"
    if "secret" in tool_name.lower() or "credential" in tool_name.lower():
        return "secret_access"
    return "safe"


def evaluate_tool_call(
    tool_name: str,
    args: Optional[Mapping[str, Any]],
    *,
    context: Optional[SecurityContext] = None,
) -> SecurityDecision:
    name = str(tool_name or "").strip()
    payload = args or {}
    ctx = context or default_security_context()
    mode = normalize_permission_mode(ctx.permission_mode)
    risk = _tool_risk(name, payload)

    if name in _COMMAND_TOOLS:
        reason, command_risk = _command_block_reason(str(payload.get("command") or ""))
        risk = command_risk
        if reason:
            if mode == FULL_PERMISSION and command_risk in {"destructive_command", "server_admin"}:
                return SecurityDecision(ACTION_CONFIRM, reason, risk, metadata={"tool": name})
            return SecurityDecision(ACTION_DENY, reason, risk, command_risk in {"destructive_command", "server_admin"})

    for key in ("path", "cwd", "target", "file", "filename"):
        marker = _path_is_protected(payload.get(key))
        if marker:
            return SecurityDecision(
                ACTION_DENY,
                f"Access to protected credential/app data path is blocked: {marker}",
                "secret_access",
            )

    if name in _WRITE_TOOLS:
        binding_status = str(ctx.workspace_binding_status or "").strip().lower()
        if ctx.workspace_write_enabled is False or binding_status in {"missing", "read_only", "readonly", "needs_reconnect", "suspicious"}:
            return SecurityDecision(
                ACTION_DENY,
                "File-writing tools are blocked until this workspace is reconnected on this machine.",
                "workspace_write_blocked",
                metadata={"workspace_binding_status": binding_status or None},
            )
        workspace_value = str(ctx.workspace_path or "").strip()
        if workspace_value:
            try:
                workspace_path = Path(os.path.expandvars(workspace_value)).expanduser()
                if not workspace_path.exists():
                    return SecurityDecision(
                        ACTION_DENY,
                        "File-writing tools are blocked because the session workspace path is missing on this machine.",
                        "workspace_write_blocked",
                        metadata={"workspace_path": workspace_value},
                    )
            except Exception:
                return SecurityDecision(
                    ACTION_DENY,
                    "File-writing tools are blocked because the session workspace path could not be validated.",
                    "workspace_write_blocked",
                    metadata={"workspace_path": workspace_value},
                )
        for text in _iter_arg_strings(payload):
            if "[REDACTED_SECRET]" in redact_text(text):
                return SecurityDecision(
                    ACTION_DENY,
                    "Writing content that appears to contain secrets is blocked by default.",
                    "secret_write",
                )

    if name in _ACTIVE_BROWSER_TOOLS or name in _APP_OPEN_TOOLS or name in _NETWORK_TOOLS:
        for key in ("url", "target", "app", "name", "path"):
            reason = _url_or_target_is_blocked(payload.get(key))
            if reason:
                return SecurityDecision(ACTION_DENY, reason, "explicit_or_illegal_destination")

    if mode == LOW_PERMISSION and risk in {
        "shell",
        "file_write",
        "browser_control",
        "desktop_control",
        "app_launch",
        "external_send",
    }:
        return SecurityDecision(
            ACTION_CONFIRM,
            f"Low permission mode requires confirmation before {risk.replace('_', ' ')}.",
            risk,
            metadata={"tool": name},
        )

    return SecurityDecision(ACTION_ALLOW, risk=risk)


def _contains_explicit_or_illegal_text(text: str) -> Optional[str]:
    lower = str(text or "").lower()
    for marker in _EXPLICIT_DOMAIN_MARKERS:
        if marker in lower:
            return "explicit adult content detected"
    for marker in _ILLEGAL_DESTINATION_MARKERS:
        if marker in lower:
            return "illegal or abusive content detected"
    return None


def filter_tool_result(tool_name: str, args: Optional[Mapping[str, Any]], result: Any) -> Any:
    cleaned = redact_json(result)
    if str(tool_name or "") not in _OBSERVATION_TOOLS:
        return cleaned

    observation_text = ""
    if isinstance(cleaned, Mapping):
        fields = ["description", "vision_summary", "plain_text", "unfiltered_text", "text", "formatted", "title", "url"]
        observation_text = "\n".join(str(cleaned.get(field) or "") for field in fields)
    else:
        observation_text = str(cleaned or "")
    reason = _contains_explicit_or_illegal_text(observation_text)
    if not reason:
        return cleaned

    return {
        "error": (
            f"Observation blocked because {reason}. Active interaction with this content has been stopped."
        ),
        "error_type": "security_policy",
        "tool_name": tool_name,
        "security_decision": "blocked_observation",
        "risk": "explicit_or_illegal_content",
        "retry": False,
    }


def confirmation_prompt_for(decision: SecurityDecision, *, tool_name: str, args: Mapping[str, Any]) -> str:
    safe_args = redact_json(dict(args or {}))
    return (
        f"Security confirmation required for {tool_name}.\n"
        f"Risk: {decision.risk}\n"
        f"Reason: {decision.reason}\n"
        f"Arguments: {safe_args}\n"
        "Approve this exact action?"
    )
