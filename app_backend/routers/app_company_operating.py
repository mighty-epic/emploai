from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Header, HTTPException

from app_backend.company_models import (
    CompanyEmergencyControlRequest,
    CompanyHandoffCreateRequest,
    CompanyHandoffReviewRequest,
    CompanyInitiativeCreateRequest,
    CompanyInitiativeStatusRequest,
    CompanyRecurringOperationCreateRequest,
    CompanyRecurringOperationStatusRequest,
    CompanyRunbookCreateRequest,
    CompanyRunbookStatusRequest,
)
from app_backend.company_operating_service import CompanyOperatingService
from app_backend.company_store import (
    CompanyNotFoundError,
    CompanySelectionError,
    CompanyStoreError,
)


@dataclass(frozen=True)
class AppCompanyOperatingRouterDeps:
    resolve_token: Callable[[Optional[str]], Dict[str, Any]]
    get_store: Callable[[], Any]
    get_fleet_store: Callable[[], Any]


def create_app_company_operating_router(
    deps: AppCompanyOperatingRouterDeps,
) -> APIRouter:
    router = APIRouter(tags=["app-company-operating"])

    def local_computer(
        authorization: Optional[str],
    ) -> Dict[str, Any]:
        auth = deps.resolve_token(authorization)
        user_id = int(auth.get("user_id") or 0)
        device_id = str(
            auth.get("device_id") or auth.get("desktop_id") or ""
        ).strip()
        if not device_id:
            raise HTTPException(
                status_code=403,
                detail="A local computer session is required.",
            )
        desktop = (
            deps.get_fleet_store().ensure_standalone_manager_desktop(
                user_id=user_id,
                display_name=str(
                    auth.get("device_name")
                    or auth.get("desktop_name")
                    or "EmploAI Desktop"
                ),
                device_platform=str(
                    auth.get("device_platform") or "desktop-electron"
                ),
                device_key=f"local-app:{device_id}",
            )
        )
        return {
            "user_id": user_id,
            "computer_id": str(desktop.get("desktop_id") or ""),
        }

    def service() -> CompanyOperatingService:
        return CompanyOperatingService(store=deps.get_store())

    def translate_error(exc: Exception) -> HTTPException:
        if isinstance(exc, (CompanyNotFoundError, KeyError)):
            return HTTPException(
                status_code=404,
                detail=str(exc).strip("'"),
            )
        if isinstance(exc, CompanySelectionError):
            return HTTPException(status_code=403, detail=str(exc))
        if isinstance(exc, CompanyStoreError):
            return HTTPException(status_code=409, detail=str(exc))
        return HTTPException(status_code=400, detail=str(exc))

    @router.post("/api/companies/{company_id}/emergency-control")
    async def company_emergency_control(
        company_id: str,
        request: CompanyEmergencyControlRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().apply_emergency_control(
                company_id=company_id,
                computer_id=local["computer_id"],
                scope=request.scope,
                target_id=request.target_id,
                action=request.action,
                reason=request.reason,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/api/companies/{company_id}/initiatives")
    async def create_initiative(
        company_id: str,
        request: CompanyInitiativeCreateRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().create_initiative(
                company_id=company_id,
                computer_id=local["computer_id"],
                title=request.title,
                outcome=request.outcome,
                owner_identity_id=request.owner_identity_id,
                objective_ids=request.objective_ids,
                plan=request.plan,
                risks=request.risks,
                due_at=request.due_at,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.put(
        "/api/companies/{company_id}/initiatives/"
        "{initiative_id}/status"
    )
    async def update_initiative_status(
        company_id: str,
        initiative_id: str,
        request: CompanyInitiativeStatusRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().update_initiative_status(
                company_id=company_id,
                computer_id=local["computer_id"],
                initiative_id=initiative_id,
                status=request.status,
                reason=request.reason,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/api/companies/{company_id}/runbooks")
    async def create_runbook(
        company_id: str,
        request: CompanyRunbookCreateRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().create_runbook(
                company_id=company_id,
                computer_id=local["computer_id"],
                title=request.title,
                trigger=request.trigger,
                steps=request.steps,
                required_roles=request.required_roles,
                approval_gates=request.approval_gates,
                evidence_requirements=request.evidence_requirements,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.put(
        "/api/companies/{company_id}/runbooks/{runbook_id}/status"
    )
    async def update_runbook_status(
        company_id: str,
        runbook_id: str,
        request: CompanyRunbookStatusRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().update_runbook_status(
                company_id=company_id,
                computer_id=local["computer_id"],
                runbook_id=runbook_id,
                status=request.status,
                review_note=request.review_note,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post(
        "/api/companies/{company_id}/recurring-operations"
    )
    async def create_recurring_operation(
        company_id: str,
        request: CompanyRecurringOperationCreateRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().create_recurring_operation(
                company_id=company_id,
                computer_id=local["computer_id"],
                title=request.title,
                trigger=request.trigger,
                owner_identity_id=request.owner_identity_id,
                runbook_id=request.runbook_id,
                automation_id=request.automation_id,
                schedule=request.schedule,
                inputs=request.inputs,
                expected_output=request.expected_output,
                quality_gate=request.quality_gate,
                escalation_minutes=request.escalation_minutes,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.put(
        "/api/companies/{company_id}/recurring-operations/"
        "{operation_id}/status"
    )
    async def update_recurring_operation_status(
        company_id: str,
        operation_id: str,
        request: CompanyRecurringOperationStatusRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().update_recurring_operation_status(
                company_id=company_id,
                computer_id=local["computer_id"],
                operation_id=operation_id,
                status=request.status,
                reason=request.reason,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/api/companies/{company_id}/handoffs")
    async def create_handoff(
        company_id: str,
        request: CompanyHandoffCreateRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().create_handoff(
                company_id=company_id,
                computer_id=local["computer_id"],
                from_identity_id=request.from_identity_id,
                to_identity_id=request.to_identity_id,
                deliverable=request.deliverable,
                acceptance_criteria=request.acceptance_criteria,
                objective_id=request.objective_id,
                assignment_id=request.assignment_id,
                evidence=request.evidence,
                open_questions=request.open_questions,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post(
        "/api/companies/{company_id}/handoffs/{handoff_id}/review"
    )
    async def review_handoff(
        company_id: str,
        handoff_id: str,
        request: CompanyHandoffReviewRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().review_handoff(
                company_id=company_id,
                computer_id=local["computer_id"],
                handoff_id=handoff_id,
                reviewer_identity_id=request.reviewer_identity_id,
                decision=request.decision,
                rationale=request.rationale,
                rework_instructions=request.rework_instructions,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    return router
