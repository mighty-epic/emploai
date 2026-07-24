from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from app_backend.company_store import CompanySelectionError, CompanyStore


INITIATIVE_STATES = frozenset(
    {
        "proposed",
        "scoped",
        "approved",
        "planned",
        "active",
        "at_risk",
        "blocked",
        "completed",
        "stopped",
        "superseded",
        "reviewed",
    }
)
HANDOFF_DECISIONS = frozenset({"accepted", "rework_requested"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"


def _required_text(value: Any, field: str, limit: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text[:limit]


class CompanyOperatingService:
    """Durable Company planning, runbook, and handoff records."""

    def __init__(self, *, store: CompanyStore):
        self.store = store

    @staticmethod
    def _root_membership(
        company: Mapping[str, Any],
        computer_id: str,
    ) -> Mapping[str, Any]:
        membership = next(
            (
                item
                for item in list(company.get("memberships") or [])
                if str(item.get("computer_id") or "")
                == str(computer_id or "")
                and str(item.get("status") or "active") == "active"
            ),
            None,
        )
        if not membership:
            raise CompanySelectionError(
                "This computer is not a member of that company."
            )
        if str(membership.get("membership_role") or "") != "root_controller":
            raise CompanySelectionError(
                "This Company record must be changed on its root computer."
            )
        return membership

    @staticmethod
    def _employee(
        company: Mapping[str, Any],
        identity_id: Optional[str],
    ) -> Optional[Mapping[str, Any]]:
        clean_id = str(identity_id or "").strip()
        if not clean_id:
            return None
        return next(
            (
                item
                for item in list(company.get("employees") or [])
                if str(item.get("identity_id") or "") == clean_id
                and str(item.get("status") or "active") == "active"
            ),
            None,
        )

    @staticmethod
    def _audit(
        company: Dict[str, Any],
        *,
        event_type: str,
        target_kind: str,
        target_id: str,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        company.setdefault("company_audit_events", []).append(
            {
                "event_id": _record_id("caud"),
                "event_type": event_type,
                "target_kind": target_kind,
                "target_id": target_id,
                "metadata": dict(metadata or {}),
                "created_at": _utc_now(),
            }
        )

    def create_initiative(
        self,
        *,
        company_id: str,
        computer_id: str,
        title: str,
        outcome: str,
        owner_identity_id: Optional[str],
        objective_ids: list[str],
        plan: list[str],
        risks: list[str],
        due_at: Optional[str],
    ) -> Dict[str, Any]:
        initiative_id = _record_id("ini")
        now = _utc_now()

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            membership = self._root_membership(company, computer_id)
            owner_id = str(
                owner_identity_id
                or membership.get("manager_identity_id")
                or ""
            ).strip()
            if owner_id and not self._employee(company, owner_id):
                raise ValueError(
                    "The initiative owner does not belong to this company."
                )
            known_objective_ids = {
                str(item.get("objective_id") or "")
                for item in list(company.get("objectives") or [])
            }
            clean_objective_ids = [
                str(item).strip()
                for item in objective_ids
                if str(item).strip()
            ]
            if any(
                item not in known_objective_ids
                for item in clean_objective_ids
            ):
                raise ValueError(
                    "An initiative objective is not in this company."
                )
            initiative = {
                "initiative_id": initiative_id,
                "title": _required_text(title, "initiative title", 240),
                "outcome": _required_text(
                    outcome,
                    "initiative outcome",
                    2000,
                ),
                "owner_identity_id": owner_id or None,
                "objective_ids": clean_objective_ids,
                "plan": [
                    str(item).strip()[:2000]
                    for item in plan
                    if str(item).strip()
                ],
                "risks": [
                    str(item).strip()[:2000]
                    for item in risks
                    if str(item).strip()
                ],
                "due_at": str(due_at or "").strip() or None,
                "status": "proposed",
                "created_at": now,
                "updated_at": now,
            }
            company.setdefault("initiatives", []).append(initiative)
            self._audit(
                company,
                event_type="initiative_created",
                target_kind="initiative",
                target_id=initiative_id,
                metadata={"objective_ids": clean_objective_ids},
            )
            return initiative

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result

    def update_initiative_status(
        self,
        *,
        company_id: str,
        computer_id: str,
        initiative_id: str,
        status: str,
        reason: Optional[str],
    ) -> Dict[str, Any]:
        clean_status = str(status or "").strip().lower()
        if clean_status not in INITIATIVE_STATES:
            raise ValueError("Unknown initiative state.")

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            self._root_membership(company, computer_id)
            initiative = next(
                (
                    item
                    for item in list(company.get("initiatives") or [])
                    if str(item.get("initiative_id") or "")
                    == str(initiative_id or "")
                ),
                None,
            )
            if not initiative:
                raise KeyError("Unknown initiative")
            initiative["status"] = clean_status
            initiative["status_reason"] = (
                str(reason or "").strip() or None
            )
            initiative["updated_at"] = _utc_now()
            self._audit(
                company,
                event_type="initiative_status_changed",
                target_kind="initiative",
                target_id=str(initiative_id),
                metadata={
                    "status": clean_status,
                    "reason": initiative["status_reason"],
                },
            )
            return dict(initiative)

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result

    def create_runbook(
        self,
        *,
        company_id: str,
        computer_id: str,
        title: str,
        trigger: str,
        steps: list[Mapping[str, Any]],
        required_roles: list[str],
        approval_gates: list[Mapping[str, Any]],
        evidence_requirements: list[str],
    ) -> Dict[str, Any]:
        if not steps:
            raise ValueError("A runbook requires at least one step.")
        runbook_id = _record_id("run")
        now = _utc_now()

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            self._root_membership(company, computer_id)
            runbook = {
                "runbook_id": runbook_id,
                "title": _required_text(title, "runbook title", 240),
                "trigger": _required_text(
                    trigger,
                    "runbook trigger",
                    2000,
                ),
                "steps": [dict(item) for item in steps],
                "required_roles": [
                    str(item).strip()[:240]
                    for item in required_roles
                    if str(item).strip()
                ],
                "approval_gates": [
                    dict(item) for item in approval_gates
                ],
                "evidence_requirements": [
                    str(item).strip()[:1000]
                    for item in evidence_requirements
                    if str(item).strip()
                ],
                "status": "draft",
                "version": 1,
                "created_at": now,
                "updated_at": now,
            }
            company.setdefault("runbooks", []).append(runbook)
            self._audit(
                company,
                event_type="runbook_created",
                target_kind="runbook",
                target_id=runbook_id,
            )
            return runbook

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result

    def update_runbook_status(
        self,
        *,
        company_id: str,
        computer_id: str,
        runbook_id: str,
        status: str,
        review_note: str,
    ) -> Dict[str, Any]:
        clean_status = str(status or "").strip().lower()
        if clean_status not in {"active", "archived"}:
            raise ValueError("Unknown runbook state.")

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            membership = self._root_membership(company, computer_id)
            runbook = next(
                (
                    item
                    for item in list(company.get("runbooks") or [])
                    if str(item.get("runbook_id") or "")
                    == str(runbook_id or "")
                ),
                None,
            )
            if not runbook:
                raise KeyError("Unknown runbook")
            now = _utc_now()
            runbook["status"] = clean_status
            runbook["review_note"] = _required_text(
                review_note,
                "runbook review note",
                4000,
            )
            runbook["reviewed_by_identity_id"] = str(
                membership.get("manager_identity_id") or ""
            ) or None
            runbook["reviewed_at"] = now
            runbook["updated_at"] = now
            self._audit(
                company,
                event_type=f"runbook_{clean_status}",
                target_kind="runbook",
                target_id=str(runbook_id),
                metadata={
                    "reviewed_by_identity_id": runbook[
                        "reviewed_by_identity_id"
                    ],
                },
            )
            return dict(runbook)

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result

    def create_recurring_operation(
        self,
        *,
        company_id: str,
        computer_id: str,
        title: str,
        trigger: str,
        owner_identity_id: Optional[str],
        runbook_id: str,
        automation_id: Optional[str],
        schedule: str,
        inputs: list[str],
        expected_output: str,
        quality_gate: str,
        escalation_minutes: int,
    ) -> Dict[str, Any]:
        operation_id = _record_id("rop")
        now = _utc_now()

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            membership = self._root_membership(company, computer_id)
            owner_id = str(
                owner_identity_id
                or membership.get("manager_identity_id")
                or ""
            ).strip()
            if owner_id and not self._employee(company, owner_id):
                raise ValueError(
                    "The recurring-operation owner does not belong to this company."
                )
            runbook = next(
                (
                    item
                    for item in list(company.get("runbooks") or [])
                    if str(item.get("runbook_id") or "")
                    == str(runbook_id or "")
                ),
                None,
            )
            if not runbook:
                raise ValueError(
                    "A recurring operation requires a runbook from this company."
                )
            operation = {
                "operation_id": operation_id,
                "title": _required_text(
                    title,
                    "recurring operation title",
                    240,
                ),
                "trigger": _required_text(
                    trigger,
                    "recurring operation trigger",
                    2000,
                ),
                "owner_identity_id": owner_id or None,
                "runbook_id": str(runbook_id),
                "automation_id": (
                    str(automation_id or "").strip() or None
                ),
                "schedule": _required_text(
                    schedule,
                    "recurring operation schedule",
                    500,
                ),
                "inputs": [
                    str(item).strip()[:1000]
                    for item in inputs
                    if str(item).strip()
                ],
                "expected_output": _required_text(
                    expected_output,
                    "recurring operation output",
                    4000,
                ),
                "quality_gate": _required_text(
                    quality_gate,
                    "recurring operation quality gate",
                    4000,
                ),
                "escalation_minutes": max(
                    1,
                    min(int(escalation_minutes or 60), 525600),
                ),
                "status": "proposed",
                "status_history": [
                    {
                        "status": "proposed",
                        "reason": "Created for operator review.",
                        "created_at": now,
                    }
                ],
                "run_history": [],
                "created_at": now,
                "updated_at": now,
            }
            company.setdefault("recurring_operations", []).append(
                operation
            )
            self._audit(
                company,
                event_type="recurring_operation_proposed",
                target_kind="recurring_operation",
                target_id=operation_id,
                metadata={
                    "runbook_id": str(runbook_id),
                    "automation_id": operation["automation_id"],
                },
            )
            return operation

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result

    def update_recurring_operation_status(
        self,
        *,
        company_id: str,
        computer_id: str,
        operation_id: str,
        status: str,
        reason: str,
    ) -> Dict[str, Any]:
        clean_status = str(status or "").strip().lower()
        if clean_status not in {"active", "paused", "archived"}:
            raise ValueError("Unknown recurring-operation state.")

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            membership = self._root_membership(company, computer_id)
            operation = next(
                (
                    item
                    for item in list(
                        company.get("recurring_operations") or []
                    )
                    if str(item.get("operation_id") or "")
                    == str(operation_id or "")
                ),
                None,
            )
            if not operation:
                raise KeyError("Unknown recurring operation")
            if clean_status == "active":
                if not str(operation.get("automation_id") or "").strip():
                    raise ValueError(
                        "Link a company-scoped automation before activating this operation."
                    )
                runbook = next(
                    (
                        item
                        for item in list(company.get("runbooks") or [])
                        if str(item.get("runbook_id") or "")
                        == str(operation.get("runbook_id") or "")
                    ),
                    None,
                )
                if not runbook or str(runbook.get("status") or "") != "active":
                    raise ValueError(
                        "Activate the operation's reviewed runbook first."
                    )
            now = _utc_now()
            clean_reason = _required_text(
                reason,
                "recurring operation status reason",
                4000,
            )
            operation["status"] = clean_status
            operation["status_reason"] = clean_reason
            operation["updated_at"] = now
            operation.setdefault("status_history", []).append(
                {
                    "status": clean_status,
                    "reason": clean_reason,
                    "changed_by_identity_id": str(
                        membership.get("manager_identity_id") or ""
                    )
                    or None,
                    "created_at": now,
                }
            )
            self._audit(
                company,
                event_type=f"recurring_operation_{clean_status}",
                target_kind="recurring_operation",
                target_id=str(operation_id),
                metadata={
                    "reason": clean_reason,
                    "automation_id": operation.get("automation_id"),
                },
            )
            return dict(operation)

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result

    def create_handoff(
        self,
        *,
        company_id: str,
        computer_id: str,
        from_identity_id: str,
        to_identity_id: str,
        deliverable: str,
        acceptance_criteria: str,
        objective_id: Optional[str],
        assignment_id: Optional[str],
        evidence: list[Mapping[str, Any]],
        open_questions: list[str],
    ) -> Dict[str, Any]:
        handoff_id = _record_id("hof")
        now = _utc_now()

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            self._root_membership(company, computer_id)
            if not self._employee(company, from_identity_id):
                raise ValueError(
                    "The handoff sender does not belong to this company."
                )
            if not self._employee(company, to_identity_id):
                raise ValueError(
                    "The handoff recipient does not belong to this company."
                )
            if objective_id and not any(
                str(item.get("objective_id") or "")
                == str(objective_id)
                for item in list(company.get("objectives") or [])
            ):
                raise ValueError(
                    "The handoff objective is not in this company."
                )
            if assignment_id and not any(
                str(item.get("assignment_id") or "")
                == str(assignment_id)
                for item in list(company.get("assignments") or [])
            ):
                raise ValueError(
                    "The handoff assignment is not in this company."
                )
            handoff = {
                "handoff_id": handoff_id,
                "from_identity_id": str(from_identity_id),
                "to_identity_id": str(to_identity_id),
                "objective_id": str(objective_id or "") or None,
                "assignment_id": str(assignment_id or "") or None,
                "deliverable": _required_text(
                    deliverable,
                    "handoff deliverable",
                    8000,
                ),
                "acceptance_criteria": _required_text(
                    acceptance_criteria,
                    "handoff acceptance criteria",
                    4000,
                ),
                "evidence": [dict(item) for item in evidence],
                "open_questions": [
                    str(item).strip()[:2000]
                    for item in open_questions
                    if str(item).strip()
                ],
                "status": "pending",
                "created_at": now,
                "updated_at": now,
            }
            company.setdefault("handoffs", []).append(handoff)
            self._audit(
                company,
                event_type="handoff_created",
                target_kind="handoff",
                target_id=handoff_id,
                metadata={
                    "from_identity_id": from_identity_id,
                    "to_identity_id": to_identity_id,
                },
            )
            return handoff

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result

    def apply_emergency_control(
        self,
        *,
        company_id: str,
        computer_id: str,
        scope: str,
        target_id: Optional[str],
        action: str,
        reason: str,
    ) -> Dict[str, Any]:
        clean_scope = str(scope or "").strip().lower()
        clean_target_id = str(target_id or "").strip()
        clean_action = str(action or "").strip().lower()
        clean_reason = _required_text(reason, "reason", 4000)
        if clean_action not in {"pause", "resume"}:
            raise ValueError("Emergency control action must be pause or resume.")
        if clean_scope != "company" and not clean_target_id:
            raise ValueError("A target is required for that emergency scope.")

        collection_by_scope = {
            "assignment": ("assignments", "assignment_id"),
            "employee": ("employees", "identity_id"),
            "department": ("departments", "department_id"),
            "runbook": ("runbooks", "runbook_id"),
            "recurring_operation": (
                "recurring_operations",
                "operation_id",
            ),
        }

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            membership = self._root_membership(company, computer_id)
            now = _utc_now()
            if clean_scope == "company":
                manifest = dict(company.get("manifest") or {})
                previous_state = str(
                    manifest.get("operating_state") or "active"
                )
                manifest["operating_state"] = (
                    "paused" if clean_action == "pause" else "active"
                )
                manifest["operating_state_changed_at"] = now
                manifest["operating_state_reason"] = clean_reason
                manifest["operating_state_changed_by_identity_id"] = str(
                    membership.get("manager_identity_id") or ""
                ) or None
                company["manifest"] = manifest
                target: Dict[str, Any] = manifest
                resolved_target_id = company_id
            else:
                collection_name, identifier = collection_by_scope.get(
                    clean_scope,
                    (None, None),
                )
                if not collection_name or not identifier:
                    raise ValueError("Unknown emergency control scope.")
                target = next(
                    (
                        item
                        for item in list(company.get(collection_name) or [])
                        if str(item.get(identifier) or "") == clean_target_id
                        or (
                            clean_scope == "employee"
                            and str(item.get("employee_id") or "")
                            == clean_target_id
                        )
                    ),
                    None,
                )
                if not target:
                    raise KeyError(
                        f"Unknown {clean_scope.replace('_', ' ')}"
                    )
                resolved_target_id = str(
                    target.get(identifier)
                    or target.get("employee_id")
                    or clean_target_id
                )
                if clean_scope in {"employee", "department"}:
                    previous_state = (
                        "paused"
                        if bool(target.get("assignment_paused"))
                        else "active"
                    )
                    target["assignment_paused"] = clean_action == "pause"
                    target["assignment_pause_reason"] = (
                        clean_reason if clean_action == "pause" else None
                    )
                elif clean_scope == "assignment":
                    current_state = str(
                        target.get("status")
                        or target.get("state")
                        or "queued"
                    )
                    previous_state = current_state
                    if clean_action == "pause":
                        if current_state in {
                            "accepted",
                            "archived",
                            "cancelled",
                            "canceled",
                            "completed",
                            "failed",
                            "rejected",
                            "stopped",
                        }:
                            raise ValueError(
                                "Completed or terminal assignments cannot be paused."
                            )
                        target["pre_pause_status"] = current_state
                        target["status"] = "paused"
                    else:
                        if current_state != "paused":
                            raise ValueError("That assignment is not paused.")
                        target["status"] = str(
                            target.pop("pre_pause_status", None) or "queued"
                        )
                elif clean_scope == "runbook":
                    previous_state = str(target.get("status") or "draft")
                    if previous_state == "archived":
                        raise ValueError(
                            "An archived runbook cannot be resumed with emergency controls."
                        )
                    target["status"] = (
                        "paused" if clean_action == "pause" else "active"
                    )
                else:
                    previous_state = str(target.get("status") or "proposed")
                    if previous_state == "archived":
                        raise ValueError(
                            "An archived recurring operation cannot be resumed."
                        )
                    target["status"] = (
                        "paused" if clean_action == "pause" else "active"
                    )
                target["emergency_control_changed_at"] = now
                target["emergency_control_reason"] = clean_reason

            self._audit(
                company,
                event_type=f"company_emergency_{clean_action}",
                target_kind=clean_scope,
                target_id=resolved_target_id,
                metadata={
                    "previous_state": previous_state,
                    "reason": clean_reason,
                    "manager_identity_id": str(
                        membership.get("manager_identity_id") or ""
                    )
                    or None,
                },
            )
            return {
                "company_id": company_id,
                "scope": clean_scope,
                "target_id": resolved_target_id,
                "action": clean_action,
                "previous_state": previous_state,
                "current_state": (
                    "paused" if clean_action == "pause" else "active"
                ),
                "changed_at": now,
            }

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result

    def review_handoff(
        self,
        *,
        company_id: str,
        computer_id: str,
        handoff_id: str,
        reviewer_identity_id: Optional[str],
        decision: str,
        rationale: str,
        rework_instructions: Optional[str],
    ) -> Dict[str, Any]:
        clean_decision = str(decision or "").strip().lower()
        if clean_decision not in HANDOFF_DECISIONS:
            raise ValueError("Unknown handoff decision.")

        def mutation(company: Dict[str, Any]) -> Dict[str, Any]:
            membership = self._root_membership(company, computer_id)
            handoff = next(
                (
                    item
                    for item in list(company.get("handoffs") or [])
                    if str(item.get("handoff_id") or "")
                    == str(handoff_id or "")
                ),
                None,
            )
            if not handoff:
                raise KeyError("Unknown handoff")
            reviewer_id = str(
                reviewer_identity_id
                or handoff.get("to_identity_id")
                or membership.get("manager_identity_id")
                or ""
            ).strip()
            reviewer = self._employee(company, reviewer_id)
            if not reviewer:
                raise ValueError(
                    "The handoff reviewer does not belong to this company."
                )
            allowed_reviewer_ids = {
                str(handoff.get("to_identity_id") or ""),
                str(membership.get("manager_identity_id") or ""),
            }
            if reviewer_id not in allowed_reviewer_ids:
                raise ValueError(
                    "Only the recipient or owning manager may review this handoff."
                )
            now = _utc_now()
            handoff["status"] = clean_decision
            handoff["reviewer_identity_id"] = reviewer_id
            handoff["review_rationale"] = _required_text(
                rationale,
                "handoff review rationale",
                4000,
            )
            handoff["rework_instructions"] = (
                str(rework_instructions or "").strip() or None
            )
            handoff["reviewed_at"] = now
            handoff["updated_at"] = now
            self._audit(
                company,
                event_type="handoff_reviewed",
                target_kind="handoff",
                target_id=str(handoff_id),
                metadata={
                    "decision": clean_decision,
                    "reviewer_identity_id": reviewer_id,
                },
            )
            return dict(handoff)

        _company, result = self.store.mutate_company(
            company_id=company_id,
            mutation=mutation,
        )
        return result
