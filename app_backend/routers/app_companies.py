from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Header, HTTPException

from app_backend.company_models import (
    CompanyContextView,
    CompanyCreateRequest,
    CompanyDeleteRequest,
    CompanyDetailView,
    CompanyMigrationCompleteRequest,
    CompanySelectRequest,
    CompanyUpdateRequest,
)
from app_backend.company_runtime_context import resolve_local_company_runtime
from app_backend.company_store import (
    CompanyNotFoundError,
    CompanyPartitionError,
    CompanyRootExistsError,
    CompanySelectionError,
    CompanyStore,
    CompanyStoreError,
)
from shared.memory import delete_company_memory
from shared.runtime_paths import runtime_home


@dataclass(frozen=True)
class AppCompaniesRouterDeps:
    resolve_token: Callable[[Optional[str]], Dict[str, Any]]
    get_store: Callable[[], CompanyStore]
    get_fleet_store: Callable[[], Any]
    bridge_for_user: Callable[[int], Any]
    consume_approved_confirmation: Callable[..., Dict[str, Any]]


def create_app_companies_router(deps: AppCompaniesRouterDeps) -> APIRouter:
    router = APIRouter(prefix="/api/companies", tags=["app-companies"])

    def local_context(authorization: Optional[str]) -> Dict[str, Any]:
        auth = deps.resolve_token(authorization)
        device_id = str(auth.get("device_id") or auth.get("desktop_id") or "").strip()
        if not device_id:
            raise HTTPException(status_code=403, detail="A local computer session is required.")
        runtime = resolve_local_company_runtime(
            auth=auth,
            company_store=deps.get_store(),
            fleet_store=deps.get_fleet_store(),
        )
        if not runtime:
            raise HTTPException(
                status_code=503,
                detail="The local Company runtime is unavailable.",
            )
        return {
            "auth": auth,
            "user_id": int(runtime["user_id"]),
            "computer_id": str(runtime["computer_id"]),
            "computer_name": str(runtime["computer_name"]),
            "manager_identity": runtime["manager_identity"],
            "default_worker_identity": runtime["default_worker_identity"],
        }

    def bind_company_identities(local: Dict[str, Any], company: Dict[str, Any]) -> Dict[str, Any]:
        company_id = str(company.get("company_id") or "")
        membership = next(
            (
                item
                for item in list(company.get("memberships") or [])
                if str(item.get("computer_id") or "") == local["computer_id"]
            ),
            {},
        )
        identities = deps.get_fleet_store().ensure_company_membership_identities(
            user_id=int(local["user_id"]),
            desktop_id=str(local["computer_id"]),
            company_id=company_id,
            company_name=str(local["computer_name"]),
            membership_role=str(membership.get("membership_role") or "worker_node"),
            adopt_unscoped=bool(
                str((company.get("migration") or {}).get("state") or "") == "legacy_compatibility"
            ),
        )
        local["manager_identity"] = identities["manager_identity"]
        local["default_worker_identity"] = identities["default_worker_identity"]
        deps.get_store().reconcile_membership_identities(
            company_id=company_id,
            computer_id=str(local["computer_id"]),
            manager_identity=local["manager_identity"],
            default_worker_identity=local["default_worker_identity"],
        )
        return local

    def translate_store_error(exc: CompanyStoreError) -> HTTPException:
        if isinstance(exc, CompanyNotFoundError):
            return HTTPException(status_code=404, detail=str(exc))
        if isinstance(exc, (CompanySelectionError, CompanyRootExistsError)):
            return HTTPException(status_code=409, detail=str(exc))
        if isinstance(exc, CompanyPartitionError):
            return HTTPException(status_code=503, detail=str(exc))
        return HTTPException(status_code=400, detail=str(exc))

    def require_root_company(
        *,
        company_id: str,
        computer_id: str,
    ) -> Dict[str, Any]:
        company = deps.get_store().get_company(company_id)
        membership = next(
            (
                item
                for item in list(company.get("memberships") or [])
                if str(item.get("computer_id") or "") == computer_id
            ),
            None,
        )
        if (
            not membership
            or str(membership.get("membership_role") or "") != "root_controller"
        ):
            raise CompanySelectionError(
                "Only this company's fixed root computer may perform that action."
            )
        return company

    @router.get("/context", response_model=CompanyContextView)
    async def company_context(
        authorization: Optional[str] = Header(default=None),
    ) -> CompanyContextView:
        local = local_context(authorization)
        try:
            payload = deps.get_store().context(
                computer_id=local["computer_id"],
                computer_name=local["computer_name"],
                manager_identity=local["manager_identity"],
                default_worker_identity=local["default_worker_identity"],
            )
            if payload.get("active_company"):
                local = bind_company_identities(local, payload["active_company"])
                payload = deps.get_store().context(
                    computer_id=local["computer_id"],
                    computer_name=local["computer_name"],
                    manager_identity=local["manager_identity"],
                    default_worker_identity=local["default_worker_identity"],
                )
        except CompanyStoreError as exc:
            raise translate_store_error(exc) from exc
        return CompanyContextView.model_validate(payload)

    @router.post("", response_model=CompanyDetailView)
    async def create_company(
        request: CompanyCreateRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> CompanyDetailView:
        local = local_context(authorization)
        try:
            company = deps.get_store().create_root_company(
                computer_id=local["computer_id"],
                computer_name=local["computer_name"],
                display_name=request.display_name,
            )
            company = deps.get_store().ensure_default_company(
                computer_id=local["computer_id"],
                computer_name=local["computer_name"],
                manager_identity=local["manager_identity"],
                default_worker_identity=local["default_worker_identity"],
            )
            local = bind_company_identities(local, company)
            company = deps.get_store().ensure_default_company(
                computer_id=local["computer_id"],
                computer_name=local["computer_name"],
                manager_identity=local["manager_identity"],
                default_worker_identity=local["default_worker_identity"],
            )
        except CompanyStoreError as exc:
            raise translate_store_error(exc) from exc
        return CompanyDetailView.model_validate(company)

    @router.put("/active", response_model=CompanyContextView)
    async def select_company(
        request: CompanySelectRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> CompanyContextView:
        local = local_context(authorization)
        try:
            deps.get_store().select_company(
                computer_id=local["computer_id"],
                company_id=request.company_id,
            )
            selected = deps.get_store().get_company(request.company_id)
            local = bind_company_identities(local, selected)
            payload = deps.get_store().context(
                computer_id=local["computer_id"],
                computer_name=local["computer_name"],
                manager_identity=local["manager_identity"],
                default_worker_identity=local["default_worker_identity"],
            )
        except CompanyStoreError as exc:
            raise translate_store_error(exc) from exc
        return CompanyContextView.model_validate(payload)

    @router.get("/{company_id}/migration-preview")
    async def migration_preview(
        company_id: str,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_context(authorization)
        try:
            require_root_company(
                company_id=company_id,
                computer_id=local["computer_id"],
            )
            preview = deps.get_store().migration_preview(company_id=company_id)
            session_preview = (
                deps.bridge_for_user(int(local["user_id"]))
                .session_manager.preview_unscoped_sessions()
            )
            fleet_preview = deps.get_fleet_store().preview_unscoped_company_records(
                user_id=int(local["user_id"]),
            )
            counts = dict(preview.get("counts") or {})
            counts.update(
                {
                    "legacy_chats_to_scope": int(
                        session_preview.get("unscoped_count") or 0
                    ),
                    "legacy_fleet_records_to_scope": int(
                        fleet_preview.get("unscoped_total") or 0
                    ),
                }
            )
            preview["counts"] = counts
            preview["legacy_data"] = {
                "chats": session_preview,
                "fleet": fleet_preview,
            }
            return preview
        except CompanyStoreError as exc:
            raise translate_store_error(exc) from exc

    @router.post("/{company_id}/migration-complete")
    async def complete_migration(
        company_id: str,
        request: CompanyMigrationCompleteRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_context(authorization)
        try:
            company = require_root_company(
                company_id=company_id,
                computer_id=local["computer_id"],
            )
            clean_backup_id = str(request.verified_backup_id or "").strip()
            backup_verified = any(
                str(item.get("backup_id") or "") == clean_backup_id
                and str(item.get("integrity") or "") == "verified"
                for item in list(company.get("backup_history") or [])
            )
            if not backup_verified:
                raise CompanySelectionError(
                    "Export and verify an encrypted company backup before completing migration."
                )

            # Keep legacy compatibility enabled until every external store is
            # explicitly bound. Each migration is idempotent, so a failed run
            # can be retried without losing the still-visible legacy records.
            local = bind_company_identities(local, company)
            session_report = (
                deps.bridge_for_user(int(local["user_id"]))
                .session_manager.migrate_unscoped_sessions_to_company(company_id)
            )
            fleet_report = deps.get_fleet_store().migrate_unscoped_company_records(
                user_id=int(local["user_id"]),
                company_id=company_id,
            )
            return deps.get_store().complete_migration(
                company_id=company_id,
                verified_backup_id=clean_backup_id,
                external_mapping_report={
                    "chats": session_report,
                    "fleet": fleet_report,
                },
            )
        except CompanyStoreError as exc:
            raise translate_store_error(exc) from exc

    @router.get("/{company_id}/deletion-preview")
    async def deletion_preview(
        company_id: str,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_context(authorization)
        try:
            require_root_company(
                company_id=company_id,
                computer_id=local["computer_id"],
            )
            return deps.get_store().deletion_preview(
                company_id=company_id,
                computer_id=local["computer_id"],
            )
        except CompanyStoreError as exc:
            raise translate_store_error(exc) from exc

    @router.delete("/{company_id}")
    async def delete_company(
        company_id: str,
        request: CompanyDeleteRequest,
        authorization: Optional[str] = Header(default=None),
        confirmation_id: Optional[str] = Header(
            default=None,
            alias="X-EmploAI-Confirmation-Id",
        ),
    ) -> Dict[str, Any]:
        local = local_context(authorization)
        try:
            require_root_company(
                company_id=company_id,
                computer_id=local["computer_id"],
            )
            deps.consume_approved_confirmation(
                user_id=int(local["user_id"]),
                confirmation_id=confirmation_id,
                action_kind="company_delete",
                executed_by_surface=str(
                    local["auth"].get("actor_kind") or "desktop_company"
                ),
                metadata={"company_id": company_id},
            )
            result = deps.get_store().delete_root_company(
                company_id=company_id,
                computer_id=local["computer_id"],
                company_name_confirmation=request.company_name_confirmation,
                active_work_action=request.active_work_action,
                final_backup_id=request.final_backup_id,
            )
            session_cleanup = (
                deps.bridge_for_user(int(local["user_id"]))
                .session_manager.delete_company_sessions(company_id)
            )
            fleet_cleanup = deps.get_fleet_store().delete_company_records(
                user_id=int(local["user_id"]),
                company_id=company_id,
            )
            home = runtime_home()
            memory_cleanup = (
                delete_company_memory(home, company_id=company_id)
                if home is not None
                else {"company_id": company_id, "deleted": False}
            )
            result["local_cleanup"] = {
                "sessions": session_cleanup,
                "fleet": fleet_cleanup,
                "memory": memory_cleanup,
            }
        except CompanyStoreError as exc:
            raise translate_store_error(exc) from exc
        return result

    @router.get("/{company_id}", response_model=CompanyDetailView)
    async def get_company(
        company_id: str,
        authorization: Optional[str] = Header(default=None),
    ) -> CompanyDetailView:
        local = local_context(authorization)
        try:
            company = deps.get_store().get_company(company_id)
        except CompanyStoreError as exc:
            raise translate_store_error(exc) from exc
        membership_computers = {
            str(item.get("computer_id") or "")
            for item in list(company.get("memberships") or [])
        }
        if local["computer_id"] not in membership_computers:
            raise HTTPException(status_code=404, detail="That company is not available on this computer.")
        return CompanyDetailView.model_validate(company)

    @router.patch("/{company_id}", response_model=CompanyDetailView)
    async def update_company(
        company_id: str,
        request: CompanyUpdateRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> CompanyDetailView:
        local = local_context(authorization)
        try:
            current = deps.get_store().get_company(company_id)
            membership = next(
                (
                    item
                    for item in list(current.get("memberships") or [])
                    if str(item.get("computer_id") or "") == local["computer_id"]
                ),
                None,
            )
            if not membership or str(membership.get("membership_role") or "") != "root_controller":
                raise CompanySelectionError("Only this company's root controller may change its manifest.")
            company = deps.get_store().update_company(
                company_id=company_id,
                display_name=request.display_name,
                onboarding_status=request.onboarding_status,
                manifest_updates=request.manifest,
            )
        except CompanyStoreError as exc:
            raise translate_store_error(exc) from exc
        return CompanyDetailView.model_validate(company)

    return router
