from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import websockets
from websockets.client import WebSocketClientProtocol

from mobile_app.backend.desktop_runtime import start_runtime_context


logger = logging.getLogger(__name__)

REMOTE_CONTROL_BASE_URL_ENV = "EMPLOAI_REMOTE_CONTROL_BASE_URL"
REMOTE_CONTROL_EMAIL_ENV = "EMPLOAI_REMOTE_CONTROL_EMAIL"
REMOTE_CONTROL_PASSWORD_ENV = "EMPLOAI_REMOTE_CONTROL_PASSWORD"
REMOTE_CONTROL_DESKTOP_NAME_ENV = "EMPLOAI_REMOTE_DESKTOP_NAME"
REMOTE_CONTROL_DESKTOP_KEY_ENV = "EMPLOAI_REMOTE_DESKTOP_KEY"
REMOTE_CONTROL_STATUS_PATH_ENV = "EMPLOAI_REMOTE_CONTROL_STATUS_PATH"
SNAPSHOT_INTERVAL_SECONDS = 1.2
HEARTBEAT_INTERVAL_SECONDS = 12.0
REMOTE_CLIENT_ID = "remote-desktop-bridge"


@dataclass
class RemoteDesktopConfig:
    remote_base_url: str
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


def load_remote_desktop_config() -> RemoteDesktopConfig:
    remote_base_url = _normalize_base_url(os.getenv(REMOTE_CONTROL_BASE_URL_ENV, ""))
    email = str(os.getenv(REMOTE_CONTROL_EMAIL_ENV, "") or "").strip()
    password = str(os.getenv(REMOTE_CONTROL_PASSWORD_ENV, "") or "").strip()
    desktop_name = str(os.getenv(REMOTE_CONTROL_DESKTOP_NAME_ENV, "") or "").strip() or "EmploAI Desktop"
    device_key = str(os.getenv(REMOTE_CONTROL_DESKTOP_KEY_ENV, "") or "").strip() or "desktop-default"
    if not remote_base_url:
        raise RuntimeError(f"{REMOTE_CONTROL_BASE_URL_ENV} is required")
    if not email or not password:
        raise RuntimeError(
            f"{REMOTE_CONTROL_EMAIL_ENV} and {REMOTE_CONTROL_PASSWORD_ENV} are required"
        )
    return RemoteDesktopConfig(
        remote_base_url=remote_base_url,
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
        return response.json()


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
        "current_session_changed",
        "artifact_created",
    }:
        return {
            "type": event_type,
            "session_id": session_id,
            "payload": payload,
        }
    return None


async def _relay_local_chat_command(
    *,
    local_api_base_url: str,
    local_token: str,
    session_id: Optional[str],
    text: str,
    source_format: str,
    interrupt_policy: str,
    remote_ws: WebSocketClientProtocol,
    send_lock: asyncio.Lock,
) -> None:
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
                }
            )
        )
        while True:
            raw = await local_ws.recv()
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
            if str(data.get("type") or "") == "assistant_final":
                break


async def _handle_command(
    *,
    command_name: str,
    payload: Dict[str, Any],
    local_api_base_url: str,
    local_token: str,
    remote_ws: WebSocketClientProtocol,
    send_lock: asyncio.Lock,
) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        if command_name == "create_session":
            await client.post(
                f"{local_api_base_url}/api/app/sessions",
                headers={"Authorization": f"Bearer {local_token}"},
                json={
                    "name": payload.get("name"),
                    "workspace": payload.get("workspace"),
                    "telegram_bot_config_id": payload.get("telegram_bot_config_id"),
                    "enabled_tool_packs": payload.get("enabled_tool_packs") or [],
                    "headless_eligible": bool(payload.get("headless_eligible", False)),
                },
            )
            return

        if command_name == "activate_session":
            session_id = str(payload.get("session_id") or "").strip()
            if not session_id:
                return
            await client.post(
                f"{local_api_base_url}/api/app/sessions/{session_id}/activate",
                headers={"Authorization": f"Bearer {local_token}"},
            )
            return

        if command_name == "chat_send":
            await _relay_local_chat_command(
                local_api_base_url=local_api_base_url,
                local_token=local_token,
                session_id=str(payload.get("session_id") or "").strip() or None,
                text=str(payload.get("text") or ""),
                source_format=str(payload.get("source_format") or "app_text"),
                interrupt_policy=str(payload.get("interrupt_policy") or "none"),
                remote_ws=remote_ws,
                send_lock=send_lock,
            )
            return

        if command_name == "pause_run":
            target = str(payload.get("session_id") or "").strip() or None
            params = f"?session_id={target}" if target else ""
            await client.post(
                f"{local_api_base_url}/api/app/agent/control/pause{params}",
                headers={"Authorization": f"Bearer {local_token}"},
            )
            return

        if command_name == "stop_run":
            target = str(payload.get("session_id") or "").strip() or None
            params = f"?session_id={target}" if target else ""
            await client.post(
                f"{local_api_base_url}/api/app/agent/control/stop{params}",
                headers={"Authorization": f"Bearer {local_token}"},
            )
            return

        if command_name == "restart_runtime":
            target = str(payload.get("session_id") or "").strip() or None
            params = f"?session_id={target}" if target else ""
            await client.post(
                f"{local_api_base_url}/api/app/agent/control/restart{params}",
                headers={"Authorization": f"Bearer {local_token}"},
            )
            return


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


async def run_remote_desktop_client() -> None:
    logging.basicConfig(level=logging.INFO)
    _write_remote_status(state="starting", detail="Signing in to the EmploAI remote control plane...")
    config = load_remote_desktop_config()
    login = await _remote_login(config)
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
            async with websockets.connect(remote_ws_url, max_size=16 * 1024 * 1024) as ws:
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
                try:
                    async for raw in ws:
                        message = json.loads(raw)
                        if str(message.get("type") or "") != "command":
                            continue
                        payload = dict(message.get("payload") or {})
                        command_name = str(payload.pop("name", "") or "")
                        if not command_name:
                            continue
                        try:
                            await _handle_command(
                                command_name=command_name,
                                payload=payload,
                                local_api_base_url=local_api_base_url,
                                local_token=local_token,
                                remote_ws=ws,
                                send_lock=send_lock,
                            )
                        finally:
                            snapshot = await _collect_local_snapshot(local_api_base_url, local_token)
                            await _send_json(
                                ws,
                                send_lock,
                                {
                                    "type": "state_snapshot",
                                    "payload": {
                                        "desktop_id": desktop_id,
                                        "desktop_name": config.desktop_name,
                                        "current_session_id": snapshot.get("current_session_id"),
                                        "current_model": snapshot.get("current_model"),
                                        "current_variant": snapshot.get("current_variant"),
                                        "sessions": snapshot.get("sessions") or [],
                                        "session_details": snapshot.get("session_details") or {},
                                        "jobs": snapshot.get("jobs") or [],
                                    },
                                },
                            )
                finally:
                    snapshot_task.cancel()
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
