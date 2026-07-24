from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Header, HTTPException

from app_backend.company_backup import CompanyBackupError, create_portable_company_backup
from app_backend.company_models import CompanyBackupExportRequest, CompanyBackupExportResponse
from app_backend.company_store import CompanyNotFoundError


@dataclass(frozen=True)
class AppCompanyBackupRouterDeps:
    resolve_token: Callable[[Optional[str]], Dict[str, Any]]
    get_store: Callable[[], Any]
    get_fleet_store: Callable[[], Any]


def create_app_company_backup_router(deps: AppCompanyBackupRouterDeps) -> APIRouter:
    router = APIRouter(tags=["app-company-backup"])

    def local_computer(authorization: Optional[str]) -> Dict[str, Any]:
        auth = deps.resolve_token(authorization)
        user_id = int(auth.get("user_id") or 0)
        device_id = str(auth.get("device_id") or auth.get("desktop_id") or "").strip()
        if not device_id:
            raise HTTPException(status_code=403, detail="A local computer session is required.")
        desktop = deps.get_fleet_store().ensure_standalone_manager_desktop(
            user_id=user_id,
            display_name=str(auth.get("device_name") or auth.get("desktop_name") or "EmploAI Desktop"),
            device_platform=str(auth.get("device_platform") or "desktop-electron"),
            device_key=f"local-app:{device_id}",
        )
        return {
            "computer_id": str(desktop.get("desktop_id") or ""),
        }

    def require_root_company(company_id: str, computer_id: str) -> Dict[str, Any]:
        try:
            company = deps.get_store().get_company(company_id)
        except CompanyNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        membership = next(
            (
                item
                for item in list(company.get("memberships") or [])
                if str(item.get("computer_id") or "") == computer_id
            ),
            None,
        )
        if not membership:
            raise HTTPException(status_code=404, detail="That company is not available on this computer.")
        if str(membership.get("membership_role") or "") != "root_controller":
            raise HTTPException(status_code=403, detail="Only the company's root computer may export its complete backup.")
        return company

    @router.post(
        "/api/companies/{company_id}/backup/export",
        response_model=CompanyBackupExportResponse,
    )
    async def export_company_backup(
        company_id: str,
        request: CompanyBackupExportRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> CompanyBackupExportResponse:
        local = local_computer(authorization)
        company = require_root_company(company_id, local["computer_id"])
        try:
            envelope, recovery_key = create_portable_company_backup(
                company,
                passphrase=request.passphrase,
            )
            deps.get_store().record_verified_backup(
                company_id=company_id,
                backup_id=str(envelope.get("backup_id") or ""),
                created_at=str(envelope.get("created_at") or ""),
            )
        except CompanyBackupError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return CompanyBackupExportResponse(
            backup=envelope,
            recovery_key=recovery_key,
        )

    return router
