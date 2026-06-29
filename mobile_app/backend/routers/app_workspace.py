from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from mobile_app.backend.models import WorkspaceGitCheckoutRequest, WorkspaceGitStateView


@dataclass(frozen=True)
class AppWorkspaceRouterDeps:
    resolve_token: Callable[[Optional[str]], Dict[str, object]]
    is_remote_session_auth: Callable[[Dict[str, Any]], bool]
    workspace_git_state: Callable[[str], Dict[str, Any]]
    workspace_git_checkout: Callable[[str, str], Dict[str, Any]]
    check_rate_limit: Callable[..., None]
    rate_limit_max_attempts: int


def create_app_workspace_router(deps: AppWorkspaceRouterDeps) -> APIRouter:
    router = APIRouter(tags=["app-workspace"])

    @router.get("/api/app/workspace/git", response_model=WorkspaceGitStateView)
    async def get_workspace_git_state(
        path: str = "",
        authorization: Optional[str] = Header(default=None),
    ) -> WorkspaceGitStateView:
        auth = dict(deps.resolve_token(authorization))
        _ensure_local_app_backend(auth)
        return WorkspaceGitStateView(**deps.workspace_git_state(path))

    @router.post("/api/app/workspace/git/checkout", response_model=WorkspaceGitStateView)
    async def checkout_workspace_git_branch(
        request: WorkspaceGitCheckoutRequest,
        http_request: Request,
        authorization: Optional[str] = Header(default=None),
    ) -> WorkspaceGitStateView:
        auth = dict(deps.resolve_token(authorization))
        _ensure_local_app_backend(auth)
        deps.check_rate_limit(
            http_request,
            email=str(auth["user_id"]),
            action="workspace_git_checkout",
            max_attempts=deps.rate_limit_max_attempts,
        )
        return WorkspaceGitStateView(**deps.workspace_git_checkout(request.path, request.branch))

    def _ensure_local_app_backend(auth: Dict[str, Any]) -> None:
        if deps.is_remote_session_auth(auth):
            raise HTTPException(status_code=409, detail="Workspace Git operations must run on the local desktop backend")

    return router
