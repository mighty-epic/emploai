from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import HTTPException


def publish_confirmation_delta(
    *,
    sync_hub: Any,
    user_id: int,
    confirmation: Dict[str, Any],
    origin_channel: str = "app",
) -> None:
    sync_hub.publish(
        user_id=int(user_id),
        event={
            "type": "confirmation_changed",
            "session_id": confirmation.get("origin_chat_id"),
            "origin_channel": origin_channel,
            "payload": {"confirmation": confirmation},
        },
    )


def consume_approved_confirmation(
    *,
    store: Any,
    publish_confirmation_delta: Callable[..., None],
    user_id: int,
    confirmation_id: Optional[str],
    action_kind: str,
    executed_by_surface: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    clean_id = str(confirmation_id or "").strip()
    if not clean_id:
        raise HTTPException(
            status_code=409,
            detail={
                "error_type": "confirmation_required",
                "action_kind": action_kind,
                "message": "This action requires confirmation before it can continue.",
            },
        )
    try:
        confirmation = store.get_confirmation(user_id=int(user_id), confirmation_id=clean_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Confirmation not found") from exc
    if str(confirmation.get("action_kind") or "") != str(action_kind or ""):
        raise HTTPException(status_code=409, detail="Confirmation does not match this action")
    if str(confirmation.get("status") or "") != "approved":
        raise HTTPException(status_code=409, detail=f"Confirmation is {confirmation.get('status') or 'not approved'}")
    try:
        executed = store.record_confirmation_executed(
            user_id=int(user_id),
            confirmation_id=clean_id,
            executed_by_surface=executed_by_surface,
            metadata=metadata,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    publish_confirmation_delta(user_id=int(user_id), confirmation=executed, origin_channel=executed_by_surface)
    return executed
