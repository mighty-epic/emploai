from __future__ import annotations

import pytest

from app_backend.company_intelligence_service import (
    CompanyIntelligenceService,
)
from app_backend.company_store import CompanyStore


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
    return store, company, CompanyIntelligenceService(store=store)


def test_company_knowledge_requires_explicit_provenance(tmp_path):
    store, company, service = _setup(tmp_path)

    with pytest.raises(ValueError, match="provenance"):
        service.publish_knowledge(
            company_id=company["company_id"],
            computer_id="root-computer",
            title="Customer policy",
            content="Only publish approved customer claims.",
            provenance={},
            sensitivity="company",
            review_due_at=None,
        )

    item = service.publish_knowledge(
        company_id=company["company_id"],
        computer_id="root-computer",
        title="Customer policy",
        content="Only publish approved customer claims.",
        provenance={
            "source": "Operator-approved policy review",
            "evidence_ids": ["decision-1"],
        },
        sensitivity="company",
        review_due_at=None,
    )
    assert item["status"] == "active"
    assert store.get_company(company["company_id"])["knowledge"][0][
        "provenance"
    ]["source"] == "Operator-approved policy review"

    reviewed = service.review_knowledge(
        company_id=company["company_id"],
        computer_id="root-computer",
        knowledge_id=item["knowledge_id"],
        next_review_due_at="2026-12-01",
        review_note="The operator confirmed the source remains current.",
    )
    assert reviewed["review_due_at"] == "2026-12-01"
    assert reviewed["last_reviewed_by_identity_id"] == "manager-root"


def test_metric_definition_and_observation_keep_source_and_confidence(
    tmp_path,
):
    _store, company, service = _setup(tmp_path)
    metric = service.create_metric(
        company_id=company["company_id"],
        computer_id="root-computer",
        name="Paid pilots",
        definition="Number of independently verified paid pilots",
        formula="count(distinct signed paid pilot agreements)",
        unit="pilots",
        source="Approved sales evidence register",
        cadence="weekly",
        owner_identity_id="manager-root",
        guardrails=["Do not count survey intent or unpaid trials"],
    )
    observation = service.record_metric_observation(
        company_id=company["company_id"],
        computer_id="root-computer",
        metric_id=metric["metric_id"],
        value=2,
        period_start="2026-07-01",
        period_end="2026-07-31",
        confidence="high",
        evidence=[{"kind": "agreement", "id": "pilot-1"}],
        note="Both payments were verified.",
    )

    assert observation["value"] == 2
    assert observation["confidence"] == "high"
    assert metric["guardrails"] == [
        "Do not count survey intent or unpaid trials"
    ]


def test_financial_entries_are_explicit_sourced_facts(tmp_path):
    store, company, service = _setup(tmp_path)
    revenue = service.record_financial_entry(
        company_id=company["company_id"],
        computer_id="root-computer",
        entry_type="revenue",
        amount=500,
        currency="usd",
        description="Paid discovery pilot",
        recognized_at="2026-07-20",
        source="Operator-verified bank receipt",
        evidence=[{"kind": "receipt", "id": "receipt-1"}],
    )
    cost = service.record_financial_entry(
        company_id=company["company_id"],
        computer_id="root-computer",
        entry_type="cost",
        amount=125,
        currency="USD",
        description="Model and hosting cost",
        recognized_at="2026-07-20",
        source="Provider invoice",
        evidence=[{"kind": "invoice", "id": "invoice-1"}],
    )

    assert revenue["currency"] == "USD"
    assert cost["entry_type"] == "cost"
    assert len(
        store.get_company(company["company_id"])["financial_entries"]
    ) == 2
