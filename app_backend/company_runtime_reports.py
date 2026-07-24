from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from app_backend.company_domain import CompanyDomainService
from app_backend.job_catalog import get_job_catalog


def record_linked_company_report(
    *,
    company_store: Any,
    company_id: Optional[str],
    computer_id: str,
    report: Mapping[str, Any],
    route_metadata: Optional[Mapping[str, Any]] = None,
    task_id: Optional[str] = None,
    delegation_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Project a Fleet result into Company only when it carries an objective link."""

    metadata = dict(route_metadata or {})
    clean_company_id = str(company_id or metadata.get("company_id") or "").strip()
    objective_id = str(metadata.get("objective_id") or "").strip()
    if not clean_company_id or not objective_id:
        return None
    return CompanyDomainService(
        store=company_store,
        catalog=get_job_catalog(),
    ).record_assignment_report(
        company_id=clean_company_id,
        computer_id=computer_id,
        report=report,
        task_id=task_id,
        delegation_id=delegation_id,
        objective_id=objective_id,
    )
