from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import websockets
from websockets.client import WebSocketClientProtocol

from mobile_app.backend.desktop_runtime import start_runtime_context
from shared.runtime_paths import runtime_home


logger = logging.getLogger(__name__)

REMOTE_CONTROL_BASE_URL_ENV = "EMPLOAI_REMOTE_CONTROL_BASE_URL"
REMOTE_CONTROL_SESSION_TOKEN_ENV = "EMPLOAI_REMOTE_CONTROL_SESSION_TOKEN"
REMOTE_CONTROL_EMAIL_ENV = "EMPLOAI_REMOTE_CONTROL_EMAIL"
REMOTE_CONTROL_PASSWORD_ENV = "EMPLOAI_REMOTE_CONTROL_PASSWORD"
REMOTE_CONTROL_DESKTOP_NAME_ENV = "EMPLOAI_REMOTE_DESKTOP_NAME"
REMOTE_CONTROL_DESKTOP_KEY_ENV = "EMPLOAI_REMOTE_DESKTOP_KEY"
REMOTE_CONTROL_STATUS_PATH_ENV = "EMPLOAI_REMOTE_CONTROL_STATUS_PATH"
REMOTE_CONTROL_SESSION_FILENAME = "remote-account-session.json"
DEFAULT_REMOTE_BASE_URL = "https://api.kraitos.app"
FLEET_ACTIVE_TASK_SESSIONS: Dict[str, str] = {}
FLEET_STOP_REQUESTED_TASKS: set[str] = set()
SNAPSHOT_INTERVAL_SECONDS = 1.2
HEARTBEAT_INTERVAL_SECONDS = 12.0
POST_FINAL_RELAY_GRACE_SECONDS = 2.0
REMOTE_CLIENT_ID = "remote-desktop-bridge"
REMOTE_WS_MAX_SIZE_BYTES = 96 * 1024 * 1024

_FORWARDED_REQUEST_HEADERS = {
    "accept",
    "accept-language",
    "content-type",
}
_FORWARDED_RESPONSE_HEADERS = {
    "cache-control",
    "content-disposition",
    "content-language",
    "content-type",
    "etag",
    "last-modified",
}


_WORKER_REPORT_FIELDS = {
    "status",
    "summary",
    "evidence",
    "artifacts",
    "blockers",
    "confidence",
    "next_suggested_action",
}


def _coerce_report_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    if isinstance(value, str):
        chunks = [item.strip(" -\t") for item in re.split(r"\n|;", value) if item.strip(" -\t")]
        return chunks or [value.strip()]
    return [value]


def _extract_worker_report(text: str) -> Dict[str, Any]:
    raw_text = str(text or "").strip()
    if not raw_text:
        return {}

    candidates: list[str] = []
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, flags=re.IGNORECASE | re.DOTALL)
    candidates.extend(fenced)
    first_brace = raw_text.find("{")
    last_brace = raw_text.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        candidates.append(raw_text[first_brace:last_brace + 1])
    candidates.append(raw_text)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict) and _WORKER_REPORT_FIELDS.intersection(parsed.keys()):
            return {
                "status": str(parsed.get("status") or "").strip() or None,
                "summary": str(parsed.get("summary") or "").strip() or None,
                "evidence": _coerce_report_list(parsed.get("evidence")),
                "artifacts": _coerce_report_list(parsed.get("artifacts")),
                "blockers": _coerce_report_list(parsed.get("blockers")),
                "confidence": str(parsed.get("confidence") or "").strip() or None,
                "next_suggested_action": str(parsed.get("next_suggested_action") or "").strip() or None,
                "raw": {"worker_report": parsed},
            }

    labeled: Dict[str, Any] = {}
    current_key: Optional[str] = None
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^(status|summary|evidence|artifacts|blockers|confidence|next_suggested_action)\s*:\s*(.*)$", line, flags=re.IGNORECASE)
        if match:
            current_key = match.group(1).lower()
            labeled[current_key] = match.group(2).strip()
            continue
        if current_key:
            labeled[current_key] = f"{labeled.get(current_key, '')}\n{line}".strip()
    if _WORKER_REPORT_FIELDS.intersection(labeled.keys()):
        return {
            "status": str(labeled.get("status") or "").strip() or None,
            "summary": str(labeled.get("summary") or "").strip() or None,
            "evidence": _coerce_report_list(labeled.get("evidence")),
            "artifacts": _coerce_report_list(labeled.get("artifacts")),
            "blockers": _coerce_report_list(labeled.get("blockers")),
            "confidence": str(labeled.get("confidence") or "").strip() or None,
            "next_suggested_action": str(labeled.get("next_suggested_action") or "").strip() or None,
            "raw": {"worker_report": labeled},
        }
    return {}


@dataclass
class RemoteDesktopConfig:
    remote_base_url: str
    session_token: str
    email: str
    password: str
    desktop_name: str
    device_key: str


def _remote_status_path() -> Optional[Path]:
    raw = str(os.getenv(REMOTE_CONTROL_STATUS_PATH_ENV, "") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def _write_remote_status(
    *,
    state: str,
    detail: str,
    desktop_id: Optional[str] = None,
    desktop_name: Optional[str] = None,
    ready: bool = False,
) -> None:
    path = _remote_status_path()
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {
        "state": state,
        "detail": detail,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    if desktop_id:
        payload["desktopId"] = desktop_id
    if desktop_name:
        payload["desktopName"] = desktop_name
    if ready:
        payload["readyAt"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _normalize_base_url(value: str) -> str:
    return value.strip().rstrip("/")


def _remote_session_file_payload() -> Dict[str, Any]:
    try:
        path = runtime_home() / REMOTE_CONTROL_SESSION_FILENAME
    except Exception:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_remote_desktop_config() -> RemoteDesktopConfig:
    session_payload = _remote_session_file_payload()
    remote_base_url = _normalize_base_url(
        os.getenv(REMOTE_CONTROL_BASE_URL_ENV, "")
        or str(session_payload.get("apiBaseUrl") or session_payload.get("api_base_url") or "")
        or DEFAULT_REMOTE_BASE_URL
    )
    session_token = str(
        os.getenv(REMOTE_CONTROL_SESSION_TOKEN_ENV, "")
        or session_payload.get("sessionToken")
        or session_payload.get("session_token")
        or ""
    ).strip()
    email = str(os.getenv(REMOTE_CONTROL_EMAIL_ENV, "") or "").strip()
    password = str(os.getenv(REMOTE_CONTROL_PASSWORD_ENV, "") or "").strip()
    desktop_name = str(os.getenv(REMOTE_CONTROL_DESKTOP_NAME_ENV, "") or "").strip() or "EmploAI Desktop"
    device_key = str(os.getenv(REMOTE_CONTROL_DESKTOP_KEY_ENV, "") or "").strip() or "desktop-default"
    if not remote_base_url:
        raise RuntimeError(f"{REMOTE_CONTROL_BASE_URL_ENV} is required")
    if not session_token and (not email or not password):
        raise RuntimeError(
            f"{REMOTE_CONTROL_SESSION_TOKEN_ENV} or {REMOTE_CONTROL_EMAIL_ENV}/{REMOTE_CONTROL_PASSWORD_ENV} is required"
        )
    return RemoteDesktopConfig(
        remote_base_url=remote_base_url,
        session_token=session_token,
        email=email,
        password=password,
        desktop_name=desktop_name,
        device_key=device_key,
    )


def _ws_url_from_base(base_url: str, path: str) -> str:
    normalized = _normalize_base_url(base_url)
    if normalized.startswith("https://"):
        return f"wss://{normalized[len('https://'):]}/{path.lstrip('/')}"
    if normalized.startswith("http://"):
        return f"ws://{normalized[len('http://'):]}/{path.lstrip('/')}"
    raise RuntimeError(f"Unsupported base URL: {base_url}")


async def _remote_login(config: RemoteDesktopConfig) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{config.remote_base_url}/api/remote/auth/login",
            json={
                "email": config.email,
                "password": config.password,
                "actor_kind": "desktop",
                "device_name": config.desktop_name,
                "device_platform": "desktop-electron",
                "device_key": config.device_key,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if str(payload.get("status") or "") == "otp_required":
            raise RuntimeError(
                "Email/password remote login now requires OTP verification. "
                "Sign in interactively once and use the saved remote session token for the desktop relay."
            )
        return payload


async def _remote_account_profile(config: RemoteDesktopConfig, token: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{config.remote_base_url}/api/remote/account/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        return response.json()


async def _remote_authenticate(config: RemoteDesktopConfig) -> Dict[str, Any]:
    if config.session_token:
        try:
            profile = await _remote_account_profile(config, config.session_token)
            if str(profile.get("actor_kind") or "") != "desktop":
                raise RuntimeError("Stored remote session token is not a desktop token")
            return {
                "session_token": config.session_token,
                "desktop": profile.get("desktop") or {},
                "user": profile.get("user") or {},
            }
        except Exception:
            if not (config.email and config.password):
                raise
            logger.warning("Stored remote session token failed; falling back to email/password login")
    return await _remote_login(config)


async def _request_json(
    client: httpx.AsyncClient,
    *,
    method: str,
    url: str,
    token: str,
    json_body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    response = await client.request(
        method,
        url,
        json=json_body,
        headers={"Authorization": f"Bearer {token}"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected response shape from {url}")
    return payload


async def _request_list(
    client: httpx.AsyncClient,
    *,
    url: str,
    token: str,
) -> list[dict[str, Any]]:
    response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected response shape from {url}")
    return [item for item in payload if isinstance(item, dict)]


def _filtered_headers(raw: Dict[str, Any], allowed: set[str]) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for key, value in dict(raw or {}).items():
        normalized = str(key or "").strip().lower()
        if not normalized or normalized not in allowed:
            continue
        headers[normalized] = str(value)
    return headers


async def _relay_local_http_request(
    client: httpx.AsyncClient,
    *,
    local_api_base_url: str,
    local_token: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    method = str(payload.get("method") or "GET").strip().upper()
    path = str(payload.get("path") or "").strip()
    query_string = str(payload.get("query_string") or "").strip()
    if not path.startswith("/api/app/"):
        raise RuntimeError("Remote HTTP relay only supports /api/app paths")

    url = f"{local_api_base_url.rstrip('/')}{path}"
    if query_string:
        url = f"{url}?{query_string}"

    headers = _filtered_headers(dict(payload.get("headers") or {}), _FORWARDED_REQUEST_HEADERS)
    headers["authorization"] = f"Bearer {local_token}"

    body_base64 = str(payload.get("body_base64") or "")
    body = base64.b64decode(body_base64) if body_base64 else b""
    response = await client.request(method, url, headers=headers, content=body)
    response_headers = _filtered_headers(dict(response.headers), _FORWARDED_RESPONSE_HEADERS)
    return {
        "status_code": int(response.status_code),
        "headers": response_headers,
        "body_base64": base64.b64encode(response.content).decode("ascii"),
    }


async def _collect_local_snapshot(local_api_base_url: str, local_token: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        profile = await _request_json(
            client,
            method="GET",
            url=f"{local_api_base_url}/api/app/me",
            token=local_token,
        )
        sessions = await _request_list(
            client,
            url=f"{local_api_base_url}/api/app/sessions",
            token=local_token,
        )
        jobs = await _request_list(
            client,
            url=f"{local_api_base_url}/api/app/jobs",
            token=local_token,
        )
        sidebar_state = await _request_json(
            client,
            method="GET",
            url=f"{local_api_base_url}/api/app/sidebar-state",
            token=local_token,
        )
        current_session_id = str(profile.get("current_session_id") or "").strip() or None
        session_details: Dict[str, Any] = {}
        if current_session_id:
            try:
                detail = await _request_json(
                    client,
                    method="GET",
                    url=f"{local_api_base_url}/api/app/sessions/{current_session_id}",
                    token=local_token,
                )
                session_details[current_session_id] = detail
            except Exception:
                logger.exception("Failed collecting local detail for session %s", current_session_id)
        return {
            "current_session_id": current_session_id,
            "current_model": profile.get("current_model"),
            "current_variant": profile.get("current_variant"),
            "sessions": sessions,
            "session_details": session_details,
            "jobs": jobs,
            "sidebar_state": dict(sidebar_state.get("state") or {}),
        }


async def _send_json(ws: WebSocketClientProtocol, send_lock: asyncio.Lock, payload: Dict[str, Any]) -> None:
    async with send_lock:
        await ws.send(json.dumps(payload))


def _map_local_ws_event_to_sync_event(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    event_type = str(data.get("type") or "").strip()
    session_id = str(data.get("session_id") or "").strip() or None
    payload = dict(data.get("payload") or {})
    if event_type in {
        "user_message",
        "assistant_delta",
        "assistant_final",
        "tool_event",
        "log",
        "status",
        "warning",
        "error",
        "task_board",
        "timeline_event",
        "session_sync",
        "current_session_changed",
        "artifact_created",
    }:
        return {
            "type": event_type,
            "session_id": session_id,
            "payload": payload,
        }
    return None


def _terminal_local_chat_event_error(data: Dict[str, Any]) -> Optional[str]:
    event_type = str(data.get("type") or "").strip()
    payload = dict(data.get("payload") or {})
    message = str(payload.get("message") or "").strip()
    code = str(payload.get("code") or "").strip()
    if event_type == "error":
        return message or "Local chat turn failed"
    if event_type != "warning":
        return None
    normalized_message = message.lower()
    if (
        code == "session_unavailable"
        or "already processing another message" in normalized_message
        or "empty message ignored" in normalized_message
    ):
        return message or "Local chat turn was not accepted"
    return None


async def _relay_local_chat_command(
    *,
    local_api_base_url: str,
    local_token: str,
    session_id: Optional[str],
    text: str,
    source_format: str,
    interrupt_policy: str,
    source_client_id: Optional[str],
    remote_ws: WebSocketClientProtocol,
    send_lock: asyncio.Lock,
) -> Dict[str, Any]:
    params = [f"token={local_token}", f"client_id={REMOTE_CLIENT_ID}"]
    if session_id:
        params.append(f"session_id={session_id}")
    local_ws_url = _ws_url_from_base(local_api_base_url, f"ws/app/chat?{'&'.join(params)}")
    async with websockets.connect(local_ws_url, max_size=16 * 1024 * 1024) as local_ws:
        await local_ws.send(
            json.dumps(
                {
                    "text": text,
                    "session_id": session_id,
                    "source_format": source_format,
                    "interrupt_policy": interrupt_policy,
                    "source_client_id": source_client_id,
                }
            )
        )
        seen_assistant_final = False
        assistant_final_payload: Dict[str, Any] = {}
        final_session_id = session_id
        while True:
            try:
                if seen_assistant_final:
                    raw = await asyncio.wait_for(
                        local_ws.recv(),
                        timeout=POST_FINAL_RELAY_GRACE_SECONDS,
                    )
                else:
                    raw = await local_ws.recv()
            except asyncio.TimeoutError:
                if seen_assistant_final:
                    break
                raise
            data = json.loads(raw)
            mapped = _map_local_ws_event_to_sync_event(data)
            if mapped is not None:
                await _send_json(
                    remote_ws,
                    send_lock,
                    {
                        "type": "sync_event",
                        "payload": mapped,
                    },
                )
            event_type = str(data.get("type") or "")
            if event_type == "assistant_final":
                seen_assistant_final = True
                assistant_final_payload = dict(data.get("payload") or {})
                final_session_id = str(data.get("session_id") or final_session_id or "").strip() or final_session_id
            elif seen_assistant_final and event_type == "session_sync":
                break
            terminal_error = _terminal_local_chat_event_error(data)
            if terminal_error:
                raise RuntimeError(terminal_error)
        return {
            "session_id": final_session_id,
            "assistant_text": str(assistant_final_payload.get("text") or ""),
            "assistant_final": assistant_final_payload,
        }


async def _handle_command(
    *,
    command_name: str,
    payload: Dict[str, Any],
    local_api_base_url: str,
    local_token: str,
    remote_ws: WebSocketClientProtocol,
    send_lock: asyncio.Lock,
) -> Optional[Dict[str, Any]]:
    timeout = httpx.Timeout(120.0, connect=30.0, read=120.0, write=120.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if command_name == "http_request":
            return await _relay_local_http_request(
                client,
                local_api_base_url=local_api_base_url,
                local_token=local_token,
                payload=payload,
            )

        if command_name == "create_session":
            response = await client.post(
                f"{local_api_base_url}/api/app/sessions",
                headers={"Authorization": f"Bearer {local_token}"},
                json={
                    "name": payload.get("name"),
                    "workspace": payload.get("workspace"),
                        "workspace_id": payload.get("workspace_id"),
                        "workspace_binding_status": payload.get("workspace_binding_status"),
                        "telegram_bot_config_id": payload.get("telegram_bot_config_id"),
                        "enabled_tool_packs": payload.get("enabled_tool_packs") or [],
                        "security_permission_mode": payload.get("security_permission_mode"),
                        "headless_eligible": bool(payload.get("headless_eligible", False)),
                        "fleet_identity_id": payload.get("fleet_identity_id"),
                        "fleet_identity_role": payload.get("fleet_identity_role"),
                        "fleet_worker_id": payload.get("fleet_worker_id"),
                    },
                )
            response.raise_for_status()
            result = response.json()
            return result if isinstance(result, dict) else {}

        if command_name == "activate_session":
            session_id = str(payload.get("session_id") or "").strip()
            if not session_id:
                return None
            response = await client.post(
                f"{local_api_base_url}/api/app/sessions/{session_id}/activate",
                headers={"Authorization": f"Bearer {local_token}"},
            )
            response.raise_for_status()
            result = response.json()
            return result if isinstance(result, dict) else {}

        if command_name == "delete_session":
            session_id = str(payload.get("session_id") or "").strip()
            if not session_id:
                return None
            response = await client.delete(
                f"{local_api_base_url}/api/app/sessions/{session_id}",
                headers={"Authorization": f"Bearer {local_token}"},
            )
            response.raise_for_status()
            result = response.json()
            return result if isinstance(result, dict) else {}

        if command_name == "chat_send":
            await _relay_local_chat_command(
                local_api_base_url=local_api_base_url,
                local_token=local_token,
                session_id=str(payload.get("session_id") or "").strip() or None,
                text=str(payload.get("text") or ""),
                source_format=str(payload.get("source_format") or "app_text"),
                interrupt_policy=str(payload.get("interrupt_policy") or "none"),
                source_client_id=str(payload.get("source_client_id") or "").strip() or None,
                remote_ws=remote_ws,
                send_lock=send_lock,
            )
            return None

        if command_name == "fleet_run_task":
            task_id = str(payload.get("task_id") or "").strip()
            worker_id = str(payload.get("worker_id") or "").strip()
            worker_name = str(payload.get("worker_name") or "").strip() or "Worker"
            prompt = str(payload.get("prompt") or "").strip()
            task_metadata = dict(payload.get("metadata") or {})
            if not task_id or not worker_id or not prompt:
                raise ValueError("task_id, worker_id, and prompt are required")

            await _send_json(
                remote_ws,
                send_lock,
                {
                    "type": "fleet_task_status",
                    "payload": {
                        "task_id": task_id,
                        "worker_id": worker_id,
                        "status": "running",
                        "metadata": {"detail": "Worker accepted task"},
                    },
                },
            )
            try:
                session_id = str(payload.get("target_session_id") or task_metadata.get("target_session_id") or "").strip() or None
                if not session_id:
                    response = await client.post(
                        f"{local_api_base_url}/api/app/sessions",
                        headers={"Authorization": f"Bearer {local_token}"},
                        json={
                            "name": f"{worker_name}: {task_id[-6:]}",
                            "workspace": payload.get("workspace"),
                            "telegram_bot_config_id": payload.get("telegram_bot_config_id"),
                            "enabled_tool_packs": payload.get("enabled_tool_packs") or [],
                            "security_permission_mode": payload.get("security_permission_mode"),
                            "headless_eligible": True,
                            "fleet_identity_id": payload.get("fleet_identity_id"),
                            "fleet_identity_role": "worker",
                            "fleet_worker_id": worker_id,
                        },
                    )
                    response.raise_for_status()
                    created = response.json()
                    session_payload = created.get("session") if isinstance(created, dict) else {}
                    session_id = str((session_payload or {}).get("id") or "").strip() or None
                if session_id:
                    FLEET_ACTIVE_TASK_SESSIONS[task_id] = session_id
                if task_id in FLEET_STOP_REQUESTED_TASKS:
                    stopped_summary = "Task stopped by manager before the worker turn started."
                    await _send_json(
                        remote_ws,
                        send_lock,
                        {
                            "type": "fleet_task_report",
                            "payload": {
                                "task_id": task_id,
                                "worker_id": worker_id,
                                "status": "stopped",
                                "summary": stopped_summary,
                                "evidence": [],
                                "artifacts": [],
                                "blockers": ["Stopped by manager"],
                                "confidence": "medium",
                                "next_suggested_action": "Review the task instructions and retry if needed.",
                                "raw": {
                                    "session_id": session_id,
                                    "stopped": True,
                                    "stopped_before_start": True,
                                },
                            },
                        },
                    )
                    return {
                        "task_id": task_id,
                        "worker_id": worker_id,
                        "session_id": session_id,
                        "stopped": True,
                        "summary": stopped_summary,
                    }
                result = await _relay_local_chat_command(
                    local_api_base_url=local_api_base_url,
                    local_token=local_token,
                    session_id=session_id,
                    text=prompt,
                    source_format="app_text",
                    interrupt_policy="none",
                    source_client_id=f"fleet:{task_id}",
                    remote_ws=remote_ws,
                    send_lock=send_lock,
                )
                stop_requested = task_id in FLEET_STOP_REQUESTED_TASKS
                summary = str(result.get("assistant_text") or "").strip() or "Task completed."
                parsed_report = _extract_worker_report(summary)
                report_payload = {
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "status": "stopped" if stop_requested else "completed",
                    "summary": "Task stopped by manager." if stop_requested else summary,
                    "evidence": [],
                    "artifacts": [],
                    "blockers": ["Stopped by manager"] if stop_requested else [],
                    "confidence": "medium" if stop_requested else None,
                    "next_suggested_action": "Review the partial worker transcript if needed." if stop_requested else None,
                    "raw": {
                        "session_id": result.get("session_id") or session_id,
                        "assistant_final": result.get("assistant_final") or {},
                        "stopped": stop_requested,
                    },
                }
                if parsed_report and not stop_requested:
                    report_payload.update({
                        "status": parsed_report.get("status") or report_payload["status"],
                        "summary": parsed_report.get("summary") or report_payload["summary"],
                        "evidence": parsed_report.get("evidence") if parsed_report.get("evidence") is not None else report_payload["evidence"],
                        "artifacts": parsed_report.get("artifacts") if parsed_report.get("artifacts") is not None else report_payload["artifacts"],
                        "blockers": parsed_report.get("blockers") if parsed_report.get("blockers") is not None else report_payload["blockers"],
                        "confidence": parsed_report.get("confidence") or report_payload["confidence"],
                        "next_suggested_action": parsed_report.get("next_suggested_action") or report_payload["next_suggested_action"],
                    })
                    report_payload["raw"] = {
                        **dict(report_payload.get("raw") or {}),
                        **dict(parsed_report.get("raw") or {}),
                    }
                await _send_json(remote_ws, send_lock, {"type": "fleet_task_report", "payload": report_payload})
                return {
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "session_id": result.get("session_id") or session_id,
                    "summary": summary,
                }
            except Exception as exc:
                await _send_json(
                    remote_ws,
                    send_lock,
                    {
                        "type": "fleet_task_report",
                        "payload": {
                            "task_id": task_id,
                            "worker_id": worker_id,
                            "status": "failed",
                            "summary": f"Worker task failed: {type(exc).__name__}: {exc}",
                            "evidence": [],
                            "artifacts": [],
                            "blockers": [str(exc)],
                            "confidence": "low",
                            "next_suggested_action": "Inspect worker runtime logs and retry.",
                            "raw": {"error": str(exc)},
                        },
                    },
                )
                raise
            finally:
                FLEET_ACTIVE_TASK_SESSIONS.pop(task_id, None)
                FLEET_STOP_REQUESTED_TASKS.discard(task_id)

        if command_name == "fleet_worker_preview":
            preview_id = str(payload.get("preview_id") or "").strip()
            worker_id = str(payload.get("worker_id") or "").strip()
            worker_name = str(payload.get("display_name") or payload.get("worker_name") or "").strip() or "Worker"
            if not preview_id or not worker_id:
                raise ValueError("preview_id and worker_id are required")
            detail = "Worker desktop acknowledged preview request; live preview capture is not enabled in this runtime yet."
            await _send_json(
                remote_ws,
                send_lock,
                {
                    "type": "status",
                    "payload": {
                        "message": f"Preview requested for {worker_name}.",
                        "fleet_preview": {
                            "preview_id": preview_id,
                            "worker_id": worker_id,
                            "status": "acknowledged",
                            "detail": detail,
                            "view_only": True,
                        },
                    },
                },
            )
            return {
                "preview_id": preview_id,
                "worker_id": worker_id,
                "status": "acknowledged",
                "detail": detail,
            }

        if command_name == "fleet_stop_task":
            task_id = str(payload.get("task_id") or "").strip()
            if not task_id:
                raise ValueError("task_id is required")
            FLEET_STOP_REQUESTED_TASKS.add(task_id)
            session_id = FLEET_ACTIVE_TASK_SESSIONS.get(task_id)
            if not session_id:
                return {
                    "stopped": False,
                    "pending": True,
                    "task_id": task_id,
                    "detail": "Stop recorded; Fleet task is not active on this desktop yet.",
                }
            response = await client.post(
                f"{local_api_base_url}/api/app/agent/control/stop?session_id={session_id}",
                headers={"Authorization": f"Bearer {local_token}"},
            )
            response.raise_for_status()
            return {"stopped": True, "task_id": task_id, "session_id": session_id}

        if command_name == "pause_run":
            target = str(payload.get("session_id") or "").strip() or None
            params = f"?session_id={target}" if target else ""
            response = await client.post(
                f"{local_api_base_url}/api/app/agent/control/pause{params}",
                headers={"Authorization": f"Bearer {local_token}"},
            )
            response.raise_for_status()
            return None

        if command_name == "stop_run":
            target = str(payload.get("session_id") or "").strip() or None
            params = f"?session_id={target}" if target else ""
            response = await client.post(
                f"{local_api_base_url}/api/app/agent/control/stop{params}",
                headers={"Authorization": f"Bearer {local_token}"},
            )
            response.raise_for_status()
            return None

        if command_name == "restart_runtime":
            target = str(payload.get("session_id") or "").strip() or None
            params = f"?session_id={target}" if target else ""
            response = await client.post(
                f"{local_api_base_url}/api/app/agent/control/restart{params}",
                headers={"Authorization": f"Bearer {local_token}"},
            )
            response.raise_for_status()
            return None

        if command_name == "update_sidebar_state":
            response = await client.put(
                f"{local_api_base_url}/api/app/sidebar-state",
                headers={
                    "Authorization": f"Bearer {local_token}",
                    "Content-Type": "application/json",
                },
                json={"state": dict(payload.get("state") or {})},
            )
            response.raise_for_status()
            return None

    return None


async def _snapshot_loop(
    ws: WebSocketClientProtocol,
    *,
    send_lock: asyncio.Lock,
    local_api_base_url: str,
    local_token: str,
    desktop_id: str,
    desktop_name: str,
) -> None:
    last_signature = ""
    last_heartbeat_at = 0.0
    while True:
        snapshot = await _collect_local_snapshot(local_api_base_url, local_token)
        envelope = {
            "desktop_id": desktop_id,
            "desktop_name": desktop_name,
            "current_session_id": snapshot.get("current_session_id"),
            "current_model": snapshot.get("current_model"),
            "current_variant": snapshot.get("current_variant"),
            "sessions": snapshot.get("sessions") or [],
            "session_details": snapshot.get("session_details") or {},
            "jobs": snapshot.get("jobs") or [],
            "sidebar_state": snapshot.get("sidebar_state") or {},
        }
        signature = json.dumps(envelope, sort_keys=True, ensure_ascii=False)
        if signature != last_signature:
            last_signature = signature
            await _send_json(ws, send_lock, {"type": "state_snapshot", "payload": envelope})

        now = asyncio.get_running_loop().time()
        if now - last_heartbeat_at >= HEARTBEAT_INTERVAL_SECONDS:
            last_heartbeat_at = now
            await _send_json(
                ws,
                send_lock,
                {
                    "type": "heartbeat",
                    "payload": {"detail": "desktop client alive"},
                },
            )
        await asyncio.sleep(SNAPSHOT_INTERVAL_SECONDS)


async def _send_snapshot_once(
    ws: WebSocketClientProtocol,
    *,
    send_lock: asyncio.Lock,
    local_api_base_url: str,
    local_token: str,
    desktop_id: str,
    desktop_name: str,
) -> None:
    snapshot = await _collect_local_snapshot(local_api_base_url, local_token)
    await _send_json(
        ws,
        send_lock,
        {
            "type": "state_snapshot",
            "payload": {
                "desktop_id": desktop_id,
                "desktop_name": desktop_name,
                "current_session_id": snapshot.get("current_session_id"),
                "current_model": snapshot.get("current_model"),
                "current_variant": snapshot.get("current_variant"),
                "sessions": snapshot.get("sessions") or [],
                "session_details": snapshot.get("session_details") or {},
                "jobs": snapshot.get("jobs") or [],
                "sidebar_state": snapshot.get("sidebar_state") or {},
            },
        },
    )


async def _send_command_result(
    ws: WebSocketClientProtocol,
    send_lock: asyncio.Lock,
    *,
    command_id: Optional[str],
    ok: bool,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[BaseException] = None,
) -> None:
    if not command_id:
        return
    payload: Dict[str, Any] = {"ok": ok}
    if ok:
        payload["result"] = result or {}
    else:
        if isinstance(error, httpx.HTTPStatusError) and error.response is not None:
            payload["status_code"] = int(error.response.status_code)
            payload["error"] = error.response.text or str(error)
        else:
            payload["error"] = str(error or "Remote desktop command failed")
        payload["error_type"] = type(error).__name__ if error else "RuntimeError"
    await _send_json(
        ws,
        send_lock,
        {
            "type": "command_result",
            "command_id": command_id,
            "payload": payload,
        },
    )


async def run_remote_desktop_client() -> None:
    logging.basicConfig(level=logging.INFO)
    _write_remote_status(state="starting", detail="Signing in to the EmploAI remote control plane...")
    config = load_remote_desktop_config()
    login = await _remote_authenticate(config)
    remote_token = str(login.get("session_token") or "")
    desktop = dict(login.get("desktop") or {})
    desktop_id = str(desktop.get("desktop_id") or "").strip()
    if not remote_token or not desktop_id:
        raise RuntimeError("Remote desktop login did not return a usable session")

    local_bootstrap = start_runtime_context()
    local_api_base_url = str(local_bootstrap.get("apiBaseUrl") or "").strip()
    local_token = str(local_bootstrap.get("accessToken") or "").strip()
    if not local_api_base_url or not local_token:
        raise RuntimeError("Local desktop runtime is not available for remote relay")
    _write_remote_status(
        state="starting",
        detail="Desktop authenticated. Connecting remote websocket...",
        desktop_id=desktop_id,
        desktop_name=config.desktop_name,
    )

    remote_ws_url = _ws_url_from_base(
        config.remote_base_url,
        f"ws/remote/desktop?token={remote_token}&desktop_id={desktop_id}",
    )

    while True:
        try:
            async with websockets.connect(remote_ws_url, max_size=REMOTE_WS_MAX_SIZE_BYTES) as ws:
                _write_remote_status(
                    state="running",
                    detail="Desktop is connected to the EmploAI remote control plane.",
                    desktop_id=desktop_id,
                    desktop_name=config.desktop_name,
                    ready=True,
                )
                send_lock = asyncio.Lock()
                snapshot_task = asyncio.create_task(
                    _snapshot_loop(
                        ws,
                        send_lock=send_lock,
                        local_api_base_url=local_api_base_url,
                        local_token=local_token,
                        desktop_id=desktop_id,
                        desktop_name=config.desktop_name,
                    )
                )
                command_tasks: set[asyncio.Task[None]] = set()

                async def run_command(message: Dict[str, Any]) -> None:
                    command_id = str(message.get("command_id") or "").strip() or None
                    payload = dict(message.get("payload") or {})
                    command_name = str(payload.pop("name", "") or "")
                    if not command_name:
                        return
                    try:
                        result = await _handle_command(
                            command_name=command_name,
                            payload=payload,
                            local_api_base_url=local_api_base_url,
                            local_token=local_token,
                            remote_ws=ws,
                            send_lock=send_lock,
                        )
                        await _send_command_result(
                            ws,
                            send_lock,
                            command_id=command_id,
                            ok=True,
                            result=result,
                        )
                    except Exception as exc:
                        logger.exception("Remote desktop command failed: %s", command_name)
                        await _send_command_result(
                            ws,
                            send_lock,
                            command_id=command_id,
                            ok=False,
                            error=exc,
                        )
                    finally:
                        try:
                            await _send_snapshot_once(
                                ws,
                                send_lock=send_lock,
                                local_api_base_url=local_api_base_url,
                                local_token=local_token,
                                desktop_id=desktop_id,
                                desktop_name=config.desktop_name,
                            )
                        except Exception:
                            logger.exception("Failed sending post-command remote snapshot")

                try:
                    async for raw in ws:
                        message = json.loads(raw)
                        if str(message.get("type") or "") != "command":
                            continue
                        task = asyncio.create_task(run_command(message))
                        command_tasks.add(task)
                        task.add_done_callback(command_tasks.discard)
                finally:
                    snapshot_task.cancel()
                    for task in list(command_tasks):
                        task.cancel()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _write_remote_status(
                state="degraded",
                detail=f"{type(exc).__name__}: {exc}",
                desktop_id=desktop_id,
                desktop_name=config.desktop_name,
            )
            logger.exception("Remote desktop client disconnected; retrying")
            await asyncio.sleep(2.0)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Connect a local desktop runtime to the EmploAI remote control plane.")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    _build_parser().parse_args(argv)
    asyncio.run(run_remote_desktop_client())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
