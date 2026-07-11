import asyncio

import shared.proactive_runtime as proactive_runtime
from shared.proactive_runtime import handle_background_process_event
from shared.runtime_attention import queue_runtime_system_context


class _SessionManager:
    def get_current_session_id(self) -> str:
        return "session_a"


class _BusySession:
    is_processing = True
    user_id = 1
    session_manager = _SessionManager()
    chat_history = [{"role": "user", "content": "Run the long test suite."}]

    def __init__(self) -> None:
        self.deferred_interrupt_queue = []
        self.queued = []

    def queue_interrupt(self, message: str, *, deferred: bool = False) -> None:
        self.queued.append((message, deferred))
        if deferred:
            self.deferred_interrupt_queue.append(message)


def _patch_event_storage(monkeypatch):
    monkeypatch.setattr(proactive_runtime, "append_event", lambda **_kwargs: {"id": "feed_1"})
    monkeypatch.setattr(
        proactive_runtime,
        "_append_process_timeline_event",
        lambda *_args, **_kwargs: {"id": "timeline_1"},
    )


def test_process_no_progress_can_queue_runtime_context_for_active_agent(monkeypatch) -> None:
    _patch_event_storage(monkeypatch)

    async def wake_agent(*_args, **_kwargs):
        return {"action": "wake_agent", "reason": "output suggests the command is stuck"}

    monkeypatch.setattr(proactive_runtime, "_hidden_process_no_progress_decision", wake_agent)

    session = _BusySession()
    result = asyncio.run(
        handle_background_process_event(
            session,
            {
                "status": "process_no_progress",
                "command_id": "cmd_test",
                "command": "npm test",
                "resume_policy": "on_exit",
                "auto_resume": True,
                "no_progress_seconds": 60,
                "deadline_seconds": 60,
                "output": "Still waiting...",
                "original_user_task": "Run tests.",
            },
        )
    )

    assert result["reason"] == "queued_for_active_run"
    assert result["queued"] is True
    assert session.deferred_interrupt_queue
    message = session.deferred_interrupt_queue[0]
    assert message.startswith("[RUNTIME SYSTEM CONTEXT]")
    assert "process_no_progress" in message
    assert "output suggests the command is stuck" in message


def test_process_no_progress_can_keep_waiting(monkeypatch) -> None:
    _patch_event_storage(monkeypatch)

    async def keep_waiting(*_args, **_kwargs):
        return {"action": "keep_waiting", "reason": "normal progress"}

    monkeypatch.setattr(proactive_runtime, "_hidden_process_no_progress_decision", keep_waiting)

    result = asyncio.run(
        handle_background_process_event(
            _BusySession(),
            {
                "status": "process_no_progress",
                "command_id": "cmd_test",
                "command": "npm install",
                "resume_policy": "on_exit",
                "auto_resume": True,
                "no_progress_seconds": 60,
                "deadline_seconds": 60,
                "output": "Downloading packages...",
            },
        )
    )

    assert result["resumed"] is False
    assert result["reason"] == "planner_kept_waiting"
    assert result["planner_decision"]["reason"] == "normal progress"


def test_runtime_context_merges_matching_deferred_events() -> None:
    session = _BusySession()

    assert queue_runtime_system_context(
        session,
        headline="A background command event fired while this agent turn was still running.",
        prompt="first event",
        merge_marker="background command event",
        additional_label="ADDITIONAL BACKGROUND COMMAND EVENT",
    )
    assert queue_runtime_system_context(
        session,
        headline="A background command event fired while this agent turn was still running.",
        prompt="second event",
        merge_marker="background command event",
        additional_label="ADDITIONAL BACKGROUND COMMAND EVENT",
    )

    assert len(session.deferred_interrupt_queue) == 1
    merged = session.deferred_interrupt_queue[0]
    assert "first event" in merged
    assert "second event" in merged
    assert "ADDITIONAL BACKGROUND COMMAND EVENT" in merged
