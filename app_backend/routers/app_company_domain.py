from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app_backend.company_domain import CompanyDomainService
from app_backend.company_models import (
    CompanyDepartmentCreateRequest,
    CompanyDecisionCreateRequest,
    CompanyObjectiveAssignmentLinkRequest,
    CompanyObjectiveCreateRequest,
    CompanyObjectiveStatusRequest,
    CompanyJobContractUpdateRequest,
    CompanyPolicyCreateRequest,
    CompanyPositionCreateRequest,
    CompanyPositionOccupantChangeRequest,
    CompanyReadinessReviewRequest,
    CompanyReportReviewRequest,
)
from app_backend.company_store import CompanyNotFoundError, CompanySelectionError, CompanyStoreError
from app_backend.job_catalog import JobCatalog


@dataclass(frozen=True)
class AppCompanyDomainRouterDeps:
    resolve_token: Callable[[Optional[str]], Dict[str, Any]]
    get_store: Callable[[], Any]
    get_fleet_store: Callable[[], Any]
    get_job_catalog: Callable[[], JobCatalog]


def create_app_company_domain_router(deps: AppCompanyDomainRouterDeps) -> APIRouter:
    router = APIRouter(tags=["app-company-domain"])

    def local_computer(authorization: Optional[str]) -> Dict[str, Any]:
        auth = deps.resolve_token(authorization)
        user_id = int(auth.get("user_id") or 0)
        device_id = str(auth.get("device_id") or auth.get("desktop_id") or "").strip()
        if not device_id:
            raise HTTPException(status_code=403, detail="A local computer session is required.")
        device_name = str(auth.get("device_name") or auth.get("desktop_name") or "EmploAI Desktop").strip()
        desktop = deps.get_fleet_store().ensure_standalone_manager_desktop(
            user_id=user_id,
            display_name=device_name,
            device_platform=str(auth.get("device_platform") or "desktop-electron"),
            device_key=f"local-app:{device_id}",
        )
        return {
            "user_id": user_id,
            "computer_id": str(desktop.get("desktop_id") or ""),
            "computer_name": str(desktop.get("display_name") or device_name),
        }

    def service() -> CompanyDomainService:
        return CompanyDomainService(store=deps.get_store(), catalog=deps.get_job_catalog())

    def translate_error(exc: Exception) -> HTTPException:
        if isinstance(exc, (CompanyNotFoundError, KeyError)):
            return HTTPException(status_code=404, detail=str(exc).strip("'"))
        if isinstance(exc, CompanySelectionError):
            return HTTPException(status_code=403, detail=str(exc))
        if isinstance(exc, CompanyStoreError):
            return HTTPException(status_code=409, detail=str(exc))
        return HTTPException(status_code=400, detail=str(exc))

    def require_membership(company_id: str, computer_id: str) -> Dict[str, Any]:
        company = deps.get_store().get_company(company_id)
        if not any(
            str(item.get("computer_id") or "") == computer_id
            for item in list(company.get("memberships") or [])
        ):
            raise CompanyNotFoundError("That company is not available on this computer.")
        return company

    def eligible_local_identities(
        *,
        company_id: str,
        local: Dict[str, Any],
    ) -> list[Dict[str, Any]]:
        company = require_membership(company_id, local["computer_id"])
        include_unscoped = (
            str((company.get("migration") or {}).get("state") or "")
            == "legacy_compatibility"
        )
        snapshot = deps.get_fleet_store().get_fleet_snapshot(
            user_id=local["user_id"],
            desktop_id=local["computer_id"],
        )
        eligible: list[Dict[str, Any]] = []
        for identity in list(snapshot.get("identities") or []):
            identity_company_id = str(
                dict(identity.get("metadata") or {}).get("company_id") or ""
            ).strip()
            if identity_company_id == company_id or (
                include_unscoped and not identity_company_id
            ):
                eligible.append(identity)
        return eligible

    def eligible_company_identities(
        *,
        company_id: str,
        local: Dict[str, Any],
    ) -> list[Dict[str, Any]]:
        company = require_membership(company_id, local["computer_id"])
        items = eligible_local_identities(
            company_id=company_id,
            local=local,
        )
        by_identity = {
            str(item.get("identity_id") or ""): dict(item)
            for item in items
            if str(item.get("identity_id") or "").strip()
        }
        membership_by_id = {
            str(item.get("membership_id") or ""): item
            for item in list(company.get("memberships") or [])
        }
        for employee in list(company.get("employees") or []):
            identity_id = str(employee.get("identity_id") or "").strip()
            if (
                not identity_id
                or identity_id in by_identity
                or str(employee.get("status") or "active") != "active"
                or employee.get("published_upstream") is False
            ):
                continue
            membership = membership_by_id.get(
                str(employee.get("home_membership_id") or ""),
                {},
            )
            by_identity[identity_id] = {
                "identity_id": identity_id,
                "instance_id": identity_id,
                "display_name": str(
                    employee.get("display_name") or "Company employee"
                ),
                "role": str(
                    employee.get("system_role") or "worker"
                ),
                "status": str(employee.get("status") or "active"),
                "is_default": bool(employee.get("is_default")),
                "protected": bool(employee.get("protected")),
                "desktop_id": str(
                    membership.get("computer_id") or ""
                )
                or None,
                "metadata": {
                    "company_id": company_id,
                    "company_directory": True,
                    "home_membership_id": str(
                        employee.get("home_membership_id") or ""
                    ),
                    "computer_name": str(
                        membership.get("computer_name") or ""
                    )
                    or None,
                },
            }
        return sorted(
            by_identity.values(),
            key=lambda item: (
                str(item.get("role") or "") != "manager",
                str(item.get("display_name") or "").casefold(),
            ),
        )

    @router.get("/api/company/job-catalog")
    async def job_catalog(
        query: Optional[str] = Query(default=None, max_length=240),
        division: Optional[str] = Query(default=None, max_length=120),
        review_status: Optional[str] = Query(default=None, max_length=80),
        limit: int = Query(default=245, ge=1, le=245),
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local_computer(authorization)
        catalog = deps.get_job_catalog()
        items = catalog.list_templates(
            query=query,
            division=division,
            review_status=review_status,
            limit=limit,
        )
        return {
            **catalog.summary(),
            "items": [
                {
                    "template_id": item.get("template_id"),
                    "title": item.get("title"),
                    "division": item.get("division"),
                    "division_label": item.get("division_label"),
                    "version": item.get("version"),
                    "source_commit": item.get("source_commit"),
                    "review_status": item.get("review_status"),
                    "availability_status": item.get("availability_status"),
                    "purpose": item.get("purpose"),
                    "mission": list(item.get("mission") or [])[:3],
                    "responsibilities": list(item.get("responsibilities") or [])[:6],
                    "deliverables": list(item.get("deliverables") or [])[:4],
                    "success_measures": list(item.get("success_measures") or [])[:4],
                    "source_metadata": dict(item.get("source_metadata") or {}),
                }
                for item in items
            ],
        }

    @router.get("/api/company/job-catalog/{template_id:path}")
    async def job_template_detail(
        template_id: str,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local_computer(authorization)
        try:
            return deps.get_job_catalog().get_template(template_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown job template") from exc

    @router.get("/api/companies/{company_id}/operating-model")
    async def company_operating_model(
        company_id: str,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            company = require_membership(company_id, local["computer_id"])
        except Exception as exc:
            raise translate_error(exc) from exc
        return {
            "company_id": company_id,
            "revision": int(company.get("revision") or 0),
            "departments": list(company.get("departments") or []),
            "positions": list(company.get("positions") or []),
            "job_contracts": list(company.get("job_contracts") or []),
            "objectives": list(company.get("objectives") or []),
            "initiatives": list(company.get("initiatives") or []),
            "runbooks": list(company.get("runbooks") or []),
            "recurring_operations": list(
                company.get("recurring_operations") or []
            ),
            "assignments": list(company.get("assignments") or []),
            "handoffs": list(company.get("handoffs") or []),
            "approvals": list(company.get("approvals") or []),
            "reports": list(company.get("reports") or []),
            "objective_reviews": list(company.get("objective_reviews") or []),
            "policies": list(company.get("policies") or []),
            "knowledge": list(company.get("knowledge") or []),
            "metrics": list(company.get("metrics") or []),
            "financial_entries": list(
                company.get("financial_entries") or []
            ),
            "company_audit_events": list(company.get("company_audit_events") or [])[-200:],
        }

    @router.get("/api/companies/{company_id}/eligible-identities")
    async def company_eligible_identities(
        company_id: str,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            items = eligible_company_identities(
                company_id=company_id,
                local=local,
            )
        except Exception as exc:
            raise translate_error(exc) from exc
        return {"company_id": company_id, "items": items}

    @router.post("/api/companies/{company_id}/departments")
    async def create_department(
        company_id: str,
        request: CompanyDepartmentCreateRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().create_department(
                company_id=company_id,
                computer_id=local["computer_id"],
                name=request.name,
                mandate=request.mandate,
                manager_identity_id=request.manager_identity_id,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/api/companies/{company_id}/positions")
    async def create_position(
        company_id: str,
        request: CompanyPositionCreateRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            identity_record = None
            if request.identity_id:
                identity_record = next(
                    (
                        item
                        for item in eligible_company_identities(
                            company_id=company_id,
                            local=local,
                        )
                        if str(item.get("identity_id") or "") == request.identity_id
                    ),
                    None,
                )
                if identity_record is None:
                    raise ValueError(
                        "The selected identity is not available in this company."
                    )
            return service().create_position(
                company_id=company_id,
                computer_id=local["computer_id"],
                title=request.title,
                template_id=request.template_id,
                manager_identity_id=request.manager_identity_id,
                department_id=request.department_id,
                identity_id=request.identity_id,
                overlay=request.overlay,
                identity_record=identity_record,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.put(
        "/api/companies/{company_id}/positions/{position_id}/occupant"
    )
    async def change_position_occupant(
        company_id: str,
        position_id: str,
        request: CompanyPositionOccupantChangeRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            identity_record = None
            if request.identity_id:
                identity_record = next(
                    (
                        item
                        for item in eligible_company_identities(
                            company_id=company_id,
                            local=local,
                        )
                        if str(item.get("identity_id") or "")
                        == request.identity_id
                    ),
                    None,
                )
                if identity_record is None:
                    raise ValueError(
                        "The selected identity is not eligible for this Company."
                    )
            return service().change_position_occupant(
                company_id=company_id,
                computer_id=local["computer_id"],
                position_id=position_id,
                identity_id=request.identity_id,
                move_from_position_id=request.move_from_position_id,
                reason=request.reason,
                identity_record=identity_record,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.put(
        "/api/companies/{company_id}/job-contracts/{job_contract_id}"
    )
    async def update_job_contract(
        company_id: str,
        job_contract_id: str,
        request: CompanyJobContractUpdateRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().update_job_contract(
                company_id=company_id,
                computer_id=local["computer_id"],
                job_contract_id=job_contract_id,
                updates=request.model_dump(exclude_unset=True),
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post(
        "/api/companies/{company_id}/job-contracts/"
        "{job_contract_id}/readiness"
    )
    async def review_job_readiness(
        company_id: str,
        job_contract_id: str,
        request: CompanyReadinessReviewRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().review_job_readiness(
                company_id=company_id,
                computer_id=local["computer_id"],
                job_contract_id=job_contract_id,
                reviewer_identity_id=request.reviewer_identity_id,
                checks=request.checks,
                evidence=request.evidence,
                missing_requirements=request.missing_requirements,
                limited_mode=request.limited_mode,
                limitations=request.limitations,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/api/companies/{company_id}/objectives")
    async def create_objective(
        company_id: str,
        request: CompanyObjectiveCreateRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().create_objective(
                company_id=company_id,
                computer_id=local["computer_id"],
                outcome=request.outcome,
                success_criteria=request.success_criteria,
                owner_identity_id=request.owner_identity_id,
                priority=request.priority,
                due_at=request.due_at,
                low_risk_auto_accept=request.low_risk_auto_accept,
                optional_proposals=request.optional_proposals,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.put("/api/companies/{company_id}/objectives/{objective_id}/status")
    async def update_objective_status(
        company_id: str,
        objective_id: str,
        request: CompanyObjectiveStatusRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().update_objective_status(
                company_id=company_id,
                computer_id=local["computer_id"],
                objective_id=objective_id,
                status=request.status,
                reason=request.reason,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/api/companies/{company_id}/objectives/{objective_id}/assignments")
    async def link_objective_assignment(
        company_id: str,
        objective_id: str,
        request: CompanyObjectiveAssignmentLinkRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().link_objective_assignment(
                company_id=company_id,
                computer_id=local["computer_id"],
                objective_id=objective_id,
                assignee_identity_id=request.assignee_identity_id,
                prompt=request.prompt,
                task_id=request.task_id,
                delegation_id=request.delegation_id,
                route=request.route,
                state=request.state,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/api/companies/{company_id}/report-reviews")
    async def review_report(
        company_id: str,
        request: CompanyReportReviewRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            company = require_membership(company_id, local["computer_id"])
            company_report = next(
                (
                    item
                    for item in list(company.get("reports") or [])
                    if str(item.get("report_id") or "") == request.report_id
                ),
                None,
            )
            if not company_report:
                raise KeyError("Unknown Company report")
            task_id = str(company_report.get("task_id") or "").strip()
            fleet_task = None
            if task_id:
                fleet_task = deps.get_fleet_store().get_worker_task(
                    user_id=local["user_id"],
                    task_id=task_id,
                )
                task_company_id = str(
                    dict(fleet_task.get("metadata") or {}).get("company_id") or ""
                ).strip()
                if task_company_id != company_id:
                    raise CompanySelectionError(
                        "The reviewed task does not belong to this company."
                    )
            review = service().review_report(
                company_id=company_id,
                computer_id=local["computer_id"],
                report_id=request.report_id,
                objective_id=request.objective_id,
                reviewer_identity_id=request.reviewer_identity_id,
                decision=request.decision,
                rationale=request.rationale,
                rework_instructions=request.rework_instructions,
            )
            if fleet_task:
                try:
                    deps.get_fleet_store().mark_worker_queue_reviewed(
                        user_id=local["user_id"],
                        worker_id=str(fleet_task.get("worker_id") or ""),
                        reviewed_report_id=request.report_id,
                        source="company_manager_review",
                        metadata={
                            "company_id": company_id,
                            "objective_id": review.get("objective_id"),
                            "decision": review.get("decision"),
                        },
                    )
                except (KeyError, ValueError) as exc:
                    review["queue_review_warning"] = str(exc)
            return review
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/api/companies/{company_id}/policies")
    async def create_policy(
        company_id: str,
        request: CompanyPolicyCreateRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().create_policy(
                company_id=company_id,
                computer_id=local["computer_id"],
                title=request.title,
                rule=request.rule,
                scope=request.scope,
                enforcement=request.enforcement,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/api/companies/{company_id}/decisions")
    async def record_decision(
        company_id: str,
        request: CompanyDecisionCreateRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().record_decision(
                company_id=company_id,
                computer_id=local["computer_id"],
                question=request.question,
                decision=request.decision,
                rationale=request.rationale,
                scope=request.scope,
                related_record_ids=request.related_record_ids,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    return router
