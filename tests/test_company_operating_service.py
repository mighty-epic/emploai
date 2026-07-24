from __future__ import annotations

import pytest

from app_backend.company_domain import CompanyDomainService
from app_backend.company_operating_service import CompanyOperatingService
from app_backend.company_store import CompanyStore
from app_backend.job_catalog import JobCatalog


def _protect(payload, *, purpose):
    return {"purpose": purpose, "payload": dict(payload)}


def _unprotect(envelope, *, purpose):
    assert envelope["purpose"] == purpose
    return dict(envelope["payload"])


def _setup(tmp_path):
    store = CompanyStore(
        root_path=tmp_path,
        protect_payload=_protect,
        unprotect_payload=_unprotect,
    )
    company = store.ensure_default_company(
        computer_id="root-computer",
        computer_name="Root PC",
        manager_identity={
            "identity_id": "manager-root",
            "display_name": "CEO",
            "role": "manager",
            "status": "active",
            "protected": True,
        },
        default_worker_identity={
            "identity_id": "worker-default",
            "display_name": "Default Worker",
            "role": "worker",
            "status": "active",
            "protected": True,
            "is_default": True,
        },
    )
    domain = CompanyDomainService(
        store=store,
        catalog=JobCatalog(),
    )
    operating = CompanyOperatingService(store=store)
    return store, company, domain, operating


def test_initiative_links_only_objectives_from_same_company(tmp_path):
    store, company, domain, operating = _setup(tmp_path)
    objective = domain.create_objective(
        company_id=company["company_id"],
        computer_id="root-computer",
        outcome="Validate the offer",
        success_criteria="Two paid pilots are independently verified",
        owner_identity_id="manager-root",
        priority="high",
        due_at=None,
        low_risk_auto_accept=False,
        optional_proposals=[],
    )
    initiative = operating.create_initiative(
        company_id=company["company_id"],
        computer_id="root-computer",
        title="Offer validation",
        outcome="Reach a reliable buy or stop decision",
        owner_identity_id="manager-root",
        objective_ids=[objective["objective_id"]],
        plan=["Interview target buyers", "Request economic commitment"],
        risks=["False-positive survey interest"],
        due_at=None,
    )

    assert initiative["status"] == "proposed"
    assert initiative["objective_ids"] == [objective["objective_id"]]
    saved = store.get_company(company["company_id"])
    assert saved["initiatives"][0]["initiative_id"] == initiative["initiative_id"]

    with pytest.raises(ValueError, match="not in this company"):
        operating.create_initiative(
            company_id=company["company_id"],
            computer_id="root-computer",
            title="Invalid",
            outcome="Should not persist",
            owner_identity_id="manager-root",
            objective_ids=["obj_other_company"],
            plan=[],
            risks=[],
            due_at=None,
        )


def test_root_emergency_pause_blocks_new_company_assignment_and_resumes(
    tmp_path,
):
    store, company, domain, operating = _setup(tmp_path)
    objective = domain.create_objective(
        company_id=company["company_id"],
        computer_id="root-computer",
        outcome="Prepare a verified brief",
        success_criteria="The manager accepts a sourced brief",
        owner_identity_id="manager-root",
        priority="normal",
        due_at=None,
        low_risk_auto_accept=False,
        optional_proposals=[],
    )
    paused = operating.apply_emergency_control(
        company_id=company["company_id"],
        computer_id="root-computer",
        scope="company",
        target_id=None,
        action="pause",
        reason="Operator incident review.",
    )
    assert paused["current_state"] == "paused"

    with pytest.raises(ValueError, match="paused by the root operator"):
        domain.link_objective_assignment(
            company_id=company["company_id"],
            computer_id="root-computer",
            objective_id=objective["objective_id"],
            assignee_identity_id="worker-default",
            prompt="Prepare the brief.",
            task_id="task-paused",
            delegation_id=None,
            route={},
            state="queued",
        )

    resumed = operating.apply_emergency_control(
        company_id=company["company_id"],
        computer_id="root-computer",
        scope="company",
        target_id=None,
        action="resume",
        reason="Operator completed the incident review.",
    )
    assert resumed["current_state"] == "active"
    assignment = domain.link_objective_assignment(
        company_id=company["company_id"],
        computer_id="root-computer",
        objective_id=objective["objective_id"],
        assignee_identity_id="worker-default",
        prompt="Prepare the brief.",
        task_id="task-resumed",
        delegation_id=None,
        route={},
        state="queued",
    )
    assert assignment["task_id"] == "task-resumed"
    saved = store.get_company(company["company_id"])
    assert saved["company_audit_events"][-2]["event_type"] == "company_emergency_resume"


def test_runbook_starts_as_draft_and_preserves_gates(tmp_path):
    _store, company, _domain, operating = _setup(tmp_path)
    runbook = operating.create_runbook(
        company_id=company["company_id"],
        computer_id="root-computer",
        title="Customer incident",
        trigger="A customer reports a material service failure",
        steps=[
            {"order": 1, "action": "Confirm impact"},
            {"order": 2, "action": "Prepare an operator-approved response"},
        ],
        required_roles=["Support", "Engineering"],
        approval_gates=[
            {"before_step": 2, "authority": "human_operator"}
        ],
        evidence_requirements=["Incident timeline"],
    )

    assert runbook["status"] == "draft"
    assert runbook["approval_gates"][0]["authority"] == "human_operator"

    active = operating.update_runbook_status(
        company_id=company["company_id"],
        computer_id="root-computer",
        runbook_id=runbook["runbook_id"],
        status="active",
        review_note="The operator reviewed the trigger, steps, and gates.",
    )
    assert active["status"] == "active"
    assert active["reviewed_by_identity_id"] == "manager-root"
    assert active["review_note"].startswith("The operator reviewed")


def test_recurring_operation_requires_deliberate_activation(tmp_path):
    store, company, _domain, operating = _setup(tmp_path)
    runbook = operating.create_runbook(
        company_id=company["company_id"],
        computer_id="root-computer",
        title="Weekly customer insight",
        trigger="Friday at 15:00",
        steps=[{"order": 1, "action": "Synthesize verified feedback"}],
        required_roles=["Customer research"],
        approval_gates=[],
        evidence_requirements=["Source links"],
    )
    operation = operating.create_recurring_operation(
        company_id=company["company_id"],
        computer_id="root-computer",
        title="Weekly customer insight",
        trigger="The weekly automation becomes due",
        owner_identity_id="manager-root",
        runbook_id=runbook["runbook_id"],
        automation_id=None,
        schedule="Fridays at 15:00",
        inputs=["Approved customer feedback"],
        expected_output="A sourced insight report",
        quality_gate="Every claim links to customer evidence",
        escalation_minutes=120,
    )

    assert operation["status"] == "proposed"
    with pytest.raises(ValueError, match="Link a company-scoped automation"):
        operating.update_recurring_operation_status(
            company_id=company["company_id"],
            computer_id="root-computer",
            operation_id=operation["operation_id"],
            status="active",
            reason="Activate it.",
        )

    def link_automation(record):
        record["recurring_operations"][0]["automation_id"] = "automation-1"

    store.mutate_company(
        company_id=company["company_id"],
        mutation=link_automation,
    )
    with pytest.raises(ValueError, match="Activate the operation's reviewed runbook"):
        operating.update_recurring_operation_status(
            company_id=company["company_id"],
            computer_id="root-computer",
            operation_id=operation["operation_id"],
            status="active",
            reason="Activate it.",
        )

    operating.update_runbook_status(
        company_id=company["company_id"],
        computer_id="root-computer",
        runbook_id=runbook["runbook_id"],
        status="active",
        review_note="The operator reviewed the runbook.",
    )
    active = operating.update_recurring_operation_status(
        company_id=company["company_id"],
        computer_id="root-computer",
        operation_id=operation["operation_id"],
        status="active",
        reason="The root operator approved this recurring operation.",
    )
    assert active["status"] == "active"
    assert active["status_history"][-1]["changed_by_identity_id"] == "manager-root"


def test_handoff_requires_recipient_or_manager_acceptance(tmp_path):
    _store, company, _domain, operating = _setup(tmp_path)
    handoff = operating.create_handoff(
        company_id=company["company_id"],
        computer_id="root-computer",
        from_identity_id="worker-default",
        to_identity_id="manager-root",
        deliverable="A verified incident timeline",
        acceptance_criteria="Every material event has a timestamp and source",
        objective_id=None,
        assignment_id=None,
        evidence=[{"kind": "artifact", "id": "timeline-1"}],
        open_questions=["Was customer notification required?"],
    )
    reviewed = operating.review_handoff(
        company_id=company["company_id"],
        computer_id="root-computer",
        handoff_id=handoff["handoff_id"],
        reviewer_identity_id="manager-root",
        decision="accepted",
        rationale="The timeline meets the stated criteria.",
        rework_instructions=None,
    )

    assert reviewed["status"] == "accepted"
    assert reviewed["reviewer_identity_id"] == "manager-root"
