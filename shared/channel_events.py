from __future__ import annotations

from typing import Any, Dict, Optional

from shared.channel_sync import get_channel_sync_hub


def publish_current_session_changed(
    *,
    user_id: int,
    session_id: Optional[str],
    origin_channel: str,
    reason: str,
    previous_session_id: Optional[str] = None,
    source_client_id: Optional[str] = None,
) -> None:
    get_channel_sync_hub().publish(
        user_id=user_id,
        event={
            "type": "current_session_changed",
            "session_id": session_id,
            "origin_channel": origin_channel,
            "source_client_id": source_client_id,
            "payload": {
                "current_session_id": session_id,
                "previous_session_id": previous_session_id,
                "reason": reason,
            },
        },
    )


def publish_status_update(
    *,
    user_id: int,
    session_id: Optional[str],
    origin_channel: str,
    message: str,
    run_state: str,
    source_client_id: Optional[str] = None,
    extra_payload: Optional[Dict[str, Any]] = None,
) -> None:
    payload = {
        "message": message,
        "run_state": run_state,
    }
    if extra_payload:
        payload.update(extra_payload)

    get_channel_sync_hub().publish(
        user_id=user_id,
        event={
            "type": "status",
            "session_id": session_id,
            "origin_channel": origin_channel,
            "source_client_id": source_client_id,
            "payload": payload,
        },
    )
