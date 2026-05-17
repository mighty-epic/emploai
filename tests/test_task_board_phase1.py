from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from cli.models.session import Session


_TASK_BOARD_PATH = Path(__file__).resolve().parents[1] / "shared" / "task_board.py"
_TASK_BOARD_SPEC = spec_from_file_location("task_board_module_for_tests", _TASK_BOARD_PATH)
assert _TASK_BOARD_SPEC and _TASK_BOARD_SPEC.loader
_TASK_BOARD_MODULE = module_from_spec(_TASK_BOARD_SPEC)
_TASK_BOARD_SPEC.loader.exec_module(_TASK_BOARD_MODULE)

TASK_BOARD_METHOD_FAILURE_THRESHOLD = _TASK_BOARD_MODULE.TASK_BOARD_METHOD_FAILURE_THRESHOLD
TASK_BOARD_MODEL_TURN_THRESHOLD = _TASK_BOARD_MODULE.TASK_BOARD_MODEL_TURN_THRESHOLD
apply_task_board_failure_report = _TASK_BOARD_MODULE.apply_task_board_failure_report
before_model_turn_messages = _TASK_BOARD_MODULE.before_model_turn_messages
completed_task_boards = _TASK_BOARD_MODULE.completed_task_boards
create_task_board = _TASK_BOARD_MODULE.create_task_board
finalize_task_board_turn = _TASK_BOARD_MODULE.finalize_task_board_turn
get_active_task_board = _TASK_BOARD_MODULE.get_active_task_board
get_display_task_board = _TASK_BOARD_MODULE.get_display_task_board
handle_tool_result = _TASK_BOARD_MODULE.handle_tool_result
note_user_turn = _TASK_BOARD_MODULE.note_user_turn


def _make_session() -> Session:
    session = Session(
        id="sess-task-board",
        name="Task Board",
        created_at="2026-05-04T00:00:00",
        updated_at="2026-05-04T00:00:00",
        workspace="C:\\workspace",
        model="gpt-5.4",
        variant="standard",
        agent_mode="auto",
    )
    session.last_user_message = "Open Spotify and play a song"
    return session


def test_same_tool_twice_does_not_activate_until_third_qualifying_call():
    session = _make_session()

    note_user_turn(session, session.last_user_message)
    first = handle_tool_result(
        session,
        tool_name="launch_app",
        tool_args={"path": "Spotify"},
        tool_result={"error": "Spotify is not installed"},
        channel="telegram",
    )
    second = handle_tool_result(
        session,
        tool_name="launch_app",
        tool_args={"path": "Spotify"},
        tool_result={"error": "Spotify is not installed"},
        channel="telegram",
    )
    third = handle_tool_result(
        session,
        tool_name="launch_app",
        tool_args={"path": "Spotify"},
        tool_result={"error": "Spotify is not installed"},
        channel="telegram",
    )

    board = get_active_task_board(session)

    assert first["created"] is False
    assert second["created"] is False
    assert third["created"] is True
    assert board is not None
    assert board["main_goal"] == "Open Spotify and play a song"
    assert board["qualifying_tool_calls"] == 3


def test_two_distinct_tool_families_activate_immediately():
    session = _make_session()

    note_user_turn(session, session.last_user_message)
    first = handle_tool_result(
        session,
        tool_name="describe_screen",
        tool_args={},
        tool_result="Spotify is not visible.",
        channel="telegram",
    )
    second = handle_tool_result(
        session,
        tool_name="launch_app",
        tool_args={"path": "Spotify"},
        tool_result={"ok": True},
        channel="telegram",
    )

    board = get_active_task_board(session)

    assert first["created"] is False
    assert second["created"] is True
    assert board is not None
    assert board["qualifying_tool_calls"] == 2


def test_chat_only_and_single_tool_turn_never_activate_board():
    session = _make_session()

    assert note_user_turn(session, "Just explain what Spotify is.") is None
    assert get_active_task_board(session) is None

    note_user_turn(session, "Open Chrome.")
    result = handle_tool_result(
        session,
        tool_name="launch_app",
        tool_args={"path": "Chrome"},
        tool_result={"ok": True},
        channel="telegram",
    )

    assert result["created"] is False
    assert get_active_task_board(session) is None


def test_turn_threshold_triggers_runtime_reassessment_before_model_turn():
    session = _make_session()
    board = create_task_board(session, user_message="Open Spotify and play a song")
    board["model_turn_count"] = TASK_BOARD_MODEL_TURN_THRESHOLD - 1
    board["reassessment_count"] = 0

    messages = before_model_turn_messages(session)

    assert board["model_turn_count"] == TASK_BOARD_MODEL_TURN_THRESHOLD
    assert board["reassessment_count"] == 1
    assert board["state"] == "active"
    assert any("ACTIVE MANAGED TASK BOARD" in str(item.get("content", "")) for item in messages)


def test_failure_report_before_threshold_does_not_reassess():
    session = _make_session()
    board = create_task_board(session, user_message="Open Spotify and play a song")
    board["reassessment_count"] = 0

    result = apply_task_board_failure_report(
        session,
        {
            "method_key": "launch_app|path=Spotify",
            "method_label": "launch_app (path=Spotify)",
            "failure_summary": "Spotify is not installed.",
            "attempt_count": TASK_BOARD_METHOD_FAILURE_THRESHOLD - 1,
            "state_changed": False,
            "suspected_blocker_type": "none",
        },
    )

    assert "will not reassess" in result["summary"]
    assert board["reassessment_count"] == 0
    assert board["state"] == "active"


def test_failure_report_at_threshold_reassesses_and_continues():
    session = _make_session()
    board = create_task_board(session, user_message="Open Spotify and play a song")
    board["next_method"] = "Launch Spotify directly."

    result = apply_task_board_failure_report(
        session,
        {
            "method_key": "launch_app|path=Spotify",
            "method_label": "launch_app (path=Spotify)",
            "failure_summary": "Spotify is not installed.",
            "attempt_count": TASK_BOARD_METHOD_FAILURE_THRESHOLD,
            "state_changed": False,
            "suspected_blocker_type": "none",
        },
    )

    assert "Task reassessed" in result["summary"]
    assert board["reassessment_count"] == 1
    assert board["state"] == "active"
    assert board["next_method"] != "Launch Spotify directly."
    assert result["prompt_messages"]


def test_duplicate_failure_report_does_not_loop_reassessment():
    session = _make_session()
    board = create_task_board(session, user_message="Open Spotify and play a song")

    args = {
        "method_key": "launch_app|path=Spotify",
        "method_label": "launch_app (path=Spotify)",
        "failure_summary": "Spotify is not installed.",
        "attempt_count": TASK_BOARD_METHOD_FAILURE_THRESHOLD,
        "state_changed": False,
        "suspected_blocker_type": "none",
    }
    first = apply_task_board_failure_report(session, args)
    second = apply_task_board_failure_report(session, args)

    assert "Task reassessed" in first["summary"]
    assert "Duplicate failure report ignored" in second["summary"]
    assert board["reassessment_count"] == 1


def test_only_allowed_user_blockers_move_board_to_blocked_waiting_user():
    session = _make_session()
    board = create_task_board(session, user_message="Log in to GitHub")

    result = apply_task_board_failure_report(
        session,
        {
            "method_key": "browser_type|selector=#password",
            "method_label": "browser_type (#password)",
            "failure_summary": "The account password is required.",
            "attempt_count": TASK_BOARD_METHOD_FAILURE_THRESHOLD,
            "state_changed": False,
            "suspected_blocker_type": "credentials",
        },
    )

    assert board["state"] == "blocked_waiting_user"
    assert board["status"] == "blocked"
    assert "credentials" in str(board.get("blocked_reason"))
    assert result["prompt_messages"]


def test_verified_completion_immediately_collapses_into_completed_history():
    session = _make_session()
    board = create_task_board(session, user_message="Open Spotify and play a song")
    board["sub_goals"] = [
        {
            "id": "sg_1",
            "title": "Open Spotify and play a song",
            "status": "done",
            "completion_reason": "Spotify is open and playback started",
            "completion_evidence": "Observed playback controls and active audio session",
        },
        {
            "id": "sg_2",
            "title": "Verify the requested result",
            "status": "open",
            "completion_reason": None,
            "completion_evidence": None,
        },
    ]
    _TASK_BOARD_MODULE._set_progress_summary(board)

    note_user_turn(session, "continue")
    handle_tool_result(
        session,
        tool_name="describe_screen",
        tool_args={},
        tool_result="Spotify is open and the play button has changed to pause.",
        channel="telegram",
    )
    finalized = finalize_task_board_turn(
        session,
        "Spotify is open and the song is playing. Verified from the visible playback controls.",
    )

    active = get_active_task_board(session)
    completed = completed_task_boards(session)

    assert finalized is not None
    assert active is None
    assert len(completed) == 1
    assert completed[0]["state"] == "completed_collapsed"
    assert completed[0]["display_mode"] == "completed_collapsed"
    assert completed[0]["collapsed_title"] == f"[x] {completed[0]['main_goal']}"
    assert completed[0]["verification_status"] == "done"


def test_unverified_done_message_does_not_collapse_board():
    session = _make_session()
    board = create_task_board(session, user_message="Open Spotify and play a song")

    note_user_turn(session, "continue")
    finalized = finalize_task_board_turn(session, "Done.")

    assert finalized is not None
    assert finalized["summary"] is None
    assert finalized["completed_boards"] == []
    assert get_active_task_board(session) is board
    assert completed_task_boards(session) == []


def test_completed_history_keeps_last_five_collapsed_boards():
    session = _make_session()

    for index in range(6):
        board = create_task_board(session, user_message=f"Task {index}")
        _TASK_BOARD_MODULE._collapse_completed_board(board, f"Task {index} complete.")
        session.active_task_id = None
        _TASK_BOARD_MODULE._prune_completed_boards(session)

    completed = completed_task_boards(session)

    assert len(completed) == 5
    assert all(item["display_mode"] == "completed_collapsed" for item in completed)
    titles = [item["main_goal"] for item in completed]
    assert "Task 0" not in titles
    assert "Task 5" in titles


def test_session_round_trip_preserves_active_and_completed_task_board_state():
    session = _make_session()
    active_board = create_task_board(session, user_message="Open Spotify and play a song")
    completed_board = create_task_board(session, user_message="Open Chrome")
    _TASK_BOARD_MODULE._collapse_completed_board(completed_board, "Chrome opened.")
    session.active_task_id = active_board["task_id"]
    _TASK_BOARD_MODULE._prune_completed_boards(session)

    restored = Session.from_dict(session.to_dict())

    assert restored.active_task_id == active_board["task_id"]
    assert any(item["task_id"] == active_board["task_id"] for item in restored.task_history)
    assert any(item["task_id"] == completed_board["task_id"] and item["display_mode"] == "completed_collapsed" for item in restored.task_history)
