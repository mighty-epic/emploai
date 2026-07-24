from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app_backend.models import ArtifactDetailView, ArtifactSummaryView, UploadResponse
from app_backend.company_runtime_context import require_company_record, selected_company_scope


@dataclass(frozen=True)
class AppFilesRouterDeps:
    resolve_token: Callable[[Optional[str]], Dict[str, object]]
    is_remote_session_auth: Callable[[Dict[str, Any]], bool]
    bridge_for_user: Callable[[int], Any]
    get_company_store: Callable[[], Any]
    get_fleet_store: Callable[[], Any]
    load_runtime_session_or_409: Callable[..., Any]
    check_rate_limit: Callable[..., None]
    rate_limit_max_attempts: int


def create_app_files_router(deps: AppFilesRouterDeps) -> APIRouter:
    router = APIRouter(tags=["app-files"])

    @router.get("/api/app/sessions/{session_id}/artifacts", response_model=list[ArtifactSummaryView])
    async def list_session_artifacts(
        session_id: str,
        authorization: Optional[str] = Header(default=None),
    ) -> list[ArtifactSummaryView]:
        auth = _require_local_app_backend(deps, authorization)
        bridge = deps.bridge_for_user(int(auth["user_id"]))
        _require_selected_company_session(deps, auth, bridge, session_id)
        return [ArtifactSummaryView(**item) for item in bridge.list_session_artifacts(session_id)]

    @router.get("/api/app/sessions/{session_id}/artifacts/{artifact_id}", response_model=ArtifactDetailView)
    async def get_session_artifact(
        session_id: str,
        artifact_id: str,
        authorization: Optional[str] = Header(default=None),
    ) -> ArtifactDetailView:
        auth = _require_local_app_backend(deps, authorization)
        bridge = deps.bridge_for_user(int(auth["user_id"]))
        _require_selected_company_session(deps, auth, bridge, session_id)
        try:
            detail = bridge.get_session_artifact(session_id, artifact_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Artifact not found") from exc
        return ArtifactDetailView(**detail)

    @router.get("/api/app/sessions/{session_id}/artifacts/{artifact_id}/download")
    async def download_session_artifact(
        session_id: str,
        artifact_id: str,
        authorization: Optional[str] = Header(default=None),
    ) -> FileResponse:
        auth = _require_local_app_backend(deps, authorization)
        bridge = deps.bridge_for_user(int(auth["user_id"]))
        _require_selected_company_session(deps, auth, bridge, session_id)
        try:
            detail = bridge.get_session_artifact(session_id, artifact_id)
            path = bridge.session_artifact_download_path(session_id, artifact_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Artifact not found") from exc
        return FileResponse(
            path,
            media_type=str(detail.get("mime_type") or "application/octet-stream"),
            filename=str(detail.get("payload_file_name") or path.name),
        )

    @router.post("/api/app/upload", response_model=UploadResponse)
    async def upload(
        http_request: Request,
        file: UploadFile = File(...),
        session_id: Optional[str] = None,
        authorization: Optional[str] = Header(default=None),
    ) -> UploadResponse:
        auth = _require_local_app_backend(deps, authorization)
        user_id = int(auth["user_id"])
        deps.check_rate_limit(
            http_request,
            email=str(user_id),
            action="app_upload",
            max_attempts=deps.rate_limit_max_attempts,
        )
        bridge = deps.bridge_for_user(user_id)
        requested_session_id = str(
            session_id
            or getattr(bridge.get_current_session(), "id", "")
            or ""
        ).strip()
        if not requested_session_id:
            raise HTTPException(status_code=404, detail="Session not found")
        _require_selected_company_session(
            deps,
            auth,
            bridge,
            requested_session_id,
        )
        runtime = deps.load_runtime_session_or_409(bridge, session_id)
        effective_session_id = runtime.session_manager.get_current_session_id()
        if not effective_session_id:
            raise HTTPException(status_code=404, detail="Session not found")
        upload_id = secrets.token_hex(10)
        data = await file.read()
        bridge.attach_pending_file(
            runtime=runtime,
            filename=file.filename or "upload",
            content_type=file.content_type,
            data=data,
        )
        return UploadResponse(
            upload_id=upload_id,
            filename=file.filename or "upload",
            session_id=effective_session_id,
            attached=True,
        )

    return router


def _require_local_app_backend(
    deps: AppFilesRouterDeps,
    authorization: Optional[str],
) -> Dict[str, Any]:
    auth = dict(deps.resolve_token(authorization))
    if deps.is_remote_session_auth(auth):
        raise HTTPException(status_code=409, detail="File and artifact operations must run on the local desktop backend")
    return auth


def _require_selected_company_session(
    deps: AppFilesRouterDeps,
    auth: Dict[str, Any],
    bridge: Any,
    session_id: str,
) -> Any:
    try:
        session = bridge.get_session(session_id)
        scope = selected_company_scope(
            auth=auth,
            company_store=deps.get_company_store(),
            fleet_store=deps.get_fleet_store(),
        )
        return require_company_record(
            session,
            company_id=scope.get("company_id"),
            include_legacy=bool(scope.get("include_legacy")),
            message="Session not found in the selected company",
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc
