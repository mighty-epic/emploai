from __future__ import annotations

import pytest

from app_backend.company_domain import CompanyDomainService
from app_backend.company_store import CompanySelectionError, CompanyStore
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
        computer_id="computer-a",
        computer_name="Owner PC",
        manager_identity={
            "identity_id": "manager-a",
            "display_name": "CEO",
            "role": "manager",
            "status": "active",
            "metadata": {"protected": True},
        },
        default_worker_identity={
            "identity_id": "worker-a",
            "display_name": "Default Worker",
            "role": "worker",
            "status": "active",
            "metadata": {"protected": False, "is_default": True},
        },
    )
    return store, company, CompanyDomainService(store=store, catalog=JobCatalog())


def test_bundled_agency_agents_catalog_exposes_complete_pinned_list():
    catalog = JobCatalog()
    summary = catalog.summary()

    assert summary["template_count"] == 245
    assert len(summary["divisions"]) == 17
    assert summary["source"]["commit"] == "86a6695d4cee1c9720e2be4fd8ae007f9b6d96ae"
    assert summary["source"]["license"] == "MIT"
    frontend = catalog.list_templates(query="frontend developer")
    assert any(item["template_id"] == "agency:engineering-frontend-developer" for item in frontend)
    assert all(item["review_status"] == "experimental" for item in catalog.list_templates())


def test_position_pins_template_without_granting_tools_or_authority(tmp_path):
    store, company, service = _setup(tmp_path)

    result = service.create_position(
        company_id=company["company_id"],
        computer_id="computer-a",
        title="Frontend Developer",
        template_id="agency:engineering-frontend-developer",
        manager_identity_id="manager-a",
        department_id=None,
        identity_id="worker-a",
        overlay={},
    )

    contract = result["job_contract"]
    assert contract["template_ref"]["source_commit"] == "86a6695d4cee1c9720e2be4fd8ae007f9b6d96ae"
    assert contract["template_ref"]["review_status"] == "experimental"
    assert contract["approved_tool_packs"] == []
    assert contract["authority"]["external_actions"] == "draft_only"
    assert contract["authority"]["spending"] == "not_allowed"
    assert contract["status"] == "setup_incomplete"
    saved = store.get_company(company["company_id"])
    assert saved["positions"][0]["occupant_identity_id"] == "worker-a"
    assert saved["departments"] == []


def test_identity_cannot_silently_occupy_two_positions(tmp_path):
    _store, company, service = _setup(tmp_path)
    service.create_position(
        company_id=company["company_id"],
        computer_id="computer-a",
        title="First role",
        template_id=None,
        manager_identity_id="manager-a",
        department_id=None,
        identity_id="worker-a",
        overlay={},
    )

    with pytest.raises(ValueError, match="controlled job change"):
        service.create_position(
            company_id=company["company_id"],
            computer_id="computer-a",
            title="Second role",
            template_id=None,
            manager_identity_id="manager-a",
            department_id=None,
            identity_id="worker-a",
            overlay={},
        )


def test_controlled_occupant_change_keeps_memory_with_identity_and_resets_readiness(
    tmp_path,
):
    store, company, service = _setup(tmp_path)
    created = service.create_position(
        company_id=company["company_id"],
        computer_id="computer-a",
        title="Support Specialist",
        template_id="agency:support-support-responder",
        manager_identity_id="manager-a",
        department_id=None,
        identity_id="worker-a",
        overlay={},
    )
    replacement = service.change_position_occupant(
        company_id=company["company_id"],
        computer_id="computer-a",
        position_id=created["position"]["position_id"],
        identity_id="worker-b",
        move_from_position_id=None,
        reason="Replace the role after an operator review.",
        identity_record={
            "identity_id": "worker-b",
            "display_name": "Replacement Worker",
            "role": "worker",
            "status": "active",
            "metadata": {},
        },
    )

    saved = store.get_company(company["company_id"])
    old_employee = next(
        item for item in saved["employees"] if item["identity_id"] == "worker-a"
    )
    new_employee = next(
        item for item in saved["employees"] if item["identity_id"] == "worker-b"
    )
    assert replacement["private_memory_transferred"] is False
    assert old_employee["position_id"] is None
    assert old_employee["position_history"][0]["position_id"] == created["position"]["position_id"]
    assert new_employee["position_id"] == created["position"]["position_id"]
    assert new_employee["job_contract_status"] == "setup_incomplete"
    assert saved["job_contracts"][0]["status"] == "setup_incomplete"
    assert saved["company_audit_events"][-1]["metadata"]["private_memory_transferred"] is False


def test_controlled_move_requires_exact_source_position(tmp_path):
    _store, company, service = _setup(tmp_path)
    first = service.create_position(
        company_id=company["company_id"],
        computer_id="computer-a",
        title="First role",
        template_id=None,
        manager_identity_id="manager-a",
        department_id=None,
        identity_id="worker-a",
        overlay={},
    )
    second = service.create_position(
        company_id=company["company_id"],
        computer_id="computer-a",
        title="Second role",
        template_id=None,
        manager_identity_id="manager-a",
        department_id=None,
        identity_id=None,
        overlay={},
    )

    with pytest.raises(ValueError, match="exact position"):
        service.change_position_occupant(
            company_id=company["company_id"],
            computer_id="computer-a",
            position_id=second["position"]["position_id"],
            identity_id="worker-a",
            move_from_position_id=None,
            reason="Move to the second role.",
        )

    moved = service.change_position_occupant(
        company_id=company["company_id"],
        computer_id="computer-a",
        position_id=second["position"]["position_id"],
        identity_id="worker-a",
        move_from_position_id=first["position"]["position_id"],
        reason="Move to the second role.",
    )
    assert moved["moved_from_position_id"] == first["position"]["position_id"]


def test_departments_are_optional_and_positions_can_join_one(tmp_path):
    store, company, service = _setup(tmp_path)

    department = service.create_department(
        company_id=company["company_id"],
        computer_id="computer-a",
        name="Customer Operations",
        mandate="Own customer support quality and response operations.",
        manager_identity_id="manager-a",
    )
    result = service.create_position(
        company_id=company["company_id"],
        computer_id="computer-a",
        title="Support Specialist",
        template_id="agency:support-support-responder",
        manager_identity_id="manager-a",
        department_id=department["department_id"],
        identity_id=None,
        overlay={},
    )

    assert result["position"]["department_id"] == department["department_id"]
    saved = store.get_company(company["company_id"])
    assert saved["departments"] == [department]
    assert saved["departments"][0]["mandate"].startswith("Own customer")

    with pytest.raises(ValueError, match="already uses"):
        service.create_department(
            company_id=company["company_id"],
            computer_id="computer-a",
            name="customer operations",
            mandate="Duplicate.",
            manager_identity_id="manager-a",
        )

    with pytest.raises(ValueError, match="reporting identity is not a manager"):
        service.create_position(
            company_id=company["company_id"],
            computer_id="computer-a",
            title="Invalid reporting line",
            template_id=None,
            manager_identity_id="worker-a",
            department_id=None,
            identity_id=None,
            overlay={},
        )


def test_position_can_onboard_a_verified_local_identity_with_selected_job(tmp_path):
    store, company, service = _setup(tmp_path)

    result = service.create_position(
        company_id=company["company_id"],
        computer_id="computer-a",
        title="Identity & Access Engineer",
        template_id="agency:engineering-identity-access-engineer",
        manager_identity_id="manager-a",
        department_id=None,
        identity_id="worker-security",
        identity_record={
            "identity_id": "worker-security",
            "display_name": "Security Worker",
            "role": "worker",
            "status": "active",
            "protected": False,
            "is_default": False,
        },
        overlay={},
    )

    assert result["position"]["occupant_identity_id"] == "worker-security"
    saved = store.get_company(company["company_id"])
    employee = next(item for item in saved["employees"] if item["identity_id"] == "worker-security")
    assert employee["company_role"] == "Identity & Access Engineer"
    assert employee["home_membership_id"] == saved["memberships"][0]["membership_id"]
    assert employee["job_contract_status"] == "setup_incomplete"
    assert result["job_contract"]["approved_tool_packs"] == []


def test_root_manager_position_reports_to_human_not_itself(tmp_path):
    _store, company, service = _setup(tmp_path)

    result = service.create_position(
        company_id=company["company_id"],
        computer_id="computer-a",
        title="Chief Executive Officer",
        template_id=None,
        manager_identity_id="manager-a",
        department_id=None,
        identity_id="manager-a",
        overlay={},
    )

    assert result["position"]["manager_identity_id"] is None
    assert result["job_contract"]["escalation_route"] == "human_operator"


def test_incomplete_specialist_cannot_receive_company_work(tmp_path):
    store, company, service = _setup(tmp_path)
    service.create_position(
        company_id=company["company_id"],
        computer_id="computer-a",
        title="Identity & Access Engineer",
        template_id="agency:engineering-identity-access-engineer",
        manager_identity_id="manager-a",
        department_id=None,
        identity_id="worker-security",
        identity_record={
            "identity_id": "worker-security",
            "display_name": "Security Worker",
            "role": "worker",
            "status": "active",
            "protected": False,
            "is_default": False,
        },
        overlay={},
    )
    objective = service.create_objective(
        company_id=company["company_id"],
        computer_id="computer-a",
        outcome="Review access controls",
        success_criteria="The manager accepts a sourced control review",
        owner_identity_id="manager-a",
        priority="normal",
        due_at=None,
        low_risk_auto_accept=False,
        optional_proposals=[],
    )

    with pytest.raises(ValueError, match="readiness review"):
        service.link_objective_assignment(
            company_id=company["company_id"],
            computer_id="computer-a",
            objective_id=objective["objective_id"],
            assignee_identity_id="worker-security",
            prompt="Review the access controls.",
            task_id="task-security",
            delegation_id=None,
            route={},
            state="queued",
        )


def test_readiness_review_activates_specialist_and_material_edit_resets_it(
    tmp_path,
):
    store, company, service = _setup(tmp_path)
    created = service.create_position(
        company_id=company["company_id"],
        computer_id="computer-a",
        title="Identity & Access Engineer",
        template_id="agency:engineering-identity-access-engineer",
        manager_identity_id="manager-a",
        department_id=None,
        identity_id="worker-security",
        identity_record={
            "identity_id": "worker-security",
            "display_name": "Security Worker",
            "role": "worker",
            "status": "active",
            "protected": False,
            "is_default": False,
        },
        overlay={},
    )
    contract_id = created["job_contract"]["job_contract_id"]
    review = service.review_job_readiness(
        company_id=company["company_id"],
        computer_id="computer-a",
        job_contract_id=contract_id,
        reviewer_identity_id="manager-a",
        checks={
            "mission": True,
            "objective_context": True,
            "approved_input": True,
            "representative_deliverable": True,
            "approval_boundary": True,
            "handoff": True,
            "uncertainty": True,
        },
        evidence=[
            {
                "kind": "readiness_test",
                "summary": "Produced and reviewed a representative access report.",
            }
        ],
        missing_requirements=[],
        limited_mode=False,
        limitations=None,
    )
    assert review["status"] == "ready"
    saved = store.get_company(company["company_id"])
    employee = next(
        item
        for item in saved["employees"]
        if item["identity_id"] == "worker-security"
    )
    assert employee["job_contract_status"] == "ready"

    updated = service.update_job_contract(
        company_id=company["company_id"],
        computer_id="computer-a",
        job_contract_id=contract_id,
        updates={"authority": {"external_actions": "draft_only"}},
    )
    assert updated["status"] == "setup_incomplete"
    reset_employee = next(
        item
        for item in store.get_company(company["company_id"])["employees"]
        if item["identity_id"] == "worker-security"
    )
    assert reset_employee["job_contract_status"] == "setup_incomplete"


def test_limited_readiness_requires_evidence_and_explicit_limits(tmp_path):
    _store_instance, company, service = _setup(tmp_path)
    created = service.create_position(
        company_id=company["company_id"],
        computer_id="computer-a",
        title="Support Specialist",
        template_id="agency:support-support-responder",
        manager_identity_id="manager-a",
        department_id=None,
        identity_id="worker-support",
        identity_record={
            "identity_id": "worker-support",
            "display_name": "Support Worker",
            "role": "worker",
            "status": "active",
        },
        overlay={},
    )
    review = service.review_job_readiness(
        company_id=company["company_id"],
        computer_id="computer-a",
        job_contract_id=created["job_contract"]["job_contract_id"],
        reviewer_identity_id="manager-a",
        checks={key: True for key in (
            "mission",
            "objective_context",
            "approved_input",
            "representative_deliverable",
            "approval_boundary",
            "handoff",
            "uncertainty",
        )},
        evidence=[{"kind": "manual_test", "summary": "Draft reply reviewed."}],
        missing_requirements=[
            {"kind": "credential", "label": "Support inbox"}
        ],
        limited_mode=True,
        limitations=(
            "May draft replies from supplied text but cannot read or send email."
        ),
    )
    assert review["status"] == "limited_ready"


def test_objective_preserves_user_directive_and_keeps_optional_parts_proposed(tmp_path):
    store, company, service = _setup(tmp_path)

    objective = service.create_objective(
        company_id=company["company_id"],
        computer_id="computer-a",
        outcome="Ship the accountless desktop beta",
        success_criteria="The human operator accepts the verified desktop build",
        owner_identity_id="manager-a",
        priority="high",
        due_at=None,
        low_risk_auto_accept=False,
        optional_proposals=[
            {"title": "Write a launch post", "reason": "Helpful but not requested"},
        ],
    )

    assert objective["user_directive"] == {
        "outcome": "Ship the accountless desktop beta",
        "success_criteria": "The human operator accepts the verified desktop build",
    }
    assert objective["optional_proposals"][0]["status"] == "proposed"
    assert objective["low_risk_auto_accept"] is False
    assert store.get_company(company["company_id"])["objectives"][0]["status"] == "planned"


def test_report_completion_requires_explicit_manager_review(tmp_path):
    store, company, service = _setup(tmp_path)
    objective = service.create_objective(
        company_id=company["company_id"],
        computer_id="computer-a",
        outcome="Verify the release",
        success_criteria="All required checks pass",
        owner_identity_id="manager-a",
        priority="normal",
        due_at=None,
        low_risk_auto_accept=False,
        optional_proposals=[],
    )
    assignment = service.link_objective_assignment(
        company_id=company["company_id"],
        computer_id="computer-a",
        objective_id=objective["objective_id"],
        assignee_identity_id="worker-a",
        prompt="Run the release checks and attach the results.",
        task_id="task-1",
        delegation_id=None,
        route={"kind": "local_worker"},
        state="running",
    )
    report = service.record_assignment_report(
        company_id=company["company_id"],
        computer_id="computer-a",
        objective_id=objective["objective_id"],
        task_id="task-1",
        report={
            "report_id": "report-1",
            "task_id": "task-1",
            "worker_id": "worker-a",
            "status": "completed",
            "summary": "Release checks finished.",
            "evidence": ["backend passed"],
            "artifacts": [],
            "blockers": [],
            "confidence": "high",
        },
    )

    review = service.review_report(
        company_id=company["company_id"],
        computer_id="computer-a",
        report_id="report-1",
        objective_id=objective["objective_id"],
        reviewer_identity_id="manager-a",
        decision="rework_requested",
        rationale="The evidence does not include the renderer build.",
        rework_instructions="Run and attach the renderer export result.",
    )

    assert review["decision"] == "rework_requested"
    assert review["assignment_id"] == assignment["assignment_id"]
    assert report["review_status"] == "awaiting_review"
    saved = store.get_company(company["company_id"])
    assert saved["objectives"][0]["status"] == "active"
    assert saved["assignments"][0]["status"] == "rework_requested"
    assert saved["reports"][0]["review_status"] == "rework_requested"
    assert saved["objective_reviews"][0]["report_id"] == "report-1"


def test_assignment_links_employee_task_and_objective(tmp_path):
    store, company, service = _setup(tmp_path)
    objective = service.create_objective(
        company_id=company["company_id"],
        computer_id="computer-a",
        outcome="Ship the verified package",
        success_criteria="The package hash and smoke test are recorded",
        owner_identity_id="manager-a",
        priority="high",
        due_at=None,
        low_risk_auto_accept=False,
        optional_proposals=[],
    )

    assignment = service.link_objective_assignment(
        company_id=company["company_id"],
        computer_id="computer-a",
        objective_id=objective["objective_id"],
        assignee_identity_id="worker-a",
        prompt="Build and smoke test the package.",
        task_id="task-package",
        delegation_id=None,
        route={"kind": "local_worker", "worker_id": "worker-a"},
        state="queued",
    )

    saved = store.get_company(company["company_id"])
    assert assignment["assignee_identity_id"] == "worker-a"
    assert saved["assignments"][0]["task_id"] == "task-package"
    assert saved["objectives"][0]["linked_task_ids"] == ["task-package"]
    assert saved["objectives"][0]["status"] == "active"

    with pytest.raises(ValueError, match="does not belong"):
        service.link_objective_assignment(
            company_id=company["company_id"],
            computer_id="computer-a",
            objective_id=objective["objective_id"],
            assignee_identity_id="outside-worker",
            prompt="Do unrelated work.",
            task_id="task-outside",
            delegation_id=None,
            route={},
            state="queued",
        )


def test_assignment_report_replay_is_idempotent(tmp_path):
    store, company, service = _setup(tmp_path)
    objective = service.create_objective(
        company_id=company["company_id"],
        computer_id="computer-a",
        outcome="Collect one result",
        success_criteria="The result is reviewed",
        owner_identity_id="manager-a",
        priority="normal",
        due_at=None,
        low_risk_auto_accept=False,
        optional_proposals=[],
    )
    service.link_objective_assignment(
        company_id=company["company_id"],
        computer_id="computer-a",
        objective_id=objective["objective_id"],
        assignee_identity_id="worker-a",
        prompt="Collect it.",
        task_id="task-replay",
        delegation_id=None,
        route={},
        state="running",
    )
    payload = {
        "report_id": "report-replay",
        "task_id": "task-replay",
        "status": "completed",
        "summary": "Collected.",
    }

    service.record_assignment_report(
        company_id=company["company_id"],
        computer_id="computer-a",
        objective_id=objective["objective_id"],
        task_id="task-replay",
        report=payload,
    )
    service.record_assignment_report(
        company_id=company["company_id"],
        computer_id="computer-a",
        objective_id=objective["objective_id"],
        task_id="task-replay",
        report=payload,
    )

    saved = store.get_company(company["company_id"])
    assert len(saved["reports"]) == 1
    assert saved["assignments"][0]["report_id"] == "report-replay"
    assert saved["objectives"][0]["status"] == "submitted"


def test_worker_membership_cannot_restructure_company(tmp_path):
    store, company, service = _setup(tmp_path)

    def demote_local_membership(payload):
        payload["memberships"][0]["membership_role"] = "worker_node"

    store.mutate_company(company_id=company["company_id"], mutation=demote_local_membership)

    with pytest.raises(CompanySelectionError):
        service.create_policy(
            company_id=company["company_id"],
            computer_id="computer-a",
            title="No public sends",
            rule="Require human approval before public communication.",
            scope="external_actions",
            enforcement="manager",
        )


def test_operator_decision_is_durable_and_audited(tmp_path):
    store, company, service = _setup(tmp_path)

    decision = service.record_decision(
        company_id=company["company_id"],
        computer_id="computer-a",
        question="May the company publish directly?",
        decision="No. Public messages remain drafts until operator approval.",
        rationale="The company is still validating its external communication process.",
        scope="external_actions",
        related_record_ids=[],
    )

    assert decision["decided_by"] == "human_operator"
    saved = store.get_company(company["company_id"])
    assert saved["decisions"][0]["decision_id"] == decision["decision_id"]
    assert any(
        event["event_type"] == "decision_recorded"
        and event["target_id"] == decision["decision_id"]
        for event in saved["company_audit_events"]
    )
