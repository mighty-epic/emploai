from __future__ import annotations

import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from app_backend.models import (
    RecoveryActionResponse,
    RecoveryArchiveItemView,
    RecoveryListResponse,
)
from cli.models.session import Session


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppRecoveryRouterDeps:
    resolve_token: Callable[[Optional[str]], Dict[str, object]]
    is_remote_session_auth: Callable[[Dict[str, Any]], bool]
    get_store: Callable[[], Any]
    bridge_for_user: Callable[[int], Any]
    sync_session_workspace_binding: Callable[..., None]
    consume_approved_confirmation: Callable[..., Dict[str, Any]]
    check_rate_limit: Callable[..., None]
    rate_limit_max_attempts: int


def create_app_recovery_router(deps: AppRecoveryRouterDeps) -> APIRouter:
    router = APIRouter(tags=["app-recovery"])

    @router.get("/api/app/recovery", response_model=RecoveryListResponse)
    async def list_recovery_items(authorization: Optional[str] = Header(default=None)) -> RecoveryListResponse:
        auth = dict(deps.resolve_token(authorization))
        items = deps.get_store().list_archived_items(user_id=int(auth["user_id"]))
        return RecoveryListResponse(items=[RecoveryArchiveItemView(**item) for item in items])

    @router.post("/api/app/recovery/{archive_id}/restore", response_model=RecoveryActionResponse)
    async def restore_recovery_item(
        archive_id: str,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> RecoveryActionResponse:
        auth = dict(deps.resolve_token(authorization))
        user_id = int(auth["user_id"])
        deps.check_rate_limit(
            http_request,
            email=str(user_id),
            action="recovery_restore",
            max_attempts=deps.rate_limit_max_attempts,
        )
        try:
            archived = deps.get_store().get_archived_item(user_id=user_id, archive_id=archive_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Archived item not found") from exc
        restored_session_id = None
        if archived.get("object_kind") == "chat":
            restored_session_id = _restore_chat_archive(deps, user_id=user_id, auth=auth, archived=archived)
        try:
            item = deps.get_store().restore_archived_item(user_id=user_id, archive_id=archive_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Archived item not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return RecoveryActionResponse(
            action="restore",
            item=RecoveryArchiveItemView(**item),
            restored_session_id=restored_session_id,
        )

    @router.delete("/api/app/recovery/{archive_id}", response_model=RecoveryActionResponse)
    async def permanently_delete_recovery_item(
        archive_id: str,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
        confirmation_id: Optional[str] = Header(default=None, alias="X-EmploAI-Confirmation-Id"),
    ) -> RecoveryActionResponse:
        auth = dict(deps.resolve_token(authorization))
        user_id = int(auth["user_id"])
        deps.check_rate_limit(
            http_request,
            email=str(user_id),
            action="recovery_permanent_delete",
            max_attempts=deps.rate_limit_max_attempts,
        )
        deps.consume_approved_confirmation(
            user_id=user_id,
            confirmation_id=confirmation_id,
            action_kind="recovery_permanent_delete",
            executed_by_surface=str(auth.get("actor_kind") or "app"),
            metadata={"archive_id": archive_id},
        )
        try:
            item = deps.get_store().permanently_delete_archived_item(user_id=user_id, archive_id=archive_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Archived item not found") from exc
        return RecoveryActionResponse(action="permanent_delete", item=RecoveryArchiveItemView(**item))

    @router.post("/api/app/recovery/purge-expired", response_model=RecoveryActionResponse)
    async def purge_expired_recovery_items(
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> RecoveryActionResponse:
        auth = dict(deps.resolve_token(authorization))
        user_id = int(auth["user_id"])
        deps.check_rate_limit(
            http_request,
            email=str(user_id),
            action="recovery_purge_expired",
            max_attempts=deps.rate_limit_max_attempts,
        )
        result = deps.get_store().purge_expired_archives(user_id=user_id)
        return RecoveryActionResponse(action="purge_expired", purged=int(result.get("purged") or 0))

    return router


def _restore_chat_archive(
    deps: AppRecoveryRouterDeps,
    *,
    user_id: int,
    auth: Dict[str, Any],
    archived: Dict[str, Any],
) -> str:
    payload = dict(archived.get("payload") or {})
    session_payload = dict(payload.get("session") or {})
    bridge = deps.bridge_for_user(user_id)
    try:
        original_session_id = str(session_payload.get("id") or archived.get("object_id") or "").strip()
        if not original_session_id:
            raise ValueError("Archived chat is missing its original session id")
        restored_history = [
            dict(message.get("raw") or {"role": message.get("role", "user"), "content": message.get("content", "")})
            for message in list(session_payload.get("messages") or [])
            if isinstance(message, dict)
        ]
        restored_timeline = [
            dict(event)
            for event in list(session_payload.get("timeline_events") or [])
            if isinstance(event, dict)
        ]
        restored_session = Session.from_dict({
            "id": original_session_id,
            "name": str(session_payload.get("name") or archived.get("display_name") or "Restored chat"),
            "created_at": str(session_payload.get("created_at") or archived.get("archived_at") or ""),
            "updated_at": str(session_payload.get("updated_at") or ""),
            "workspace": str(session_payload.get("workspace") or ""),
            "model": str(session_payload.get("model") or "claude-haiku-4.5"),
            "variant": str(session_payload.get("variant") or "standard"),
            "planner_model": session_payload.get("planner_model"),
            "security_permission_mode": session_payload.get("security_permission_mode") or "standard",
            "workspace_id": session_payload.get("workspace_id"),
            "workspace_binding_status": session_payload.get("workspace_binding_status") or (
                "active" if session_payload.get("workspace") and Path(str(session_payload.get("workspace"))).expanduser().exists() else "needs_reconnect"
            ),
            "fleet_identity_id": session_payload.get("fleet_identity_id"),
            "fleet_identity_role": session_payload.get("fleet_identity_role"),
            "fleet_worker_id": session_payload.get("fleet_worker_id"),
            "account_user_id": user_id,
            "chat_history": restored_history,
            "event_timeline": restored_timeline,
        })
        deps.sync_session_workspace_binding(user_id=user_id, auth=auth, session=restored_session)
        bridge.session_manager.save_session(restored_session)
        bridge.session_manager.set_current_session(restored_session.id)
        runtime = bridge._runtime()
        if runtime and not getattr(runtime, "is_processing", False):
            runtime.load_session_by_id(restored_session.id)
        deps.mirror_session_snapshot(user_id=user_id, bridge=bridge, session=restored_session, reason="chat_restored")
        return restored_session.id
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"Could not restore chat: {exc}") from exc
