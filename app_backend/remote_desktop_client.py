from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

import httpx
from websockets.asyncio.client import ClientConnection, connect as websocket_connect

from app_backend.local_runtime_server import start_runtime_context
from app_backend.fleet_policy import FLEET_PREVIEW_MODE
from app_backend.fleet_worker_report import extract_worker_report
from shared.atomic_io import atomic_write_json
from shared.fleet_connection import load_fleet_connection
from shared.fleet_connection_policy import (
    connection_policy_view,
    load_connection_policy,
    normalize_connection_permissions,
    policy_signature,
    record_permission_request,
)
from shared.fleet_upstream_activity import (
    mark_upstream_request_sent,
    pending_upstream_requests,
    record_incoming_delegation,
    record_upstream_request_decision,
)
from shared.runtime_paths import runtime_home


logger = logging.getLogger(__name__)

REMOTE_CONTROL_DESKTOP_NAME_ENV = "EMPLOAI_REMOTE_DESKTOP_NAME"
REMOTE_CONTROL_DESKTOP_KEY_ENV = "EMPLOAI_REMOTE_DESKTOP_KEY"
REMOTE_CONTROL_STATUS_PATH_ENV = "EMPLOAI_REMOTE_CONTROL_STATUS_PATH"
FLEET_ACTIVE_TASK_SESSIONS: Dict[str, str] = {}
FLEET_STOP_REQUESTED_TASKS: set[str] = set()
CONNECTION_STATE_INTERVAL_SECONDS = 1.2
CAPABILITY_STATE_INTERVAL_SECONDS = 5.0
HEARTBEAT_INTERVAL_SECONDS = 12.0
POST_FINAL_RELAY_GRACE_SECONDS = 2.0
REMOTE_CLIENT_ID = "remote-desktop-bridge"
REMOTE_WS_MAX_SIZE_BYTES = 96 * 1024 * 1024

@dataclass
class RemoteDesktopConfig:
    remote_base_url: str
    session_token: str
    desktop_id: str
    desktop_name: str
    device_key: str


@dataclass
class LocalRuntimeCredentials:
    api_base_url: str
    access_token: str
    _refresh_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @classmethod
    def from_bootstrap(cls, payload: Dict[str, Any]) -> "LocalRuntimeCredentials":
        api_base_url = str(payload.get("apiBaseUrl") or "").strip()
        access_token = str(payload.get("accessToken") or "").strip()
        if not api_base_url or not access_token:
            raise RuntimeError("Local desktop runtime is not available for remote relay")
        return cls(api_base_url=api_base_url, access_token=access_token)

    async def refresh_if_stale(self, stale_access_token: str, *, force: bool = False) -> None:
        async with self._refresh_lock:
            if not force and self.access_token != stale_access_token:
                return
            bootstrap = await asyncio.to_thread(start_runtime_context)
            refreshed = LocalRuntimeCredentials.from_bootstrap(bootstrap)
            self.api_base_url = refreshed.api_base_url
            self.access_token = refreshed.access_token


def _is_local_runtime_auth_error(exc: BaseException) -> bool:
    return bool(
        isinstance(exc, httpx.HTTPStatusError)
        and exc.response is not None
        and int(exc.response.status_code) == 401
    )


def _is_local_runtime_connectivity_error(exc: BaseException) -> bool:
    return isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout))


async def _with_local_runtime_credentials(
    credentials: LocalRuntimeCredentials,
    operation: Callable[[str, str], Awaitable[Any]],
) -> Any:
    api_base_url = credentials.api_base_url
    access_token = credentials.access_token
    try:
        return await operation(api_base_url, access_token)
    except Exception as exc:
        auth_error = _is_local_runtime_auth_error(exc)
        connectivity_error = _is_local_runtime_connectivity_error(exc)
        if not auth_error and not connectivity_error:
            raise
    await credentials.refresh_if_stale(access_token, force=connectivity_error)
    return await operation(credentials.api_base_url, credentials.access_token)


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
    atomic_write_json(path, payload)


def _normalize_base_url(value: str) -> str:
    return value.strip().rstrip("/")


def _remote_session_file_payload() -> Dict[str, Any]:
    try:
        return load_fleet_connection(runtime_home())
    except Exception:
        return {}


def load_remote_desktop_config() -> RemoteDesktopConfig:
    session_payload = _remote_session_file_payload()
    remote_base_url = _normalize_base_url(
        str(session_payload.get("managerUrl") or session_payload.get("apiBaseUrl") or "")
    )
    session_token = str(
        session_payload.get("sessionToken") or ""
    ).strip()
    desktop = session_payload.get("desktop") if isinstance(session_payload.get("desktop"), dict) else {}
    desktop_id = str((desktop or {}).get("desktop_id") or "").strip()
    desktop_name = str(
        os.getenv(REMOTE_CONTROL_DESKTOP_NAME_ENV, "")
        or (desktop or {}).get("display_name")
        or "Paired EmploAI Computer"
    ).strip()
    device_key = str(os.getenv(REMOTE_CONTROL_DESKTOP_KEY_ENV, "") or "").strip() or "desktop-default"
    if not remote_base_url:
        raise RuntimeError("A locally paired Yggdrasil Fleet manager is required")
    if not session_token or not desktop_id:
        raise RuntimeError("The Fleet connection is missing its session token or paired-computer identity")
    return RemoteDesktopConfig(
        remote_base_url=remote_base_url,
        session_token=session_token,
        desktop_id=desktop_id,
        desktop_name=desktop_name,
        device_key=device_key,
    )


def _ws_url_from_base(base_url: str, path: str) -> str:
    normalized = _normalize_base_url(base_url)
    if normalized.startswith("http://"):
        return f"ws://{normalized[len('http://'):]}/{path.lstrip('/')}"
    raise RuntimeError("Paired computers only connect to their Yggdrasil manager over HTTP")


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


async def _send_json(ws: ClientConnection, send_lock: asyncio.Lock, payload: Dict[str, Any]) -> None:
    async with send_lock:
        await ws.send(json.dumps(payload))


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
    remote_ws: ClientConnection,
    send_lock: asyncio.Lock,
) -> Dict[str, Any]:
    params = [f"token={local_token}", f"client_id={REMOTE_CLIENT_ID}"]
    if session_id:
        params.append(f"session_id={session_id}")
    local_ws_url = _ws_url_from_base(local_api_base_url, f"ws/app/chat?{'&'.join(params)}")
    async with websocket_connect(local_ws_url, max_size=16 * 1024 * 1024) as local_ws:
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
        provider_failure_payload: Dict[str, Any] = {}
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
            event_type = str(data.get("type") or "")
            if event_type == "assistant_final":
                seen_assistant_final = True
                assistant_final_payload = dict(data.get("payload") or {})
                final_session_id = str(data.get("session_id") or final_session_id or "").strip() or final_session_id
            elif event_type == "run_failed":
                provider_failure_payload = dict(data.get("payload") or {})
                final_session_id = str(data.get("session_id") or final_session_id or "").strip() or final_session_id
                break
            elif seen_assistant_final and event_type == "session_sync":
                break
            terminal_error = _terminal_local_chat_event_error(data)
            if terminal_error:
                raise RuntimeError(terminal_error)
        return {
            "session_id": final_session_id,
            "assistant_text": str(assistant_final_payload.get("text") or ""),
            "assistant_final": assistant_final_payload,
            "failure": provider_failure_payload or None,
        }


async def _handle_command(
    *,
    command_name: str,
    payload: Dict[str, Any],
    local_api_base_url: str,
    local_token: str,
    remote_ws: ClientConnection,
    send_lock: asyncio.Lock,
) -> Optional[Dict[str, Any]]:
    timeout = httpx.Timeout(120.0, connect=30.0, read=120.0, write=120.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        home = runtime_home()
        policy = load_connection_policy(home) if home else connection_policy_view({})
        permissions = normalize_connection_permissions(policy.get("permissions"))

        if command_name == "fleet_permission_request":
            if not home:
                raise RuntimeError("The local runtime home is unavailable")
            return record_permission_request(
                home,
                request_id=str(payload.get("request_id") or "").strip() or None,
                requested=dict(payload.get("permissions") or {}),
                reason=str(payload.get("reason") or "").strip() or None,
            )

        if command_name == "fleet_upstream_request_decision":
            if not home:
                raise RuntimeError("The local runtime home is unavailable")
            return record_upstream_request_decision(
                home,
                request_id=str(payload.get("request_id") or "").strip(),
                decision=str(payload.get("decision") or "").strip(),
                response=str(payload.get("response") or "").strip() or None,
            )

        if command_name == "fleet_create_local_worker":
            if not permissions.get("create_workers", False):
                raise PermissionError("Creating workers from the paired manager is not allowed on this computer")
            display_name = str(payload.get("display_name") or "").strip()
            if not display_name:
                raise ValueError("display_name is required")
            response = await client.post(
                f"{local_api_base_url}/api/fleet/workers/local",
                headers={"Authorization": f"Bearer {local_token}"},
                json={
                    "display_name": display_name,
                    "metadata": {"created_by": "paired_manager_request"},
                },
            )
            response.raise_for_status()
            created = response.json()
            worker = created if isinstance(created, dict) else {}
            return {
                "created": True,
                "display_name": str(worker.get("display_name") or display_name),
                "detail": "The worker was created locally on the paired computer.",
            }

        if command_name == "fleet_delegate":
            delegation_id = str(payload.get("delegation_id") or "").strip()
            prompt = str(payload.get("prompt") or "").strip()
            target_kind = str(payload.get("target_kind") or "manager").strip().lower()
            target_selector = str(payload.get("target_selector") or "").strip()
            if not delegation_id or not prompt:
                raise ValueError("delegation_id and prompt are required")
            if target_kind not in {"manager", "worker"}:
                raise ValueError("target_kind must be manager or worker")
            permission_key = "delegate_workers" if target_kind == "worker" else "delegate_manager"
            if not permissions.get(permission_key, False):
                raise PermissionError(f"Delegating to the local {target_kind} agent is not allowed on this computer")

            if home:
                try:
                    record_incoming_delegation(
                        home,
                        delegation_id=delegation_id,
                        message=prompt,
                        identity_label=target_selector or ("Main manager" if target_kind == "manager" else "Worker"),
                        status="running",
                    )
                except Exception:
                    logger.exception("Failed recording incoming Fleet delegation activity")

            await _send_json(
                remote_ws,
                send_lock,
                {
                    "type": "fleet_delegation_status",
                    "payload": {"delegation_id": delegation_id, "status": "running"},
                },
            )
            try:
                local_fleet = await _request_json(
                    client,
                    method="GET",
                    url=f"{local_api_base_url}/api/fleet/snapshot",
                    token=local_token,
                )
                identities = [item for item in list(local_fleet.get("identities") or []) if isinstance(item, dict)]
                if target_kind == "manager":
                    identity = next((item for item in identities if str(item.get("role") or "") == "manager"), None)
                else:
                    needle = target_selector.casefold()
                    identity = next(
                        (
                            item for item in identities
                            if str(item.get("role") or "") == "worker"
                            and needle
                            and needle in {
                                str(item.get("identity_id") or "").casefold(),
                                str(item.get("worker_id") or "").casefold(),
                                str(item.get("display_name") or "").casefold(),
                            }
                        ),
                        None,
                    )
                if not identity:
                    target_label = f"worker {target_selector!r}" if target_kind == "worker" else "manager"
                    raise LookupError(f"The local {target_label} agent was not found")

                if home:
                    try:
                        record_incoming_delegation(
                            home,
                            delegation_id=delegation_id,
                            message=prompt,
                            identity_id=str(identity.get("identity_id") or "").strip() or None,
                            identity_label=str(identity.get("display_name") or target_kind),
                            status="running",
                        )
                    except Exception:
                        logger.exception("Failed updating incoming Fleet delegation target")

                response = await client.post(
                    f"{local_api_base_url}/api/app/sessions",
                    headers={"Authorization": f"Bearer {local_token}"},
                    json={
                        "name": f"Delegation {delegation_id[-6:]}",
                        "enabled_tool_packs": [],
                        "headless_eligible": True,
                        "fleet_identity_id": identity.get("identity_id"),
                        "fleet_identity_role": identity.get("role"),
                        "fleet_worker_id": identity.get("worker_id"),
                    },
                )
                response.raise_for_status()
                created = response.json()
                session_payload = created.get("session") if isinstance(created, dict) else {}
                session_id = str((session_payload or {}).get("id") or "").strip() or None
                if not session_id:
                    raise RuntimeError("The local agent session could not be created")
                FLEET_ACTIVE_TASK_SESSIONS[delegation_id] = session_id
                result = await _relay_local_chat_command(
                    local_api_base_url=local_api_base_url,
                    local_token=local_token,
                    session_id=session_id,
                    text=prompt,
                    source_format="fleet_delegation",
                    interrupt_policy="none",
                    source_client_id=f"fleet-delegation:{delegation_id}",
                    remote_ws=remote_ws,
                    send_lock=send_lock,
                )
                failure = result.get("failure") if isinstance(result.get("failure"), dict) else None
                summary = str(result.get("assistant_text") or "").strip()
                report = {
                    "delegation_id": delegation_id,
                    "status": "failed" if failure else "completed",
                    "summary": str((failure or {}).get("user_message") or summary or "Delegation completed."),
                    "evidence": [],
                    "artifacts": [],
                    "blockers": [
                        {
                            "code": str(failure.get("code") or "provider_failed"),
                            "message": str(failure.get("user_message") or "The provider could not complete this delegation."),
                        }
                    ] if failure else [],
                    "confidence": "low" if failure else "medium",
                    "next_suggested_action": "Review the provider configuration on the paired computer." if failure else None,
                    "target_kind": target_kind,
                    "target_label": str(identity.get("display_name") or target_kind),
                }
                parsed = extract_worker_report(summary) if summary and not failure else None
                if parsed:
                    for key in ("status", "summary", "evidence", "artifacts", "blockers", "confidence", "next_suggested_action"):
                        if parsed.get(key) is not None:
                            report[key] = parsed.get(key)
                if home:
                    try:
                        record_incoming_delegation(
                            home,
                            delegation_id=delegation_id,
                            message=prompt,
                            identity_id=str(identity.get("identity_id") or "").strip() or None,
                            identity_label=str(identity.get("display_name") or target_kind),
                            status=str(report.get("status") or "completed"),
                            report=report,
                        )
                    except Exception:
                        logger.exception("Failed recording completed Fleet delegation activity")
                await _send_json(remote_ws, send_lock, {"type": "fleet_delegation_report", "payload": report})
                return report
            except Exception as exc:
                report = {
                    "delegation_id": delegation_id,
                    "status": "failed",
                    "summary": "The paired computer could not complete the delegation.",
                    "evidence": [],
                    "artifacts": [],
                    "blockers": [str(exc)],
                    "confidence": "low",
                    "next_suggested_action": "Check the target agent name and connection permissions, then retry.",
                    "target_kind": target_kind,
                }
                if home:
                    try:
                        record_incoming_delegation(
                            home,
                            delegation_id=delegation_id,
                            message=prompt,
                            identity_label=target_selector or target_kind,
                            status="failed",
                            report=report,
                        )
                    except Exception:
                        logger.exception("Failed recording failed Fleet delegation activity")
                await _send_json(remote_ws, send_lock, {"type": "fleet_delegation_report", "payload": report})
                raise
            finally:
                FLEET_ACTIVE_TASK_SESSIONS.pop(delegation_id, None)

        if command_name in {
            "provider_availability_sync",
            "http_request",
            "create_session",
            "activate_session",
            "delete_session",
            "rename_session",
            "chat_send",
            "pause_run",
            "stop_run",
            "restart_runtime",
            "update_sidebar_state",
        }:
            raise PermissionError(
                "Paired computers accept Fleet delegation envelopes only; direct runtime, chat, session, provider, sidebar, and HTTP control is disabled"
            )

        if command_name == "fleet_run_task":
            if not permissions.get("delegate_workers", False):
                raise PermissionError("Delegating to local workers is not allowed on this computer")
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
                provider_failure = result.get("failure") if isinstance(result.get("failure"), dict) else None
                if provider_failure and not stop_requested:
                    report_payload = {
                        "task_id": task_id,
                        "worker_id": worker_id,
                        "status": "failed",
                        "summary": str(provider_failure.get("user_message") or "The provider could not complete this worker task."),
                        "evidence": [],
                        "artifacts": [],
                        "blockers": [{
                            "code": str(provider_failure.get("code") or "provider_failed"),
                            "provider_id": provider_failure.get("provider_id"),
                            "model_id": provider_failure.get("model_id"),
                        }],
                        "confidence": "low",
                        "next_suggested_action": "Switch to an available provider and explicitly retry the failed task.",
                        "raw": {
                            "session_id": result.get("session_id") or session_id,
                            "provider_failure": provider_failure,
                        },
                    }
                    await _send_json(remote_ws, send_lock, {"type": "fleet_task_report", "payload": report_payload})
                    return {
                        "task_id": task_id,
                        "worker_id": worker_id,
                        "session_id": result.get("session_id") or session_id,
                        "failure": provider_failure,
                    }
                summary = str(result.get("assistant_text") or "").strip() or "Task completed."
                parsed_report = extract_worker_report(summary)
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
                elif not stop_requested:
                    report_payload.update({
                        "status": "needs_review",
                        "summary": summary,
                        "blockers": [{
                            "kind": "report_validation",
                            "message": "The worker response did not contain the required structured report fields.",
                        }],
                        "confidence": "low",
                        "next_suggested_action": "Review the worker transcript and retry with corrected report instructions.",
                    })
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
            if payload.get("view_only") is not True or str(payload.get("mode") or "") != FLEET_PREVIEW_MODE:
                raise PermissionError("Fleet previews must use the bounded view-only preview mode")
            from app_backend.capture_runtime import capture_screen_snapshot
            from app_backend.windows_capture_session import DesktopCaptureUnavailableError

            loop = asyncio.get_running_loop()
            try:
                capture = await loop.run_in_executor(
                    None,
                    lambda: capture_screen_snapshot(max_width=1280, jpeg_quality=62),
                )
            except DesktopCaptureUnavailableError as exc:
                return {
                    "status": "unavailable",
                    "detail": str(exc),
                    "capture_capability": exc.capability(),
                }
            encoded = str(capture.get("image_base64") or "")
            if not encoded or len(encoded) > 2_000_000:
                raise RuntimeError("Captured preview exceeded the safe image size limit")
            return {
                "status": "captured",
                "detail": "View-only desktop preview captured.",
                "capture_capability": {
                    "available": True,
                    "code": "available",
                    "state": str((capture.get("display") or {}).get("state") or "active"),
                    "retryable": True,
                },
                "capture": capture,
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

        raise ValueError(f"Unsupported paired-computer command: {command_name or '<empty>'}")


def _fleet_capability_view(snapshot: Dict[str, Any], permissions: Dict[str, bool]) -> Dict[str, Any]:
    identities = [item for item in list(snapshot.get("identities") or []) if isinstance(item, dict)]
    targets: list[Dict[str, Any]] = []
    if permissions.get("delegate_manager", False):
        manager = next((item for item in identities if str(item.get("role") or "") == "manager"), None)
        if manager:
            targets.append(
                {
                    "target_kind": "manager",
                    "target_selector": None,
                    "identity_id": str(manager.get("identity_id") or "").strip() or None,
                    "display_name": str(manager.get("display_name") or "Main manager"),
                    "role": "manager",
                    "status": str(manager.get("status") or "ready"),
                }
            )
    if permissions.get("delegate_workers", False):
        for identity in identities:
            if str(identity.get("role") or "") != "worker":
                continue
            selector = str(identity.get("identity_id") or identity.get("worker_id") or "").strip()
            if not selector:
                continue
            targets.append(
                {
                    "target_kind": "worker",
                    "target_selector": selector,
                    "identity_id": str(identity.get("identity_id") or "").strip() or None,
                    "display_name": str(identity.get("display_name") or "Worker"),
                    "role": "worker",
                    "status": str(identity.get("status") or "ready"),
                }
            )
    manager_desktop_id = str((snapshot.get("manager") or {}).get("desktop_id") or "").strip()
    child_count = sum(
        1
        for desktop in list(snapshot.get("desktops") or [])
        if isinstance(desktop, dict)
        and str(desktop.get("desktop_id") or "").strip()
        and str(desktop.get("desktop_id") or "").strip() != manager_desktop_id
    )
    return {
        "schema_version": 1,
        "node_role": "intermediary" if child_count else "leaf",
        "child_count": child_count,
        "can_enroll_children": True,
        "can_create_workers": bool(permissions.get("create_workers", False)),
        "targets": targets,
    }


async def _connection_state_loop(
    ws: ClientConnection,
    *,
    send_lock: asyncio.Lock,
    desktop_id: str,
    desktop_name: str,
    credentials: Optional[LocalRuntimeCredentials] = None,
) -> None:
    last_signature = ""
    last_heartbeat_at = 0.0
    last_capability_refresh_at = 0.0
    capabilities: Dict[str, Any] = {}
    timeout = httpx.Timeout(20.0, connect=10.0, read=20.0, write=20.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        while True:
            home = runtime_home()
            policy = load_connection_policy(home) if home else connection_policy_view({})
            permissions = normalize_connection_permissions(policy.get("permissions"))
            now = asyncio.get_running_loop().time()
            if credentials and now - last_capability_refresh_at >= CAPABILITY_STATE_INTERVAL_SECONDS:
                last_capability_refresh_at = now
                try:
                    snapshot = await _with_local_runtime_credentials(
                        credentials,
                        lambda api_base_url, access_token: _request_json(
                            client,
                            method="GET",
                            url=f"{api_base_url}/api/fleet/snapshot",
                            token=access_token,
                        ),
                    )
                    capabilities = _fleet_capability_view(dict(snapshot or {}), permissions)
                except Exception:
                    logger.debug("Fleet capability refresh is temporarily unavailable", exc_info=True)

            envelope = {
                "desktop_id": desktop_id,
                "desktop_name": desktop_name,
                **policy,
                "capabilities": capabilities,
            }
            signature = policy_signature(envelope)
            if signature != last_signature:
                last_signature = signature
                await _send_json(ws, send_lock, {"type": "fleet_permission_state", "payload": envelope})

            if home:
                for request in pending_upstream_requests(home):
                    await _send_json(
                        ws,
                        send_lock,
                        {
                            "type": "fleet_upstream_request",
                            "payload": {
                                "request_id": request["activity_id"],
                                "request_kind": request["request_kind"],
                                "identity_id": request.get("identity_id"),
                                "identity_label": request.get("identity_label"),
                                "message": request["message"],
                                "created_at": request.get("created_at"),
                            },
                        },
                    )
                    mark_upstream_request_sent(home, request["activity_id"])

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
            await asyncio.sleep(CONNECTION_STATE_INTERVAL_SECONDS)


async def _send_command_result(
    ws: ClientConnection,
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
            try:
                response_payload = error.response.json()
            except Exception:
                response_payload = None
            if isinstance(response_payload, dict):
                response_detail = response_payload.get("detail") or response_payload.get("message")
            else:
                response_detail = None
            payload["error"] = str(response_detail or error.response.text or str(error)).strip()[:2000]
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
    status_path = _remote_status_path()
    log_path = status_path.parent / "desktop_remote_control.log" if status_path else None
    logging.basicConfig(
        level=logging.INFO,
        filename=str(log_path) if log_path else None,
        encoding="utf-8" if log_path else None,
    )
    _write_remote_status(state="starting", detail="Connecting to the paired Yggdrasil Fleet manager...")
    config = load_remote_desktop_config()
    remote_token = config.session_token
    desktop_id = config.desktop_id

    credentials = LocalRuntimeCredentials.from_bootstrap(start_runtime_context())
    _write_remote_status(
        state="starting",
        detail="Computer paired. Connecting directly to its manager...",
        desktop_id=desktop_id,
        desktop_name=config.desktop_name,
    )

    remote_ws_url = _ws_url_from_base(
        config.remote_base_url,
        f"ws/remote/desktop?token={remote_token}&desktop_id={desktop_id}",
    )

    while True:
        try:
            async with websocket_connect(remote_ws_url, max_size=REMOTE_WS_MAX_SIZE_BYTES) as ws:
                _write_remote_status(
                    state="running",
                    detail="Paired computer is connected directly to its Yggdrasil manager.",
                    desktop_id=desktop_id,
                    desktop_name=config.desktop_name,
                    ready=True,
                )
                send_lock = asyncio.Lock()
                connection_state_task = asyncio.create_task(
                    _connection_state_loop(
                        ws,
                        send_lock=send_lock,
                        desktop_id=desktop_id,
                        desktop_name=config.desktop_name,
                        credentials=credentials,
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
                        result = await _with_local_runtime_credentials(
                            credentials,
                            lambda api_base_url, access_token: _handle_command(
                                command_name=command_name,
                                payload=payload,
                                local_api_base_url=api_base_url,
                                local_token=access_token,
                                remote_ws=ws,
                                send_lock=send_lock,
                            ),
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

                try:
                    async for raw in ws:
                        message = json.loads(raw)
                        if str(message.get("type") or "") != "command":
                            continue
                        task = asyncio.create_task(run_command(message))
                        command_tasks.add(task)
                        task.add_done_callback(command_tasks.discard)
                finally:
                    connection_state_task.cancel()
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
    parser = argparse.ArgumentParser(description="Connect a local Fleet worker to its paired Yggdrasil manager.")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    _build_parser().parse_args(argv)
    asyncio.run(run_remote_desktop_client())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
