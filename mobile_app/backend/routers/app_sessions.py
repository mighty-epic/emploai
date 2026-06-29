from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from mobile_app.backend.models import (
    SessionDetailView,
    SessionSearchRequest,
    SessionSearchResponse,
    SessionSearchResultView,
    SessionSummaryView,
    TimelineEventAppendRequest,
)
from shared.channel_sync import get_channel_sync_hub


_REMOTE_SESSION_SEARCH_LIMIT_MAX = 100
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppSessionsRouterDeps:
    resolve_token: Callable[[Optional[str]], Dict[str, object]]
    is_remote_session_auth: Callable[[Dict[str, Any]], bool]
    bridge_for_user: Callable[[int], Any]
    remote_session_summary_views: Callable[[Dict[str, Any]], list[SessionSummaryView]]
    remote_session_detail_view: Callable[[Dict[str, Any], Optional[str]], SessionDetailView]
    remote_shared_state: Callable[[Dict[str, Any]], Dict[str, Any]]
    search_sessions_in_manager: Callable[..., list[dict[str, Any]]]
    mirror_session_snapshot: Callable[..., None]
    check_rate_limit: Callable[..., None]
    rate_limit_max_attempts: int


def create_app_sessions_router(deps: AppSessionsRouterDeps) -> APIRouter:
    router = APIRouter(tags=["app-sessions"])

    @router.get("/api/app/sessions", response_model=list[SessionSummaryView])
    async def list_sessions(authorization: Optional[str] = Header(default=None)) -> list[SessionSummaryView]:
        auth = dict(deps.resolve_token(authorization))
        if deps.is_remote_session_auth(auth):
            return deps.remote_session_summary_views(auth)
        bridge = deps.bridge_for_user(int(auth["user_id"]))
        return [SessionSummaryView(**bridge.summarize_session_summary(s)) for s in bridge.list_session_summaries()]

    @router.post("/api/app/sessions/search", response_model=SessionSearchResponse)
    async def search_sessions(
        request: SessionSearchRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> SessionSearchResponse:
        auth = dict(deps.resolve_token(authorization))
        user_id = int(auth["user_id"])
        if deps.is_remote_session_auth(auth):
            results = _search_remote_shared_sessions(
                state=deps.remote_shared_state(auth),
                query=request.query,
                limit=request.limit,
            )
            return SessionSearchResponse(results=[SessionSearchResultView(**item) for item in results])

        bridge = deps.bridge_for_user(user_id)
        results = deps.search_sessions_in_manager(
            user_id=user_id,
            session_manager=bridge.session_manager,
            query=request.query,
            limit=request.limit,
        )
        return SessionSearchResponse(results=[SessionSearchResultView(**item) for item in results])

    @router.get("/api/app/sessions/{session_id}", response_model=SessionDetailView)
    async def get_session(session_id: str, authorization: Optional[str] = Header(default=None)) -> SessionDetailView:
        auth = dict(deps.resolve_token(authorization))
        if deps.is_remote_session_auth(auth):
            return deps.remote_session_detail_view(auth, session_id)
        bridge = deps.bridge_for_user(int(auth["user_id"]))
        session = bridge.get_session(session_id)
        return SessionDetailView(**bridge.detailed_session_view(session))

    @router.post("/api/app/sessions/{session_id}/timeline")
    async def append_session_timeline(
        session_id: str,
        request: TimelineEventAppendRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> dict:
        auth = _require_local_desktop_session_backend(deps, authorization)
        user_id = int(auth["user_id"])
        deps.check_rate_limit(
            http_request,
            email=str(user_id),
            action="app_timeline_append",
            max_attempts=deps.rate_limit_max_attempts,
        )
        bridge = deps.bridge_for_user(user_id)
        event = bridge.append_timeline_event(
            session_id=session_id,
            kind=request.kind,
            title=request.title,
            content=request.content,
            tone=request.tone,
            channel=request.channel,
            source_format=request.source_format,
            metadata=request.metadata,
        )
        get_channel_sync_hub().publish(
            user_id=user_id,
            event={
                "type": "timeline_event",
                "session_id": session_id,
                "origin_channel": request.channel,
                "source_client_id": request.source_client_id,
                "payload": {"event": event},
            },
        )
        try:
            session = bridge.get_session(session_id)
            deps.mirror_session_snapshot(user_id=user_id, bridge=bridge, session=session, reason="timeline_event")
        except Exception:
            logger.exception("[recovery] failed mirroring timeline event session")
        return {"event": event}

    return router


def _require_local_desktop_session_backend(
    deps: AppSessionsRouterDeps,
    authorization: Optional[str],
) -> Dict[str, Any]:
    auth = dict(deps.resolve_token(authorization))
    if deps.is_remote_session_auth(auth):
        raise HTTPException(status_code=409, detail="Session timeline operations must run on the local desktop backend")
    return auth


def _normalize_search_text(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _project_name(project_path: str) -> str:
    normalized = str(project_path or "").replace("\\", "/").rstrip("/")
    if not normalized:
        return ""
    return normalized.rsplit("/", 1)[-1] or normalized


def _snippet(content: Any, normalized_query: str, query_tokens: list[str]) -> str:
    text = " ".join(str(content or "").split())
    if not text:
        return ""
    lowered = text.casefold()
    needles = [normalized_query, *query_tokens]
    match_index = -1
    match_length = 0
    for needle in needles:
        if not needle:
            continue
        match_index = lowered.find(needle)
        if match_index >= 0:
            match_length = len(needle)
            break
    if match_index < 0:
        return text[:180]
    start = max(0, match_index - 60)
    end = min(len(text), match_index + max(match_length, 1) + 120)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end]}{suffix}"


def _append_name_match(
    results: list[dict[str, Any]],
    *,
    kind: str,
    field_name: str,
    candidate: str,
    normalized_query: str,
    session_id: str,
    session_name: str,
    project_path: str,
    project_name: str,
    updated_at: str,
) -> None:
    normalized_candidate = _normalize_search_text(candidate)
    if not normalized_candidate:
        return
    if normalized_candidate == normalized_query:
        reason = f"{field_name}_exact"
        score = 300.0 if kind == "project" else 270.0
    elif normalized_candidate.startswith(normalized_query):
        reason = f"{field_name}_prefix"
        score = 290.0 if kind == "project" else 260.0
    elif normalized_query in normalized_candidate:
        reason = f"{field_name}_substring"
        score = 280.0 if kind == "project" else 250.0
    else:
        return
    results.append(
        {
            "kind": kind,
            "project_path": project_path,
            "project_name": project_name,
            "session_id": session_id,
            "session_name": session_name,
            "timestamp": updated_at,
            "snippet": str(candidate or "")[:180],
            "match_reason": reason,
            "score": score,
            "_updated_at": updated_at,
        }
    )


def _search_remote_shared_sessions(*, state: Dict[str, Any], query: str, limit: int) -> list[dict[str, Any]]:
    normalized_query = _normalize_search_text(query)
    if not normalized_query:
        return []
    normalized_limit = max(1, min(int(limit or 40), _REMOTE_SESSION_SEARCH_LIMIT_MAX))
    query_tokens = [token for token in normalized_query.split(" ") if token]
    details_by_id = state.get("session_details") if isinstance(state.get("session_details"), dict) else {}
    summaries = list(state.get("sessions") or [])
    if not summaries:
        summaries = [
            {"id": session_id, **detail}
            for session_id, detail in details_by_id.items()
            if isinstance(detail, dict)
        ]
    summaries = sorted(summaries, key=lambda item: str((item or {}).get("updated_at") or ""), reverse=True)

    results: list[dict[str, Any]] = []
    for raw_summary in summaries:
        if not isinstance(raw_summary, dict):
            continue
        session_id = str(raw_summary.get("id") or "").strip()
        if not session_id:
            continue
        raw_detail = details_by_id.get(session_id) if isinstance(details_by_id.get(session_id), dict) else {}
        session_name = str(raw_summary.get("name") or raw_detail.get("name") or "")
        project_path = str(raw_summary.get("workspace") or raw_detail.get("workspace") or "")
        project_display_name = _project_name(project_path)
        updated_at = str(raw_summary.get("updated_at") or raw_detail.get("updated_at") or "")

        _append_name_match(
            results,
            kind="project",
            field_name="project",
            candidate=project_display_name or project_path,
            normalized_query=normalized_query,
            session_id=session_id,
            session_name=session_name,
            project_path=project_path,
            project_name=project_display_name,
            updated_at=updated_at,
        )
        _append_name_match(
            results,
            kind="session",
            field_name="session",
            candidate=session_name,
            normalized_query=normalized_query,
            session_id=session_id,
            session_name=session_name,
            project_path=project_path,
            project_name=project_display_name,
            updated_at=updated_at,
        )

        messages = raw_detail.get("messages") if isinstance(raw_detail, dict) else []
        for index, message in enumerate(list(messages or [])):
            if not isinstance(message, dict):
                continue
            content = str(message.get("content") or "")
            normalized_content = _normalize_search_text(content)
            if not normalized_content:
                continue
            if normalized_query in normalized_content:
                reason = "message_phrase"
                score = 190.0
            elif all(token in normalized_content for token in query_tokens):
                reason = "message_tokens"
                score = 150.0 + min(25.0, len(query_tokens) * 3.0)
            else:
                continue
            results.append(
                {
                    "kind": "message",
                    "project_path": project_path,
                    "project_name": project_display_name,
                    "session_id": session_id,
                    "session_name": session_name,
                    "message_index": index,
                    "message_role": str(message.get("role") or ""),
                    "timestamp": str(message.get("timestamp") or updated_at),
                    "snippet": _snippet(content, normalized_query, query_tokens),
                    "match_reason": reason,
                    "score": score,
                    "_updated_at": updated_at,
                }
            )

    results.sort(key=lambda item: (float(item.get("score") or 0.0), str(item.get("_updated_at") or "")), reverse=True)
    return [{key: value for key, value in item.items() if key != "_updated_at"} for item in results[:normalized_limit]]
