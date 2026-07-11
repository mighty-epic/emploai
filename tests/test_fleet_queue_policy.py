from __future__ import annotations

import itertools

import pytest

from app_backend.fleet_queue_policy import (
    QUEUE_POLICY_REVIEW_REQUIRED,
    normalize_queue_policy,
    report_allows_auto_continue,
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
