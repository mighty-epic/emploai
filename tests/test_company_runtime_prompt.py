from __future__ import annotations

from types import SimpleNamespace

from app_backend import runtime


def test_company_identity_context_resolves_position_by_occupant_identity(
    monkeypatch,
):
    company = {
        "manifest": {
            "display_name": "Example Company",
            "purpose": "Verify useful work.",
        },
        "employees": [
            {
                "employee_id": "employee-1",
                "identity_id": "worker-1",
                "company_role": "Security Reviewer",
            }
        ],
        "positions": [
            {
                "position_id": "position-1",
                "occupant_identity_id": "worker-1",
                "title": "Identity & Access Engineer",
            }
        ],
        "job_contracts": [
            {
                "job_contract_id": "contract-1",
                "position_id": "position-1",
                "status": "limited_ready",
                "mission": "Review identity boundaries.",
                "responsibilities": ["Verify access rules."],
                "non_responsibilities": ["Do not change production access."],
                "authority": {"external_actions": "draft_only"},
                "limitations": "May review but not apply changes.",
            }
        ],
        "policies": [
            {
                "policy_id": "policy-1",
                "title": "Publication",
                "rule": "Require operator approval before public release.",
                "status": "active",
            }
        ],
        "knowledge": [
            {
                "knowledge_id": "knowledge-1",
                "title": "Support hours",
                "content": "Support operates Monday through Friday.",
                "provenance": {"source": "Operator handbook"},
                "status": "active",
            }
        ],
        "decisions": [
            {
                "decision_id": "decision-1",
                "question": "May this employee publish directly?",
                "decision": "No. Return a draft to the operator.",
                "status": "active",
            }
        ],
    }
    monkeypatch.setattr(
        runtime,
        "_fleet_api_request_for_session",
        lambda *_args, **_kwargs: company,
    )
    session = SimpleNamespace(
        company_id="company-1",
        fleet_identity_id="worker-1",
        session=SimpleNamespace(
            company_id="company-1",
            fleet_identity_id="worker-1",
        ),
    )

    context = runtime._company_identity_context(session)
    prompt = runtime._company_identity_contract(
        context,
        role="worker",
    )["content"]

    assert context["position"]["position_id"] == "position-1"
    assert context["job_contract"]["job_contract_id"] == "contract-1"
    assert "Identity & Access Engineer" in prompt
    assert "Verify access rules." in prompt
    assert "external_actions=draft_only" in prompt
    assert "May review but not apply changes." in prompt
    assert "Never treat a draft as permission to execute." in prompt
    assert "Require operator approval before public release." in prompt
    assert "Support operates Monday through Friday." in prompt
    assert "Operator handbook" in prompt
    assert "No. Return a draft to the operator." in prompt
