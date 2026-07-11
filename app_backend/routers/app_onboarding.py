from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from app_backend.models import (
    ProjectOnboardingProfile,
    ProjectOnboardingResponse,
    ProjectOnboardingSaveRequest,
    ProjectOnboardingSummarizeRequest,
    ProjectOnboardingToolRequirement,
)
from shared.project_onboarding import (
    ProjectOnboardingStore,
    merge_tool_packs,
    sanitize_profile_payload,
    summarize_onboarding_answers,
    workspace_key,
)
from shared.tool_packs import get_tool_pack, normalize_enabled_tool_packs


@dataclass(frozen=True)
class AppOnboardingRouterDeps:
    resolve_token: Callable[[Optional[str]], Dict[str, object]]
    is_remote_session_auth: Callable[[Dict[str, Any]], bool]
    bridge_for_user: Callable[[int], Any]
    check_rate_limit: Callable[..., None]
    rate_limit_max_attempts: int


def create_app_onboarding_router(deps: AppOnboardingRouterDeps) -> APIRouter:
    router = APIRouter(tags=["app-onboarding"])

    @router.get("/api/app/onboarding", response_model=ProjectOnboardingResponse)
    async def get_project_onboarding(
        workspace: str = "",
        authorization: Optional[str] = Header(default=None),
    ) -> ProjectOnboardingResponse:
        auth = _require_local_app_backend(deps, authorization)
        clean_workspace = str(workspace or "").strip()
        if not clean_workspace:
            raise HTTPException(status_code=400, detail="Workspace is required")
        store = ProjectOnboardingStore(user_id=int(auth["user_id"]))
        profile = store.get_by_workspace(clean_workspace)
        return _response(profile)

    @router.put("/api/app/onboarding", response_model=ProjectOnboardingResponse)
    async def save_project_onboarding(
        request: ProjectOnboardingSaveRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> ProjectOnboardingResponse:
        auth = _require_local_app_backend(deps, authorization)
        _check_onboarding_rate_limit(deps, http_request, auth)
        user_id = int(auth["user_id"])
        store = ProjectOnboardingStore(user_id=user_id)
        profile = store.upsert(
            workspace=request.workspace,
            workspace_id=request.workspace_id,
            profile=_request_payload(request),
        )
        updated_session_ids: list[str] = []
        if request.apply_tool_packs:
            bridge = deps.bridge_for_user(user_id)
            updated_session_ids = _apply_project_tool_packs(bridge, profile)
        return _response(profile, updated_session_ids=updated_session_ids, message="Project onboarding saved.")

    @router.post("/api/app/onboarding/summarize", response_model=ProjectOnboardingResponse)
    async def summarize_project_onboarding(
        request: ProjectOnboardingSummarizeRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> ProjectOnboardingResponse:
        auth = _require_local_app_backend(deps, authorization)
        _check_onboarding_rate_limit(deps, http_request, auth)
        draft = summarize_onboarding_answers(
            {
                "answers": request.answers,
                "guided_transcript": [message.model_dump() for message in request.guided_transcript],
            }
        )
        profile = sanitize_profile_payload(draft, workspace=request.workspace)
        return _response(profile, message="Draft created from guided onboarding.")

    return router


def _request_payload(request: ProjectOnboardingSaveRequest) -> Dict[str, Any]:
    if hasattr(request, "model_dump"):
        return dict(request.model_dump())
    return dict(request.dict())


def _response(
    profile: Dict[str, Any],
    *,
    updated_session_ids: Optional[list[str]] = None,
    message: Optional[str] = None,
) -> ProjectOnboardingResponse:
    return ProjectOnboardingResponse(
        profile=ProjectOnboardingProfile(**profile),
        tool_requirements=_tool_requirements(profile),
        updated_session_ids=list(updated_session_ids or []),
        message=message,
    )


def _tool_requirements(profile: Dict[str, Any]) -> list[ProjectOnboardingToolRequirement]:
    items: list[ProjectOnboardingToolRequirement] = []
    desired = normalize_enabled_tool_packs(profile.get("desired_tool_packs") or [])
    for pack_id in desired:
        definition = get_tool_pack(pack_id)
        items.append(
            ProjectOnboardingToolRequirement(
                tool_pack_id=pack_id,
                label=definition.label if definition else pack_id,
                status="enabled",
                reason=definition.description if definition else None,
            )
        )
    for index, missing in enumerate(profile.get("missing_requirements") or []):
        items.append(
            ProjectOnboardingToolRequirement(
                tool_pack_id=f"setup:{index}",
                label="Setup",
                status="missing",
                reason=str(missing),
            )
        )
    return items


def _apply_project_tool_packs(bridge: Any, profile: Dict[str, Any]) -> list[str]:
    project_key = workspace_key(profile.get("workspace"))
    desired = normalize_enabled_tool_packs(profile.get("desired_tool_packs") or [])
    if not project_key or not desired:
        return []
    updated: list[str] = []
    for summary in bridge.list_session_summaries():
        if workspace_key(getattr(summary, "workspace", "")) != project_key:
            continue
        current = list(getattr(summary, "enabled_tool_packs", []) or [])
        next_enabled = merge_tool_packs(current, desired)
        if set(next_enabled) == set(normalize_enabled_tool_packs(current)):
            continue
        try:
            bridge.update_session_tool_packs(summary.id, next_enabled)
            updated.append(summary.id)
        except Exception:
            continue
    return updated


def _require_local_app_backend(
    deps: AppOnboardingRouterDeps,
    authorization: Optional[str],
) -> Dict[str, Any]:
    auth = dict(deps.resolve_token(authorization))
    if deps.is_remote_session_auth(auth):
        raise HTTPException(status_code=409, detail="Project onboarding must run on the local desktop backend.")
    return auth


def _check_onboarding_rate_limit(
    deps: AppOnboardingRouterDeps,
    http_request: Request,
    auth: Dict[str, Any],
) -> None:
    deps.check_rate_limit(
        http_request,
        email=str(auth["user_id"]),
        action="project_onboarding",
        max_attempts=deps.rate_limit_max_attempts,
    )
