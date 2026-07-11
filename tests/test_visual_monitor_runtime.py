from PIL import Image

import asyncio

import pytest

import shared.visual_monitor_runtime as visual_monitor_runtime
from shared.visual_monitor_runtime import (
    VisualMonitorManager,
    handle_visual_monitor_event,
    normalize_visual_monitor_threshold,
    visual_monitor_changed_fraction,
)


def test_visual_monitor_threshold_presets_are_fixed() -> None:
    assert normalize_visual_monitor_threshold("10%") == ("10%", 0.10)
    assert normalize_visual_monitor_threshold("30%") == ("30%", 0.30)
    assert normalize_visual_monitor_threshold("50%") == ("50%", 0.50)
    assert normalize_visual_monitor_threshold("70%") == ("70%", 0.70)

    with pytest.raises(ValueError):
        normalize_visual_monitor_threshold("25%")


def test_visual_monitor_pixel_diff_reports_changed_area() -> None:
    before = Image.new("RGB", (10, 10), "black")
    after = Image.new("RGB", (10, 10), "black")
    for x in range(5):
        for y in range(5):
            after.putpixel((x, y), (255, 255, 255))

    assert visual_monitor_changed_fraction(before, after) == pytest.approx(0.25)


def test_visual_monitor_manager_stop_by_session_cancels_matching_monitor() -> None:
    manager = VisualMonitorManager()
    canceled = []

    class FakeMonitor:
        monitor_id = "vmon_test"
        context = {"session_id": "session_a"}

        def cancel(self) -> None:
            canceled.append(self.monitor_id)

        def _emit(self, _payload) -> None:
            pass

    manager._monitors[FakeMonitor.monitor_id] = FakeMonitor()  # type: ignore[attr-defined]

    result = manager.stop_monitor(session_id="session_a", reason="unit test")

    assert result["stopped"] == ["vmon_test"]
    assert result["stopped_count"] == 1
    assert canceled == ["vmon_test"]


def test_visual_monitor_manager_replaces_any_existing_monitor(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = VisualMonitorManager()
    canceled = []
    emitted = []

    class FakeMonitor:
        def __init__(self, monitor_id: str, session_id: str) -> None:
            self.monitor_id = monitor_id
            self.context = {"session_id": session_id}

        def cancel(self) -> None:
            canceled.append(self.monitor_id)

        def _emit(self, payload) -> None:
            emitted.append((self.monitor_id, payload))

    monkeypatch.setattr(visual_monitor_runtime.VisualMonitor, "start", lambda *_args, **_kwargs: None)

    manager._monitors["vmon_a"] = FakeMonitor("vmon_a", "session_a")  # type: ignore[assignment]
    manager._monitors["vmon_b"] = FakeMonitor("vmon_b", "session_b")  # type: ignore[assignment]

    result = manager.start_monitor(
        threshold_preset="30%",
        reason="waiting for app launch",
        context={"session_id": "session_c"},
    )

    assert result["replaced_count"] == 2
    assert set(result["replaced"]) == {"vmon_a", "vmon_b"}
    assert set(canceled) == {"vmon_a", "vmon_b"}
    assert all(payload["status"] == "monitor_stopped" for _monitor_id, payload in emitted)


def test_visual_change_while_agent_busy_queues_runtime_context() -> None:
    class BusySession:
        is_processing = True

        def __init__(self) -> None:
            self.queued = []

        def queue_interrupt(self, message: str, *, deferred: bool = False) -> None:
            self.queued.append((message, deferred))

    session = BusySession()
    result = asyncio.run(
        handle_visual_monitor_event(
            session,
            {
                "status": "visual_change",
                "monitor_id": "vmon_test",
                "reason": "waiting for app launch",
                "changed_fraction": 0.5,
            },
        )
    )

    assert result["queued"] is True
    assert result["reason"] == "queued_for_active_run"
    assert session.queued
    message, deferred = session.queued[0]
    assert deferred is True
    assert message.startswith("[RUNTIME SYSTEM CONTEXT]")
    assert "describe_screen" in message


def test_no_change_while_agent_busy_does_not_wake_planner(monkeypatch: pytest.MonkeyPatch) -> None:
    class BusySession:
        is_processing = True

    async def fail_planner(*_args, **_kwargs):
        raise AssertionError("planner should not run while agent is active")

    monkeypatch.setattr(visual_monitor_runtime, "_hidden_planner_no_change_decision", fail_planner)

    result = asyncio.run(
        handle_visual_monitor_event(
            BusySession(),
            {
                "status": "no_change",
                "monitor_id": "vmon_test",
                "reason": "waiting for page load",
            },
        )
    )

    assert result == {"resumed": False, "reason": "agent_busy_monitor_kept_running"}
