from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from app_backend.company_store import CompanySelectionError, CompanyStore
from app_backend.company_work_eligibility import (
    company_assignment_blocker,
    company_employee_can_accept_work,
    company_employee_work_blocker,
)
from app_backend.job_catalog import JobCatalog


OBJECTIVE_STATES = {
    "draft",
    "planned",
    "active",
    "at_risk",
    "blocked",
    "submitted",
    "completed",
    "stopped",
    "superseded",
}
REVIEW_DECISIONS = {"accepted", "rework_requested", "rejected", "escalated"}
READINESS_CHECKS = (
    "mission",
    "objective_context",
    "approved_input",
    "representative_deliverable",
    "approval_boundary",
    "handoff",
    "uncertainty",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any, *, field: str, limit: int = 2000) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text[:limit]


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


class CompanyDomainService:
    """Company-scoped jobs, objectives, reviews, and policy mutations."""

    def __init__(self, *, store: CompanyStore, catalog: JobCatalog):
        self.store = store
        self.catalog = catalog

    def _root_membership(self, company: Mapping[str, Any], computer_id: str) -> Dict[str, Any]:
        membership = self._membership(company, computer_id)
        if str(membership.get("membership_role") or "") != "root_controller":
            raise CompanySelectionError("This company change must be made on its root computer.")
        return membership

    def _membership(self, company: Mapping[str, Any], computer_id: str) -> Dict[str, Any]:
        membership = next(
            (
                dict(item)
                for item in list(company.get("memberships") or [])
                if str(item.get("computer_id") or "") == str(computer_id or "")
                and str(item.get("status") or "active") == "active"
            ),
            None,
        )
        if not membership:
            raise CompanySelectionError("This computer is not a member of that company.")
        return membership

    def create_department(
        self,
        *,
        company_id: str,
        computer_id: str,
        name: str,
        mandate: str,
        manager_identity_id: Optional[str],
    ) -> Dict[str, Any]:
        department_id = _id("dep")
        now = _utc_now()

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            membership = self._root_membership(company, computer_id)
            manager_id = str(
                manager_identity_id
                or membership.get("manager_identity_id")
                or ""
            ).strip()
            manager = next(
                (
                    item
                    for item in list(company.get("employees") or [])
                    if str(item.get("identity_id") or "") == manager_id
                    and str(item.get("status") or "active") == "active"
                ),
                None,
            )
            if manager_id and not manager:
                raise ValueError(
                    "The department manager does not belong to this company."
                )
            if manager and str(manager.get("system_role") or "") != "manager":
                raise ValueError(
                    "A department must be owned by a Company manager."
                )
            clean_name = _clean(
                name,
                field="department name",
                limit=160,
            )
            if any(
                str(item.get("name") or "").strip().casefold()
                == clean_name.casefold()
                and str(item.get("status") or "active") == "active"
                for item in list(company.get("departments") or [])
            ):
                raise ValueError(
                    "An active department already uses that name."
                )
            department = {
                "department_id": department_id,
                "name": clean_name,
                "mandate": _clean(
                    mandate,
                    field="department mandate",
                    limit=4000,
                ),
                "manager_identity_id": manager_id or None,
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
            company.setdefault("departments", []).append(department)
            self._audit(
                company,
                event_type="department_created",
                target_kind="department",
                target_id=department_id,
                metadata={"manager_identity_id": manager_id or None},
            )
            return department

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result

    def create_position(
        self,
        *,
        company_id: str,
        computer_id: str,
        title: str,
        template_id: Optional[str],
        manager_identity_id: Optional[str],
        department_id: Optional[str],
        identity_id: Optional[str],
        overlay: Mapping[str, Any],
        identity_record: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        template = self.catalog.get_template(template_id) if template_id else None
        now = _utc_now()
        position_id = _id("pos")
        contract_id = _id("job")

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            membership = self._root_membership(company, computer_id)
            employees = [dict(item) for item in list(company.get("employees") or [])]
            manager_id = str(manager_identity_id or membership.get("manager_identity_id") or "").strip()
            manager = next(
                (
                    item
                    for item in employees
                    if str(item.get("identity_id") or "") == manager_id
                    and str(item.get("status") or "active") == "active"
                ),
                None,
            )
            if manager_id and not manager:
                raise ValueError("The selected manager does not belong to this company.")
            if manager and str(manager.get("system_role") or "") != "manager":
                raise ValueError("The selected reporting identity is not a manager.")
            occupant_id = str(identity_id or "").strip() or None
            occupant = next(
                (item for item in employees if str(item.get("identity_id") or "") == occupant_id),
                None,
            )
            if occupant_id and not occupant:
                verified_identity_id = str(
                    (identity_record or {}).get("identity_id")
                    or (identity_record or {}).get("instance_id")
                    or ""
                ).strip()
                if verified_identity_id != occupant_id:
                    raise ValueError("The selected identity is not available on this computer.")
                metadata = dict((identity_record or {}).get("metadata") or {})
                occupant = {
                    "employee_id": _id("emp"),
                    "identity_id": occupant_id,
                    "display_name": _clean(
                        (identity_record or {}).get("display_name") or "Employee",
                        field="employee name",
                        limit=160,
                    ),
                    "system_role": str((identity_record or {}).get("role") or "worker"),
                    "company_role": _clean(title, field="position title", limit=160),
                    "protected": bool((identity_record or {}).get("protected")),
                    "is_default": bool((identity_record or {}).get("is_default") or metadata.get("is_default")),
                    "home_membership_id": str(membership.get("membership_id") or ""),
                    "status": str((identity_record or {}).get("status") or "active"),
                    "job_contract_status": "setup_incomplete",
                }
                employees.append(occupant)
            if occupant_id and any(
                str(item.get("occupant_identity_id") or "") == occupant_id
                and str(item.get("status") or "occupied")
                not in {"archived", "closed"}
                for item in list(company.get("positions") or [])
            ):
                raise ValueError(
                    "That identity already occupies a Company position. "
                    "Use a controlled job change or replacement flow."
                )
            if occupant_id and manager_id == occupant_id:
                if manager_id == str(
                    membership.get("manager_identity_id") or ""
                ).strip():
                    # The root Company manager reports to the human operator;
                    # never persist a self-referential manager edge.
                    manager_id = ""
                else:
                    raise ValueError(
                        "A Company manager cannot report to itself."
                    )
            clean_department = str(department_id or "").strip() or None
            if clean_department and not any(
                str(item.get("department_id") or item.get("id") or "") == clean_department
                for item in list(company.get("departments") or [])
            ):
                raise ValueError("Unknown department.")

            responsibilities = list(overlay.get("responsibilities") or (template or {}).get("responsibilities") or [])
            exclusions = list(overlay.get("non_responsibilities") or (template or {}).get("non_responsibilities") or [])
            mission = str(
                overlay.get("mission")
                or next(iter((template or {}).get("mission") or []), "")
                or (template or {}).get("purpose")
                or ""
            ).strip()
            position = {
                "position_id": position_id,
                "title": _clean(title or (template or {}).get("title"), field="position title", limit=160),
                "department_id": clean_department,
                "manager_identity_id": manager_id or None,
                "occupant_identity_id": occupant_id,
                "status": "occupied" if occupant_id else "open",
                "mission": mission,
                "created_at": now,
                "updated_at": now,
            }
            contract = {
                "job_contract_id": contract_id,
                "position_id": position_id,
                "version": 1,
                "status": "setup_incomplete",
                "template_ref": {
                    "template_id": (template or {}).get("template_id"),
                    "version": (template or {}).get("version"),
                    "source_commit": (template or {}).get("source_commit"),
                    "review_status": (template or {}).get("review_status"),
                },
                "mission": mission,
                "responsibilities": responsibilities,
                "non_responsibilities": exclusions,
                "deliverables": list(overlay.get("deliverables") or (template or {}).get("deliverables") or []),
                "inputs": list(overlay.get("inputs") or (template or {}).get("inputs") or []),
                "quality_gates": list(overlay.get("quality_gates") or (template or {}).get("quality_gates") or []),
                "success_measures": list(overlay.get("success_measures") or (template or {}).get("success_measures") or []),
                "reporting_cadence": overlay.get("reporting_cadence"),
                "escalation_route": overlay.get("escalation_route") or manager_id or "human_operator",
                "approved_tool_packs": list(overlay.get("approved_tool_packs") or []),
                "approved_workspace_ids": list(overlay.get("approved_workspace_ids") or []),
                "authority": {
                    "external_actions": "draft_only",
                    "spending": "not_allowed",
                    "hiring": "not_allowed",
                    **dict(overlay.get("authority") or {}),
                },
                "memory_policy": dict(overlay.get("memory_policy") or {}),
                "resource_policy": dict(overlay.get("resource_policy") or {}),
                "created_at": now,
                "updated_at": now,
            }
            company.setdefault("positions", []).append(position)
            company.setdefault("job_contracts", []).append(contract)
            if occupant_id:
                for employee in employees:
                    if str(employee.get("identity_id") or "") != occupant_id:
                        continue
                    employee["company_role"] = position["title"]
                    employee["position_id"] = position_id
                    employee["job_contract_id"] = contract_id
                    employee["job_contract_status"] = "setup_incomplete"
                company["employees"] = employees
            self._audit(
                company,
                event_type="position_created",
                target_kind="position",
                target_id=position_id,
                metadata={"template_id": template_id, "occupant_identity_id": occupant_id},
            )
            return {"position": position, "job_contract": contract}

        _company, result = self.store.mutate_company(company_id=company_id, mutation=mutation)
        return result

    def update_job_contract(
        self,
        *,
        company_id: str,
        computer_id: str,
        job_contract_id: str,
        updates: Mapping[str, Any],
    ) -> Dict[str, Any]:
        editable_fields = {
            "mission",
            "responsibilities",
            "non_responsibilities",
            "deliverables",
            "inputs",
            "quality_gates",
            "success_measures",
            "reporting_cadence",
            "escalation_route",
            "approved_tool_packs",
            "approved_workspace_ids",
            "authority",
            "memory_policy",
            "resource_policy",
            "missing_requirements",
        }

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            self._root_membership(company, computer_id)
            contract = next(
                (
                    item
                    for item in list(company.get("job_contracts") or [])
                    if str(item.get("job_contract_id") or "")
                    == str(job_contract_id or "")
                ),
                None,
            )
            if not contract:
                raise KeyError("Unknown job contract")
            supplied = {
                key: value
                for key, value in dict(updates or {}).items()
                if key in editable_fields and value is not None
            }
            if not supplied:
                return dict(contract)
            for key, value in supplied.items():
                if key in {
                    "responsibilities",
                    "non_responsibilities",
                    "deliverables",
                    "inputs",
                    "quality_gates",
                    "success_measures",
                    "approved_tool_packs",
                    "approved_workspace_ids",
                    "missing_requirements",
                }:
                    contract[key] = list(value or [])
                elif key in {"authority", "memory_policy", "resource_policy"}:
                    contract[key] = dict(value or {})
                else:
                    contract[key] = str(value or "").strip() or None
            contract["version"] = int(contract.get("version") or 1) + 1
            contract["status"] = "setup_incomplete"
            contract["updated_at"] = _utc_now()
            position_id = str(contract.get("position_id") or "")
            for employee in list(company.get("employees") or []):
                if str(employee.get("position_id") or "") == position_id:
                    employee["job_contract_status"] = "setup_incomplete"
            self._audit(
                company,
                event_type="job_contract_updated",
                target_kind="job_contract",
                target_id=str(job_contract_id),
                metadata={"version": contract["version"]},
            )
            return dict(contract)

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result

    def change_position_occupant(
        self,
        *,
        company_id: str,
        computer_id: str,
        position_id: str,
        identity_id: Optional[str],
        move_from_position_id: Optional[str],
        reason: str,
        identity_record: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Replace, move, or vacate a position without transferring private memory."""

        clean_position_id = str(position_id or "").strip()
        clean_identity_id = str(identity_id or "").strip() or None
        clean_move_from = str(move_from_position_id or "").strip() or None
        clean_reason = _clean(reason, field="occupant change reason", limit=2000)

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            membership = self._root_membership(company, computer_id)
            positions = [
                dict(item) for item in list(company.get("positions") or [])
            ]
            position = next(
                (
                    item
                    for item in positions
                    if str(item.get("position_id") or "") == clean_position_id
                    and str(item.get("status") or "") not in {"archived", "closed"}
                ),
                None,
            )
            if not position:
                raise KeyError("Unknown active position")
            previous_identity_id = (
                str(position.get("occupant_identity_id") or "").strip() or None
            )
            if previous_identity_id == clean_identity_id:
                raise ValueError("That identity already occupies this position.")

            employees = [
                dict(item) for item in list(company.get("employees") or [])
            ]
            new_employee = next(
                (
                    item
                    for item in employees
                    if str(item.get("identity_id") or "") == clean_identity_id
                ),
                None,
            )
            if clean_identity_id and not new_employee:
                verified_identity_id = str(
                    (identity_record or {}).get("identity_id")
                    or (identity_record or {}).get("instance_id")
                    or ""
                ).strip()
                if verified_identity_id != clean_identity_id:
                    raise ValueError(
                        "The selected identity is not eligible for this Company."
                    )
                metadata = dict((identity_record or {}).get("metadata") or {})
                new_employee = {
                    "employee_id": _id("emp"),
                    "identity_id": clean_identity_id,
                    "display_name": _clean(
                        (identity_record or {}).get("display_name") or "Employee",
                        field="employee name",
                        limit=160,
                    ),
                    "system_role": str(
                        (identity_record or {}).get("role") or "worker"
                    ),
                    "company_role": str(position.get("title") or "Employee"),
                    "protected": bool((identity_record or {}).get("protected")),
                    "is_default": bool(
                        (identity_record or {}).get("is_default")
                        or metadata.get("is_default")
                    ),
                    "home_membership_id": str(
                        metadata.get("home_membership_id")
                        or membership.get("membership_id")
                        or ""
                    ),
                    "status": str(
                        (identity_record or {}).get("status") or "active"
                    ),
                    "job_contract_status": "setup_incomplete",
                }
                employees.append(new_employee)

            occupied_elsewhere = next(
                (
                    item
                    for item in positions
                    if clean_identity_id
                    and str(item.get("position_id") or "") != clean_position_id
                    and str(item.get("occupant_identity_id") or "")
                    == clean_identity_id
                    and str(item.get("status") or "occupied")
                    not in {"archived", "closed"}
                ),
                None,
            )
            if occupied_elsewhere:
                occupied_id = str(occupied_elsewhere.get("position_id") or "")
                if clean_move_from != occupied_id:
                    raise ValueError(
                        "That identity already occupies another position. "
                        "Confirm a controlled move from that exact position."
                    )
                occupied_elsewhere["occupant_identity_id"] = None
                occupied_elsewhere["status"] = "open"
                occupied_elsewhere["updated_at"] = _utc_now()
            elif clean_move_from:
                raise ValueError(
                    "The selected move source does not match the identity's current position."
                )

            current_contract = next(
                (
                    item
                    for item in reversed(list(company.get("job_contracts") or []))
                    if str(item.get("position_id") or "") == clean_position_id
                    and str(item.get("status") or "") != "superseded"
                ),
                None,
            )
            contract_id = str(
                (current_contract or {}).get("job_contract_id") or ""
            ) or None
            now = _utc_now()

            if previous_identity_id:
                for employee in employees:
                    if (
                        str(employee.get("identity_id") or "")
                        != previous_identity_id
                    ):
                        continue
                    history = list(employee.get("position_history") or [])
                    history.append(
                        {
                            "position_id": clean_position_id,
                            "job_contract_id": employee.get("job_contract_id"),
                            "ended_at": now,
                            "reason": clean_reason,
                        }
                    )
                    employee["position_history"] = history[-100:]
                    employee["position_id"] = None
                    employee["job_contract_id"] = None
                    employee["job_contract_status"] = "unassigned"
                    employee["company_role"] = "Unassigned employee"

            if new_employee:
                new_employee["company_role"] = str(
                    position.get("title") or "Employee"
                )
                new_employee["position_id"] = clean_position_id
                new_employee["job_contract_id"] = contract_id
                new_employee["job_contract_status"] = "setup_incomplete"
                new_employee["status"] = "active"
            if current_contract:
                current_contract["status"] = "setup_incomplete"
                current_contract["readiness_reset_at"] = now
                current_contract["readiness_reset_reason"] = (
                    "position_occupant_changed"
                )
                current_contract["updated_at"] = now

            position["occupant_identity_id"] = clean_identity_id
            position["status"] = "occupied" if clean_identity_id else "open"
            position["readiness_status"] = (
                "setup_incomplete" if clean_identity_id else "unassigned"
            )
            position["updated_at"] = now
            company["positions"] = positions
            company["employees"] = employees
            self._audit(
                company,
                event_type="position_occupant_changed",
                target_kind="position",
                target_id=clean_position_id,
                metadata={
                    "previous_identity_id": previous_identity_id,
                    "new_identity_id": clean_identity_id,
                    "move_from_position_id": clean_move_from,
                    "private_memory_transferred": False,
                    "reason": clean_reason,
                },
            )
            return {
                "position": position,
                "previous_identity_id": previous_identity_id,
                "new_identity_id": clean_identity_id,
                "moved_from_position_id": clean_move_from,
                "readiness_required": bool(clean_identity_id),
                "private_memory_transferred": False,
            }

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result

    def review_job_readiness(
        self,
        *,
        company_id: str,
        computer_id: str,
        job_contract_id: str,
        reviewer_identity_id: Optional[str],
        checks: Mapping[str, Any],
        evidence: list[Mapping[str, Any]],
        missing_requirements: list[Mapping[str, Any]],
        limited_mode: bool,
        limitations: Optional[str],
    ) -> Dict[str, Any]:
        now = _utc_now()
        review_id = _id("ready")

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            membership = self._root_membership(company, computer_id)
            contract = next(
                (
                    item
                    for item in list(company.get("job_contracts") or [])
                    if str(item.get("job_contract_id") or "")
                    == str(job_contract_id or "")
                ),
                None,
            )
            if not contract:
                raise KeyError("Unknown job contract")
            position = next(
                (
                    item
                    for item in list(company.get("positions") or [])
                    if str(item.get("position_id") or "")
                    == str(contract.get("position_id") or "")
                ),
                None,
            )
            if not position:
                raise KeyError("Unknown position")
            occupant_id = str(
                position.get("occupant_identity_id") or ""
            ).strip()
            if not occupant_id:
                raise ValueError(
                    "Assign an identity before running readiness review."
                )
            reviewer_id = str(
                reviewer_identity_id
                or membership.get("manager_identity_id")
                or ""
            ).strip()
            if reviewer_id and not any(
                str(item.get("identity_id") or "") == reviewer_id
                for item in list(company.get("employees") or [])
            ):
                raise ValueError(
                    "The readiness reviewer does not belong to this company."
                )
            normalized_checks = {
                key: bool(checks.get(key)) for key in READINESS_CHECKS
            }
            missing = [dict(item) for item in missing_requirements]
            recorded_evidence = [dict(item) for item in evidence]
            all_demonstrated = all(normalized_checks.values())
            clean_limitations = str(limitations or "").strip()
            if (
                all_demonstrated
                and recorded_evidence
                and not missing
            ):
                readiness_status = "ready"
            elif (
                all_demonstrated
                and recorded_evidence
                and missing
                and limited_mode
                and clean_limitations
            ):
                readiness_status = "limited_ready"
            else:
                readiness_status = "blocked"
            review = {
                "readiness_review_id": review_id,
                "job_contract_id": str(job_contract_id),
                "position_id": str(position.get("position_id") or ""),
                "occupant_identity_id": occupant_id,
                "reviewer_identity_id": reviewer_id or None,
                "checks": normalized_checks,
                "evidence": recorded_evidence,
                "missing_requirements": missing,
                "limited_mode": bool(limited_mode),
                "limitations": clean_limitations or None,
                "status": readiness_status,
                "created_at": now,
            }
            contract.setdefault("readiness_reviews", []).append(review)
            contract["missing_requirements"] = missing
            contract["limited_mode"] = bool(
                readiness_status == "limited_ready"
            )
            contract["limitations"] = clean_limitations or None
            contract["status"] = readiness_status
            contract["updated_at"] = now
            position["readiness_status"] = readiness_status
            position["updated_at"] = now
            for employee in list(company.get("employees") or []):
                if str(employee.get("identity_id") or "") == occupant_id:
                    employee["job_contract_status"] = readiness_status
            self._audit(
                company,
                event_type="job_readiness_reviewed",
                target_kind="job_contract",
                target_id=str(job_contract_id),
                metadata={
                    "readiness_review_id": review_id,
                    "status": readiness_status,
                    "occupant_identity_id": occupant_id,
                },
            )
            return review

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result

    def create_objective(
        self,
        *,
        company_id: str,
        computer_id: str,
        outcome: str,
        success_criteria: str,
        owner_identity_id: Optional[str],
        priority: str,
        due_at: Optional[str],
        low_risk_auto_accept: bool,
        optional_proposals: list[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        now = _utc_now()
        objective_id = _id("obj")
        exact_user_outcome = _clean(outcome, field="outcome", limit=2000)
        exact_success_criteria = _clean(success_criteria, field="success criteria", limit=4000)

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            membership = self._root_membership(company, computer_id)
            owner_id = str(owner_identity_id or membership.get("manager_identity_id") or "").strip()
            if owner_id and not any(
                str(item.get("identity_id") or "") == owner_id
                for item in list(company.get("employees") or [])
            ):
                raise ValueError("The objective owner does not belong to this company.")
            objective = {
                "objective_id": objective_id,
                "outcome": exact_user_outcome,
                "success_criteria": exact_success_criteria,
                "user_directive": {
                    "outcome": exact_user_outcome,
                    "success_criteria": exact_success_criteria,
                },
                "optional_proposals": [
                    {**dict(item), "status": str(item.get("status") or "proposed")}
                    for item in optional_proposals
                ],
                "owner_identity_id": owner_id or None,
                "department_id": None,
                "priority": str(priority or "normal").strip().lower()[:40] or "normal",
                "due_at": str(due_at or "").strip() or None,
                "status": "planned",
                # Retained in the record for migration compatibility. The
                # authoritative company contract requires manager review.
                "low_risk_auto_accept": False,
                "linked_task_ids": [],
                "linked_report_ids": [],
                "created_at": now,
                "updated_at": now,
            }
            company.setdefault("objectives", []).append(objective)
            self._audit(
                company,
                event_type="objective_created",
                target_kind="objective",
                target_id=objective_id,
            )
            return objective

        _company, result = self.store.mutate_company(company_id=company_id, mutation=mutation)
        return result

    def update_objective_status(
        self,
        *,
        company_id: str,
        computer_id: str,
        objective_id: str,
        status: str,
        reason: Optional[str],
    ) -> Dict[str, Any]:
        clean_status = str(status or "").strip().lower()
        if clean_status not in OBJECTIVE_STATES:
            raise ValueError("Unknown objective state.")

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            self._root_membership(company, computer_id)
            objective = next(
                (
                    item
                    for item in list(company.get("objectives") or [])
                    if str(item.get("objective_id") or "") == str(objective_id)
                ),
                None,
            )
            if not objective:
                raise KeyError("Unknown objective")
            objective["status"] = clean_status
            objective["status_reason"] = str(reason or "").strip() or None
            objective["updated_at"] = _utc_now()
            self._audit(
                company,
                event_type="objective_status_changed",
                target_kind="objective",
                target_id=objective_id,
                metadata={"status": clean_status, "reason": objective["status_reason"]},
            )
            return dict(objective)

        _company, result = self.store.mutate_company(company_id=company_id, mutation=mutation)
        return result

    def link_objective_assignment(
        self,
        *,
        company_id: str,
        computer_id: str,
        objective_id: str,
        assignee_identity_id: str,
        prompt: str,
        task_id: Optional[str],
        delegation_id: Optional[str],
        route: Mapping[str, Any],
        state: str,
    ) -> Dict[str, Any]:
        now = _utc_now()
        assignment_id = _id("asn")
        clean_task_id = str(task_id or "").strip() or None
        clean_delegation_id = str(delegation_id or "").strip() or None
        if not clean_task_id and not clean_delegation_id:
            raise ValueError("A routed task or delegation is required.")

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            membership = self._root_membership(company, computer_id)
            objective = next(
                (
                    item
                    for item in list(company.get("objectives") or [])
                    if str(item.get("objective_id") or "") == str(objective_id)
                ),
                None,
            )
            if not objective:
                raise KeyError("Unknown objective")
            assignee = next(
                (
                    item
                    for item in list(company.get("employees") or [])
                    if str(item.get("identity_id") or "")
                    == str(assignee_identity_id or "")
                ),
                None,
            )
            if not assignee:
                raise ValueError("The assignment target does not belong to this company.")
            assignment_blocker = company_assignment_blocker(company, assignee)
            if assignment_blocker:
                raise ValueError(assignment_blocker)
            assignment = {
                "assignment_id": assignment_id,
                "objective_id": objective_id,
                "issuing_manager_identity_id": str(
                    membership.get("manager_identity_id") or ""
                )
                or None,
                "assignee_identity_id": str(assignee_identity_id),
                "prompt": _clean(prompt, field="assignment", limit=20000),
                "task_id": clean_task_id,
                "delegation_id": clean_delegation_id,
                "route": dict(route or {}),
                "status": str(state or "queued").strip().lower()[:80] or "queued",
                "report_id": None,
                "review_status": "awaiting_report",
                "created_at": now,
                "updated_at": now,
            }
            company.setdefault("assignments", []).append(assignment)
            linked_report = next(
                (
                    item
                    for item in list(company.get("reports") or [])
                    if (
                        clean_task_id
                        and str(item.get("task_id") or "") == clean_task_id
                    )
                    or (
                        clean_delegation_id
                        and str(item.get("delegation_id") or "")
                        == clean_delegation_id
                    )
                ),
                None,
            )
            if linked_report:
                assignment["report_id"] = str(linked_report.get("report_id") or "") or None
                assignment["status"] = "submitted"
                assignment["review_status"] = str(
                    linked_report.get("review_status") or "awaiting_review"
                )
                linked_report["assignment_id"] = assignment_id
                linked_report["objective_id"] = objective_id
                linked_report["updated_at"] = now
            link_id = clean_task_id or clean_delegation_id
            linked_task_ids = list(objective.get("linked_task_ids") or [])
            if link_id and link_id not in linked_task_ids:
                linked_task_ids.append(link_id)
            objective["linked_task_ids"] = linked_task_ids
            if str(objective.get("status") or "") in {"draft", "planned"}:
                objective["status"] = "active"
            objective["updated_at"] = now
            self._audit(
                company,
                event_type="objective_assignment_created",
                target_kind="assignment",
                target_id=assignment_id,
                metadata={
                    "objective_id": objective_id,
                    "assignee_identity_id": assignee_identity_id,
                    "task_id": clean_task_id,
                    "delegation_id": clean_delegation_id,
                },
            )
            return assignment

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result

    def record_assignment_report(
        self,
        *,
        company_id: str,
        computer_id: str,
        report: Mapping[str, Any],
        task_id: Optional[str] = None,
        delegation_id: Optional[str] = None,
        objective_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Attach an execution report to its durable Company assignment.

        Fleet remains authoritative for execution. Company stores a compact,
        reviewable result record so completion cannot be mistaken for business
        acceptance. The operation is idempotent for reconnect/replay safety.
        """

        now = _utc_now()
        clean_task_id = str(task_id or report.get("task_id") or "").strip() or None
        clean_delegation_id = str(
            delegation_id or report.get("delegation_id") or ""
        ).strip() or None
        clean_report_id = str(report.get("report_id") or "").strip()
        if not clean_report_id:
            route_id = clean_task_id or clean_delegation_id
            if not route_id:
                raise ValueError("The assignment report has no stable route identifier.")
            clean_report_id = f"company_{route_id}"

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            self._membership(company, computer_id)
            assignment = next(
                (
                    item
                    for item in list(company.get("assignments") or [])
                    if (
                        clean_task_id
                        and str(item.get("task_id") or "") == clean_task_id
                    )
                    or (
                        clean_delegation_id
                        and str(item.get("delegation_id") or "")
                        == clean_delegation_id
                    )
                ),
                None,
            )
            resolved_objective_id = str(
                (assignment or {}).get("objective_id") or objective_id or ""
            ).strip()
            if not resolved_objective_id:
                raise ValueError("The assignment report is not linked to a Company objective.")
            objective = next(
                (
                    item
                    for item in list(company.get("objectives") or [])
                    if str(item.get("objective_id") or "")
                    == resolved_objective_id
                ),
                None,
            )
            if not objective:
                raise KeyError("Unknown objective")

            compact_report = {
                "report_id": clean_report_id,
                "objective_id": resolved_objective_id,
                "assignment_id": str(
                    (assignment or {}).get("assignment_id") or ""
                )
                or None,
                "assignee_identity_id": str(
                    (assignment or {}).get("assignee_identity_id") or ""
                )
                or None,
                "task_id": clean_task_id,
                "delegation_id": clean_delegation_id,
                "worker_id": str(report.get("worker_id") or "").strip() or None,
                "execution_status": str(report.get("status") or "completed")
                .strip()
                .lower()[:80],
                "summary": _clean(
                    report.get("summary") or "Assignment report submitted",
                    field="report summary",
                    limit=8000,
                ),
                "evidence": list(report.get("evidence") or []),
                "artifacts": list(report.get("artifacts") or []),
                "blockers": list(report.get("blockers") or []),
                "confidence": str(report.get("confidence") or "").strip() or None,
                "next_suggested_action": str(
                    report.get("next_suggested_action") or ""
                ).strip()
                or None,
                "review_status": "awaiting_review",
                "submitted_at": str(report.get("created_at") or now),
                "updated_at": now,
            }
            company_reports = company.setdefault("reports", [])
            existing = next(
                (
                    item
                    for item in company_reports
                    if str(item.get("report_id") or "") == clean_report_id
                ),
                None,
            )
            if existing:
                previous_review_status = str(
                    existing.get("review_status") or "awaiting_review"
                )
                existing.update(compact_report)
                if previous_review_status != "awaiting_review":
                    existing["review_status"] = previous_review_status
                stored_report = existing
            else:
                company_reports.append(compact_report)
                stored_report = compact_report

            if assignment:
                assignment["report_id"] = clean_report_id
                assignment["status"] = "submitted"
                assignment["review_status"] = stored_report["review_status"]
                assignment["updated_at"] = now

            report_ids = list(objective.get("linked_report_ids") or [])
            if clean_report_id not in report_ids:
                report_ids.append(clean_report_id)
            objective["linked_report_ids"] = report_ids
            objective_assignments = [
                item
                for item in list(company.get("assignments") or [])
                if str(item.get("objective_id") or "") == resolved_objective_id
            ]
            if objective_assignments and all(
                str(item.get("report_id") or "").strip()
                for item in objective_assignments
            ):
                objective["status"] = "submitted"
            elif str(objective.get("status") or "") in {"draft", "planned"}:
                objective["status"] = "active"
            objective["updated_at"] = now
            self._audit(
                company,
                event_type="assignment_report_submitted",
                target_kind="report",
                target_id=clean_report_id,
                metadata={
                    "objective_id": resolved_objective_id,
                    "assignment_id": stored_report.get("assignment_id"),
                    "task_id": clean_task_id,
                    "delegation_id": clean_delegation_id,
                },
            )
            return dict(stored_report)

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result

    def review_report(
        self,
        *,
        company_id: str,
        computer_id: str,
        report_id: str,
        objective_id: Optional[str],
        reviewer_identity_id: Optional[str],
        decision: str,
        rationale: str,
        rework_instructions: Optional[str],
    ) -> Dict[str, Any]:
        clean_decision = str(decision or "").strip().lower()
        if clean_decision not in REVIEW_DECISIONS:
            raise ValueError("Unknown review decision.")
        now = _utc_now()
        review_id = _id("rev")

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            membership = self._root_membership(company, computer_id)
            reviewer_id = str(reviewer_identity_id or membership.get("manager_identity_id") or "").strip()
            if reviewer_id and not any(
                str(item.get("identity_id") or "") == reviewer_id
                for item in list(company.get("employees") or [])
            ):
                raise ValueError("The report reviewer does not belong to this company.")
            company_report = next(
                (
                    item
                    for item in list(company.get("reports") or [])
                    if str(item.get("report_id") or "") == str(report_id or "")
                ),
                None,
            )
            if not company_report:
                raise KeyError("Unknown Company report")
            resolved_objective_id = str(
                company_report.get("objective_id") or objective_id or ""
            ).strip()
            if objective_id and resolved_objective_id != str(objective_id):
                raise ValueError("The report is linked to a different objective.")
            assignment = next(
                (
                    item
                    for item in list(company.get("assignments") or [])
                    if str(item.get("assignment_id") or "")
                    == str(company_report.get("assignment_id") or "")
                    or (
                        company_report.get("task_id")
                        and str(item.get("task_id") or "")
                        == str(company_report.get("task_id") or "")
                    )
                    or (
                        company_report.get("delegation_id")
                        and str(item.get("delegation_id") or "")
                        == str(company_report.get("delegation_id") or "")
                    )
                ),
                None,
            )
            review = {
                "review_id": review_id,
                "report_id": _clean(report_id, field="report id", limit=160),
                "objective_id": resolved_objective_id or None,
                "reviewer_identity_id": reviewer_id or None,
                "decision": clean_decision,
                "rationale": _clean(rationale, field="review rationale", limit=4000),
                "rework_instructions": str(rework_instructions or "").strip() or None,
                "assignment_id": str((assignment or {}).get("assignment_id") or "") or None,
                "task_id": str(company_report.get("task_id") or "") or None,
                "delegation_id": str(company_report.get("delegation_id") or "") or None,
                "assignee_identity_id": str(
                    (assignment or {}).get("assignee_identity_id") or ""
                )
                or None,
                "created_at": now,
            }
            company.setdefault("objective_reviews", []).append(review)
            company_report["review_status"] = clean_decision
            company_report["review_id"] = review_id
            company_report["reviewed_at"] = now
            company_report["updated_at"] = now
            if assignment:
                assignment["review_status"] = clean_decision
                assignment["status"] = (
                    "accepted"
                    if clean_decision == "accepted"
                    else "rework_requested"
                    if clean_decision == "rework_requested"
                    else clean_decision
                )
                assignment["updated_at"] = now
            if resolved_objective_id:
                objective = next(
                    (
                        item
                        for item in list(company.get("objectives") or [])
                        if str(item.get("objective_id") or "")
                        == resolved_objective_id
                    ),
                    None,
                )
                if not objective:
                    raise KeyError("Unknown objective")
                report_ids = list(objective.get("linked_report_ids") or [])
                if report_id not in report_ids:
                    report_ids.append(report_id)
                objective["linked_report_ids"] = report_ids
                if clean_decision == "accepted":
                    objective_assignments = [
                        item
                        for item in list(company.get("assignments") or [])
                        if str(item.get("objective_id") or "")
                        == resolved_objective_id
                    ]
                    if objective_assignments and all(
                        str(item.get("review_status") or "") == "accepted"
                        for item in objective_assignments
                    ):
                        objective["status"] = "completed"
                    else:
                        objective["status"] = "submitted"
                elif clean_decision == "rework_requested":
                    objective["status"] = "active"
                elif clean_decision == "rejected":
                    objective["status"] = "blocked"
                elif clean_decision == "escalated":
                    objective["status"] = "at_risk"
                objective["updated_at"] = now
            self._audit(
                company,
                event_type="report_reviewed",
                target_kind="report",
                target_id=report_id,
                metadata={
                    "decision": clean_decision,
                    "objective_id": resolved_objective_id or None,
                    "assignment_id": review.get("assignment_id"),
                },
            )
            return review

        _company, result = self.store.mutate_company(company_id=company_id, mutation=mutation)
        return result

    def create_policy(
        self,
        *,
        company_id: str,
        computer_id: str,
        title: str,
        rule: str,
        scope: str,
        enforcement: str,
    ) -> Dict[str, Any]:
        now = _utc_now()
        policy_id = _id("pol")

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            self._root_membership(company, computer_id)
            policy = {
                "policy_id": policy_id,
                "title": _clean(title, field="policy title", limit=200),
                "rule": _clean(rule, field="policy rule", limit=6000),
                "scope": str(scope or "company").strip()[:120] or "company",
                "enforcement": str(enforcement or "manager").strip()[:120] or "manager",
                "status": "active",
                "version": 1,
                "created_at": now,
                "updated_at": now,
            }
            company.setdefault("policies", []).append(policy)
            self._audit(
                company,
                event_type="policy_created",
                target_kind="policy",
                target_id=policy_id,
            )
            return policy

        _company, result = self.store.mutate_company(company_id=company_id, mutation=mutation)
        return result

    def record_decision(
        self,
        *,
        company_id: str,
        computer_id: str,
        question: str,
        decision: str,
        rationale: str,
        scope: str,
        related_record_ids: list[str],
    ) -> Dict[str, Any]:
        decision_id = _id("dec")
        now = _utc_now()

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            membership = self._root_membership(company, computer_id)
            record = {
                "decision_id": decision_id,
                "question": _clean(
                    question,
                    field="decision question",
                    limit=2000,
                ),
                "decision": _clean(
                    decision,
                    field="decision",
                    limit=4000,
                ),
                "rationale": _clean(
                    rationale,
                    field="decision rationale",
                    limit=4000,
                ),
                "scope": str(scope or "company").strip()[:160],
                "related_record_ids": [
                    str(item).strip()[:240]
                    for item in related_record_ids
                    if str(item).strip()
                ],
                "decided_by": "human_operator",
                "recorded_by_identity_id": str(
                    membership.get("manager_identity_id") or ""
                )
                or None,
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
            company.setdefault("decisions", []).append(record)
            self._audit(
                company,
                event_type="decision_recorded",
                target_kind="decision",
                target_id=decision_id,
                metadata={"scope": record["scope"]},
            )
            return record

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result

    def _audit(
        self,
        company: Dict[str, Any],
        *,
        event_type: str,
        target_kind: str,
        target_id: str,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        company.setdefault("company_audit_events", []).append(
            {
                "event_id": _id("evt"),
                "event_type": event_type,
                "actor_kind": "human_operator",
                "actor_id": "local_os_operator",
                "target_kind": target_kind,
                "target_id": target_id,
                "metadata": dict(metadata or {}),
                "created_at": _utc_now(),
            }
        )
