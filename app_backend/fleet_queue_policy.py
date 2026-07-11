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
