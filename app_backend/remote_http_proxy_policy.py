from __future__ import annotations

import base64
import re
from typing import Any, Dict, Set

from fastapi import HTTPException


def filter_remote_http_proxy_headers(headers: Dict[str, str], allowed: Set[str]) -> Dict[str, str]:
    filtered: Dict[str, str] = {}
    for key, value in dict(headers or {}).items():
        normalized = str(key or "").strip().lower()
        if normalized in allowed:
            value_text = str(value)
            if "\r" in value_text or "\n" in value_text or "\x00" in value_text:
                continue
            filtered[normalized] = value_text
    return filtered


def should_proxy_remote_http_request(method: str, path: str, *, allowed_methods: Set[str]) -> bool:
    method = method.upper()
    if method not in allowed_methods:
        return False
    if not path.startswith("/api/app/"):
        return False
    if path in {"/api/app/health", "/api/app/me"}:
        return False
    if path.startswith("/api/app/pair/") or path.startswith("/api/app/devices"):
        return False
    if path.startswith("/api/app/voice/"):
        return False
    if path == "/api/app/sessions":
        return False
    if re.fullmatch(r"/api/app/sessions/[^/]+", path):
        return method == "DELETE"
    if re.fullmatch(r"/api/app/sessions/[^/]+/activate", path):
        return False
    if path.startswith("/api/app/sessions/"):
        return True
    if path in {"/api/app/jobs", "/api/app/automations"}:
        return method != "GET"
    if path.startswith("/api/app/jobs/") or path.startswith("/api/app/automations/"):
        return True
    return (
        path == "/api/app/chat/send"
        or path == "/api/app/cron/feed"
        or path == "/api/app/events"
        or path.startswith("/api/app/events/")
        or path == "/api/app/upload"
        or path.startswith("/api/app/agent/")
        or path.startswith("/api/app/runtime/")
        or path.startswith("/api/app/screenshot/")
        or path.startswith("/api/app/telegram-bots")
        or path.startswith("/api/app/workspace/")
    )


def max_base64_chars_for_bytes(byte_limit: int) -> int:
    return ((max(0, int(byte_limit)) + 2) // 3) * 4


def remote_http_proxy_status_code(value: Any) -> int:
    try:
        status_code = int(value or 502)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Malformed remote desktop response status") from exc
    if status_code < 100 or status_code > 599:
        raise HTTPException(status_code=502, detail="Remote desktop returned an invalid status code")
    return status_code


def remote_http_proxy_body_bytes(value: Any, *, max_response_body_bytes: int) -> bytes:
    raw_body = str(value or "")
    if not raw_body:
        return b""
    if len(raw_body) > max_base64_chars_for_bytes(max_response_body_bytes):
        raise HTTPException(status_code=502, detail="Remote desktop response body is too large")
    try:
        body_bytes = base64.b64decode(raw_body, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Malformed remote desktop response body") from exc
    if len(body_bytes) > max_response_body_bytes:
        raise HTTPException(status_code=502, detail="Remote desktop response body is too large")
    return body_bytes
