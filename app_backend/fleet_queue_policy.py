from __future__ import annotations

from typing import Any, Dict


QUEUE_POLICY_REVIEW_REQUIRED = "review_required"
QUEUE_POLICY_AUTO_CONTINUE_SUCCESS = "auto_continue_success"
VALID_QUEUE_POLICIES = {
    QUEUE_POLICY_REVIEW_REQUIRED,
    QUEUE_POLICY_AUTO_CONTINUE_SUCCESS,
}


def normalize_queue_policy(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in VALID_QUEUE_POLICIES else QUEUE_POLICY_REVIEW_REQUIRED


def report_allows_auto_continue(report: Dict[str, Any]) -> bool:
    status = str(report.get("status") or "").strip().lower()
    confidence = str(report.get("confidence") or "").strip().lower()
    blockers = list(report.get("blockers") or [])
    evidence = list(report.get("evidence") or [])
    artifacts = list(report.get("artifacts") or [])
    return (
        status == "completed"
        and confidence in {"medium", "high"}
        and not blockers
        and bool(evidence or artifacts)
        and bool(str(report.get("summary") or "").strip())
    )


def resolve_manual_queue_review_report_id(
    report: Dict[str, Any],
    requested_report_id: Any,
) -> str:
    expected_report_id = str(report.get("report_id") or "").strip()
    requested = str(requested_report_id or "").strip()
    if not expected_report_id:
        raise ValueError("Latest worker report is missing its report ID")
    if requested and requested != expected_report_id:
        raise ValueError("reviewed_report_id does not match the latest worker report")
    if not requested and not report_allows_auto_continue(report):
        raise ValueError(
            "Explicitly review the latest failed, blocked, low-confidence, or incomplete report before continuing"
        )
    return requested or expected_report_id
