from __future__ import annotations

from typing import Any, Mapping


READY_JOB_CONTRACT_STATES = frozenset({"ready", "limited_ready"})


def is_baseline_company_employee(employee: Mapping[str, Any]) -> bool:
    """Membership managers and default workers work immediately."""

    role = str(employee.get("system_role") or "").strip().lower()
    return (
        role == "manager" and bool(employee.get("protected"))
    ) or (
        role == "worker" and bool(employee.get("is_default"))
    )


def company_employee_can_accept_work(employee: Mapping[str, Any]) -> bool:
    if str(employee.get("status") or "active").strip().lower() != "active":
        return False
    if bool(employee.get("assignment_paused")):
        return False
    if is_baseline_company_employee(employee):
        return True
    return (
        str(employee.get("job_contract_status") or "")
        .strip()
        .lower()
        in READY_JOB_CONTRACT_STATES
    )


def company_employee_work_blocker(employee: Mapping[str, Any]) -> str:
    if str(employee.get("status") or "active").strip().lower() != "active":
        return "That employee is not active in this company."
    if bool(employee.get("assignment_paused")):
        return "New work is paused for that employee by the Company operator."
    if not company_employee_can_accept_work(employee):
        return (
            "That employee's job contract and readiness review must be "
            "completed before ordinary Company work can be assigned."
        )
    return ""


def company_assignment_blocker(
    company: Mapping[str, Any],
    employee: Mapping[str, Any],
) -> str:
    manifest = dict(company.get("manifest") or {})
    if str(manifest.get("operating_state") or "active").strip().lower() == "paused":
        return "New Company work is paused by the root operator."
    employee_blocker = company_employee_work_blocker(employee)
    if employee_blocker:
        return employee_blocker
    position_id = str(employee.get("position_id") or "").strip()
    if not position_id:
        return ""
    position = next(
        (
            item
            for item in list(company.get("positions") or [])
            if str(item.get("position_id") or "") == position_id
        ),
        None,
    )
    department_id = str((position or {}).get("department_id") or "").strip()
    if not department_id:
        return ""
    department = next(
        (
            item
            for item in list(company.get("departments") or [])
            if str(item.get("department_id") or "") == department_id
        ),
        None,
    )
    if department and bool(department.get("assignment_paused")):
        return "New work is paused for that department by the Company operator."
    return ""
