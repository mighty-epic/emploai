from __future__ import annotations

import itertools

import pytest

from app_backend.fleet_queue_policy import (
    QUEUE_POLICY_REVIEW_REQUIRED,
    normalize_queue_policy,
    report_allows_auto_continue,
    resolve_manual_queue_review_report_id,
)


def test_missing_or_invalid_queue_policy_defaults_to_review():
    assert normalize_queue_policy(None) == QUEUE_POLICY_REVIEW_REQUIRED
    assert normalize_queue_policy("anything_else") == QUEUE_POLICY_REVIEW_REQUIRED


@pytest.mark.parametrize(
    ("confidence", "evidence_key"),
    [("medium", "evidence"), ("high", "evidence"), ("medium", "artifacts"), ("high", "artifacts")],
)
def test_auto_continue_accepts_only_valid_success_reports(confidence, evidence_key):
    report = {
        "status": "completed",
        "confidence": confidence,
        "summary": "Work completed and checked.",
        "blockers": [],
        "evidence": [],
        "artifacts": [],
    }
    report[evidence_key] = [{"kind": "result"}]
    assert report_allows_auto_continue(report) is True


def test_every_unsafe_terminal_report_pauses():
    unsafe_statuses = ["failed", "blocked", "stopped", "canceled", "needs_review", "running", "queued"]
    confidences = ["low", "medium", "high", None]
    for status, confidence in itertools.product(unsafe_statuses, confidences):
        assert report_allows_auto_continue({
            "status": status,
            "confidence": confidence,
            "summary": "Report",
            "blockers": [],
            "evidence": [{"kind": "result"}],
        }) is False

    for malformed in [
        {"status": "completed", "confidence": "low", "summary": "Report", "evidence": [{}]},
        {"status": "completed", "confidence": "high", "summary": "", "evidence": [{}]},
        {"status": "completed", "confidence": "high", "summary": "Report", "evidence": []},
        {"status": "completed", "confidence": "high", "summary": "Report", "evidence": [{}], "blockers": ["blocked"]},
    ]:
        assert report_allows_auto_continue(malformed) is False


def test_manual_review_can_continue_after_explicitly_acknowledging_failed_report():
    report = {
        "report_id": "rpt_failed",
        "status": "failed",
        "confidence": "low",
        "summary": "Provider unavailable",
        "blockers": ["Provider unavailable"],
        "evidence": [],
    }

    assert resolve_manual_queue_review_report_id(report, "rpt_failed") == "rpt_failed"
    with pytest.raises(ValueError, match="Explicitly review"):
        resolve_manual_queue_review_report_id(report, None)
    with pytest.raises(ValueError, match="does not match"):
        resolve_manual_queue_review_report_id(report, "rpt_other")


def test_safe_success_report_keeps_backward_compatible_implicit_review():
    report = {
        "report_id": "rpt_success",
        "status": "completed",
        "confidence": "high",
        "summary": "Work completed",
        "blockers": [],
        "evidence": [{"kind": "result"}],
    }

    assert resolve_manual_queue_review_report_id(report, None) == "rpt_success"
