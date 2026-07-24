from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Header, HTTPException

from app_backend.company_intelligence_service import (
    CompanyIntelligenceService,
)
from app_backend.company_models import (
    CompanyFinancialEntryCreateRequest,
    CompanyKnowledgeCreateRequest,
    CompanyKnowledgeReviewRequest,
    CompanyMetricCreateRequest,
    CompanyMetricObservationRequest,
)
from app_backend.company_store import (
    CompanyNotFoundError,
    CompanySelectionError,
    CompanyStoreError,
)


@dataclass(frozen=True)
class AppCompanyIntelligenceRouterDeps:
    resolve_token: Callable[[Optional[str]], Dict[str, Any]]
    get_store: Callable[[], Any]
    get_fleet_store: Callable[[], Any]


def create_app_company_intelligence_router(
    deps: AppCompanyIntelligenceRouterDeps,
) -> APIRouter:
    router = APIRouter(tags=["app-company-intelligence"])

    def local_computer(
        authorization: Optional[str],
    ) -> Dict[str, Any]:
        auth = deps.resolve_token(authorization)
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
                user_id=int(auth.get("user_id") or 0),
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
        return {"computer_id": str(desktop.get("desktop_id") or "")}

    def service() -> CompanyIntelligenceService:
        return CompanyIntelligenceService(store=deps.get_store())

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

    @router.post("/api/companies/{company_id}/knowledge")
    async def publish_knowledge(
        company_id: str,
        request: CompanyKnowledgeCreateRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().publish_knowledge(
                company_id=company_id,
                computer_id=local["computer_id"],
                title=request.title,
                content=request.content,
                provenance=request.provenance,
                sensitivity=request.sensitivity,
                review_due_at=request.review_due_at,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.put(
        "/api/companies/{company_id}/knowledge/{knowledge_id}/review"
    )
    async def review_knowledge(
        company_id: str,
        knowledge_id: str,
        request: CompanyKnowledgeReviewRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().review_knowledge(
                company_id=company_id,
                computer_id=local["computer_id"],
                knowledge_id=knowledge_id,
                next_review_due_at=request.next_review_due_at,
                review_note=request.review_note,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/api/companies/{company_id}/metrics")
    async def create_metric(
        company_id: str,
        request: CompanyMetricCreateRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().create_metric(
                company_id=company_id,
                computer_id=local["computer_id"],
                name=request.name,
                definition=request.definition,
                formula=request.formula,
                unit=request.unit,
                source=request.source,
                cadence=request.cadence,
                owner_identity_id=request.owner_identity_id,
                guardrails=request.guardrails,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post(
        "/api/companies/{company_id}/metrics/{metric_id}/observations"
    )
    async def record_metric_observation(
        company_id: str,
        metric_id: str,
        request: CompanyMetricObservationRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().record_metric_observation(
                company_id=company_id,
                computer_id=local["computer_id"],
                metric_id=metric_id,
                value=request.value,
                period_start=request.period_start,
                period_end=request.period_end,
                confidence=request.confidence,
                evidence=request.evidence,
                note=request.note,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    @router.post("/api/companies/{company_id}/financial-entries")
    async def record_financial_entry(
        company_id: str,
        request: CompanyFinancialEntryCreateRequest,
        authorization: Optional[str] = Header(default=None),
    ) -> Dict[str, Any]:
        local = local_computer(authorization)
        try:
            return service().record_financial_entry(
                company_id=company_id,
                computer_id=local["computer_id"],
                entry_type=request.entry_type,
                amount=request.amount,
                currency=request.currency,
                description=request.description,
                recognized_at=request.recognized_at,
                source=request.source,
                evidence=request.evidence,
            )
        except Exception as exc:
            raise translate_error(exc) from exc

    return router
