from __future__ import annotations

from mobile_app.backend.fleet_report_validation import normalize_worker_task_report


def test_normalize_worker_task_report_keeps_completed_report_with_evidence():
    report = normalize_worker_task_report(
        status="completed",
        summary="Updated the deployment notes.",
        evidence=[{"kind": "file", "path": "notes.md"}],
        confidence="high",
    )

    assert report.status == "completed"
    assert report.summary == "Updated the deployment notes."
    assert report.evidence == [{"kind": "file", "path": "notes.md"}]
    assert report.blockers == []
    assert report.confidence == "high"
    assert report.raw["runtime_repaired_fields"]["completion_missing_evidence"] is False
    assert report.raw["runtime_repaired_fields"]["evidence_count"] == 1


def test_normalize_worker_task_report_repairs_completed_report_without_evidence():
    report = normalize_worker_task_report(
        status="completed",
        summary="Looks done.",
        evidence=[],
        artifacts=[],
        confidence="high",
    )

    assert report.status == "needs_review"
    assert report.confidence == "medium"
    assert report.completion_missing_evidence is True
    assert report.blockers == [
        {
            "kind": "report_validation",
            "message": "Completed worker reports require at least one structured evidence or artifact entry.",
        }
    ]
    assert report.next_suggested_action == "Manager review or direction is required before the worker continues."
    assert report.raw["runtime_repaired_fields"]["completion_missing_evidence"] is True
    assert report.raw["runtime_repaired_fields"]["blocker_count"] == 1


def test_normalize_worker_task_report_defaults_invalid_fields_without_overwriting_raw():
    report = normalize_worker_task_report(
        status="surprisingly-done",
        summary="",
        artifacts=[{"kind": "screenshot", "path": "proof.png"}],
        confidence="certain",
        raw={"runtime_repaired_fields": {"preserve": True}, "source": "worker"},
    )

    assert report.status == "completed"
    assert report.summary == "No summary provided."
    assert report.confidence == "medium"
    assert report.artifacts == [{"kind": "screenshot", "path": "proof.png"}]
    assert report.raw["runtime_repaired_fields"] == {"preserve": True}
    assert report.raw["source"] == "worker"
