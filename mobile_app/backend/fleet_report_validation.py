from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


ALLOWED_FLEET_REPORT_STATUSES = {"completed", "failed", "stopped", "blocked", "needs_review", "canceled"}
VALID_FLEET_REPORT_CONFIDENCE = {"low", "medium", "high"}
MAX_FLEET_REPORT_SUMMARY_CHARS = 20000
MAX_FLEET_REPORT_NEXT_ACTION_CHARS = 4000
MAX_FLEET_REPORT_LIST_ITEMS = 50


@dataclass(frozen=True)
class NormalizedFleetReport:
    status: str
    summary: str
    evidence: List[Any]
    artifacts: List[Any]
    blockers: List[Any]
    confidence: str
    next_suggested_action: str
    raw: Dict[str, Any]
    completion_missing_evidence: bool


def _bounded_report_list(value: Optional[List[Any]]) -> tuple[List[Any], int]:
    items = list(value or [])
    return items[:MAX_FLEET_REPORT_LIST_ITEMS], len(items)


def normalize_worker_task_report(
    *,
    status: str,
    summary: str,
    evidence: Optional[List[Any]] = None,
    artifacts: Optional[List[Any]] = None,
    blockers: Optional[List[Any]] = None,
    confidence: Optional[str] = None,
    next_suggested_action: Optional[str] = None,
    raw: Optional[Dict[str, Any]] = None,
) -> NormalizedFleetReport:
    raw_summary_text = str(summary or "").strip()
    summary_text = raw_summary_text[:MAX_FLEET_REPORT_SUMMARY_CHARS] or "No summary provided."
    normalized_status = str(status or "completed").strip().lower() or "completed"
    if normalized_status not in ALLOWED_FLEET_REPORT_STATUSES:
        normalized_status = "completed"

    evidence_list, original_evidence_count = _bounded_report_list(evidence)
    artifact_list, original_artifact_count = _bounded_report_list(artifacts)
    blocker_source = list(blockers or [])
    confidence_text = str(confidence or "").strip().lower()
    if confidence_text not in VALID_FLEET_REPORT_CONFIDENCE:
        confidence_text = "medium"

    completion_missing_evidence = normalized_status == "completed" and not evidence_list and not artifact_list
    if completion_missing_evidence:
        normalized_status = "needs_review"
        if confidence_text == "high":
            confidence_text = "medium"
        blocker_source.insert(
            0,
            {
                "kind": "report_validation",
                "message": "Completed worker reports require at least one structured evidence or artifact entry.",
            }
        )
    blocker_list = blocker_source[:MAX_FLEET_REPORT_LIST_ITEMS]

    next_action_text = str(next_suggested_action or "").strip()[:MAX_FLEET_REPORT_NEXT_ACTION_CHARS]
    if not next_action_text:
        if normalized_status in {"blocked", "needs_review"}:
            next_action_text = "Manager review or direction is required before the worker continues."
        elif normalized_status in {"failed", "stopped", "canceled"}:
            next_action_text = "Review the worker transcript and decide whether to retry, redirect, or reassign."
        else:
            next_action_text = "Review the evidence and artifacts if further verification is needed."

    report_raw = dict(raw or {})
    repaired_fields = dict(report_raw.get("runtime_repaired_fields") or {})
    repaired_fields.update(
        {
            "status": normalized_status,
            "summary_present": bool(raw_summary_text),
            "summary_truncated": len(raw_summary_text) > MAX_FLEET_REPORT_SUMMARY_CHARS,
            "next_suggested_action_truncated": len(str(next_suggested_action or "").strip()) > MAX_FLEET_REPORT_NEXT_ACTION_CHARS,
            "evidence_count": len(evidence_list),
            "artifact_count": len(artifact_list),
            "blocker_count": len(blocker_list),
            "original_evidence_count": original_evidence_count,
            "original_artifact_count": original_artifact_count,
            "original_blocker_count": len(blocker_source),
            "evidence_truncated": original_evidence_count > MAX_FLEET_REPORT_LIST_ITEMS,
            "artifacts_truncated": original_artifact_count > MAX_FLEET_REPORT_LIST_ITEMS,
            "blockers_truncated": len(blocker_source) > MAX_FLEET_REPORT_LIST_ITEMS,
            "completion_missing_evidence": bool(completion_missing_evidence),
        }
    )
    report_raw["runtime_repaired_fields"] = repaired_fields

    return NormalizedFleetReport(
        status=normalized_status,
        summary=summary_text,
        evidence=evidence_list,
        artifacts=artifact_list,
        blockers=blocker_list,
        confidence=confidence_text,
        next_suggested_action=next_action_text,
        raw=report_raw,
        completion_missing_evidence=bool(completion_missing_evidence),
    )
